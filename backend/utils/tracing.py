"""Agent tracing for the exercise flow.

Captures full LLM inputs, outputs, token usage, and timing for each agent call.
Writes streaming JSONL events to backend/logs/traces/traces_YYYY-MM-DD.jsonl
and prints real-time summaries to the terminal.

Usage:
    with TraceSession("exercise_generation", metadata={"topic": "VLOOKUP"}) as trace:
        with trace.span("ExercisePlanner", "step_1_plan") as rec:
            messages = planner._build_messages(input_dict, task_prompt=prompt)
            rec.set_input(messages)
            raw_result = planner._model.with_structured_output(ExercisePlan, include_raw=True).invoke(messages)
            rec.set_response(raw_result["raw"])
            result = raw_result["parsed"]
            rec.set_parsed(result)
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

logger = logging.getLogger("tracing")

TRACES_DIR = Path(__file__).parent.parent / "logs" / "traces"


def _traces_file() -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return TRACES_DIR / f"traces_{date_str}.jsonl"


def _append_event(event: dict) -> None:
    with open(_traces_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Point-in-time event helpers (not wrapped in a TraceSession)
# ---------------------------------------------------------------------------

def log_user_message(exercise_id: str | None, content: str, mode: str) -> None:
    """Record a student's chat turn in the exercise trace."""
    if not exercise_id:
        return
    _append_event({
        "event": "user_message",
        "exercise_id": exercise_id,
        "timestamp": _now_iso(),
        "content": content,
        "mode": mode,
    })


def log_sheet_snapshot(exercise_id: str | None, cell_values: Any) -> None:
    """Record the current spreadsheet state (cell values 2-D grid) in the exercise trace."""
    if not exercise_id or cell_values is None:
        return
    _append_event({
        "event": "sheet_snapshot",
        "exercise_id": exercise_id,
        "timestamp": _now_iso(),
        "cell_values": cell_values,
    })


def log_lifecycle(exercise_id: str | None, kind: str) -> None:
    """Record an exercise lifecycle event (exercise_started / exercise_completed / exercise_abandoned)."""
    if not exercise_id:
        return
    _append_event({
        "event": "lifecycle",
        "exercise_id": exercise_id,
        "timestamp": _now_iso(),
        "kind": kind,
    })


def _serialize_messages(messages: list) -> list[dict]:
    result = []
    for m in messages:
        role = getattr(m, "type", None) or getattr(m, "role", "unknown")
        content = getattr(m, "content", str(m))
        result.append({"role": role, "content": content})
    return result


def _extract_token_usage(ai_message: Any) -> dict:
    usage = getattr(ai_message, "usage_metadata", None)
    if not usage:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    output_details = usage.get("output_token_details", {}) or {}
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "reasoning_tokens": output_details.get("reasoning", 0),
    }


@dataclass
class SpanRecorder:
    """Mutable helper populated by call sites during a traced agent call."""

    agent_name: str
    step_label: str
    input_messages: list[dict] = field(default_factory=list)
    raw_response: str | None = None
    thinking: str | None = None
    parsed_output: Any = None
    token_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    success: bool = True
    error: str | None = None
    duration_seconds: float = 0.0
    _start_time: float = field(default=0.0, repr=False)

    def set_input(self, messages: list) -> None:
        self.input_messages = _serialize_messages(messages)

    def set_response(self, ai_message: Any) -> None:
        content = getattr(ai_message, "content", str(ai_message))
        # Flatten list content (Responses API returns blocks, not a plain string)
        if isinstance(content, list):
            text_parts = [
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") in ("text", "output_text")
            ]
            self.raw_response = "".join(text_parts)
        else:
            self.raw_response = content
        self.token_usage = _extract_token_usage(ai_message)
        # Capture reasoning content: Responses API exposes it via additional_kwargs
        # or as "reasoning" blocks inside content list
        thinking_parts: list[str] = []
        if isinstance(content, list):
            for b in content:
                if not (isinstance(b, dict) and b.get("type") == "reasoning"):
                    continue
                # Responses API: {"type": "reasoning", "summary": [{"type": "summary_text", "text": "..."}]}
                for summary_item in b.get("summary") or []:
                    if isinstance(summary_item, dict) and summary_item.get("text"):
                        thinking_parts.append(summary_item["text"])
                # Fallback: direct text/reasoning key (other providers)
                direct = b.get("text") or b.get("reasoning")
                if direct and isinstance(direct, str):
                    thinking_parts.append(direct)
        self.thinking = "\n\n".join(filter(None, thinking_parts)) or None

    def set_parsed(self, output: Any) -> None:
        if hasattr(output, "model_dump"):
            self.parsed_output = output.model_dump()
        elif isinstance(output, dict):
            self.parsed_output = output
        else:
            self.parsed_output = str(output)[:5000]

    def to_event(self, trace_id: str, exercise_id: str | None = None) -> dict:
        event: dict = {
            "event": "span",
            "trace_id": trace_id,
            "agent_name": self.agent_name,
            "step_label": self.step_label,
            "duration_seconds": round(self.duration_seconds, 3),
            "token_usage": self.token_usage,
            "success": self.success,
            "error": self.error,
            "input_messages": self.input_messages,
            "thinking": self.thinking,
            "raw_response": self.raw_response,
            "parsed_output": self.parsed_output,
        }
        if exercise_id:
            event["exercise_id"] = exercise_id
        return event


