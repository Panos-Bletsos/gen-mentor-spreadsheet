# User Flow Diagram — GenMentor Spreadsheet Learning App

## Context

The app is a 9-page Streamlit frontend for an interactive spreadsheet learning environment. It has a treatment/control A/B structure driven by `config.interactive_exercises`:

- **Treatment**: Incomplete sessions route to an interactive spreadsheet exercise with AI tutor (`exercise.py`)
- **Control**: Incomplete sessions route to a read-only knowledge document (`knowledge_document.py`)

Onboarding is a prerequisite gate: all content pages redirect to onboarding until `if_complete_onboarding=True` is set in session state.

---

## User Flow Diagram

```mermaid
flowchart TD
    Start([Start]) --> OB0

    subgraph Onboarding
        OB0["Onboarding\n(Card 0: Goal)"] -->|Next| OB1["Onboarding\n(Card 1: Information)"]
    end

    OB1 -->|Save & Continue| SG

    subgraph Goal Setup
        SG["Skill Gap Analysis\n(auto-triggers backend)"]
    end

    SG -->|Schedule Learning Path| LP

    LP["Learning Path"]

    LP -->|Select incomplete session| D{interactive_exercises?}
    D -->|True — treatment| EX["Exercise\n(spreadsheet + AI tutor)"]
    D -->|False — control| KD["Knowledge Document\n(read-only content)"]
    LP -->|Select completed session| KD

    EX -->|Finish Exercise\nsession marked complete| LP
    KD -->|Back| LP
    KD -->|Mark complete| LP

    subgraph Sidebar["Sidebar (post-onboarding)"]
        GM["Goal Management"]
        PR["Learner Profile"]
        DA["Dashboard"]
        SH["Sheets (utility)"]
    end

    LP -.->|navigate| GM
    LP -.->|navigate| PR
    LP -.->|navigate| DA
    LP -.->|navigate| SH
    GM -->|Add / switch goal| LP

    SG -.->|missing goal or info| OB0
    LP -.->|not onboarded| OB0
```

### Legend

| Style | Meaning |
|-------|---------|
| Solid arrow | Primary user-driven navigation |
| Dashed arrow | Sidebar access or guard redirect |
| Diamond `{...}` | Conditional branch (A/B cohort split) |

---

## Pages Summary

| Page | File | Role |
|------|------|------|
| Onboarding | `pages/onboarding.py` | Two-card wizard: goal entry + learner info |
| Skill Gap Analysis | `pages/skill_gap.py` | Auto-runs backend, shows editable skill gap cards |
| Learning Path | `pages/learning_path.py` | Session grid, main hub after onboarding |
| Exercise | `pages/exercise.py` | Treatment cohort: spreadsheet + AI tutor chat |
| Knowledge Document | `pages/knowledge_document.py` | Control cohort + completed session review |
| Goal Management | `pages/goal_management.py` | Add / switch / edit goals |
| Learner Profile | `pages/learner_profile.py` | View background, progress, preferences |
| Dashboard | `pages/dashboard.py` | Analytics: progress, mastery rate, timeseries |
| Sheets | `pages/sheets.py` | Utility for generating synthetic spreadsheet data |

---

## C4 Level 3 — Per-Page Interaction Diagrams

Each diagram uses three participants: **User**, the **Page** (Streamlit), and the **Backend** (FastAPI at `localhost:5000`). Arrows show temporal sequence: user action → page logic → backend round-trip. Dashed return arrows are backend responses.

---

### 1. Onboarding — `pages/onboarding.py`

