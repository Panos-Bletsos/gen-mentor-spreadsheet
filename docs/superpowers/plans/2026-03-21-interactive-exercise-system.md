# Interactive Exercise System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an interactive spreadsheet exercise system where an AI tutor generates tailored exercises, guides students through them, and updates learner profiles based on performance.

**Architecture:** A 4-step LLM chain (`/start-exercise`) generates exercises. The existing `/chat-with-tutor` endpoint is extended with `mode` and `exercise_context` fields to support brainstorming, exercise guidance, and completion flows. A postMessage bridge captures spreadsheet state from the Univer iframe. The frontend exercise page has three phases: brainstorming → loading → exercising.

**Tech Stack:** Python, FastAPI, LangChain, Streamlit, Univer.js (iframe), postMessage API

**Spec:** `docs/superpowers/specs/2026-03-21-interactive-exercise-system-design.md`

**Note:** This project has no test suite or linters configured. Steps follow the existing pattern of manual verification by running the backend/frontend servers.

---

## File Structure

### Backend — New files
- `backend/modules/exercise_generator/__init__.py` — Module exports
- `backend/modules/exercise_generator/agents/__init__.py` — Agent exports
- `backend/modules/exercise_generator/agents/exercise_planner.py` — Plan Exercise + Judge Quality + Opening Message chain
- `backend/modules/exercise_generator/prompts/__init__.py` — Prompt exports
- `backend/modules/exercise_generator/prompts/exercise_planner.py` — All prompt templates for the chain
- `backend/modules/exercise_generator/schemas.py` — Pydantic models for ExerciseTopic, ExercisePlan, StartExercisePayload

### Backend — Modified files
- `backend/api_schemas.py` — Add `StartExerciseRequest`, extend `ChatWithAutorRequest` with `mode` and `exercise_context`
- `backend/main.py` — Add `/start-exercise` endpoint, extend `/chat-with-tutor` to pass new fields
- `backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py` — Add brainstorming and exercise task prompts
- `backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py` — Add `mode` and `exercise_context` to `TutorChatPayload`, route by mode in `chat()`

### Frontend — Modified files
- `frontend/utils/state.py` — Add `exercise_phase`, `exercise_plan`, `exercise_topic` to PERSIST_KEYS and initialization
- `frontend/utils/request_api.py` — Add `start_exercise()` and `chat_with_tutor_exercise()` API wrappers, add API_NAMES entries
- `frontend/pages/exercise.py` — Full rewrite: three-phase state machine (brainstorming/loading/exercising), postMessage bridge, real API calls

---

## Task 1: Exercise Generator Schemas

**Files:**
- Create: `backend/modules/exercise_generator/__init__.py`
- Create: `backend/modules/exercise_generator/schemas.py`

- [ ] **Step 1: Create module directory and `__init__.py`**

```bash
mkdir -p backend/modules/exercise_generator/agents
mkdir -p backend/modules/exercise_generator/prompts
touch backend/modules/exercise_generator/agents/__init__.py
touch backend/modules/exercise_generator/prompts/__init__.py
```

- [ ] **Step 2: Create `schemas.py` with Pydantic models**

Create `backend/modules/exercise_generator/schemas.py`:

```python
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ExerciseTopic(BaseModel):
    """Enriched topic from brainstorming, or just a string wrapper."""
    skill: str
    domain: str = ""
    goal: str = ""
    difficulty_hint: str = ""


class SheetPlan(BaseModel):
    name: str
    columns: list[str]
    prefilled: list[str]
    student_fills: list[str] = []
    expected_formula_template: str = ""


class ExerciseStep(BaseModel):
    goal: str
    hint: str = ""


class ExercisePlan(BaseModel):
    exercise_type: str  # "fill_formulas" or "multi_step_analysis"
    scenario: str
    sheets: list[SheetPlan]
    steps: list[ExerciseStep] = []
    row_count: int = 10
    difficulty: str = "beginner"


class StartExercisePayload(BaseModel):
    topic: Any  # str or ExerciseTopic dict
    learner_profile: Any = ""
    brainstorming_history: list[dict] = []


class StartExerciseResult(BaseModel):
    exercise_plan: dict
    spreadsheet_data: dict
    tutor_message: str


class JudgeQualityResult(BaseModel):
    passed: bool
    reason: str = ""
```

- [ ] **Step 3: Create `__init__.py` exports**

Create `backend/modules/exercise_generator/__init__.py`:

```python
from modules.exercise_generator.agents.exercise_planner import (
    start_exercise_with_llm,
)
```

- [ ] **Step 4: Commit**

```bash
git add backend/modules/exercise_generator/
git commit --no-gpg-sign -m "feat: add exercise generator module scaffolding and schemas"
```

---

## Task 2: Exercise Generator Prompts

**Files:**
- Create: `backend/modules/exercise_generator/prompts/exercise_planner.py`
- Modify: `backend/modules/exercise_generator/prompts/__init__.py`

- [ ] **Step 1: Create prompt templates**

Create `backend/modules/exercise_generator/prompts/exercise_planner.py`:

