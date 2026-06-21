from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from base import BaseStructuredAgent, BaseAgent
from modules.data_generator.agents.data_generator import generate_with_tracing
from modules.exercise_generator.prompts.exercise_planner import (
    exercise_planner_system_prompt,
    exercise_planner_task_prompt,
    judge_quality_system_prompt,
    judge_quality_task_prompt,
    opening_message_system_prompt,
    opening_message_task_prompt,
)
from modules.exercise_generator.schemas import (
    ExercisePlan,
    JudgeQualityResult,
)
from utils.llm_output import preprocess_response
from utils.tracing import TraceSession

logger = logging.getLogger(__name__)

MAX_JUDGE_RETRIES = 2


def _build_skill_targets(skill_gaps: list | None, topic: Any) -> str:
    """Format per-skill current→required deltas as a labeled block for the planner prompt.

    Filters to gaps that are actual gaps (is_gap=True) so the planner focuses on
    what still needs teaching. Falls back to all entries if none are flagged as gaps.
    Returns a prose-friendly string; emits "(none provided)" when input is empty.
    """
    if not skill_gaps:
        return "(none provided)"

    # Prefer entries that are actual gaps; fall back to all if none flagged
    gaps = [g for g in skill_gaps if g.get("is_gap", True)]
    if not gaps:
        gaps = skill_gaps

    lines = []
    for g in gaps:
        name = g.get("name", "Unknown skill")
        current = g.get("current_level", "unlearned")
        required = g.get("required_level", "beginner")
        reason = g.get("reason", "")
        line = f"- {name}: currently {current} → needs {required}"
        if reason:
            line += f" ({reason})"
        lines.append(line)
    return "\n".join(lines)


def _topic_to_str(topic: Any) -> str:
    """Convert topic (str or dict/ExerciseTopic) to a descriptive string."""
    if isinstance(topic, str):
        return topic
    if isinstance(topic, dict):
        parts = []
        if topic.get("skill"):
            parts.append(f"Skill: {topic['skill']}")
        if topic.get("domain"):
            parts.append(f"Domain: {topic['domain']}")
        if topic.get("goal"):
            parts.append(f"Goal: {topic['goal']}")
        if topic.get("difficulty_hint"):
            parts.append(f"Suggested difficulty: {topic['difficulty_hint']}")
        return "; ".join(parts) if parts else str(topic)
    return str(topic)


def _build_data_request(plan: ExercisePlan, sheet_plan: dict, prev_sheets_data: list[dict], retry_reason: str = "") -> dict:
    """Build a data_generator payload from the exercise plan + one sheet."""
    all_columns = sheet_plan.get("columns", [])
    prefilled = sheet_plan.get("prefilled", [])
    student_fills = sheet_plan.get("student_fills", [])

    context_parts = [
        f"Generate data for a spreadsheet exercise.",
        f"Scenario: {plan.scenario}",
        f"Sheet: {sheet_plan['name']}",
        f"This data is for teaching {plan.difficulty}-level spreadsheet skills.",
    ]

    # Specify which columns to fill and which to leave empty
    if prefilled:
        context_parts.append(f"Fill these columns with realistic data: {prefilled}")
    if student_fills:
        context_parts.append(f"Leave these columns EMPTY (students will fill them): {student_fills}")

    if prev_sheets_data:
        prev_summary = []
        for s in prev_sheets_data:
            summary = {"name": s["name"], "headers": s.get("headers", []), "rows": s.get("rows", [])}
            prev_summary.append(summary)
        context_parts.append(f"Related sheets already generated: {json.dumps(prev_summary)}")
        context_parts.append("Ensure referential integrity — where this sheet shares column names with related sheets, use the exact same values from those sheets.")

    return {
        "user_request": " ".join(context_parts),
        "row_count": plan.row_count,
        "columns": all_columns if all_columns else None,
        "constraints": retry_reason,
    }


class ExercisePlanner(BaseStructuredAgent):
    output_schema = ExercisePlan

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=exercise_planner_system_prompt)


class QualityJudge(BaseStructuredAgent):
    output_schema = JudgeQualityResult

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=judge_quality_system_prompt)


class OpeningMessageGenerator(BaseAgent):
    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=opening_message_system_prompt,
            jsonalize_output=False,
        )


