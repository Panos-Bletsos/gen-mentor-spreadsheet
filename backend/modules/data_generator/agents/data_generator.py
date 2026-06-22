from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator

from base import BaseStructuredAgent

logger = logging.getLogger(__name__)
from modules.data_generator.prompts.data_generator import (
    synthetic_data_generator_system_prompt,
    synthetic_data_generator_task_prompt,
)

_A1_PATTERN = re.compile(r'^[A-Z]+[1-9][0-9]*$', re.IGNORECASE)


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
    cells: dict[str, Any]

    @field_validator("cells")
    @classmethod
    def validate_cells(cls, v: dict) -> dict:
        """Accept only plain A1 keys and scalar values."""
        for key in v:
            if not _A1_PATTERN.match(key):
                raise ValueError(f"Invalid A1 key: {key!r}")
        return v


class SyntheticDataGenerator(BaseStructuredAgent):
    output_schema = SyntheticSpreadsheetData

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=synthetic_data_generator_system_prompt)

    def generate(self, payload: SyntheticDataGeneratorPayload | Mapping[str, Any] | str):
        if not isinstance(payload, SyntheticDataGeneratorPayload):
            payload = SyntheticDataGeneratorPayload.model_validate(payload)

        logger.info("DATAGEN  generating %d rows, columns=%s", payload.row_count, payload.columns)

        validated_output = self.invoke(
            payload.model_dump(),
            task_prompt=synthetic_data_generator_task_prompt,
        )

        logger.info("DATAGEN  validation passed (%d cells)", len(validated_output.cells))
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


def generate_with_tracing(
    llm: Any,
    user_request: str,
    *,
    row_count: int = 20,
    columns: list[str] | None = None,
    constraints: str = "",
    recorder: Any = None,
) -> dict:
    """Like generate_synthetic_spreadsheet_data_with_llm but populates a SpanRecorder
    with the raw AIMessage (including token usage) via include_raw=True."""
    payload = SyntheticDataGeneratorPayload.model_validate({
        "user_request": user_request,
        "row_count": row_count,
        "columns": columns,
        "constraints": constraints,
    })
    generator = SyntheticDataGenerator(llm)
    logger.info("DATAGEN  generating %d rows, columns=%s (traced)", payload.row_count, payload.columns)

    messages = generator._build_messages(payload.model_dump(), task_prompt=synthetic_data_generator_task_prompt)
    if recorder is not None:
        recorder.set_input(messages)

    structured = generator._model.with_structured_output(SyntheticSpreadsheetData, include_raw=True)
    raw_result = structured.invoke(messages)
    ai_message = raw_result["raw"]
    validated_output: SyntheticSpreadsheetData = raw_result["parsed"]

    if recorder is not None:
        recorder.set_response(ai_message)

    logger.info("DATAGEN  validation passed (%d cells)", len(validated_output.cells))
    result = validated_output.model_dump()
    if recorder is not None:
        recorder.set_parsed(validated_output)
    return result