```python
exercise_planner_system_prompt = """
You are the Exercise Planner agent in a spreadsheet learning system.
Your job is to design spreadsheet exercises tailored to a learner's profile and topic.

You must output valid JSON matching the schema exactly. No markdown, no code fences.
""".strip()

exercise_planner_task_prompt = """
Design a spreadsheet exercise for the following learner and topic.

Topic: {topic}

Learner Profile: {learner_profile}

Brainstorming Context (if any): {brainstorming_context}

Output a JSON object with this exact structure:
{{
    "exercise_type": "fill_formulas" or "multi_step_analysis",
    "scenario": "A realistic scenario description for the student",
    "sheets": [
        {{
            "name": "Sheet name",
            "columns": ["Col1", "Col2", ...],
            "prefilled": ["Col1", ...],
            "student_fills": ["Col2", ...],
            "expected_formula_template": "e.g. SUM(A{{row}}:C{{row}})"
        }}
    ],
    "steps": [
        {{"goal": "What student should do", "hint": "A helpful hint"}}
    ],
    "row_count": 6,
    "difficulty": "beginner"
}}

Rules:
- If the topic is a technical skill, pick a realistic domain scenario for it.
- If the topic is a domain skill, determine which spreadsheet functions are needed.
- For "fill_formulas" type: student_fills has the columns they fill with formulas.
- For "multi_step_analysis" type: include steps in order of progression.
- Match difficulty to the learner's level from their profile.
- Use "all" in prefilled if every column in a sheet is pre-populated.
- Keep row_count between 5 and 20.
""".strip()


judge_quality_system_prompt = """
You are a quality judge for spreadsheet exercise data.
You check whether generated data is appropriate for the given exercise plan.
Output valid JSON only. No markdown, no code fences.
""".strip()

judge_quality_task_prompt = """
Evaluate whether this generated spreadsheet data is appropriate for the exercise plan.

Exercise Plan:
{exercise_plan}

Generated Data:
{generated_data}

Check:
1. Does the data match the scenario described in the plan?
2. Is the data realistic and diverse?
3. Is the difficulty appropriate for a {difficulty} level exercise?
4. Are there enough rows ({expected_rows} expected)?
5. For multi-sheet exercises, is there referential integrity across sheets?

Output:
{{"passed": true/false, "reason": "explanation if failed"}}
""".strip()


opening_message_system_prompt = """
You are an AI tutor introducing a spreadsheet exercise to a student.
Write a warm, encouraging message that explains what the student needs to do.
Do not output JSON. Write naturally as a tutor would speak.
""".strip()

opening_message_task_prompt = """
Write the opening message for this exercise. The student will see this in a chat sidebar next to their spreadsheet.

Exercise Plan:
{exercise_plan}

Learner Profile:
{learner_profile}

Generated Data Summary:
- Sheets: {sheet_names}
- Columns per sheet: {columns_summary}

Write 2-4 paragraphs:
1. Set the scene (the scenario)
2. Explain what the student needs to do
3. Tell them where to start (which cell, which sheet)
4. Encourage them to ask for help if stuck

Keep it conversational, not formal. Address them as "you".
""".strip()
```

- [ ] **Step 2: Update prompts `__init__.py`**

```python
from modules.exercise_generator.prompts.exercise_planner import (
    exercise_planner_system_prompt,
    exercise_planner_task_prompt,
    judge_quality_system_prompt,
    judge_quality_task_prompt,
    opening_message_system_prompt,
    opening_message_task_prompt,
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/modules/exercise_generator/prompts/
git commit --no-gpg-sign -m "feat: add exercise generator prompt templates"
```

---

## Task 3: Exercise Generator Agent (Chain)

**Files:**
- Create: `backend/modules/exercise_generator/agents/exercise_planner.py`
- Modify: `backend/modules/exercise_generator/agents/__init__.py`

This is the core 4-step chain: Plan → Generate Data → Judge → Opening Message.

- [ ] **Step 1: Create the exercise planner agent**