def start_exercise_with_llm(
    llm: Any,
    topic: Any,
    learner_profile: Any = "",
    brainstorming_history: list[dict] | None = None,
    extra_context: str = "",
    skill_gaps: list | None = None,
) -> dict:
    """Run the 4-step exercise generation chain.

    Returns dict with keys: exercise_plan, spreadsheet_data, tutor_message.
    """
    chain_start = time.time()
    topic_str = _topic_to_str(topic)
    logger.info("EXERCISE [Step 1/4] Planning exercise for topic: %.80s", topic_str)

    # Build the context block: label it as brainstorming history when present,
    # otherwise pass the learning-path extra_context (session goals, KPs, outcomes).
    context = ""
    if brainstorming_history:
        history_text = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in brainstorming_history
        )
        context = f"### Brainstorming History\n{history_text}"
    if extra_context:
        context = f"{context}\n\n{extra_context}".strip() if context else extra_context

    plan_input = {
        "topic": topic_str,
        "learner_profile": str(learner_profile),
        "skill_targets": _build_skill_targets(skill_gaps, topic),
        "context": context if context else "(none)",
    }

    with TraceSession("exercise_generation", metadata={"topic": topic_str}) as trace:
        # --- Step 1: Plan Exercise ---
        planner = ExercisePlanner(llm)
        with trace.span("ExercisePlanner", "step_1_plan") as rec:
            try:
                messages = planner._build_messages(plan_input, task_prompt=exercise_planner_task_prompt)
                rec.set_input(messages)
                raw_result = planner._model.with_structured_output(ExercisePlan, include_raw=True).invoke(messages)
                rec.set_response(raw_result["raw"])
                exercise_plan: ExercisePlan = raw_result["parsed"]
                rec.set_parsed(exercise_plan)
            except Exception as e:
                logger.exception("EXERCISE GENERATOR EXCEPTION", e)

        logger.info("EXERCISE plan created: difficulty=%s, sheets=%d, rows=%d", exercise_plan.difficulty, len(exercise_plan.sheets), exercise_plan.row_count)

        # --- Step 2 & 3: Generate Data + Judge Quality (with retry loop) ---
        logger.info("EXERCISE [Step 2/4] Generating data + quality judging")
        all_sheets_data = []
        judge = QualityJudge(llm)

        for sheet_plan in exercise_plan.sheets:
            sheet_dict = sheet_plan.model_dump() if hasattr(sheet_plan, "model_dump") else dict(sheet_plan)
            prefilled = sheet_dict.get("prefilled", [])
            # Skip sheets with no prefilled data
            if not prefilled:
                all_sheets_data.append({"name": sheet_dict["name"], "headers": sheet_dict.get("columns", []), "rows": []})
                continue

            logger.info("EXERCISE generating data for sheet '%s'", sheet_dict["name"])
            retry_reason = ""
            sheet_data = None
            for attempt in range(1 + MAX_JUDGE_RETRIES):
                # Step 2: Generate data
                data_request = _build_data_request(exercise_plan, sheet_dict, all_sheets_data, retry_reason)
                step_label = f"step_2_data_{sheet_dict['name']}_attempt_{attempt + 1}"
                try:
                    with trace.span("SyntheticDataGenerator", step_label) as rec:
                        sheet_data = generate_with_tracing(
                            llm,
                            user_request=data_request["user_request"],
                            row_count=data_request["row_count"],
                            columns=data_request["columns"],
                            constraints=data_request["constraints"],
                            recorder=rec,
                        )
                except (ValueError, Exception) as e:
                    retry_reason = str(e)
                    logger.warning("EXERCISE data generation FAILED for sheet '%s' (attempt %d/%d): %s", sheet_dict["name"], attempt + 1, 1 + MAX_JUDGE_RETRIES, retry_reason)
                    if attempt == MAX_JUDGE_RETRIES:
                        raise
                    continue

                # Step 3: Judge quality
                judge_input = {
                    "exercise_plan": exercise_plan.model_dump_json(),
                    "sheet_name": sheet_dict["name"],
                    "generated_data": json.dumps(sheet_data),
                    "previous_sheets_data": json.dumps(all_sheets_data) if all_sheets_data else "None",
                    "difficulty": exercise_plan.difficulty,
                    "expected_rows": exercise_plan.row_count,
                }
                judge_label = f"step_3_judge_{sheet_dict['name']}_attempt_{attempt + 1}"
                with trace.span("QualityJudge", judge_label) as rec:
                    messages = judge._build_messages(judge_input, task_prompt=judge_quality_task_prompt)
                    rec.set_input(messages)
                    raw_result = judge._model.with_structured_output(JudgeQualityResult, include_raw=True).invoke(messages)
                    rec.set_response(raw_result["raw"])
                    judge_result: JudgeQualityResult = raw_result["parsed"]
                    rec.set_parsed(judge_result)

                if judge_result.passed:
                    logger.info("EXERCISE quality judge PASSED for sheet '%s' (attempt %d)", sheet_dict["name"], attempt + 1)
                    break
                retry_reason = judge_result.reason
                logger.warning("EXERCISE quality judge REJECTED sheet '%s' (attempt %d/%d): %s", sheet_dict["name"], attempt + 1, 1 + MAX_JUDGE_RETRIES, retry_reason)

            sheet_data["name"] = sheet_dict["name"]
            all_sheets_data.append(sheet_data)

        # Combine into single spreadsheet_data payload
        spreadsheet_data = {"sheets": all_sheets_data}

        # --- Step 4: Generate Opening Message ---
        logger.info("EXERCISE [Step 3/4] Data generation complete for %d sheets", len(all_sheets_data))
        logger.info("EXERCISE [Step 4/4] Generating opening message")
        msg_gen = OpeningMessageGenerator(llm)
        sheet_names = [s["name"] for s in all_sheets_data]
        columns_summary = "; ".join(
            f"{s['name']}: {s.get('headers', [])}" for s in all_sheets_data
        )
        msg_input = {
            "exercise_plan": exercise_plan.model_dump_json(),
            "learner_profile": str(learner_profile),
            "sheet_names": str(sheet_names),
            "columns_summary": columns_summary,
        }
        with trace.span("OpeningMessageGenerator", "step_4_opening_msg") as rec:
            messages = msg_gen._build_messages(msg_input, task_prompt=opening_message_task_prompt)
            rec.set_input(messages)
            ai_response = msg_gen._model.invoke(messages)
            rec.set_response(ai_response)
            tutor_message = preprocess_response(
                {"messages": [ai_response]}, only_text=True, exclude_think=True, json_output=False
            )
            rec.set_parsed(tutor_message)

    logger.info("EXERCISE chain complete (%.1fs)", time.time() - chain_start)
    return {
        "exercise_plan": exercise_plan.model_dump(),
        "spreadsheet_data": spreadsheet_data,
        "tutor_message": tutor_message,
    }
