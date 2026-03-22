# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fork of GenMentor (WWW 2025 — LLM-powered multi-agent intelligent tutoring system) adapted for an undergraduate thesis. The thesis goal is to provide an interactive environment on top of GenMentor, for exercising on spreadsheets, with an AI Tutor that creates exercises and guides the student through them.

The system has a Python backend (FastAPI) and a Python frontend (Streamlit), each with its own virtual environment.

## Commands

### Backend
```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn main:app --reload --port 5000
```

### Frontend
```bash
cd frontend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run main.py --server.port 8501
```

### Helper Scripts
```bash
bash ./scripts/start_backend.sh [PORT]   # default 5000
bash ./scripts/start_frontend.sh [PORT]  # default 8501
bash ./scripts/stop_all.sh
```

There are no test suites or linters configured.

## Architecture

### Backend (`backend/`)

FastAPI server using Hydra for configuration and LangChain for LLM orchestration.

- **`main.py`** — FastAPI app with all route definitions and CORS setup
- **`api_schemas.py`** — Pydantic request/response models
- **`base/`** — Factory classes for swappable components:
  - `llm_factory.py` — Multi-provider LLM abstraction (OpenAI, DeepSeek, Anthropic, Ollama, Together)
  - `rag_factory.py` / `search_rag.py` — RAG pipeline with ChromaDB vector store
  - `embedder_factory.py` — HuggingFace sentence-transformers
  - `searcher_factory.py` — Web search (DuckDuckGo default)
- **`modules/`** — Core agent modules, each with `agents/`, `prompts/`, `schemas.py`:
  - `skill_gap_identification` — Analyzes knowledge gaps
  - `adaptive_learner_modeling` — Builds learner profiles
  - `personalized_resource_delivery` — Schedules learning paths, generates content
  - `ai_chatbot_tutor` — Conversational RAG-backed tutor
  - `data_generator` — Synthetic data generation for spreadsheets
- **`config/`** — Hydra YAML configs (`default.yaml`, `main.yaml`, `loader.py`)

Configuration is in `backend/config/default.yaml`. LLM provider and model are set there. API keys go in `backend/.env`.

### Frontend (`frontend/`)

Streamlit multi-page app with floating chatbot.

- **`main.py`** — Navigation setup and session state initialization
- **`config.py`** — Backend endpoint URL, mock data flag, search flag
- **`pages/`** — One file per page: `onboarding.py`, `learning_path.py`, `knowledge_document.py`, `goal_management.py`, `learner_profile.py`, `skill_gap.py`, `dashboard.py`, `sheets.py`
- **`components/`** — Reusable UI: chatbot, navigation, topbar, session completion
- **`utils/`** — HTTP client (`request_api.py`), session state persistence (`state.py`), sheet data parsing, formatting
- **`assets/`** — CSS, JS, mock data (`data_example/`), Univer spreadsheet assets

State persists to `frontend/user_data/data_store.json`. The Univer spreadsheet (in `pages/sheets.py`) is a React component loaded via CDN in an iframe, communicating via postMessage.

### Data Flow

Learner onboarding → Skill gap analysis → Learner profile → Learning path scheduling → Content generation → AI tutor chatbot. Each step maps to a backend module and a frontend page.