Create `backend/modules/exercise_generator/agents/exercise_planner.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from base import BaseAgent
from modules.data_generator import generate_synthetic_spreadsheet_data_with_llm
from modules.exercise_generator.prompts.exercise_planner import (
    exercise_planner_system_prompt,
    exercise_planner_task_prompt,
    judge_quality_system_prompt,
    judge_quality_task_prompt,
    opening_message_system_prompt,
    opening_message_task_prompt,
)
from modules.exercise_generator.schemas import (
    ExercisePlan,
    ExerciseTopic,
    JudgeQualityResult,
    StartExercisePayload,
)

logger = logging.getLogger(__name__)

MAX_JUDGE_RETRIES = 2


def _topic_to_str(topic: Any) -> str:
    """Convert topic (str or dict/ExerciseTopic) to a descriptive string."""
    if isinstance(topic, str):
        return topic
    if isinstance(topic, dict):
        parts = []
        if topic.get("skill"):
            parts.append(f"Skill: {topic['skill']}")
        if topic.get("domain"):
            parts.append(f"Domain: {topic['domain']}")
        if topic.get("goal"):
            parts.append(f"Goal: {topic['goal']}")
        if topic.get("difficulty_hint"):
            parts.append(f"Suggested difficulty: {topic['difficulty_hint']}")
        return "; ".join(parts) if parts else str(topic)
    return str(topic)


def _build_data_request(plan: ExercisePlan, sheet_plan: dict, prev_sheets_data: list[dict], retry_reason: str = "") -> dict:
    """Build a data_generator payload from the exercise plan + one sheet."""
    columns = sheet_plan.get("prefilled", [])
    if columns == ["all"]:
        columns = sheet_plan.get("columns", [])

    context_parts = [
        f"Generate data for a spreadsheet exercise.",
        f"Scenario: {plan.scenario}",
        f"Sheet: {sheet_plan['name']}",
        f"This data is for teaching {plan.difficulty}-level spreadsheet skills.",
    ]
    if prev_sheets_data:
        context_parts.append(f"Related sheets already generated: {json.dumps([s['name'] for s in prev_sheets_data])}")
        context_parts.append("Ensure referential integrity with existing sheets.")
    if retry_reason:
        context_parts.append(f"Previous attempt was rejected: {retry_reason}. Fix this issue.")

    return {
        "user_request": " ".join(context_parts),
        "row_count": plan.row_count,
        "columns": columns if columns else None,
        "constraints": retry_reason,
    }


class ExercisePlanner(BaseAgent):
    name: str = "ExercisePlanner"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=exercise_planner_system_prompt,
            jsonalize_output=True,
        )


class QualityJudge(BaseAgent):
    name: str = "QualityJudge"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=judge_quality_system_prompt,
            jsonalize_output=True,
        )


class OpeningMessageGenerator(BaseAgent):
    name: str = "OpeningMessageGenerator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=opening_message_system_prompt,
            jsonalize_output=False,
        )


def start_exercise_with_llm(
    llm: Any,
    topic: Any,
    learner_profile: Any = "",
    brainstorming_history: list[dict] | None = None,
) -> dict:
    """Run the 4-step exercise generation chain.

    Returns dict with keys: exercise_plan, spreadsheet_data, tutor_message.
    """
    # --- Step 1: Plan Exercise ---
    planner = ExercisePlanner(llm)
    brainstorming_context = ""
    if brainstorming_history:
        brainstorming_context = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in brainstorming_history
        )

    plan_input = {
        "topic": _topic_to_str(topic),
        "learner_profile": str(learner_profile),
        "brainstorming_context": brainstorming_context,
    }
    plan_raw = planner.invoke(plan_input, task_prompt=exercise_planner_task_prompt)
    if isinstance(plan_raw, str):
        plan_raw = json.loads(plan_raw)
    exercise_plan = ExercisePlan.model_validate(plan_raw)

    # --- Step 2 & 3: Generate Data + Judge Quality (with retry loop) ---
    all_sheets_data = []
    judge = QualityJudge(llm)

    for sheet_plan in exercise_plan.sheets:
        sheet_dict = sheet_plan.model_dump() if hasattr(sheet_plan, "model_dump") else dict(sheet_plan)
        prefilled = sheet_dict.get("prefilled", [])
        # Skip sheets with no prefilled data
        if not prefilled:
            all_sheets_data.append({"name": sheet_dict["name"], "headers": sheet_dict.get("columns", []), "rows": []})
            continue

        retry_reason = ""
        sheet_data = None
        for attempt in range(1 + MAX_JUDGE_RETRIES):
            data_request = _build_data_request(exercise_plan, sheet_dict, all_sheets_data, retry_reason)
            sheet_data = generate_synthetic_spreadsheet_data_with_llm(
                llm,
                user_request=data_request["user_request"],
                row_count=data_request["row_count"],
                columns=data_request["columns"],
                constraints=data_request["constraints"],
            )

            # Judge quality
            judge_input = {
                "exercise_plan": json.dumps(plan_raw),
                "generated_data": json.dumps(sheet_data),
                "difficulty": exercise_plan.difficulty,
                "expected_rows": exercise_plan.row_count,
            }
            judge_raw = judge.invoke(judge_input, task_prompt=judge_quality_task_prompt)
            if isinstance(judge_raw, str):
                judge_raw = json.loads(judge_raw)
            judge_result = JudgeQualityResult.model_validate(judge_raw)

            if judge_result.passed:
                break
            retry_reason = judge_result.reason
            logger.warning(f"Quality judge rejected data (attempt {attempt + 1}): {retry_reason}")

        # Add student_fills columns as empty
        student_cols = sheet_dict.get("student_fills", [])
        if student_cols and sheet_data:
            for col in student_cols:
                if col not in sheet_data.get("headers", []):
                    sheet_data["headers"].append(col)
                    for row in sheet_data.get("rows", []):
                        row.append("")

        sheet_data["name"] = sheet_dict["name"]
        all_sheets_data.append(sheet_data)

    # Combine into single spreadsheet_data payload
    spreadsheet_data = {"sheets": all_sheets_data}

    # --- Step 4: Generate Opening Message ---
    msg_gen = OpeningMessageGenerator(llm)
    sheet_names = [s["name"] for s in all_sheets_data]
    columns_summary = "; ".join(
        f"{s['name']}: {s.get('headers', [])}" for s in all_sheets_data
    )
    msg_input = {
        "exercise_plan": json.dumps(plan_raw),
        "learner_profile": str(learner_profile),
        "sheet_names": str(sheet_names),
        "columns_summary": columns_summary,
    }
    tutor_message = msg_gen.invoke(msg_input, task_prompt=opening_message_task_prompt)

    return {
        "exercise_plan": exercise_plan.model_dump(),
        "spreadsheet_data": spreadsheet_data,
        "tutor_message": tutor_message,
    }
```

- [ ] **Step 2: Update agents `__init__.py`**

```python
from modules.exercise_generator.agents.exercise_planner import start_exercise_with_llm
```

