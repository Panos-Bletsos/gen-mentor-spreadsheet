"""
End-to-end integration tests for POST /generate-synthetic-sheet-data.

All tests make REAL LLM calls — no mocking.
"""

import pytest


# ---------------------------------------------------------------------------
# Scenario 1: Generate data with defaults
# ---------------------------------------------------------------------------
# Given: user_request="Monthly sales data for a small electronics store"
#        (defaults: row_count=20, columns=None, constraints="")
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200, body has headers (non-empty list) and rows
#        (list of lists, each row width == len(headers))


@pytest.mark.timeout(60)
def test_generate_data_with_defaults(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={"user_request": "Monthly sales data for a small electronics store"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "headers" in data
    assert isinstance(data["headers"], list) and len(data["headers"]) > 0
    assert "rows" in data
    assert isinstance(data["rows"], list)
    for row in data["rows"]:
        assert len(row) == len(data["headers"])


# ---------------------------------------------------------------------------
# Scenario 2: Explicit columns are respected
# ---------------------------------------------------------------------------
# Given: user_request="Employee directory",
#        columns=["Name", "Department", "Salary", "Start Date"], row_count=5
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200, headers match exactly, len(rows) == 5


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
    data = response.json()
    assert data["headers"] == expected_columns
    assert len(data["rows"]) == 5


# ---------------------------------------------------------------------------
# Scenario 3: Row count is respected
# ---------------------------------------------------------------------------
# Given: user_request="Product inventory", row_count=10
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200, len(rows) == 10


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
    data = response.json()
    assert len(data["rows"]) == 10


# ---------------------------------------------------------------------------
# Scenario 4: Constraints guide the data
# ---------------------------------------------------------------------------
# Given: user_request="Student grades", columns=["Name", "Score"],
#        row_count=5, constraints="All scores must be between 0 and 100"
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 200, every Score value is a number between 0 and 100


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
    data = response.json()
    assert data["headers"] == ["Name", "Score"]
    assert len(data["rows"]) == 5
    for row in data["rows"]:
        score = row[1]
        # Score might be int or float from LLM
        assert isinstance(score, (int, float)), f"Score should be numeric, got {type(score)}: {score}"
        assert 0 <= score <= 100, f"Score {score} out of range [0, 100]"


# ---------------------------------------------------------------------------
# Scenario 5: Missing user_request returns 422
# ---------------------------------------------------------------------------
# Given: request body is {"row_count": 10} (no user_request)
# When:  POST /generate-synthetic-sheet-data is called
# Then:  response is 422


def test_missing_user_request_returns_422(client):
    response = client.post(
        "/generate-synthetic-sheet-data",
        json={"row_count": 10},
    )
    assert response.status_code == 422
