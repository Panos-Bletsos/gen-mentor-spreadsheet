from __future__ import annotations

import ast
import json
import logging
from typing import Any, List, Mapping, Optional, Sequence

from pydantic import BaseModel, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.ai_chatbot_tutor.tools import BrainstormingDone, SheetUpdate
from utils.tracing import TraceSession

logger = logging.getLogger(__name__)
from modules.ai_chatbot_tutor.prompts.ai_chatbot_tutor import (
	ai_tutor_chatbot_system_prompt,
	ai_tutor_chatbot_task_prompt,
	ai_tutor_brainstorming_task_prompt,
	ai_tutor_exercise_task_prompt,
)


def _stringify_history(messages: Any) -> str:
	if messages is None or len(messages) == 0:
		return ""
	if isinstance(messages, str):
		try:
			messages = ast.literal_eval(messages)
		except Exception:
			return messages
	lines: List[str] = []
	for m in list(messages or []):
		if isinstance(m, Mapping):
			role = str(m.get("role", "user"))
			content = str(m.get("content", ""))
		else:
			role = "user"
			content = str(m)
		lines.append(f"{role}: {content}")
	return "\n".join(lines)


def _last_user_query(messages: Any) -> str:
	if messages is None:
		return ""
	if isinstance(messages, str):
		try:
			messages = ast.literal_eval(messages)
		except Exception:
			return messages
	for m in reversed(list(messages or [])):
		if isinstance(m, Mapping) and str(m.get("role", "")).lower() == "user":
			return str(m.get("content", "")).strip()
	# fallback: last content
	if messages:
		last = messages[-1]
		if isinstance(last, Mapping):
			return str(last.get("content", "")).strip()
		return str(last).strip()
	return ""


class TutorChatPayload(BaseModel):
	learner_profile: Any = ""
	messages: Any
	use_search: bool = True
	top_k: int = 5
	external_resources: Optional[str] = None
	mode: str = "general"  # "general", "brainstorming", or "exercise"
	exercise_context: Optional[dict] = None  # {"plan": {...}, "sheet_snapshot": {...}}

	@field_validator("learner_profile")
	@classmethod
	def coerce_profile(cls, v: Any) -> Any:
		if isinstance(v, BaseModel):
			return v.model_dump()
		if isinstance(v, Mapping):
			return dict(v)
		return v


class AITutorChatbot(BaseAgent):
	name: str = "AITutorChatbot"

	def __init__(self, model: Any, *, search_rag_manager: Optional[SearchRagManager] = None):
		super().__init__(model=model, system_prompt=ai_tutor_chatbot_system_prompt, jsonalize_output=False)
		self.search_rag_manager = search_rag_manager

	def chat(self, payload: TutorChatPayload | Mapping[str, Any] | str, trace_session: Optional[TraceSession] = None):
		if not isinstance(payload, TutorChatPayload):
			payload = TutorChatPayload.model_validate(payload)

		data = payload.model_dump()
		messages = data.get("messages")
		msg_count = len(messages) if isinstance(messages, list) else 0
		history_text = _stringify_history(messages)
		query = _last_user_query(messages)
		mode = data.get("mode", "general")

		logger.info("TUTOR    chat starting (mode=%s, messages=%d, use_search=%s)", mode, msg_count, data.get("use_search", True))

		external_context = data.get("external_resources") or ""
		if self.search_rag_manager is not None and query:
			try:
				if data.get("use_search", True):
					logger.info("TUTOR    RAG web search + retrieval for query: %.80s", query)
					docs = self.search_rag_manager.invoke(query)
				else:
					logger.info("TUTOR    RAG vectorstore retrieval for query: %.80s", query)
					docs = self.search_rag_manager.retrieve(query, k=max(1, int(data.get("top_k", 5))))
				doc_count = len(docs) if docs else 0
				logger.info("TUTOR    RAG returned %d documents", doc_count)
				context = format_docs(docs)
				if context:
					external_context = f"{external_context}\n{context}" if external_context else context
			except Exception as e:
				logger.warning("TUTOR    RAG failed, continuing without external context: %s", e)

		# Select task prompt based on mode
		exercise_ctx = data.get("exercise_context") or {}

		if mode == "brainstorming":
			task_prompt = ai_tutor_brainstorming_task_prompt
			input_vars = {
				"learner_profile": data.get("learner_profile", ""),
				"messages": history_text,
			}
		elif mode == "exercise":
			task_prompt = ai_tutor_exercise_task_prompt
			input_vars = {
				"learner_profile": data.get("learner_profile", ""),
				"messages": history_text,
				"external_resources": external_context,
				"exercise_plan": json.dumps(exercise_ctx.get("plan", {})),
				"sheet_snapshot": json.dumps(exercise_ctx.get("sheet_snapshot", {})),
			}
		else:
			task_prompt = ai_tutor_chatbot_task_prompt
			input_vars = {
				"learner_profile": data.get("learner_profile", ""),
				"messages": history_text,
				"external_resources": external_context,
			}

		# General mode: use BaseAgent's invoke (unchanged path)
		if mode == "general":
			raw_reply = self.invoke(input_vars, task_prompt=task_prompt)
			return {"response": raw_reply, "tool_calls": []}

		# Brainstorming / Exercise mode: use bind_tools for structured signals
		lang_messages = self._build_messages(input_vars, task_prompt=task_prompt)

		if mode == "brainstorming":
			model_with_tools = self._model.bind_tools([BrainstormingDone])
		else:  # exercise
			model_with_tools = self._model.bind_tools([SheetUpdate])

		if trace_session is not None:
			with trace_session.span("AITutorChatbot", f"chat_{mode}") as rec:
				rec.set_input(lang_messages)
				ai_response = model_with_tools.invoke(lang_messages)
				rec.set_response(ai_response)
				tool_names = [tc["name"] for tc in (ai_response.tool_calls or [])]
				rec.set_parsed({"content_preview": (ai_response.content or "")[:200], "tool_calls": tool_names})
		else:
			ai_response = model_with_tools.invoke(lang_messages)

		# Extract conversational text + any tool calls
		result = {"response": ai_response.text or "", "tool_calls": []}
		if ai_response.tool_calls:
			for tc in ai_response.tool_calls:
				result["tool_calls"].append({
					"name": tc["name"],
					"args": tc["args"],
				})
		return result


def chat_with_tutor_with_llm(
	llm: Any,
	messages: Optional[Sequence[Mapping[str, Any]]] | str = None,
	learner_profile: Any = "",
	*,
	search_rag_manager: Optional[SearchRagManager] = None,
	use_search: bool = True,
	top_k: int = 5,
	mode: str = "general",
	exercise_context: Optional[dict] = None,
	trace_session: Optional[TraceSession] = None,
):
	"""Convenience helper to run an AI tutor chat turn with optional RAG.

	- If a SearchRagManager is provided and use_search=True, performs web search + retrieval.
	- If provided and use_search=False, performs vectorstore-only retrieval.
	- If not provided, replies without external context.
	"""
	agent = AITutorChatbot(llm, search_rag_manager=search_rag_manager)
	payload = {
		"learner_profile": learner_profile,
		"messages": messages,
		"use_search": use_search,
		"top_k": top_k,
		"mode": mode,
		"exercise_context": exercise_context,
	}
	return agent.chat(payload, trace_session=trace_session)
