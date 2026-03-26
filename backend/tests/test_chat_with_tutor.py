"""
End-to-end integration tests for POST /chat-with-tutor.

All tests make REAL LLM calls — no mocking.
"""

import pytest


# ---------------------------------------------------------------------------
# Scenario 1: General mode returns a helpful response
# ---------------------------------------------------------------------------
# Given: a valid messages JSON array with a single user question about VLOOKUP,
#        empty learner profile, mode "general"
# When:  POST /chat-with-tutor is called
# Then:  response is 200, body has key "response", value is a non-empty string


def test_general_mode_returns_helpful_response(client, single_user_message):
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": single_user_message,
            "learner_profile": "",
            "mode": "general",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 20  # Non-trivial reply


# ---------------------------------------------------------------------------
# Scenario 2: Brainstorming mode asks clarifying questions (early turn)
# ---------------------------------------------------------------------------
# Given: messages with a single user turn "I want to practice spreadsheet formulas",
#        mode "brainstorming"
# When:  POST /chat-with-tutor is called
# Then:  response is 200, response text is non-empty, and does NOT contain
#        "brainstorming_done" (too early — only 1 turn)


def test_brainstorming_early_asks_questions(client):
    messages = str([{"role": "user", "content": "I want to practice spreadsheet formulas"}])
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": messages,
            "learner_profile": "",
            "mode": "brainstorming",
        },
    )
    assert response.status_code == 200
    reply = response.json()["response"]
    assert len(reply) > 10
    # Should NOT produce the done signal on the very first turn
    assert "brainstorming_done" not in reply


# ---------------------------------------------------------------------------
# Scenario 3: Brainstorming produces done signal after enough context
# ---------------------------------------------------------------------------
# Given: messages with a full 5-turn conversation where user provides
#        skill=VLOOKUP, domain=HR, difficulty=beginner, and confirms readiness
# When:  POST /chat-with-tutor is called with mode "brainstorming"
# Then:  response is 200, response text contains "brainstorming_done" and
#        "exercise_topic" JSON block


def test_brainstorming_produces_done_signal(client, brainstorming_converged_messages):
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": brainstorming_converged_messages,
            "learner_profile": "",
            "mode": "brainstorming",
        },
    )
    assert response.status_code == 200
    reply = response.json()["response"]
    assert len(reply) > 0
    assert "brainstorming_done" in reply
    assert "exercise_topic" in reply


# ---------------------------------------------------------------------------
# Scenario 4: Exercise mode references the exercise plan
# ---------------------------------------------------------------------------
# Given: messages with "Where should I start?", mode "exercise", and an
#        exercise_context containing a VLOOKUP/bonus plan
# When:  POST /chat-with-tutor is called
# Then:  response is 200, response text is non-empty and references aspects
#        of the exercise


def test_exercise_mode_references_plan(client, exercise_context_fixture):
    messages = str([{"role": "user", "content": "Where should I start?"}])
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": messages,
            "learner_profile": "",
            "mode": "exercise",
            "exercise_context": exercise_context_fixture,
        },
    )
    assert response.status_code == 200
    reply = response.json()["response"]
    assert len(reply) > 20
    # The tutor should reference something from the exercise context
    reply_lower = reply.lower()
    context_keywords = ["vlookup", "bonus", "rating", "employee", "lookup", "formula", "rates"]
    assert any(kw in reply_lower for kw in context_keywords), (
        f"Expected tutor to reference exercise context. Got: {reply[:200]}"
    )


# ---------------------------------------------------------------------------
# Scenario 5: Invalid messages format returns 400
# ---------------------------------------------------------------------------
# Given: messages field is "hello" (not a JSON array)
# When:  POST /chat-with-tutor is called
# Then:  response is 400 with detail about JSON array format


def test_invalid_messages_not_json_array(client):
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": "hello",
            "learner_profile": "",
            "mode": "general",
        },
    )
    assert response.status_code == 400
    assert "JSON array" in response.json().get("detail", "")


# ---------------------------------------------------------------------------
# Scenario 6: Malformed JSON array returns 500
# ---------------------------------------------------------------------------
# Given: messages field is "[{broken" (starts with [ but ast.literal_eval fails)
# When:  POST /chat-with-tutor is called
# Then:  response is 500


def test_malformed_json_array_returns_500(client):
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": "[{broken",
            "learner_profile": "",
            "mode": "general",
        },
    )
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Scenario 7: Missing messages field returns 422
# ---------------------------------------------------------------------------
# Given: request body has learner_profile but no messages
# When:  POST /chat-with-tutor is called
# Then:  response is 422


def test_missing_messages_returns_422(client):
    response = client.post(
        "/chat-with-tutor",
        json={"learner_profile": "beginner"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Scenario 8: Multi-turn conversation maintains coherence
# ---------------------------------------------------------------------------
# Given: messages with 3 turns — user asks about SUM, assistant explains,
#        user asks follow-up about SUMIF
# When:  POST /chat-with-tutor is called
# Then:  response is 200, response text references SUMIF or conditional summing


def test_multi_turn_coherence(client):
    messages = str([
        {"role": "user", "content": "Can you explain the SUM function in spreadsheets?"},
        {"role": "assistant", "content": "SUM adds up a range of numbers. For example, =SUM(A1:A10) adds all values from A1 to A10."},
        {"role": "user", "content": "What if I only want to sum values that meet a condition? Like summing sales for a specific product?"},
    ])
    response = client.post(
        "/chat-with-tutor",
        json={
            "messages": messages,
            "learner_profile": "",
            "mode": "general",
        },
    )
    assert response.status_code == 200
    reply = response.json()["response"]
    assert len(reply) > 20
    reply_lower = reply.lower()
    # Should reference conditional summing concepts
    conditional_keywords = ["sumif", "sumifs", "condition", "criteria", "conditional"]
    assert any(kw in reply_lower for kw in conditional_keywords), (
        f"Expected reference to conditional summing. Got: {reply[:200]}"
    )
