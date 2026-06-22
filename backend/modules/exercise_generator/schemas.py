from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ExerciseTopic(BaseModel):
    """Enriched topic from brainstorming, or just a string wrapper."""
    skill: str
    domain: str = ""
    goal: str = ""
    difficulty_hint: str = ""


class SheetPlan(BaseModel):
    name: str
    columns: list[str]
    prefilled: list[str]
    student_fills: list[str] = []
    expected_formula_template: str = ""


class ExerciseStep(BaseModel):
    goal: str
    hint: str = ""


class ExercisePlan(BaseModel):
    exercise_type: str  # "fill_formulas" or "multi_step_analysis"
    scenario: str
    sheets: list[SheetPlan]
    steps: list[ExerciseStep] = []
    row_count: int = 10
    difficulty: str = "beginner"


class StartExercisePayload(BaseModel):
    topic: Any  # str or ExerciseTopic dict
    learner_profile: Any = ""
    brainstorming_history: list[dict] = []


class StartExerciseResult(BaseModel):
    exercise_plan: dict
    spreadsheet_data: dict
    tutor_message: str


class JudgeQualityResult(BaseModel):
    passed: bool
    reason: str = ""           # human-facing diagnosis of WHY it failed
    fix_instruction: str = ""  # concrete data change the generator must apply on the next attempt