- [ ] **Step 3: Commit**

```bash
git add backend/modules/exercise_generator/
git commit --no-gpg-sign -m "feat: implement exercise generator 4-step chain"
```

---

## Task 4: Extend Chat-With-Tutor (Brainstorming + Exercise Modes)

**Files:**
- Modify: `backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py`
- Modify: `backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py`

- [ ] **Step 1: Add brainstorming and exercise prompt templates**

Append to `backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py`:

```python
ai_tutor_brainstorming_task_prompt = """
You are the AI Tutor in brainstorming mode. Help the student decide what spreadsheet exercise to work on.

Learner Profile:
{learner_profile}

Conversation History:
{messages}

Your job:
1. Understand what the student wants to practice (a specific function, a domain skill, or general practice).
2. Ask clarifying questions: what domain/context interests them? What is their goal? What have they tried before?
3. Keep it conversational. One question at a time. Converge within 3-5 turns.
4. When you and the student have agreed on an exercise topic, append this JSON block at the END of your message (after your conversational text):

{{"brainstorming_done": true, "exercise_topic": {{"skill": "the spreadsheet skill(s)", "domain": "the domain/context", "goal": "what the exercise should achieve", "difficulty_hint": "beginner/intermediate/advanced"}}}}

Only include the JSON when you are confident the student is ready. Do not include it while still exploring.
Reply now based on the latest message.
""".strip()


ai_tutor_exercise_task_prompt = """
You are the AI Tutor guiding a student through a spreadsheet exercise.

Learner Profile:
{learner_profile}

Exercise Plan:
{exercise_plan}

Current Spreadsheet State:
{sheet_snapshot}

Relevant Context (documents, search, notes):
{external_resources}

Conversation History:
{messages}

Your job:
- Compare the student's spreadsheet state against the exercise plan's expected formulas/steps.
- Give progressive hints, not direct answers. Guide them to figure it out.
- If they completed a step correctly, confirm and prompt the next step.
- If they used a hardcoded value instead of a formula, point it out gently.
- If they ask "am I done?", check all steps/formulas against the plan.
- Be encouraging and specific about what they did well.

Reply now based on the latest message and current spreadsheet state.
""".strip()
```

- [ ] **Step 2: Extend `TutorChatPayload` and `AITutorChatbot.chat()` to route by mode**

In `backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py`, make these changes:

Add import at top:
```python
from modules.ai_chatbot_tutor.prompts.ai_chatbot_tutor import (
    ai_tutor_chatbot_system_prompt,
    ai_tutor_chatbot_task_prompt,
    ai_tutor_brainstorming_task_prompt,
    ai_tutor_exercise_task_prompt,
)
```

Extend `TutorChatPayload` — add two fields after `external_resources`:
```python
    mode: str = "general"  # "general", "brainstorming", or "exercise"
    exercise_context: Optional[dict] = None  # {"plan": {...}, "sheet_snapshot": {...}}
```

In `AITutorChatbot.chat()`, replace the `input_vars` and `raw_reply` lines (approximately lines 103-108) with mode-aware routing:

```python
        # Select task prompt based on mode
        mode = data.get("mode", "general")
        exercise_ctx = data.get("exercise_context") or {}

        if mode == "brainstorming":
            task_prompt = ai_tutor_brainstorming_task_prompt
            input_vars = {
                "learner_profile": data.get("learner_profile", ""),
                "messages": history_text,
            }
        elif mode == "exercise":
            task_prompt = ai_tutor_exercise_task_prompt
            input_vars = {
                "learner_profile": data.get("learner_profile", ""),
                "messages": history_text,
                "external_resources": external_context,
                "exercise_plan": json.dumps(exercise_ctx.get("plan", {})),
                "sheet_snapshot": json.dumps(exercise_ctx.get("sheet_snapshot", {})),
            }
        else:
            task_prompt = ai_tutor_chatbot_task_prompt
            input_vars = {
                "learner_profile": data.get("learner_profile", ""),
                "messages": history_text,
                "external_resources": external_context,
            }

        raw_reply = self.invoke(input_vars, task_prompt=task_prompt)
```

Add `import json` at the top of the file if not already present.

- [ ] **Step 3: Verify existing tutor behavior is unchanged**

Run the backend server and test the existing `/chat-with-tutor` endpoint without `mode` field — it should work identically to before.

```bash
cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 5000
```

Test with curl:
```bash
curl -X POST http://localhost:5000/chat-with-tutor \
  -H "Content-Type: application/json" \
  -d '{"messages": "[{\"role\": \"user\", \"content\": \"Hello\"}]", "learner_profile": ""}'
```

Expected: a normal tutor response (not brainstorming, not exercise).

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai_chatbot_tutor/
git commit --no-gpg-sign -m "feat: add brainstorming and exercise modes to AI tutor"
```

---

## Task 5: Backend API — `/start-exercise` Endpoint and Extended `/chat-with-tutor`

**Files:**
- Modify: `backend/api_schemas.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Add new request schemas to `api_schemas.py`**

Append to `backend/api_schemas.py`:

```python
class StartExerciseRequest(BaseRequest):
    topic: Any  # str or dict (ExerciseTopic)
    learner_profile: Any = ""
    brainstorming_history: list = []
```

Extend `ChatWithAutorRequest` — add two fields:
```python
class ChatWithAutorRequest(BaseRequest):
    messages: str
    learner_profile: str = ""
    mode: str = "general"
    exercise_context: Optional[dict] = None
```

