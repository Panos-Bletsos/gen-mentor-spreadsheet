from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class ExerciseTopic(BaseModel):
    """Enriched topic from brainstorming, or just a string wrapper."""
    skill: str
    domain: str = ""
    goal: str = ""
    difficulty_hint: str = ""


class ConstantCell(BaseModel):
    """A single off-grid constant cell, e.g. the overhead rate stored at H2."""
    cell: str          # A1 address, e.g. "H2"
    label: str         # Human-readable label, e.g. "Overhead Rate"
    label_cell: str = ""  # Optional A1 address for the label, e.g. "H1"


class SheetPlan(BaseModel):
    name: str
    columns: list[str]
    prefilled: list[str]
    student_fills: list[str] = []
    expected_formula_template: str = ""
    constants: list[ConstantCell] = []


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


class SheetData(BaseModel):
    """Generated data for one sheet, keyed by A1 address.

    Student-answer cells are simply absent from `cells`.
    Constants (off-grid) appear here alongside the main grid cells.
    Example:
        {
          "A1": "Pipeline", "B1": "GB_per_Run", ...,
          "A2": "Customer_Orders_ETL", "B2": 120,  # D2/E2/F2 absent = student fills
          "H1": "Overhead Rate", "H2": 0.15         # constant
        }
    """
    name: str
    cells: dict[str, Any]   # A1 key -> scalar value
    quality_passed: bool = True
    quality_reason: str = ""


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
