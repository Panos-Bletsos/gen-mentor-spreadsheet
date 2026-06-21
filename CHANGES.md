## Branch Changes: interactive-learning-env

---

### Docs & Config

| File | Lines | Description |
|---|---|---|
| `.gitignore` | 16 | Add `backend/logs/` to ignored paths |
| `CLAUDE.md` | 1–76 (new) | Add project-level Claude Code instructions file with architecture overview |
| `backend/config/default.yaml` | 10 | Update default model from `gpt-4o` to `gpt-4.1-nano` |
| `backend/config/main.yaml` | 16 | Update model name |
| `backend/config/schemas.py` | 11 | Update default `model_name` in `LLMConfig` |
| `scripts/start_frontend.sh` | — | Fix file permissions (mode 100644 → 100755) |
| `docs/UNIVER_INTEGRATION.md` | 1–271 (new) | Add integration guide for the Univer spreadsheet iframe/postMessage architecture |
| `docs/cursor_streamlit_to_react_migration_fea.md` | 1–454 (new) | Add Cursor-exported React migration feasibility study and plan |
| `docs/superpowers/plans/2026-03-21-interactive-exercise-system.md` | 1–1391 (new) | Add full implementation plan for the interactive exercise system |
| `docs/superpowers/specs/2026-03-21-interactive-exercise-system-design.md` | (new) | Add design spec for the exercise system |

---

### Backend: Agent Infrastructure & Logging

| File | Lines | Description |
|---|---|---|
| `backend/logging_config.py` | 1–38 (new) | Add `setup_logging()` with rotating file handler and console formatter |
| `backend/base/base_agent.py` | 1–2, 9, 86–101 | Add timing/logging instrumentation to `BaseAgent.invoke()` with per-agent duration logs and error capture |
| `backend/base/llm_factory.py` | 56 | Rename dummy vLLM key string |
| `backend/base/base_structured_agent.py` | 1–55 (new) | New `BaseStructuredAgent` class using `model.with_structured_output()` for provider-native validated Pydantic responses |

---

### Backend: API Schemas & Endpoints

| File | Lines | Description |
|---|---|---|
| `backend/api_schemas.py` | 3, 9, 17–18, 175–188 | Add `Any` import; add `mode`/`exercise_context` to `ChatWithAutorRequest`; add `SyntheticSheetDataGenerationRequest` and `StartExerciseRequest` schemas |
| `backend/main.py` | 3, 6, 10, 20–41, 42–86, 123–124, 130–143, 335–421 | Import new modules; call `setup_logging`; add HTTP request/response logging middleware; wire `mode`/`exercise_context` through `/chat-with-tutor`; add `/start-exercise` endpoint; add `/generate-synthetic-sheet-data` endpoint |

---

### Backend: AI Chatbot Tutor Changes

| File | Lines | Description |
|---|---|---|
| `backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py` | 4–5, 12–13, 17–18, 68–69, 94, 97–172 | Add `mode` and `exercise_context` to `TutorChatPayload`; route `chat()` to three distinct task prompts (`general`, `brainstorming`, `exercise`) based on mode; add logging |
| `backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py` | 29–57 (new) | Add `ai_tutor_brainstorming_task_prompt` (converging topic selection with JSON done signal) and `ai_tutor_exercise_task_prompt` (spreadsheet-aware guided tutoring) |

---

### Backend: Data Generator Module (new)

| File | Lines | Description |
|---|---|---|
| `backend/modules/data_generator/__init__.py` | 1–19 (new) | Module-level exports for `SyntheticDataGenerator` and helpers |
| `backend/modules/data_generator/agents/__init__.py` | 1–13 (new) | Agent-level exports |
| `backend/modules/data_generator/agents/data_generator.py` | 1–113 (new) | `SyntheticDataGenerator` agent: validates row count and headers, calls LLM, returns `SyntheticSpreadsheetData` |
| `backend/modules/data_generator/prompts/__init__.py` | 1–9 (new) | Prompt exports |
| `backend/modules/data_generator/prompts/data_generator.py` | 1–45 (new) | System prompt and task prompt for tabular data generation |