Ensure `from typing import Optional, Any` is at the top of the file (add `Any` — it is currently missing).

- [ ] **Step 2: Add `/start-exercise` endpoint to `main.py`**

Add import at top of `main.py`:
```python
from modules.exercise_generator import start_exercise_with_llm
```

Add endpoint after the existing `/chat-with-tutor` endpoint:

```python
@app.post("/start-exercise")
async def start_exercise(request: StartExerciseRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        result = start_exercise_with_llm(
            llm,
            topic=request.topic,
            learner_profile=request.learner_profile,
            brainstorming_history=request.brainstorming_history,
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
```

- [ ] **Step 3: Extend `/chat-with-tutor` to pass `mode` and `exercise_context`**

In `main.py`, update the existing `chat_with_autor` function to pass the new fields through. Replace the `chat_with_tutor_with_llm` call:

```python
@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})
        response = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=search_rag_manager,
            use_search=True,
            mode=request.mode,
            exercise_context=request.exercise_context,
        )
        return {"response": response}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
```

Also update `chat_with_tutor_with_llm` in `ai_chatbot_tutor.py` to accept and pass `mode` and `exercise_context`:

```python
def chat_with_tutor_with_llm(
    llm, messages=None, learner_profile="", *,
    search_rag_manager=None, use_search=True, top_k=5,
    mode="general", exercise_context=None,
):
    agent = AITutorChatbot(llm, search_rag_manager=search_rag_manager)
    payload = {
        "learner_profile": learner_profile,
        "messages": messages,
        "use_search": use_search,
        "top_k": top_k,
        "mode": mode,
        "exercise_context": exercise_context,
    }
    return agent.chat(payload)
```

- [ ] **Step 4: Verify endpoints**

Start the backend and test:

```bash
# Test /start-exercise
curl -X POST http://localhost:5000/start-exercise \
  -H "Content-Type: application/json" \
  -d '{"topic": "SUM and AVERAGE", "learner_profile": "beginner student"}'

# Test /chat-with-tutor with brainstorming mode
curl -X POST http://localhost:5000/chat-with-tutor \
  -H "Content-Type: application/json" \
  -d '{"messages": "[{\"role\": \"user\", \"content\": \"I want to practice lookups\"}]", "learner_profile": "beginner", "mode": "brainstorming"}'
```

Expected: `/start-exercise` returns JSON with `exercise_plan`, `spreadsheet_data`, `tutor_message`. Brainstorming mode returns a tutor message that asks clarifying questions about the student's goal.

- [ ] **Step 5: Commit**

```bash
git add backend/api_schemas.py backend/main.py backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py
git commit --no-gpg-sign -m "feat: add /start-exercise endpoint and extend /chat-with-tutor with mode routing"
```

---

## Task 6: Frontend — Session State and API Wrappers

**Files:**
- Modify: `frontend/utils/state.py`
- Modify: `frontend/utils/request_api.py`

- [ ] **Step 1: Add exercise state keys to `state.py`**

Add to `PERSIST_KEYS` list (after `"exercise_messages"`):
```python
"exercise_phase",      # "brainstorming", "loading", "exercising", or None
"exercise_plan",       # dict from /start-exercise
"exercise_topic",      # dict (ExerciseTopic) from brainstorming
```

Add to `initialize_session_state()` defaults (in the initialization block alongside `exercise_messages`):
```python
if "exercise_phase" not in st.session_state:
    st.session_state["exercise_phase"] = None
if "exercise_plan" not in st.session_state:
    st.session_state["exercise_plan"] = None
if "exercise_topic" not in st.session_state:
    st.session_state["exercise_topic"] = None
```

- [ ] **Step 2: Add API wrappers to `request_api.py`**

Add to `API_NAMES` dict:
```python
"start_exercise": "start-exercise",
```

Add new functions:

```python
def start_exercise(topic, learner_profile="", brainstorming_history=None, llm_type=None):
    resolved_llm_type = llm_type or st.session_state.get("llm_type", "openai/gpt-4o")
    model_provider, model_name = parse_llm_settings(resolved_llm_type)
    data = {
        "topic": topic,
        "learner_profile": str(learner_profile),
        "brainstorming_history": brainstorming_history or [],
        "model_provider": model_provider,
        "model_name": model_name,
    }
    return make_post_request(API_NAMES["start_exercise"], data, timeout=120)


def chat_with_tutor_exercise(chat_messages, learner_profile, mode="general", exercise_context=None, llm_type=None):
    resolved_llm_type = llm_type or st.session_state.get("llm_type", "openai/gpt-4o")
    model_provider, model_name = parse_llm_settings(resolved_llm_type)
    data = {
        "messages": str(chat_messages),
        "learner_profile": str(learner_profile),
        "mode": mode,
        "exercise_context": exercise_context,
        "model_provider": model_provider,
        "model_name": model_name,
    }
    response = make_post_request(API_NAMES["chat_with_tutor"], data)
    return response.get("response") if response else None
```

- [ ] **Step 3: Commit**

```bash
git add frontend/utils/state.py frontend/utils/request_api.py
git commit --no-gpg-sign -m "feat: add exercise session state keys and API wrappers"
```

---

## Task 7: Frontend — Exercise Page Rewrite