A two-card wizard that collects the learner's goal and background before any other page is accessible. Card 0 captures the goal (with optional AI refinement); Card 1 captures occupation, optional resume PDF, and study preferences. On "Save & Continue" the data is written to session state and the user is forwarded to Skill Gap.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Onboarding Page
    participant B as Backend (FastAPI)

    U->>P: Enter learning goal (Card 0)
    U->>P: Click "Refine"
    P->>B: POST /refine-learning-goal
    B-->>P: refined goal text
    P-->>U: display refined goal

    U->>P: Click "Next" → Card 1
    U->>P: Select occupation, optionally upload resume PDF
    Note over P: PDF parsed locally via utils/pdf.py — no backend call
    U->>P: Enter study preferences
    U->>P: Click "Save & Continue"
    Note over P: writes to session state, routes to Skill Gap
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/refine-learning-goal` | "Refine" button (Card 0) | `refine_learning_goal` |

---

### 2. Skill Gap Analysis — `pages/skill_gap.py`

Automatically runs skill-gap identification when first visited (no user trigger needed). Displays editable skill cards where the user can adjust required/current proficiency levels and toggle individual gaps. "Schedule Learning Path" commits the gap data, creates the learner profile, and routes forward.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Skill Gap Page
    participant B as Backend (FastAPI)

    U->>P: Open page (skill_gaps empty in state)
    P->>B: POST /identify-skill-gap-with-info
    B-->>P: skill gap list
    P-->>U: render editable skill cards

    U->>P: Adjust proficiency sliders / toggle is_gap
    Note over P: local state only — no backend call

    U->>P: Click "Schedule Learning Path"
    P->>B: POST /create-learner-profile-with-info
    B-->>P: learner profile
    P-->>U: route to Learning Path
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/identify-skill-gap-with-info` | Page load when `skill_gaps` empty | `identify_skill_gap` |
| POST | `/create-learner-profile-with-info` | "Schedule Learning Path" when profile empty | `create_learner_profile` |

---

### 3. Learning Path — `pages/learning_path.py`

The main hub after onboarding. Auto-schedules sessions on first visit. Shows a grid of sessions with per-session action buttons. Incomplete sessions route to either Exercise (treatment) or Knowledge Document (control) depending on `config.interactive_exercises`. An expander allows re-scheduling with a custom session count.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Learning Path Page
    participant B as Backend (FastAPI)

    U->>P: Open page (learning_path empty in state)
    P->>B: POST /schedule-learning-path
    B-->>P: session list
    P-->>U: render session grid

    U->>P: Expand re-schedule panel, enter session count
    U->>P: Click "Re-schedule"
    P->>B: POST /reschedule-learning-path
    B-->>P: updated session list
    P-->>U: re-render grid

    alt interactive_exercises = True (treatment cohort)
        U->>P: Click "Learning" on incomplete session
        P->>B: POST /derive-knowledge-points
        B-->>P: knowledge points for session
        P-->>U: route to Exercise page
    else interactive_exercises = False (control cohort)
        U->>P: Click "Learning" on incomplete session
        P-->>U: route to Knowledge Document page
    end
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/schedule-learning-path` | Page load when `learning_path` empty | `schedule_learning_path` |
| POST | `/reschedule-learning-path` | "Re-schedule" button | `reschedule_learning_path` |
| POST | `/derive-knowledge-points` | "Learning" button — treatment cohort only | `derive_knowledge_points` |

---

### 4. Exercise — `pages/exercise.py`

The treatment cohort's interactive learning surface. Two sequential phases: **Brainstorming** (conversational negotiation of what to practice) and **Exercise** (live spreadsheet work with AI tutor guidance). Embeds the Univer Sheets iframe; reads sheet snapshots back via `streamlit_js_eval`.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Exercise Page
    participant Univer as Univer Sheets (iframe)
    participant B as Backend (FastAPI)

    rect rgb(235, 245, 255)
        Note over U,B: Brainstorming phase
        U->>P: Send chat message
        P->>B: POST /chat-with-tutor (mode=brainstorming)
        B-->>P: tutor reply
        P-->>U: display reply (repeat until ready)
        U->>P: Click "Ready to start the exercise"
        P->>B: POST /chat-with-tutor (mode=brainstorming, trigger=ready)
        B-->>P: exercise spec confirmed
    end

    rect rgb(235, 255, 235)
        Note over U,B: Loading exercise
        P->>B: POST /start-exercise
        B-->>P: exercise config + initial sheet data
        P-->>Univer: postMessage: load sheet snapshot
        P-->>U: show Univer iframe + exercise instructions
    end

    rect rgb(255, 248, 235)
        Note over U,B: Exercise phase
        U->>P: Send chat message
        P->>Univer: read snapshot via window.getWorkbookSnapshot()
        Univer-->>P: current sheet state
        P->>B: POST /chat-with-tutor (mode=exercise)
        B-->>P: tutor reply
        P-->>U: display reply (repeat as needed)
        U->>P: Click "Finish Exercise"
        P->>B: POST /chat-with-tutor (mode=exercise, trigger=finish — performance summary)
        B-->>P: performance summary JSON
        P->>B: POST /update-learner-profile
        B-->>P: updated profile
        P-->>U: route back to Learning Path
    end
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/chat-with-tutor` (mode=`brainstorming`) | Each chat message + "Ready to start" | `chat_with_tutor_exercise` |
| POST | `/start-exercise` | Entering loading phase after brainstorming | `start_exercise` |
| POST | `/chat-with-tutor` (mode=`exercise`) | Each chat message + "Finish Exercise" (×2) | `chat_with_tutor_exercise` |
| POST | `/update-learner-profile` | "Finish Exercise" after performance summary parsed | `update_learner_profile` |