---

### Backend: Exercise Generator Module (new)

| File | Lines | Description |
|---|---|---|
| `backend/modules/exercise_generator/__init__.py` | 1–3 (new) | Module export for `start_exercise_with_llm` |
| `backend/modules/exercise_generator/agents/__init__.py` | 1 (new) | Agent export |
| `backend/modules/exercise_generator/agents/exercise_planner.py` | 1–214 (new) | 4-step chain: `ExercisePlanner` → `SyntheticDataGenerator` (with `QualityJudge` retry loop, up to 3 attempts) → `OpeningMessageGenerator`; returns `exercise_plan`, `spreadsheet_data`, `tutor_message` |
| `backend/modules/exercise_generator/prompts/__init__.py` | 1–8 (new) | Prompt exports |
| `backend/modules/exercise_generator/prompts/exercise_planner.py` | 1–101 (new) | Six prompt templates: exercise planner system/task, quality judge system/task, opening message system/task |
| `backend/modules/exercise_generator/schemas.py` | 1–51 (new) | Pydantic models: `ExerciseTopic`, `SheetPlan`, `ExerciseStep`, `ExercisePlan`, `StartExercisePayload`, `StartExerciseResult`, `JudgeQualityResult` |

---

### Frontend: Exercise Page (new)

| File | Lines | Description |
|---|---|---|
| `frontend/pages/exercise.py` | 1–396 (new) | Three-phase state machine (`brainstorming` → `loading` → `exercising` → `completed`); brainstorming chat with JSON signal parsing; exercise loading via `/start-exercise`; side-by-side Univer iframe + AI tutor chat; sheet snapshot capture via `streamlit_js_eval`; "Finish Exercise" flow |
| `frontend/main.py` | 102–111 | Register `sheets` and `exercise` pages in Streamlit navigation |
| `frontend/pages/goal_management.py` | 6, 9 | Import and call `initialize_session_state()` at page load |

---

### Frontend: Spreadsheet Integration (new)

| File | Lines | Description |
|---|---|---|
| `frontend/pages/sheets.py` | 1–266 (new) | Sheets page: LLM data generation populator, Univer iframe embed, JSON/CSV export, JSON file upload import, data inspection tabs |
| `frontend/assets/js/univer_sheets.py` | 1–58 (new) | `get_univer_sheets_html()` builder that composes HTML/CSS/JS templates with postMessage snapshot listener |
| `frontend/assets/univer/index.html` | 1–51 (new) | Univer iframe HTML template with CDN script tags, toolbar, cell-info bar |
| `frontend/assets/univer/univer.css` | 1–66 (new) | Styles for toolbar, cell-info bar, and `#app` container |
| `frontend/assets/univer/univer.js` | 1–210 (new) | Univer init script: `createWorkbook`, selection tracking, `getWorkbookSnapshot()`, JSON/CSV export functions |

---

### Frontend: State & Utilities

| File | Lines | Description |
|---|---|---|
| `frontend/utils/state.py` | 32–35, 56, 88, 111–120 | Add `exercise_messages`, `exercise_phase`, `exercise_plan`, `exercise_topic` to `PERSIST_KEYS` and session initialization |
| `frontend/utils/request_api.py` | 24–25, 226–273 | Add `generate_synthetic_sheet_data()`, `start_exercise()`, and `chat_with_tutor_exercise()` API wrapper functions |
| `frontend/utils/sheet_data_parser.py` | 1–338 (new) | Utility module: `build_univer_workbook_from_grid/records/payload()` (multi-format converter to Univer snapshot format), `extract_cell_values()`, `sheet_to_dataframe()`, `get_sheet_summary()` |
| `frontend/requirements.txt` | 9, 17–18 | Add `streamlit-js-eval`, `pandas`, and `plotly` dependencies |