**Files:**
- Modify: `frontend/pages/exercise.py`

This is the largest task. The page has three phases: brainstorming → loading → exercising.

- [ ] **Step 1: Rewrite exercise.py with three-phase state machine**

Replace the entire contents of `frontend/pages/exercise.py`:

```python
import json
import re
import time
import streamlit as st
import streamlit.components.v1 as components
from assets.js.univer_sheets import get_univer_sheets_html
from utils.sheet_data_parser import build_univer_workbook_from_payload
from utils.request_api import start_exercise, chat_with_tutor_exercise

st.markdown(
    "<style>" + open("./assets/css/main.css").read() + "</style>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_brainstorming_done(text):
    """Check if tutor response contains brainstorming_done JSON signal.
    Returns (display_text, exercise_topic_dict) or (text, None).
    Uses brace-counting to extract nested JSON with exercise_topic object.
    """
    marker = '"brainstorming_done"'
    idx = text.find(marker)
    if idx == -1:
        return text, None
    # Walk backwards to find the opening brace
    start = text.rfind("{", 0, idx)
    if start == -1:
        return text, None
    # Walk forward with brace counting to find the matching close
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        return text, None
    try:
        signal = json.loads(text[start:end])
        if signal.get("brainstorming_done"):
            display_text = text[:start].strip()
            return display_text, signal.get("exercise_topic", {})
    except json.JSONDecodeError:
        pass
    return text, None


def get_exercise_phase():
    """Determine current exercise phase from session state."""
    phase = st.session_state.get("exercise_phase")
    if phase:
        return phase
    # Check if topic was passed via query params (from learning path)
    params = st.query_params
    topic = params.get("topic")
    if topic:
        st.session_state["exercise_topic"] = topic
        return "loading"
    return "brainstorming"


# ---------------------------------------------------------------------------
# Phase: Brainstorming
# ---------------------------------------------------------------------------

def render_brainstorming():
    """On-demand mode: tutor brainstorms exercise topic with student."""
    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        st.header("Practice Mode")
        st.info("Chat with the AI tutor to decide what you'd like to practice. The spreadsheet will load once we've picked an exercise.")

    with right_col:
        st.subheader("AI Tutor")

        if not st.session_state["exercise_messages"]:
            st.session_state["exercise_messages"].append({
                "role": "assistant",
                "content": "Hi! What would you like to practice today? You can tell me a specific skill (like VLOOKUP or pivot tables) or a domain you're interested in (like sales analysis or financial modeling).",
            })

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Tell me what you want to practice..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            with st.spinner("Thinking..."):
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="brainstorming",
                )

            if reply:
                display_text, exercise_topic = parse_brainstorming_done(reply)
                st.session_state["exercise_messages"].append({"role": "assistant", "content": display_text})

                if exercise_topic:
                    st.session_state["exercise_topic"] = exercise_topic
                    st.session_state["exercise_phase"] = "loading"
                    st.rerun()
            else:
                st.session_state["exercise_messages"].append({
                    "role": "assistant",
                    "content": "I'm having trouble connecting right now. Could you try again?",
                })

            st.rerun()

        # Fallback button after 6+ student messages
        student_msg_count = sum(1 for m in st.session_state["exercise_messages"] if m["role"] == "user")
        if student_msg_count >= 6:
            if st.button("Ready to start the exercise"):
                st.session_state["exercise_messages"].append({
                    "role": "user",
                    "content": "Let's start the exercise based on what we discussed.",
                })
                with st.spinner("Finalizing exercise topic..."):
                    reply = chat_with_tutor_exercise(
                        st.session_state["exercise_messages"],
                        st.session_state.get("learner_profile", ""),
                        mode="brainstorming",
                    )
                if reply:
                    _, exercise_topic = parse_brainstorming_done(reply)
                    if exercise_topic:
                        st.session_state["exercise_topic"] = exercise_topic
                        st.session_state["exercise_phase"] = "loading"
                        st.rerun()


# ---------------------------------------------------------------------------
# Phase: Loading
# ---------------------------------------------------------------------------

def render_loading():
    """Generate exercise from topic."""
    st.header("Generating your exercise...")
    with st.spinner("The AI is creating a personalized exercise for you. This may take 20-40 seconds..."):
        topic = st.session_state.get("exercise_topic") or "general spreadsheet practice"
        result = start_exercise(
            topic=topic,
            learner_profile=st.session_state.get("learner_profile", ""),
            brainstorming_history=st.session_state.get("exercise_messages", []),
        )

    if result and "exercise_plan" in result:
        st.session_state["exercise_plan"] = result
        # Add tutor's opening message to chat
        st.session_state["exercise_messages"].append({
            "role": "assistant",
            "content": result["tutor_message"],
        })
        st.session_state["exercise_phase"] = "exercising"
        st.rerun()
    else:
        st.error("Could not generate exercise. Please try again.")
        if st.button("Go back to brainstorming"):
            st.session_state["exercise_phase"] = "brainstorming"
            st.rerun()


# ---------------------------------------------------------------------------
# Phase: Exercising
# ---------------------------------------------------------------------------

def render_exercising():
    """Main exercise view: spreadsheet + tutor chat with snapshot awareness."""
    result = st.session_state.get("exercise_plan", {})
    plan = result.get("exercise_plan", {})
    spreadsheet_data = result.get("spreadsheet_data", {})

    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        title = plan.get("scenario", "Exercise")[:80]
        st.header(title)

        # Build workbook — load first sheet for now (multi-sheet support is a follow-up)
        # TODO: extend build_univer_workbook_from_payload to accept multiple sheets
        # For now, multi-sheet exercises (e.g., VLOOKUP with lookup table) only show the first sheet.
        # The second sheet data is still passed to the tutor via exercise_context.
        sheets = spreadsheet_data.get("sheets", [])
        if sheets:
            first_sheet = sheets[0]
            payload = {"headers": first_sheet.get("headers", []), "rows": first_sheet.get("rows", [])}
            workbook = build_univer_workbook_from_payload(
                payload,
                sheet_name=first_sheet.get("name", "Sheet1"),
                workbook_name="Exercise",
            )
            workbook_json = json.dumps(workbook)
            univer_html = get_univer_sheets_html(height="100%", workbook_data=workbook_json)
            nonce = str(time.time())
            univer_html += f"<!-- nonce:{nonce} -->"
            components.html(univer_html, height=600, scrolling=False)
        else:
            st.warning("No spreadsheet data available.")

    with right_col:
        st.subheader("AI Tutor")

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Ask about this exercise..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            exercise_context = {
                "plan": plan,
                "sheet_snapshot": {},  # TODO: populate from postMessage bridge
            }

            with st.spinner("Thinking..."):
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )

            if reply:
                st.session_state["exercise_messages"].append({"role": "assistant", "content": reply})
            else:
                st.session_state["exercise_messages"].append({
                    "role": "assistant",
                    "content": "I'm having trouble connecting. Please try again.",
                })

            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_exercise():
    phase = get_exercise_phase()

    if phase == "loading":
        render_loading()
    elif phase == "exercising":
        render_exercising()
    else:
        render_brainstorming()


render_exercise()
```

