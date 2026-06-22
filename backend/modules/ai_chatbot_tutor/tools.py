"""Tutor tool schemas for LangChain bind_tools().

These Pydantic models define structured signals the AI Tutor can emit
alongside conversational text. The LLM calls these as "tools" via
provider-native tool calling, replacing the old pattern of embedding
JSON signals inside free-text responses.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BrainstormingDone(BaseModel):
    """Signal that brainstorming is complete. Called when the tutor has
    converged on an exercise topic with the student."""

    skill: str = Field(description="The spreadsheet skill(s) to practice, e.g. 'VLOOKUP', 'pivot tables'")
    domain: str = Field(description="The domain/context, e.g. 'sales analysis', 'financial modeling'")
    goal: str = Field(description="What the exercise should achieve")
    difficulty_hint: str = Field(description="beginner, intermediate, or advanced")


class SheetData(BaseModel):
    """One sheet tab in a workbook update, keyed by A1 address.

    Use plain A1 keys (no $): 'A1', 'B2', etc. Row 1 is the header row.
    Formula cells start with '=' and are evaluated by Univer on load.
    Example: {'A1': 'Revenue', 'B1': 'Cost', 'A2': 50000, 'B2': 30000}
    """

    name: str = Field(description="Sheet tab name, e.g. 'Sales Data'")
    cells: dict[str, Any] = Field(
        description=(
            "A1-keyed cell map: plain A1 address (e.g. 'B3') → scalar value or formula string. "
            "Row 1 = headers. Formula cells start with '='. Omit student-fill cells."
        )
    )


class SheetUpdate(BaseModel):
    """Signal to update the spreadsheet content. Called when the tutor
    needs to populate, fill, correct, or reset sheet data."""

    sheets: list[SheetData] = Field(description="Complete workbook content")


class HighlightCells(BaseModel):
    """Highlight target cell range(s) in the spreadsheet as a visual hint.
    Non-destructive — does not modify the student's data, never persisted to saved work."""

    sheet: str = Field(description="Sheet tab name the ranges belong to, e.g. 'Sales Data'")
    ranges: list[str] = Field(description="A1-style ranges to highlight, e.g. ['C2:C11', 'D2:D11']")
    level: int = Field(description="Hint level: 1 (column-level nudge), 2 (formula name), or 3 (exact target cell)")
    note: str = Field(description="One short line for the student, action-first, e.g. 'This column needs a formula.'")


class DemoEdit(BaseModel):
    """Write a demonstration formula into ONE cell (Level-4 hint).
    The student will be shown a 'Now you try' button to revert it and type it themselves."""

    sheet: str = Field(description="Sheet tab name, e.g. 'Sales Data'")
    cell: str = Field(description="Single A1-notation cell to write the demo into, e.g. 'C2'")
    formula: str = Field(description="Demonstration formula starting with '=', e.g. '=A2*B2'")
    explanation: str = Field(description="One-line explanation of what the formula does, e.g. 'price times quantity gives revenue'")
