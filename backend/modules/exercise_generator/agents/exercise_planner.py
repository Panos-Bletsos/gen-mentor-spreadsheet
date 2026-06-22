from __future__ import annotations

import json
import logging
import math
import re
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


def _format_correction(judge_result: "JudgeQualityResult") -> str:
    """Frame a judge rejection as an explicit correction directive for the generator."""
    lines = ["The previous attempt was REJECTED by the quality judge."]
    if judge_result.reason:
        lines.append(f"Reason: {judge_result.reason}")
    if judge_result.fix_instruction:
        lines.append(f"Required correction — you MUST apply this to the data: {judge_result.fix_instruction}")
    return "\n".join(lines)


def _col_index_to_letter(index: int) -> str:
    """Convert 0-based column index to spreadsheet column letter(s). 0='A', 25='Z', 26='AA', etc."""
    result = ""
    n = index + 1  # 1-based
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(ord('A') + remainder) + result
    return result


def _check_solvability(sheet_plan_dict: dict, sheet_data_dict: dict) -> tuple[bool, str]:
    """
    Check that expected_formula_template resolves to finite numerics for all student rows.

    Returns (passed: bool, error_message: str).
    """
    import formulas  # type: ignore[import]

    template = sheet_plan_dict.get("expected_formula_template", "")
    if not template:
        return (True, "")

    student_fills = sheet_plan_dict.get("student_fills", [])
    if not student_fills:
        return (True, "")

    columns = sheet_plan_dict.get("columns", [])
    cells = sheet_data_dict.get("cells", {})

    # Find max row index in cells (excluding row 1 which is the header)
    max_row = 1
    for key in cells:
        m = re.match(r'^([A-Z]+)([0-9]+)$', key.upper())
        if m:
            row_num = int(m.group(2))
            if row_num > max_row:
                max_row = row_num

    if max_row < 2:
        # No data rows
        return (True, "")

    # Build student_col_letters: set of column letters for student_fills columns
    student_col_letters = set()
    for col_name in student_fills:
        if col_name in columns:
            idx = columns.index(col_name)
            student_col_letters.add(_col_index_to_letter(idx))

    # Prepare cells dict with uppercased keys for fast lookup
    cells_upper = {k.upper(): v for k, v in cells.items()}

    for row in range(2, max_row + 1):
        for clause in template.split(";"):
            clause = clause.strip()
            if not clause:
                continue

            # Split on first '=' to get lhs and rhs
            eq_idx = clause.find("=")
            if eq_idx == -1:
                continue
            lhs = clause[:eq_idx]
            rhs = clause[eq_idx + 1:]

            # Substitute {row} with current row number
            lhs_subst = lhs.replace("{row}", str(row)).strip().upper()
            rhs_subst = rhs.replace("{row}", str(row))

            target_cell = lhs_subst
            formula_str = "=" + rhs_subst

            # Check if target_cell is in a student-fill column
            # Extract the column letter(s) from the target cell address
            m = re.match(r'^([A-Z]+)([0-9]+)$', target_cell)
            if not m:
                continue
            target_col = m.group(1)
            if target_col not in student_col_letters:
                # This clause is for a prefilled column or another sheet — skip
                continue

            # Structural check: find all cell references in the formula
            refs = re.findall(r'\$?([A-Z]+)\$?([0-9]+)', formula_str.upper())
            has_student_fill_ref = False
            for ref_col, ref_row_str in refs:
                ref_addr = ref_col + ref_row_str
                if ref_addr not in cells_upper:
                    # Check if this is another student-fill column
                    if ref_col in student_col_letters:
                        has_student_fill_ref = True
                        # Allowed: it's a student-computed cell from another row/column
                    else:
                        return (False, f"Structural: formula '{formula_str}' references cell '{ref_addr}' which is not in the generated data")

            # Evaluation: if the formula references other student-fill cells, skip evaluation
            if has_student_fill_ref:
                continue

            try:
                parser = formulas.Parser()
                func = parser.ast(formula_str)[1].compile()
                # Only pass the inputs the compiled function actually needs
                needed = set(func.inputs.keys())
                inputs = {addr: [[cells_upper[addr]]] for addr in needed if addr in cells_upper}
                result = func(**inputs)
                value = result.tolist()[0][0]
            except Exception as e:
                return (False, f"Evaluation: formula '{formula_str}' in cell '{target_cell}' (row {row}) raised exception: {e!r}")

            # Check for non-finite numeric result
            if isinstance(value, str) or not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)):
                return (False, f"Evaluation: formula '{formula_str}' in cell '{target_cell}' (row {row}) returned non-numeric result: {value!r}")

    return (True, "")


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
        prev_summary = [{"name": s["name"], "cells": s.get("cells", {})} for s in prev_sheets_data]
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
    exercise_id: Optional[str] = None,
) -> dict:
    """Run the 4-step exercise generation chain.

    Returns dict with keys: exercise_id, exercise_plan, spreadsheet_data, tutor_message.
    """
    chain_start = time.time()
    topic_str = _topic_to_str(topic)
    quality_summary: dict = {}
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

    # Initialise return-value locals so Pyright sees them as always-bound.
    exercise_plan: Optional[ExercisePlan] = None
    spreadsheet_data: dict = {"sheets": []}
    tutor_message: str = ""

    with TraceSession("exercise_generation", metadata={"topic": topic_str}, exercise_id=exercise_id) as trace:
        # --- Step 1: Plan Exercise ---
        planner = ExercisePlanner(llm)
        exercise_plan = None  # reassigned immediately by _run_planner()

        def _run_planner(extra_ctx: str = "") -> ExercisePlan:
            """Run ExercisePlanner, optionally with extra retry context appended."""
            pi = dict(plan_input)
            if extra_ctx:
                pi["context"] = (pi["context"] + "\n\n" + extra_ctx).strip()
            with trace.span("ExercisePlanner", "step_1_plan") as rec:
                try:
                    messages = planner._build_messages(pi, task_prompt=exercise_planner_task_prompt)
                    rec.set_input(messages)
                    raw_result: dict = planner._model.with_structured_output(ExercisePlan, include_raw=True).invoke(messages)  # type: ignore[assignment]
                    rec.set_response(raw_result["raw"])
                    ep: ExercisePlan = raw_result["parsed"]
                    rec.set_parsed(ep)
                    return ep
                except Exception as e:
                    logger.exception("EXERCISE GENERATOR EXCEPTION", e)
                    raise

        exercise_plan = _run_planner()
        logger.info("EXERCISE plan created: difficulty=%s, sheets=%d, rows=%d", exercise_plan.difficulty, len(exercise_plan.sheets), exercise_plan.row_count)

        # --- Step 2 & 3 & 4: Generate Data + Judge Quality + Solvability Gate ---
        logger.info("EXERCISE [Step 2/4] Generating data + quality judging + solvability")
        all_sheets_data = []
        quality_records: list[dict] = []  # per-sheet quality history for trace + returned data
        judge = QualityJudge(llm)

        # Outer re-plan loop: re-run the planner on structural solvability failures
        for re_plan_attempt in range(2):
            if re_plan_attempt > 0:
                logger.info("EXERCISE re-plan attempt %d triggered", re_plan_attempt)

            all_sheets_data = []
            quality_records = []
            trigger_replan = False
            replan_reason = ""

            for sheet_plan in exercise_plan.sheets:
                sheet_dict = sheet_plan.model_dump() if hasattr(sheet_plan, "model_dump") else dict(sheet_plan)
                student_fills = sheet_dict.get("student_fills", [])

                # Skip sheets with no student_fills — generate data but skip judge + solvability
                if not student_fills:
                    logger.info("EXERCISE sheet '%s' has no student_fills — generating data, skipping judge+solvability", sheet_dict["name"])
                    data_request = _build_data_request(exercise_plan, sheet_dict, all_sheets_data, "")
                    step_label = f"step_2_data_{sheet_dict['name']}_nojudge"
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
                    except Exception as e:
                        logger.exception("EXERCISE data generation FAILED for sheet '%s': %s", sheet_dict["name"], e)
                        raise
                    sheet_data["name"] = sheet_dict["name"]
                    sheet_data["quality_passed"] = True
                    sheet_data["quality_reason"] = ""
                    all_sheets_data.append(sheet_data)
                    quality_records.append({"name": sheet_dict["name"], "final_passed": True, "judged": False, "attempts": []})
                    continue

                logger.info("EXERCISE generating data for sheet '%s'", sheet_dict["name"])
                retry_reason = ""
                sheet_data = None
                sheet_attempts: list[dict] = []
                final_passed = False

                for attempt in range(1 + MAX_JUDGE_RETRIES):
                    # Step 2: Generate data (returns {"cells": {...}})
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
                        raw_result: dict = judge._model.with_structured_output(JudgeQualityResult, include_raw=True).invoke(messages)  # type: ignore[assignment]
                        rec.set_response(raw_result["raw"])
                        judge_result: JudgeQualityResult = raw_result["parsed"]
                        rec.set_parsed(judge_result)

                    sheet_attempts.append({
                        "attempt": attempt + 1,
                        "passed": judge_result.passed,
                        "reason": judge_result.reason,
                        "fix_instruction": judge_result.fix_instruction,
                    })

                    if not judge_result.passed:
                        retry_reason = _format_correction(judge_result)
                        logger.warning("EXERCISE quality judge REJECTED sheet '%s' (attempt %d/%d): %s", sheet_dict["name"], attempt + 1, 1 + MAX_JUDGE_RETRIES, judge_result.reason)
                        continue

                    logger.info("EXERCISE quality judge PASSED for sheet '%s' (attempt %d)", sheet_dict["name"], attempt + 1)

                    # Step 4 (NEW): Solvability gate
                    solved, error_msg = _check_solvability(sheet_dict, sheet_data)
                    if not solved:
                        logger.warning("EXERCISE solvability check FAILED for sheet '%s' (attempt %d): %s", sheet_dict["name"], attempt + 1, error_msg)
                        if "Structural:" in error_msg and re_plan_attempt == 0:
                            # Trigger re-plan — structural issue needs planner fix
                            trigger_replan = True
                            replan_reason = error_msg
                            break
                        else:
                            retry_reason = f"SOLVABILITY FAILURE: {error_msg}. Regenerate the data so all formula references resolve to finite numbers."
                            continue

                    # All checks passed
                    logger.info("EXERCISE solvability check PASSED for sheet '%s' (attempt %d)", sheet_dict["name"], attempt + 1)
                    final_passed = True
                    break

                if trigger_replan:
                    break

                if not final_passed:
                    logger.warning("EXERCISE quality/solvability checks EXHAUSTED retries for sheet '%s' — shipping with quality_passed=False", sheet_dict["name"])

                sheet_data["name"] = sheet_dict["name"]
                # Attach quality flag so the developer can audit shipped-despite-failure exercises
                sheet_data["quality_passed"] = final_passed
                sheet_data["quality_reason"] = sheet_attempts[-1]["reason"] if sheet_attempts and not final_passed else ""
                all_sheets_data.append(sheet_data)
                quality_records.append({
                    "name": sheet_dict["name"],
                    "final_passed": final_passed,
                    "judged": True,
                    "attempts": sheet_attempts,
                })

            if trigger_replan and re_plan_attempt == 0:
                logger.warning("EXERCISE triggering re-plan due to structural solvability failure: %s", replan_reason)
                replan_ctx = f"Previous plan failed solvability: {replan_reason}. Fix the constants list or formula templates."
                exercise_plan = _run_planner(extra_ctx=replan_ctx)
                logger.info("EXERCISE re-plan complete: difficulty=%s, sheets=%d", exercise_plan.difficulty, len(exercise_plan.sheets))
                # Reset and retry the sheet loop with new plan
                continue
            else:
                # Either no replan needed, or we've exhausted re-plan attempts
                break

        # Combine into single spreadsheet_data payload
        spreadsheet_data = {"sheets": all_sheets_data}

        # Build exercise-level quality summary and attach to the trace
        sheets_failed = [r["name"] for r in quality_records if r["judged"] and not r["final_passed"]]
        quality_summary = {
            "quality_passed": len(sheets_failed) == 0,
            "sheets_failed": sheets_failed,
            "sheets": quality_records,
        }
        trace.set_quality_summary(quality_summary)

        # --- Step 4: Generate Opening Message ---
        logger.info("EXERCISE [Step 3/4] Data generation complete for %d sheets", len(all_sheets_data))
        logger.info("EXERCISE [Step 4/4] Generating opening message")
        msg_gen = OpeningMessageGenerator(llm)
        sheet_names = [s["name"] for s in all_sheets_data]
        columns_summary = "; ".join(
            # Extract row-1 values (header names) from the A1 cell-map, sorted by column letter.
            f"{s['name']}: {[v for k, v in sorted(s.get('cells', {}).items()) if re.match(r'^[A-Z]+1$', k.upper())]}"
            for s in all_sheets_data
        )
        constants_summary = "; ".join(
            f"{sp.name}: {[c.label + '=' + c.cell for c in sp.constants]}"
            for sp in exercise_plan.sheets
        )
        msg_input = {
            "exercise_plan": exercise_plan.model_dump_json(),
            "learner_profile": str(learner_profile),
            "sheet_names": str(sheet_names),
            "columns_summary": columns_summary,
            "constants_summary": constants_summary,
        }
        with trace.span("OpeningMessageGenerator", "step_4_opening_msg") as rec:
            messages = msg_gen._build_messages(msg_input, task_prompt=opening_message_task_prompt)
            rec.set_input(messages)
            ai_response = msg_gen._model.invoke(messages)
            rec.set_response(ai_response)
            tutor_message = str(preprocess_response(
                {"messages": [ai_response]}, only_text=True, exclude_think=True, json_output=False
            ))
            rec.set_parsed(tutor_message)

    logger.info("EXERCISE chain complete (%.1fs)", time.time() - chain_start)
    return {
        "exercise_id": exercise_id,
        "exercise_plan": exercise_plan.model_dump(),
        "spreadsheet_data": spreadsheet_data,
        "tutor_message": tutor_message,
        "quality_summary": quality_summary,
    }
