from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from base import BaseAgent
from modules.data_generator.prompts.data_generator import (
    synthetic_data_generator_system_prompt,
    synthetic_data_generator_task_prompt,
)


class SyntheticDataGeneratorPayload(BaseModel):
    user_request: str = Field(..., min_length=1)
    row_count: int = Field(20, ge=1, le=500)
    columns: list[str] | None = None
    constraints: str = ""

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [col.strip() for col in value if col and col.strip()]
        if not cleaned:
            return None
        return cleaned


class SyntheticSpreadsheetData(BaseModel):
    headers: list[str] = Field(..., min_length=1)
    rows: list[list[Any]] = Field(default_factory=list)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: list[str]) -> list[str]:
        cleaned = [h.strip() for h in value if h and h.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty header is required.")
        return cleaned

    @model_validator(mode="after")
    def validate_row_width(self) -> "SyntheticSpreadsheetData":
        expected_width = len(self.headers)
        for idx, row in enumerate(self.rows):
            if len(row) != expected_width:
                raise ValueError(
                    f"Row at index {idx} has {len(row)} values, expected {expected_width}."
                )
        return self


class SyntheticDataGenerator(BaseAgent):
    name: str = "SyntheticDataGenerator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=synthetic_data_generator_system_prompt,
            jsonalize_output=True,
        )

    def generate(self, payload: SyntheticDataGeneratorPayload | Mapping[str, Any] | str):
        if not isinstance(payload, SyntheticDataGeneratorPayload):
            payload = SyntheticDataGeneratorPayload.model_validate(payload)

        raw_output = self.invoke(
            payload.model_dump(),
            task_prompt=synthetic_data_generator_task_prompt,
        )
        validated_output = SyntheticSpreadsheetData.model_validate(raw_output)

        if len(validated_output.rows) != payload.row_count:
            raise ValueError(
                f"Expected {payload.row_count} rows, got {len(validated_output.rows)}."
            )

        if payload.columns:
            expected_headers = [col.strip() for col in payload.columns if col and col.strip()]
            if validated_output.headers != expected_headers:
                raise ValueError(
                    "Model output headers do not match user-provided columns."
                )

        return validated_output.model_dump()


def generate_synthetic_spreadsheet_data_with_llm(
    llm: Any,
    user_request: str,
    *,
    row_count: int = 20,
    columns: list[str] | None = None,
    constraints: str = "",
):
    generator = SyntheticDataGenerator(llm)
    payload = {
        "user_request": user_request,
        "row_count": row_count,
        "columns": columns,
        "constraints": constraints,
    }
    return generator.generate(payload)