- [ ] **Step 2: Verify by running the frontend**

```bash
cd frontend && source .venv/bin/activate && streamlit run main.py --server.port 8501
```

Navigate to the Exercise page. Verify:
1. Brainstorming phase loads with tutor greeting
2. Chat input works (will need backend running for real responses; without backend, should show error gracefully)
3. Page layout is two columns

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/exercise.py
git commit --no-gpg-sign -m "feat: rewrite exercise page with three-phase state machine"
```

---

## Task 8: PostMessage Bridge (Spreadsheet Snapshot)

**Files:**
- Modify: `frontend/pages/exercise.py` (exercising phase)
- Modify: `frontend/assets/js/univer_sheets.py` (inject listener into Univer HTML)

This task adds the ability to capture spreadsheet cell data and send it to the tutor.

- [ ] **Step 1: Inject a postMessage listener into the Univer HTML**

In `frontend/assets/js/univer_sheets.py`, the `get_univer_sheets_html()` function builds HTML from template files. We need to inject a JS snippet that listens for `get_sheet_data` messages and responds with cell data.

Add a helper function to `univer_sheets.py`:

```python
SHEET_DATA_LISTENER_JS = """
<script>
window.addEventListener('message', function(event) {
    if (event.data === 'get_sheet_data') {
        try {
            // Access Univer's workbook data
            var app = document.getElementById('app');
            if (!app || !window.__univerInstance) {
                window.parent.postMessage({type: 'sheet_data', data: null}, '*');
                return;
            }
            var univerAPI = window.__univerInstance;
            var workbook = univerAPI.getActiveWorkbook();
            if (!workbook) {
                window.parent.postMessage({type: 'sheet_data', data: null}, '*');
                return;
            }
            var snapshot = workbook.save();
            window.parent.postMessage({type: 'sheet_data', data: JSON.stringify(snapshot)}, '*');
        } catch(e) {
            window.parent.postMessage({type: 'sheet_data', data: null, error: e.message}, '*');
        }
    }
});
</script>
"""
```

Inject it in `get_univer_sheets_html()` by appending before `</body>`:
```python
html = html.replace("</body>", SHEET_DATA_LISTENER_JS + "</body>")
```

**Note:** The exact Univer API for `save()` or accessing cell data may need adjustment based on the Univer.js version in `frontend/assets/univer/univer.js`. Check the existing JS file for the API surface (e.g., `univerAPI`, `workbook.save()`, `getSheetData()`). The implementation should capture all cell values and formulas.

- [ ] **Step 2: Add snapshot capture to the exercise page**

In the `render_exercising()` function in `exercise.py`, before the chat input handler, add a hidden component that requests and captures sheet data:

```python
# Hidden component to capture sheet snapshot via postMessage
SNAPSHOT_BRIDGE_HTML = """
<script>
(function() {
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'sheet_data') {
            // Store in a global so we can read it
            window.__lastSheetSnapshot = event.data.data;
        }
    });
    // Request sheet data from Univer iframe
    var iframes = window.parent.document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        iframes[i].contentWindow.postMessage('get_sheet_data', '*');
    }
})();
</script>
"""
```

**Known limitation:** Getting data from JS back into Streamlit's Python session state is non-trivial. This task establishes the JS-side infrastructure (listeners, postMessage protocol). The Python-side capture (writing to `session_state["sheet_snapshot"]`) will require iterative refinement during integration testing — it may need `streamlit_js_eval` (add to requirements.txt) or a custom Streamlit component. The `sheet_snapshot` in exercise_context starts as `{}` and is populated once the bridge is working end-to-end. The exercise system works without it (tutor guides based on conversation alone) — the bridge adds spreadsheet awareness as an enhancement.

- [ ] **Step 3: Commit**

```bash
git add frontend/assets/js/univer_sheets.py frontend/pages/exercise.py
git commit --no-gpg-sign -m "feat: add postMessage bridge for spreadsheet snapshot capture"
```

---

## Task 9: Exercise Completion Flow

**Files:**
- Modify: `frontend/pages/exercise.py`

- [ ] **Step 1: Add a "Finish Exercise" button to the exercising phase**

In `render_exercising()`, after the chat input block, add:

```python
        st.divider()
        if st.button("Finish Exercise", type="primary"):
            # Request performance summary from tutor
            st.session_state["exercise_messages"].append({
                "role": "user",
                "content": "[SYSTEM] The student has finished the exercise. Please summarize their performance: what they did well, what they struggled with, and what to practice next.",
            })
            with st.spinner("Generating feedback..."):
                exercise_context = {
                    "plan": plan,
                    "sheet_snapshot": {},  # TODO: from postMessage bridge
                }
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )

            if reply:
                st.session_state["exercise_messages"].append({"role": "assistant", "content": reply})

            # Generate performance summary and update learner profile
            with st.spinner("Updating your learner profile..."):
                perf_reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"] + [
                        {"role": "user", "content": "[SYSTEM] Output a JSON performance summary: {\"skills_practiced\": [...], \"completed_steps\": N, \"total_steps\": N, \"struggled_with\": [...], \"hints_requested\": N}"}
                    ],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )
                if perf_reply:
                    try:
                        perf_data = json.loads(perf_reply)
                    except json.JSONDecodeError:
                        perf_data = {}
                    if perf_data:
                        from utils.request_api import update_learner_profile
                        session_info = {
                            "type": "exercise",
                            "topic": str(st.session_state.get("exercise_topic", "")),
                            "scenario": plan.get("scenario", ""),
                            "performance": perf_data,
                        }
                        update_learner_profile(
                            st.session_state.get("learner_profile", ""),
                            str(st.session_state.get("exercise_messages", [])),
                            session_information=str(session_info),
                        )

            st.session_state["exercise_phase"] = "completed"
            st.rerun()
