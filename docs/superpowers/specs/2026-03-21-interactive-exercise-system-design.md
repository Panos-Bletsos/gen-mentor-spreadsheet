# Interactive Exercise System — Design Spec

## Overview

Add a "learn by doing" exercise system to GenMentor where students practice spreadsheet skills in an interactive Univer.js spreadsheet, guided by an AI tutor that can see their work. The system generates exercises tailored to the learner's profile and adapts to both technical skills ("VLOOKUP") and domain skills ("product analytics").

## User Flow

### From Learning Path (primary)

1. Student is on the Learning Path page, sees a session (e.g., "Lesson 3: SUM and AVERAGE")
2. Student clicks an "Exercise" button/link on that session
3. Exercise page opens. Frontend sends `{topic, learner_profile}` to `/start-exercise`
4. Backend chain produces `{spreadsheet_data, tutor_opening_message}`
5. Frontend loads spreadsheet data into Univer, shows tutor's opening message in chat
6. Student works in spreadsheet, chats with tutor for guidance. Each chat message includes a snapshot of the current spreadsheet state.
7. Student finishes — tutor gives feedback, system updates learner profile

### On-Demand (sidebar)

Same flow, but no pre-selected topic. The tutor's first message asks what the student wants to practice. The student can request:
- **Technical skills:** "I want to practice VLOOKUP"
- **Domain skills:** "I want to learn how to do product analytics" or "clickstream analysis"

The Plan Exercise step figures out which spreadsheet functions are needed for the requested domain and builds an exercise around it. The chat is the topic picker — no separate UI needed.

After the student responds with a topic, the frontend calls `/start-exercise` and the flow continues as above.

**Topic detection mechanism:** The first chat message in on-demand mode is always treated as the topic. The frontend does not need to distinguish between "topic selection" and "follow-up" — it simply takes the student's first message, passes it as the `topic` field to `/start-exercise`, and transitions to exercise mode. If the student's message is vague or off-topic, the Plan Exercise LLM call handles interpretation (e.g., "I'm not sure" → the planner picks a recommended topic based on the learner profile).

## Backend Architecture

### New endpoint: `POST /start-exercise`

**Input:**
```json
{
  "topic": "VLOOKUP",
  "learner_profile": { ... }
}
```

**Output:**
```json
{
  "exercise_plan": { ... },
  "spreadsheet_data": { ... },
  "tutor_message": "Welcome! You're working as an HR analyst today..."
}
```

**Implementation:** A chain of LLM calls in a new module `backend/modules/exercise_generator/` following the existing module pattern (agents/, prompts/, schemas.py).

**Latency note:** The 4-step chain (plus up to 2 retries) may take 20-40 seconds. The frontend should show a loading/spinner state during `/start-exercise`. Steps are sequential and cannot be parallelized.

**Error handling:** If the chain fails after all retries (e.g., invalid plan, data generation failure), the endpoint returns HTTP 500 with error detail. The frontend shows a "Could not generate exercise — try again" message.

### Chain Steps

```
Input: { topic, learner_profile }
          |
          v
   +------------------+
   | 1. Plan Exercise  |  Single LLM call. Takes topic + learner profile.
   +--------+---------+  Outputs structured exercise plan (see below).
            |              Handles both technical and domain skill topics.
            v
   +------------------+
   | 2. Generate Data  |  Reuses existing data_generator module.
   +--------+---------+  One call per sheet that has prefilled data.
            |              See "Data Generation Bridge" below.
            v
   +------------------+
   | 3. Judge Quality  |  LLM call. Returns { pass: bool, reason: str }.
   +--------+---------+  If fail, reason is fed back to step 2 as a
            |              constraint for the retry. Max 2 retries,
         pass/fail ---fail--> loop back to step 2 (with reason)
            |
           pass
            v
   +------------------+
   | 4. Generate       |  LLM creates the tutor's first message.
   |    Opening Msg    |  Exercise instructions for the student.
   +--------+---------+
            |
            v
Output: { exercise_plan, spreadsheet_data, tutor_message }
```

### Data Generation Bridge

The existing `data_generator` module accepts `{user_request, row_count, columns, constraints}` — a flat text-based interface. The exercise generator bridges the structured plan to this interface:

- **One call per sheet** that contains prefilled data. Sheets where `prefilled` is empty are skipped.
- The `user_request` is constructed from the plan's scenario + sheet context (e.g., "Generate HR employee data for a VLOOKUP exercise: columns Employee ID and Full Name, 6 rows, IDs should be in format EMP-XXX").
- The `columns` parameter maps from the plan's `prefilled` list.
- `student_fills` columns are **not generated** — they are left empty in the final spreadsheet data. The student fills them in.
- For multi-sheet exercises (e.g., VLOOKUP with a lookup table), the generator ensures referential integrity across sheets (e.g., employee IDs in the Sales Report must exist in the Directory). This is handled by passing cross-sheet constraints in the `constraints` field.

### Exercise Plan Schema

The Plan Exercise step outputs a structured plan that varies by exercise type:

**Basic formula exercise:**
```json
{
  "exercise_type": "fill_formulas",
  "scenario": "You work in HR. You have employee IDs with sales numbers...",
  "sheets": [
    {
      "name": "Sales Report",
      "columns": ["Employee ID", "Employee Name", "Q1 Sales", "Q2 Sales"],
      "prefilled": ["Employee ID", "Q1 Sales", "Q2 Sales"],
      "student_fills": ["Employee Name"],
      "expected_formula_template": "VLOOKUP(A{row}, Directory!A:B, 2, FALSE)"
    },
    {
      "name": "Directory",
      "columns": ["Employee ID", "Full Name"],
      "prefilled": ["Employee ID", "Full Name"]
    }
  ],
  "row_count": 6,
  "difficulty": "beginner"
}
```

**Multi-step analysis exercise:**
```json
{
  "exercise_type": "multi_step_analysis",
  "scenario": "Perform a contribution analysis on product revenue...",
  "sheets": [
    {
      "name": "Products",
      "columns": ["Product", "Revenue"],
      "prefilled": ["all"],
      "student_fills": []
    },
    {
      "name": "Analysis",
      "columns": ["Product", "Revenue", "% of Total", "Cumulative %"],
      "prefilled": ["Product", "Revenue"],
      "student_fills": ["% of Total", "Cumulative %"]
    }
  ],
  "steps": [
    {"goal": "Calculate total revenue", "hint": "SUM of Revenue column"},
    {"goal": "Calculate % of Total for each product", "hint": "Revenue / Total"},
    {"goal": "Calculate cumulative %", "hint": "Running sum of percentages"},
    {"goal": "Identify which products make up 80% of revenue"}
  ],
  "row_count": 15,
  "difficulty": "intermediate"
}
```

**Exercise types** are a closed enum for this phase: `fill_formulas` and `multi_step_analysis`. Additional types (e.g., `debug_errors`, `build_from_scratch`) are future work.

**Formula templates** use `{row}` as a placeholder for row references. The tutor uses these as a pattern to check against — e.g., if the template is `VLOOKUP(A{row}, Directory!A:B, 2, FALSE)`, the tutor checks that each student-filled row follows this pattern with the appropriate row number. For multi-step exercises, correctness is determined by the `steps` list: the tutor checks whether each step's goal has been achieved by examining the snapshot (e.g., "Calculate total revenue" → check if a SUM formula exists over the Revenue column).

The exercise plan is also passed to the tutor during the exercise so it knows the expected solution and can guide step-by-step.

## Frontend Architecture

### PostMessage Bridge

The Univer spreadsheet runs in an iframe. A postMessage bridge captures cell data for the tutor.

**Mechanism:** Streamlit's `components.html` does not natively write back to session state. The bridge uses a **custom bidirectional Streamlit component** pattern:

1. A hidden `components.html` block in the page contains JS that listens for messages from the Univer iframe
2. When the student clicks "Send" in chat, a JS call (`window.parent.postMessage("get_sheet_data", "*")`) requests data from the Univer iframe
3. The Univer iframe (which has an injected listener) responds with cell data via `postMessage`
4. The hidden component captures this and uses `Streamlit.setComponentValue(data)` to pass it back to Python
5. The Python side reads the component's return value and stores it in `st.session_state["sheet_snapshot"]`
6. The chat handler reads the snapshot and includes it in the `/chat-with-tutor` request

**Alternative (simpler but less clean):** Use the `streamlit_js_eval` package to execute JS that reads the iframe's data synchronously when the chat form is submitted. This avoids a custom component but requires the package as a dependency. If `streamlit_js_eval` is already in requirements.txt or easy to add, prefer this approach.

**Snapshot format:**
```json
{
  "sheets": [{
    "name": "Sales Report",
    "cells": {
      "A1": {"value": "Employee ID"},
      "B2": {"value": "Sarah Johnson", "formula": "=VLOOKUP(A2,Directory!A:B,2,FALSE)"},
      "B3": {"value": "", "formula": ""}
    }
  }]
}
```

