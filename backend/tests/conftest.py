"""
Shared fixtures for end-to-end integration tests.

These tests make REAL LLM calls (no mocking). Requires:
- backend/.env with a valid OPENAI_API_KEY
- All backend dependencies installed
"""

import os
import sys

import pytest

# Ensure backend/ is on sys.path and is the working directory (Hydra needs it)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="session")
def client():
    """A TestClient that runs the real FastAPI app (with real LLM calls)."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Reusable request payload fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_user_message():
    """A minimal valid messages string with one user turn."""
    return '[{"role": "user", "content": "What is VLOOKUP and when should I use it?"}]'


@pytest.fixture
def brainstorming_converged_messages():
    """A 5-turn brainstorming conversation ready for the done signal."""
    return str([
        {"role": "user", "content": "I want to practice VLOOKUP"},
        {"role": "assistant", "content": "Great choice! What domain or context interests you? For example, HR data, sales records, or inventory management?"},
        {"role": "user", "content": "HR data - looking up employee names from IDs"},
        {"role": "assistant", "content": "Perfect! And what difficulty level would you prefer?"},
        {"role": "user", "content": "Beginner. Yes let's start!"},
    ])


@pytest.fixture
def exercise_context_fixture():
    """A realistic exercise_context dict for exercise-mode chat tests."""
    return {
        "plan": {
            "exercise_type": "fill_formulas",
            "scenario": "Calculate employee bonuses based on performance ratings using VLOOKUP",
            "sheets": [
                {
                    "name": "Employees",
                    "columns": ["ID", "Name", "Department", "Rating", "Bonus"],
                    "prefilled": ["ID", "Name", "Department", "Rating"],
                    "student_fills": ["Bonus"],
                    "expected_formula_template": "=VLOOKUP(D2, Rates!A:B, 2, FALSE)",
                },
                {
                    "name": "Rates",
                    "columns": ["Rating", "Bonus Percentage"],
                    "prefilled": ["Rating", "Bonus Percentage"],
                    "student_fills": [],
                    "expected_formula_template": "",
                },
            ],
            "steps": [
                {"goal": "Use VLOOKUP to find the bonus percentage for each employee's rating", "hint": "Look up the Rating in the Rates sheet"},
            ],
            "row_count": 8,
            "difficulty": "beginner",
        },
        "sheet_snapshot": {},
    }


@pytest.fixture
def dict_topic_beginner():
    """A dict topic for a beginner SUM exercise."""
    return {
        "skill": "SUM",
        "domain": "retail sales",
        "goal": "calculate totals",
        "difficulty_hint": "beginner",
    }
