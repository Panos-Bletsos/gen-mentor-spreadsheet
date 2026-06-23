"""
End-to-end integration tests for POST /generate-synthetic-sheet-data.

All tests make REAL LLM calls — no mocking.
Response contract: {"cells": {"A1": value, "B2": value, ...}}
"""

import pytest


# ---------------------------------------------------------------------------
# Scenario 1: Generate data with defaults
# ---------------------------------------------------------------------------
# Given: user_request="Monthly sales data for a small electronics store"
#        (defaults: row_count=20, columns=None, constraints="")
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200, body has a non-empty "cells" dict with A1-keyed values

@pytest.mark.timeout(60)
def test_generate_data_with_defaults(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={"user_request": "Monthly sales data for a small electronics store"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "cells" in data
    cells = data["cells"]
    assert isinstance(cells, dict) and len(cells) > 0
    # All keys must be A1-style addresses
    import re
    a1_pattern = re.compile(r'^[A-Z]+[1-9][0-9]*$')
    for key in cells:
        assert a1_pattern.match(key), f"Expected A1 key, got: {key!r}"


# ---------------------------------------------------------------------------
# Scenario 2: Explicit columns are respected
# ---------------------------------------------------------------------------
# Given: user_request="Employee directory",
#        columns=["Name", "Department", "Salary", "Start Date"], row_count=5
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200; row-1 cells match the requested column names in order;
#        data rows cover rows 2-6 (row_count=5 data rows)

@pytest.mark.timeout(60)
def test_explicit_columns_respected(client):
    expected_columns = ["Name", "Department", "Salary", "Start Date"]
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={
            "user_request": "Employee directory",
            "columns": expected_columns,
            "row_count": 5,
        },
    )
    assert response.status_code == 200
    cells = response.json()["cells"]
    # Header row values should match expected columns in order
    header_values = [cells.get(f"{chr(65+i)}1") for i in range(len(expected_columns))]
    assert header_values == expected_columns


# ---------------------------------------------------------------------------
# Scenario 3: Row count is respected
# ---------------------------------------------------------------------------
# Given: user_request="Product inventory", row_count=10
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200; data rows go up to row 11 (1 header + 10 data rows)

@pytest.mark.timeout(60)
def test_row_count_respected(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={
            "user_request": "Product inventory for a hardware store",
            "row_count": 10,
        },
    )
    assert response.status_code == 200
    cells = response.json()["cells"]
    # Extract max row number from cell keys
    import re
    max_row = max(
        int(re.match(r'^[A-Z]+([0-9]+)$', k).group(1))
        for k in cells
        if re.match(r'^[A-Z]+([0-9]+)$', k)
    )
    # 1 header row + 10 data rows = row 11 max
    assert max_row == 11


# ---------------------------------------------------------------------------
# Scenario 4: Constraints guide the data — numeric values preserved
# ---------------------------------------------------------------------------
# Given: user_request="Student grades", columns=["Name", "Score"],
#        row_count=5, constraints="All scores must be between 0 and 100"
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200; Score column values (B2:B6) are numbers in [0, 100]

@pytest.mark.timeout(60)
def test_constraints_guide_data(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={
            "user_request": "Student exam grades",
            "columns": ["Name", "Score"],
            "row_count": 5,
            "constraints": "All scores must be integers between 0 and 100",
        },
    )
    assert response.status_code == 200
    cells = response.json()["cells"]
    assert cells.get("A1") == "Name"
    assert cells.get("B1") == "Score"
    for row in range(2, 7):
        score = cells.get(f"B{row}")
        assert isinstance(score, (int, float)), f"B{row} should be numeric, got {type(score)}: {score}"
        assert 0 <= score <= 100, f"Score {score} out of range [0, 100]"


# ---------------------------------------------------------------------------
# Scenario 5: Missing user_request returns 422
# ---------------------------------------------------------------------------

def test_missing_user_request_returns_422(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={"row_count": 10},
    )
    assert response.status_code == 422