Both value and formula are captured so the tutor can distinguish between correct answers achieved via formula vs. hardcoded values.

**Snapshot size:** Exercises are capped at ~20 rows and 2-3 sheets, so snapshots stay small (well under 1K tokens). No summarization needed for this phase.

### Exercise Page States

The exercise page (`frontend/pages/exercise.py`) handles two states:

- **Topic provided** (from learning path): calls `/start-exercise` immediately on page load, shows loading state, then renders spreadsheet + tutor message
- **No topic** (on-demand): shows empty chat, tutor asks what to practice, calls `/start-exercise` after student responds

### Layout

Two columns (existing pattern):
- **Left column (~60%):** Exercise title + Univer spreadsheet
- **Right column (~40%):** AI tutor chat (inline, not floating)

## Chat Integration During Exercise

### Request format

Each chat message to `/chat-with-tutor` during an exercise includes:

```json
{
  "messages": [/* full conversation history */],
  "learner_profile": { ... },
  "exercise_context": {
    "plan": {/* exercise plan from /start-exercise */},
    "sheet_snapshot": {/* current cell state from postMessage */}
  }
}
```

### Extended `/chat-with-tutor` endpoint

The existing endpoint is extended to accept an optional `exercise_context` field. The integration point is the `AITutorChatbot` agent class in `backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py`:

- Add `exercise_context` as an optional field on `TutorChatPayload`
- In `AITutorChatbot.chat()`, if `exercise_context` is present, inject it into `input_vars` alongside `learner_profile` and `messages`
- The system prompt template (`ai_tutor_chatbot_system_prompt`) is extended with a conditional section: if exercise context is provided, include the exercise plan and spreadsheet snapshot in the prompt

The endpoint in `main.py` passes the new field through. If `exercise_context` is absent, behavior is unchanged.

### Tutor behaviors in exercise mode

- Compares student's formulas against expected ones from the plan
- Identifies which step the student is on (for multi-step exercises)
- Gives progressive hints rather than direct answers
- Confirms correct steps and prompts the next one
- Can see both values and formulas to detect hardcoded answers

## Exercise Completion

When the student finishes (says "I'm done" or clicks a finish button), two things happen:

### 1. Student Feedback

A final `/chat-with-tutor` call with a "summarize performance" instruction. The tutor generates a summary:

> "Nice work! You correctly used VLOOKUP with exact match for all 6 employees. You struggled a bit with the sheet reference syntax — I'd suggest practicing cross-sheet references more. Next time we could try INDEX/MATCH as a more flexible alternative."

The tutor has the full conversation history + final spreadsheet snapshot, so it can assess what went well, what was hard, and what to do next.

### 2. Learner Profile Update

The performance summary is generated by an **LLM call** (not frontend tracking). When the exercise ends, an additional LLM call receives the full conversation history + final spreadsheet snapshot + exercise plan and produces the structured `session_information` object. This is effectively a 5th step that runs at completion time.

The LLM is well-positioned to determine `struggled_with` (it saw the student's mistakes and questions), `skills_practiced` (it knows the exercise plan), and `completed_steps` (it can compare the final snapshot against expected outcomes). `hints_requested` is the one field the frontend tracks — a simple counter incremented each time the student asks a question.

The frontend then calls the existing `/update-learner-profile` endpoint with the result:

```json
{
  "learner_profile": { ... },
  "session_information": {
    "type": "exercise",
    "topic": "VLOOKUP",
    "scenario": "HR employee lookup",
    "skills_practiced": ["VLOOKUP", "cross-sheet references"],
    "performance": {
      "completed_steps": 6,
      "total_steps": 6,
      "struggled_with": ["sheet reference syntax"],
      "hints_requested": 3
    }
  }
}
```

**How this feeds back into the system:**
- Future Plan Exercise calls see the updated profile and can increase difficulty or move to related topics
- Skill gaps update — practiced skills move toward "known"
- Struggles become new micro-gaps that future exercises can target

## Scope Boundaries

**In scope for this phase:**
- `/start-exercise` endpoint with the 4-step chain
- PostMessage bridge for snapshot-based spreadsheet awareness
- Exercise context in `/chat-with-tutor`
- Exercise completion with feedback + profile update
- On-demand mode via chat-driven topic selection

**Explicitly out of scope (future work):**
- Event-based real-time spreadsheet awareness (streaming cell changes)
- Brainstorming skill for the tutor (conversational exercise design)
- Conversational skill gap analysis (replacing automated flow)
- Exercise history / retrieval from past exercises
- ReAct agent with tool selection (current approach is a fixed chain)