class TraceSession:
    """Context manager that groups agent spans into a trace and streams events to JSONL."""

    def __init__(self, trace_type: str, metadata: dict | None = None, exercise_id: str | None = None) -> None:
        self.trace_id = str(uuid4())[:8]
        self.trace_type = trace_type
        self.metadata = metadata or {}
        self.exercise_id = exercise_id
        self._spans: list[SpanRecorder] = []
        self._start_time = 0.0
        self.quality_summary: dict | None = None

    def set_quality_summary(self, summary: dict) -> None:
        """Attach an exercise-level quality record to be included in trace_end."""
        self.quality_summary = summary

    def __enter__(self) -> "TraceSession":
        self._start_time = time.time()
        event: dict = {
            "event": "trace_start",
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "metadata": self.metadata,
        }
        if self.exercise_id:
            event["exercise_id"] = self.exercise_id
        _append_event(event)
        logger.info("TRACE    [%s] %s started", self.trace_id, self.trace_type)
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb) -> bool:
        total_duration = time.time() - self._start_time
        total_tokens = {
            "input_tokens": sum(s.token_usage.get("input_tokens", 0) for s in self._spans),
            "output_tokens": sum(s.token_usage.get("output_tokens", 0) for s in self._spans),
            "total_tokens": sum(s.token_usage.get("total_tokens", 0) for s in self._spans),
        }
        success = exc_type is None
        event: dict = {
            "event": "trace_end",
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "total_duration_seconds": round(total_duration, 3),
            "total_tokens": total_tokens,
            "span_count": len(self._spans),
            "success": success,
            "error": str(exc_val) if exc_val else None,
        }
        if self.exercise_id:
            event["exercise_id"] = self.exercise_id
        if self.quality_summary is not None:
            event["quality"] = self.quality_summary
        _append_event(event)
        self._print_summary(total_duration, total_tokens, success)
        return False  # do not suppress exceptions

    @contextmanager
    def span(self, agent_name: str, step_label: str) -> Generator[SpanRecorder, None, None]:
        rec = SpanRecorder(agent_name=agent_name, step_label=step_label)
        rec._start_time = time.time()
        try:
            yield rec
            rec.success = True
        except Exception as e:
            rec.success = False
            rec.error = str(e)
            raise
        finally:
            rec.duration_seconds = time.time() - rec._start_time
            self._spans.append(rec)
            _append_event(rec.to_event(self.trace_id, self.exercise_id))
            self._print_span(rec)

    def _print_span(self, rec: SpanRecorder) -> None:
        tok = rec.token_usage
        status = "OK" if rec.success else f"FAIL: {rec.error}"
        reasoning_tokens = tok.get("reasoning_tokens", 0)
        reasoning_str = f" reasoning:{reasoning_tokens}" if reasoning_tokens else ""
        logger.info(
            "TRACE    [%s] %-28s %5.1fs  in:%-6d out:%-6d%s  %s",
            self.trace_id,
            rec.step_label,
            rec.duration_seconds,
            tok.get("input_tokens", 0),
            tok.get("output_tokens", 0),
            reasoning_str,
            status,
        )

    def _print_summary(self, total_duration: float, total_tokens: dict, success: bool) -> None:
        status = "OK" if success else "FAILED"
        logger.info(
            "TRACE    [%s] %s done — %.1fs  total tokens: in:%d out:%d  [%s]",
            self.trace_id,
            self.trace_type,
            total_duration,
            total_tokens["input_tokens"],
            total_tokens["output_tokens"],
            status,
        )
