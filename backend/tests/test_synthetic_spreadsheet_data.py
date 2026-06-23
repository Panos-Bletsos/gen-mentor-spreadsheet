"""
Unit tests for SyntheticSpreadsheetData — the structured-output schema of the
SyntheticDataGenerator. These tests make NO LLM calls; they exercise the
list-of-cells wire format and its reduction to the A1 cell-map that the rest of
the system consumes.
"""

import pytest
from modules.data_generator.agents.data_generator import SyntheticSpreadsheetData


def test_to_cell_map_reduces_list_to_a1_dict():
    data = SyntheticSpreadsheetData(
        cells=[
            {"addr": "A1", "value": "Pipeline"},
            {"addr": "B1", "value": "GB Processed"},
            {"addr": "B2", "value": 42},
        ]
    )
    assert data.to_cell_map() == {
        "A1": "Pipeline",
        "B1": "GB Processed",
        "B2": 42,
    }


def test_to_cell_map_uppercases_addresses():
    data = SyntheticSpreadsheetData(
        cells=[{"addr": "a1", "value": "Header"}, {"addr": "b2", "value": 99}]
    )
    result = data.to_cell_map()
    assert "A1" in result and "B2" in result
    assert "a1" not in result and "b2" not in result


def test_to_cell_map_last_entry_wins_on_duplicate_address():
    data = SyntheticSpreadsheetData(
        cells=[
            {"addr": "A1", "value": "first"},
            {"addr": "A1", "value": "second"},
        ]
    )
    assert data.to_cell_map() == {"A1": "second"}


def test_to_cell_map_raises_on_invalid_a1_address():
    data = SyntheticSpreadsheetData(cells=[{"addr": "not-a-cell", "value": "x"}])
    with pytest.raises(ValueError, match="Invalid A1"):
        data.to_cell_map()


def test_to_cell_map_raises_on_empty_result():
    data = SyntheticSpreadsheetData(cells=[])
    with pytest.raises(ValueError, match="empty"):
        data.to_cell_map()


def test_to_cell_map_preserves_numeric_and_bool_types():
    data = SyntheticSpreadsheetData(
        cells=[
            {"addr": "A1", "value": 42},
            {"addr": "B1", "value": 3.14},
            {"addr": "C1", "value": True},
            {"addr": "D1", "value": None},
            {"addr": "E1", "value": "text"},
        ]
    )
    result = data.to_cell_map()
    assert isinstance(result["A1"], int)
    assert isinstance(result["B1"], float)
    assert result["C1"] is True
    assert result["D1"] is None
    assert result["E1"] == "text"