---

### 5. Knowledge Document — `pages/knowledge_document.py`

The control cohort's (and completed-session) read path. On first visit with no cached document, runs a 4-stage backend pipeline to build the learning document and quizzes. The user reads the document, answers quizzes, then completes the session and optionally submits feedback — both actions update the learner profile.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Knowledge Document Page
    participant B as Backend (FastAPI)

    U->>P: Open page (no cached document)
    P->>B: POST /explore-knowledge-points
    B-->>P: explored points (1/4)
    P->>B: POST /draft-knowledge-points
    B-->>P: drafted points (2/4)
    P->>B: POST /integrate-learning-document
    B-->>P: integrated document (3/4)
    P->>B: POST /generate-document-quizzes
    B-->>P: quizzes (4/4)
    P-->>U: render document + quiz questions

    U->>P: Answer quiz questions (radio / checkbox / text)
    Note over P: local scoring only — no backend call

    U->>P: Click "Complete Session"
    P->>B: POST /update-learner-profile
    B-->>P: updated profile
    P-->>U: show feedback form

    U->>P: Fill feedback (stars, text), click "Submit Feedback"
    P->>B: POST /update-learner-profile
    B-->>P: updated profile
    P-->>U: route back to Learning Path
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/explore-knowledge-points` | Page load, no cached doc — stage 1/4 | `explore_knowledge_points` |
| POST | `/draft-knowledge-points` | Page load, no cached doc — stage 2/4 | `draft_knowledge_points` |
| POST | `/integrate-learning-document` | Page load, no cached doc — stage 3/4 | `integrate_learning_document` |
| POST | `/generate-document-quizzes` | Page load, no cached doc — stage 4/4 | `generate_document_quizzes` |
| POST | `/update-learner-profile` | "Complete Session" and "Submit Feedback" | `update_learner_profile` |

---

### 6. Goal Management — `pages/goal_management.py`

Allows the user to add new goals (with optional AI refinement), switch the active goal, or edit and delete existing ones. Opening the "Skill Gap" dialog for a new goal triggers a fresh skill-gap analysis and profile creation, effectively restarting the learning path for that goal.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Goal Management Page
    participant B as Backend (FastAPI)

    U->>P: Enter new goal text, click "Refine"
    P->>B: POST /refine-learning-goal
    B-->>P: refined goal text
    P-->>U: display refined goal

    U->>P: Click "Add Goal"
    Note over P: goal saved to session state

    U->>P: Open "Skill Gap" dialog for the new goal
    P->>B: POST /identify-skill-gap-with-info
    B-->>P: skill gap list
    P-->>U: render editable skill cards in dialog

    U->>P: Click "Schedule Learning Path" (inside dialog)
    P->>B: POST /create-learner-profile-with-info
    B-->>P: learner profile
    P-->>U: route to Learning Path
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/refine-learning-goal` | "Refine" button | `refine_learning_goal` |
| POST | `/identify-skill-gap-with-info` | Skill Gap dialog opens with empty skill gaps | `identify_skill_gap` |
| POST | `/create-learner-profile-with-info` | "Schedule Learning Path" inside dialog | `create_learner_profile` |