```

- [ ] **Step 2: Add a completed phase render**

Add after `render_exercising()`:

```python
def render_completed():
    """Show completion state with feedback and option to start new exercise."""
    st.header("Exercise Complete!")

    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state["exercise_messages"]:
            st.chat_message(msg["role"]).write(msg["content"])

    if st.button("Start a New Exercise"):
        st.session_state["exercise_phase"] = "brainstorming"
        st.session_state["exercise_messages"] = []
        st.session_state["exercise_plan"] = None
        st.session_state["exercise_topic"] = None
        st.rerun()
```

Update `render_exercise()` to include the completed phase:

```python
def render_exercise():
    phase = get_exercise_phase()
    if phase == "loading":
        render_loading()
    elif phase == "exercising":
        render_exercising()
    elif phase == "completed":
        render_completed()
    else:
        render_brainstorming()
```

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/exercise.py
git commit --no-gpg-sign -m "feat: add exercise completion flow with tutor feedback"
```

---

## Task 10: Integration Test — Full End-to-End Flow

- [ ] **Step 1: Start backend and frontend**

```bash
# Terminal 1:
cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 5000

# Terminal 2:
cd frontend && source .venv/bin/activate && streamlit run main.py --server.port 8501
```

- [ ] **Step 2: Test the brainstorming flow**

1. Navigate to Exercise page
2. Type "I want to practice VLOOKUP"
3. Verify tutor asks clarifying questions (domain, goal)
4. Answer questions until tutor signals done
5. Verify page transitions to loading → exercising

- [ ] **Step 3: Test the exercising flow**

1. Verify spreadsheet loads with generated data
2. Type a question in chat
3. Verify tutor responds with exercise-aware guidance
4. Click "Finish Exercise"
5. Verify tutor gives performance summary

- [ ] **Step 4: Test error handling**

1. Stop the backend, try brainstorming → verify graceful error
2. Test with malformed topic → verify 500 is handled

---

## Verification Checklist

- [ ] Backend: `/start-exercise` returns `{exercise_plan, spreadsheet_data, tutor_message}` for both string and ExerciseTopic inputs
- [ ] Backend: `/chat-with-tutor` with `mode: "brainstorming"` produces clarifying questions and eventually emits `brainstorming_done` JSON
- [ ] Backend: `/chat-with-tutor` with `mode: "exercise"` responds with exercise-aware guidance
- [ ] Backend: `/chat-with-tutor` without `mode` (or `mode: "general"`) behaves identically to before
- [ ] Frontend: Exercise page starts in brainstorming phase
- [ ] Frontend: Brainstorming transitions to loading when done signal received
- [ ] Frontend: Loading calls `/start-exercise` and transitions to exercising
- [ ] Frontend: Exercising shows spreadsheet + chat with tutor
- [ ] Frontend: "Finish Exercise" generates feedback and shows completion state
- [ ] Frontend: "Start a New Exercise" resets state correctly
- [ ] Frontend: Navigating from Learning Path with `?topic=X` query param skips brainstorming and goes to loading
- [ ] Backend: Exercise completion updates learner profile via `/update-learner-profile`
