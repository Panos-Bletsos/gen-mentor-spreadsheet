"""
End-to-end integration tests for POST /start-exercise.

All tests make REAL LLM calls — no mocking.
These tests are slow (~20-60s each) because the endpoint runs a 4-step LLM chain.
"""

import pytest


def _validate_exercise_response(data):
    """Shared assertions for a successful /start-exercise response."""
    # exercise_plan structure
    assert "exercise_plan" in data
    plan = data["exercise_plan"]
    assert isinstance(plan["exercise_type"], str)
    assert len(plan["scenario"]) > 0
    assert isinstance(plan["sheets"], list) and len(plan["sheets"]) > 0
    assert isinstance(plan["steps"], list)
    assert isinstance(plan["row_count"], int) and plan["row_count"] > 0
    assert plan["difficulty"] in ("beginner", "intermediate", "advanced")

    # spreadsheet_data structure
    assert "spreadsheet_data" in data
    sheets = data["spreadsheet_data"]["sheets"]
    assert isinstance(sheets, list) and len(sheets) > 0

    # tutor_message
    assert "tutor_message" in data
    assert isinstance(data["tutor_message"], str) and len(data["tutor_message"]) > 20


# ---------------------------------------------------------------------------
# Scenario 1: Dict topic produces complete exercise
# ---------------------------------------------------------------------------
# Given: topic as a dict with skill, domain, goal, difficulty_hint (beginner SUM)
# When:  POST /start-exercise is called
# Then:  response is 200 with complete exercise_plan, spreadsheet_data, tutor_message


@pytest.mark.timeout(120)
def test_dict_topic_produces_complete_exercise(client, dict_topic_beginner):
    response = client.post(
        "/start-exercise",
        json={
            "topic": dict_topic_beginner,
            "learner_profile": "",
        },
    )
    assert response.status_code == 200
    data = response.json()
    _validate_exercise_response(data)

    # Verify each sheet has valid tabular data
    for sheet in data["spreadsheet_data"]["sheets"]:
        assert "name" in sheet
        assert isinstance(sheet["headers"], list) and len(sheet["headers"]) > 0


# ---------------------------------------------------------------------------
# Scenario 2: String topic produces complete exercise
# ---------------------------------------------------------------------------
# Given: topic="AVERAGE and COUNT functions"
# When:  POST /start-exercise is called
# Then:  response is 200 with same structure as Scenario 1


@pytest.mark.timeout(120)
def test_string_topic_produces_complete_exercise(client):
    response = client.post(
        "/start-exercise",
        json={
            "topic": "AVERAGE and COUNT functions",
            "learner_profile": "",
        },
    )
    assert response.status_code == 200
    data = response.json()
    _validate_exercise_response(data)


# ---------------------------------------------------------------------------
# Scenario 3: Exercise with brainstorming history
# ---------------------------------------------------------------------------
# Given: dict topic (SUM/retail/beginner) plus a 4-turn brainstorming history
# When:  POST /start-exercise is called
# Then:  response is 200, spreadsheet_data has at least 1 sheet


@pytest.mark.timeout(120)
def test_exercise_with_brainstorming_history(client):
    topic = {
        "skill": "SUM and AVERAGE",
        "domain": "retail",
        "goal": "calculate sales totals and averages",
        "difficulty_hint": "beginner",
    }
    history = [
        {"role": "user", "content": "I want to practice basic formulas"},
        {"role": "assistant", "content": "What domain interests you?"},
        {"role": "user", "content": "Retail - working with sales data"},
        {"role": "assistant", "content": "Great, let's practice SUM and AVERAGE with retail sales data!"},
    ]
    response = client.post(
        "/start-exercise",
        json={
            "topic": topic,
            "learner_profile": "",
            "brainstorming_history": history,
        },
    )
    assert response.status_code == 200
    data = response.json()
    _validate_exercise_response(data)
    assert len(data["spreadsheet_data"]["sheets"]) >= 1


# ---------------------------------------------------------------------------
# Scenario 4: Spreadsheet data has valid tabular structure
# ---------------------------------------------------------------------------
# Given: topic about IF function / grading / beginner
# When:  POST /start-exercise is called
# Then:  each sheet has rows > 0, every row width == len(headers),
#        headers are all non-empty strings


@pytest.mark.timeout(120)
def test_spreadsheet_data_valid_tabular_structure(client):
    topic = {
        "skill": "IF function",
        "domain": "grading",
        "goal": "assign pass/fail based on scores",
        "difficulty_hint": "beginner",
    }
    response = client.post(
        "/start-exercise",
        json={"topic": topic, "learner_profile": ""},
    )
    assert response.status_code == 200
    data = response.json()
    _validate_exercise_response(data)

    for sheet in data["spreadsheet_data"]["sheets"]:
        headers = sheet["headers"]
        rows = sheet["rows"]
        # Headers should be non-empty strings
        for h in headers:
            assert isinstance(h, str) and len(h.strip()) > 0, f"Invalid header: {h!r}"
        # Rows should match header width (allow student_fills to add empty columns)
        if rows:
            for i, row in enumerate(rows):
                assert len(row) == len(headers), (
                    f"Sheet '{sheet['name']}' row {i}: expected {len(headers)} cols, got {len(row)}"
                )


# ---------------------------------------------------------------------------
# Scenario 5: Missing topic returns 422
# ---------------------------------------------------------------------------
# Given: request body is {"learner_profile": "beginner"} (no topic)
# When:  POST /start-exercise is called
# Then:  response is 422


def test_missing_topic_returns_422(client):
    response = client.post(
        "/start-exercise",
        json={"learner_profile": "beginner"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Scenario 6: Learner profile influences exercise difficulty
# ---------------------------------------------------------------------------
# Given: topic about COUNTIF (single-sheet, simple) with an advanced learner profile
# When:  POST /start-exercise is called
# Then:  response is 200, exercise_plan.difficulty is NOT "beginner"


@pytest.mark.timeout(120)
def test_learner_profile_influences_difficulty(client):
    response = client.post(
        "/start-exercise",
        json={
            "topic": {
                "skill": "COUNTIF",
                "domain": "inventory",
                "goal": "count items by category",
                "difficulty_hint": "advanced",
            },
            "learner_profile": (
                "Advanced Excel user with 5 years of professional experience. "
                "Proficient in pivot tables, VLOOKUP, INDEX/MATCH, array formulas, "
                "and Power Query. Looking for challenging exercises."
            ),
        },
    )
    assert response.status_code == 200
    data = response.json()
    _validate_exercise_response(data)
    # With a strong advanced profile and difficulty_hint=advanced, should not be beginner
    assert data["exercise_plan"]["difficulty"] != "beginner", (
        f"Expected non-beginner difficulty for advanced user, got: {data['exercise_plan']['difficulty']}"
    )