---

### 7. Learner Profile — `pages/learner_profile.py`

Read-only view of the learner model: background info, active goal, cognitive status, preferences, and behavioral patterns. Includes a feedback form (rating stars, text suggestions, optional PDF) that triggers a profile update on submit. A fallback call to create the profile fires only if rendering throws an exception.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Learner Profile Page
    participant B as Backend (FastAPI)

    U->>P: Open page
    P-->>U: render read-only profile sections (from session state)
    Note over P: POST /create-learner-profile-with-info only on render error (fallback)

    U->>P: Fill feedback form, optionally upload resume PDF
    Note over P: PDF parsed locally via utils/pdf.py — no backend call
    U->>P: Click "Update Profile"
    P->>B: POST /update-learner-profile
    B-->>P: updated profile
    P-->>U: re-render profile with updated data
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/update-learner-profile` | "Update Profile" button | `update_learner_profile` |
| POST | `/create-learner-profile-with-info` | Render-error fallback only | `create_learner_profile` |

---

### 8. Dashboard — `pages/dashboard.py`

Read-only analytics page. All data is drawn from session state computed locally; no backend calls are made. Renders a progress bar, a selectable Plotly skill radar chart, a bar chart of per-session time, and a line chart of mastery history over time.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Dashboard Page

    U->>P: Open page
    P-->>U: render progress bar
    P-->>U: render skill radar chart (selectable)
    P-->>U: render session time bar chart
    P-->>U: render mastery history line chart
    Note over P: all data from session state — no backend calls
```

*No backend endpoints.*

---

### 9. Sheets — `pages/sheets.py`

Utility page for generating synthetic spreadsheet data via LLM. Embeds a Univer Sheets iframe. When the user enters a plain-text prompt, the backend generates structured JSON that is posted to the iframe. If the input is already valid JSON it is posted directly. Supports JSON file re-import and Univer's built-in "Export JSON / CSV" downloads.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Sheets Page
    participant Univer as Univer Sheets (iframe)
    participant B as Backend (FastAPI)

    U->>P: Enter LLM prompt + row count / columns / constraints
    U->>P: Click "Populate Sheet"

    alt input is plain-text prompt (not valid JSON)
        P->>B: POST /generate-synthetic-sheet-data
        B-->>P: JSON sheet data
        P-->>Univer: postMessage: load sheet data
        P-->>U: render Univer iframe + data preview tabs
    else input is already valid JSON
        P-->>Univer: postMessage: load sheet data directly
        Note over P: no backend call
    end

    U->>Univer: edit cells, format data
    U->>P: Upload JSON file to re-import
    Note over P: JSON parsed locally, posted to Univer iframe
    U->>Univer: use built-in Export JSON / Export CSV toolbar
    Note over Univer: download only — no backend round-trip
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/generate-synthetic-sheet-data` | "Populate Sheet" when input is plain-text prompt | `generate_synthetic_sheet_data` |

---

### Cross-cutting: Global Floating Chatbot

Mounted once in `frontend/main.py` (not inside any individual page). Visible on all pages after onboarding completes. Calls the general RAG-backed tutor endpoint in default mode on each user message.

```mermaid
sequenceDiagram
    actor U as User
    participant Shell as Streamlit Shell (main.py)
    participant B as Backend (FastAPI)

    Note over Shell: visible post-onboarding on every page
    U->>Shell: Send chat message in floating chatbot
    Shell->>B: POST /chat-with-tutor (default mode)
    B-->>Shell: RAG-backed tutor reply
    Shell-->>U: display reply in chat window
```

| Method | Route | Trigger | Helper |
|--------|-------|---------|--------|
| POST | `/chat-with-tutor` | Any user message in the global chatbot | `chat_with_tutor` |
