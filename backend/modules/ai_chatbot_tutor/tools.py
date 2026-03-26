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
    """One sheet tab in a workbook update."""

    name: str = Field(description="Sheet tab name, e.g. 'Sales Data'")
    headers: list[str] = Field(description="Column headers")
    rows: list[list[Any]] = Field(description="Data rows, each matching headers length")


class SheetUpdate(BaseModel):
    """Signal to update the spreadsheet content. Called when the tutor
    needs to populate, fill, correct, or reset sheet data."""

    sheets: list[SheetData] = Field(description="Complete workbook content")
