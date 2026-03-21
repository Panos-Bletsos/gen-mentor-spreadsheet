from __future__ import annotations

import json
import logging
from typing import Any, Optional

from base import BaseAgent
from modules.data_generator import generate_synthetic_spreadsheet_data_with_llm
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
    ExerciseTopic,
    JudgeQualityResult,
    StartExercisePayload,
)

logger = logging.getLogger(__name__)

MAX_JUDGE_RETRIES = 2


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
    columns = sheet_plan.get("prefilled", [])
    if columns == ["all"]:
        columns = sheet_plan.get("columns", [])

    context_parts = [
        f"Generate data for a spreadsheet exercise.",
        f"Scenario: {plan.scenario}",
        f"Sheet: {sheet_plan['name']}",
        f"This data is for teaching {plan.difficulty}-level spreadsheet skills.",
    ]
    if prev_sheets_data:
        context_parts.append(f"Related sheets already generated: {json.dumps([s['name'] for s in prev_sheets_data])}")
        context_parts.append("Ensure referential integrity with existing sheets.")
    if retry_reason:
        context_parts.append(f"Previous attempt was rejected: {retry_reason}. Fix this issue.")

    return {
        "user_request": " ".join(context_parts),
        "row_count": plan.row_count,
        "columns": columns if columns else None,
        "constraints": retry_reason,
    }


class ExercisePlanner(BaseAgent):
    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=exercise_planner_system_prompt,
            jsonalize_output=True,
        )


class QualityJudge(BaseAgent):
    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=judge_quality_system_prompt,
            jsonalize_output=True,
        )


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
) -> dict:
    """Run the 4-step exercise generation chain.

    Returns dict with keys: exercise_plan, spreadsheet_data, tutor_message.
    """
    # --- Step 1: Plan Exercise ---
    planner = ExercisePlanner(llm)
    brainstorming_context = ""
    if brainstorming_history:
        brainstorming_context = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in brainstorming_history
        )

    plan_input = {
        "topic": _topic_to_str(topic),
        "learner_profile": str(learner_profile),
        "brainstorming_context": brainstorming_context,
    }
    plan_raw = planner.invoke(plan_input, task_prompt=exercise_planner_task_prompt)
    if isinstance(plan_raw, str):
        plan_raw = json.loads(plan_raw)
    exercise_plan = ExercisePlan.model_validate(plan_raw)

    # --- Step 2 & 3: Generate Data + Judge Quality (with retry loop) ---
    all_sheets_data = []
    judge = QualityJudge(llm)

    for sheet_plan in exercise_plan.sheets:
        sheet_dict = sheet_plan.model_dump() if hasattr(sheet_plan, "model_dump") else dict(sheet_plan)
        prefilled = sheet_dict.get("prefilled", [])
        # Skip sheets with no prefilled data
        if not prefilled:
            all_sheets_data.append({"name": sheet_dict["name"], "headers": sheet_dict.get("columns", []), "rows": []})
            continue

        retry_reason = ""
        sheet_data = None
        for attempt in range(1 + MAX_JUDGE_RETRIES):
            data_request = _build_data_request(exercise_plan, sheet_dict, all_sheets_data, retry_reason)
            sheet_data = generate_synthetic_spreadsheet_data_with_llm(
                llm,
                user_request=data_request["user_request"],
                row_count=data_request["row_count"],
                columns=data_request["columns"],
                constraints=data_request["constraints"],
            )

            # Judge quality
            judge_input = {
                "exercise_plan": json.dumps(plan_raw),
                "generated_data": json.dumps(sheet_data),
                "difficulty": exercise_plan.difficulty,
                "expected_rows": exercise_plan.row_count,
            }
            judge_raw = judge.invoke(judge_input, task_prompt=judge_quality_task_prompt)
            if isinstance(judge_raw, str):
                judge_raw = json.loads(judge_raw)
            judge_result = JudgeQualityResult.model_validate(judge_raw)

            if judge_result.passed:
                break
            retry_reason = judge_result.reason
            logger.warning(f"Quality judge rejected data (attempt {attempt + 1}): {retry_reason}")

        # Add student_fills columns as empty
        student_cols = sheet_dict.get("student_fills", [])
        if student_cols and sheet_data:
            for col in student_cols:
                if col not in sheet_data.get("headers", []):
                    sheet_data["headers"].append(col)
                    for row in sheet_data.get("rows", []):
                        row.append("")

        sheet_data["name"] = sheet_dict["name"]
        all_sheets_data.append(sheet_data)

    # Combine into single spreadsheet_data payload
    spreadsheet_data = {"sheets": all_sheets_data}

    # --- Step 4: Generate Opening Message ---
    msg_gen = OpeningMessageGenerator(llm)
    sheet_names = [s["name"] for s in all_sheets_data]
    columns_summary = "; ".join(
        f"{s['name']}: {s.get('headers', [])}" for s in all_sheets_data
    )
    msg_input = {
        "exercise_plan": json.dumps(plan_raw),
        "learner_profile": str(learner_profile),
        "sheet_names": str(sheet_names),
        "columns_summary": columns_summary,
    }
    tutor_message = msg_gen.invoke(msg_input, task_prompt=opening_message_task_prompt)

    return {
        "exercise_plan": exercise_plan.model_dump(),
        "spreadsheet_data": spreadsheet_data,
        "tutor_message": tutor_message,
    }
