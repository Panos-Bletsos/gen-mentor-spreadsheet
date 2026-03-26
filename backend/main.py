import ast
import json
import logging
import os
import time
import uvicorn
from pathlib import Path
from dotenv import load_dotenv
from fastapi.responses import Response as RawResponse
import hydra
from omegaconf import DictConfig, OmegaConf
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from base.llm_factory import LLMFactory
from base.searcher_factory import SearchRunner
from base.search_rag import SearchRagManager
from utils.preprocess import extract_text_from_pdf
from fastapi.responses import JSONResponse
from modules.skill_gap_identification import *
from modules.adaptive_learner_modeling import *
from modules.personalized_resource_delivery import *
from modules.ai_chatbot_tutor import chat_with_tutor_with_llm
from modules.data_generator import generate_synthetic_spreadsheet_data_with_llm
from modules.exercise_generator import start_exercise_with_llm
from api_schemas import *
from config import load_config
from logging_config import setup_logging

app_config = load_config(config_name="main")
setup_logging(level=str(app_config.get("log_level", "INFO")))
logger = logging.getLogger(__name__)
http_logger = logging.getLogger("http")

search_rag_manager = SearchRagManager.from_config(app_config)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    method = request.method
    path = request.url.path

    # Read and log request body (Starlette caches the bytes so downstream handlers can still read it)
    body_bytes = await request.body()
    try:
        req_body_str = json.dumps(json.loads(body_bytes), ensure_ascii=False, indent=2) if body_bytes else "{}"
    except Exception:
        req_body_str = body_bytes.decode("utf-8", errors="replace")

    logger.info("REQUEST  %s %s started", method, path)
    http_logger.info(">>> %s %s\n%s", method, path, req_body_str)

    start = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start

        # Buffer response body so we can log it, then re-wrap to send to client
        resp_chunks = []
        async for chunk in response.body_iterator:
            resp_chunks.append(chunk)
        resp_bytes = b"".join(resp_chunks)
        try:
            resp_body_str = json.dumps(json.loads(resp_bytes), ensure_ascii=False, indent=2)
        except Exception:
            resp_body_str = resp_bytes.decode("utf-8", errors="replace")

        logger.info("REQUEST  %s %s completed (%.1fs) %s", method, path, duration, response.status_code)
        http_logger.info("<<< %s %s [%s] (%.1fs)\n%s", method, path, response.status_code, duration, resp_body_str)

        return RawResponse(
            content=resp_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
    except Exception as e:
        duration = time.time() - start
        logger.error("REQUEST  %s %s failed (%.1fs): %s", method, path, duration, e)
        http_logger.error("!!! %s %s failed (%.1fs): %s", method, path, duration, e)
        raise

def get_llm(model_provider: str | None = None, model_name: str | None = None, **kwargs):
    model_provider = model_provider or app_config.llm.provider
    model_name = model_name or app_config.llm.model_name
    if "base_url" not in kwargs and getattr(app_config.llm, "base_url", None):
        kwargs["base_url"] = app_config.llm.base_url
    return LLMFactory.create(model=model_name, model_provider=model_provider, **kwargs)

UPLOAD_LOCATION = "/mnt/datadrive/tfwang/code/llm-mentor/data/cv/"

@app.get("/list-llm-models")
async def list_llm_models():
    try:
        return {"models": [
            {
                "model_name": app_config.llm.model_name, 
                "model_provider": app_config.llm.provider
            }
        ]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})
        result = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=search_rag_manager,
            use_search=request.mode != "brainstorming",
            mode=request.mode,
            exercise_context=request.exercise_context,
        )
        # result is {"response": str, "tool_calls": list[dict]}
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

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

@app.post("/refine-learning-goal")
async def refine_learning_goal(request: LearningGoalRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        refined_learning_goal = refine_learning_goal_with_llm(llm, request.learning_goal, request.learner_information)
        return refined_learning_goal
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/identify-skill-gap-with-info")
async def identify_skill_gap_with_info(request: SkillGapIdentificationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_goal = request.learning_goal
    learner_information = request.learner_information
    skill_requirements = request.skill_requirements
    try:
        if isinstance(skill_requirements, str) and skill_requirements.strip():
            skill_requirements = ast.literal_eval(skill_requirements)
        if not isinstance(skill_requirements, dict):
            skill_requirements = None
        skill_gaps, skill_requirements = identify_skill_gap_with_llm(
            llm, learning_goal, learner_information, skill_requirements
        )
        results = {**skill_gaps, **skill_requirements}
        return results
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/identify-skill-gap")
async def identify_skill_gap(goal: str = Form(...), cv: UploadFile = File(...), model_provider: str | None = Form(None), model_name: str | None = Form(None)):
    llm = get_llm(model_provider, model_name)
    mapper = SkillRequirementMapper(llm)
    skill_gap_identifier = SkillGapIdentifier(llm)
    try:
        file_location = f"{UPLOAD_LOCATION}{cv.filename}"
#         with open(file_location, "wb") as file_object:
#             file_object.write(await cv.read())
        with open(file_location, "wb") as file_object:
            file_object.write(await cv.read())
        # print(file_location)
        cv_text = extract_text_from_pdf(file_location)  
        skill_requirements = mapper.map_goal_to_skill({
            "learning_goal": goal
        })
        skill_gaps = skill_gap_identifier.identify_skill_gap({
            "learning_goal": goal,
            "skill_requirements": skill_requirements,
            "learner_information": cv_text
        })
        results = {**skill_gaps, **skill_requirements}
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/create-learner-profile-with-info")
async def create_learner_profile_with_info(request: LearnerProfileInitializationWithInfoRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_information = request.learner_information
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    try:
        if isinstance(learner_information, str):
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, learner_information, skill_gaps
        )
        result = {"learner_profile": learner_profile}
        logger.debug("Created learner profile: %s", str(result)[:500])
        return result
    except Exception as e:
        logger.error("Failed to create learner profile: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-learner-profile")
async def create_learner_profile(request: LearnerProfileInitializationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    file_location = f"{UPLOAD_LOCATION}{request.cv_path}"
    learner_information = extract_text_from_pdf(file_location)
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    try:
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, {"raw": learner_information}, skill_gaps
        )
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-learner-profile")
async def update_learner_profile(request: LearnerProfileUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    learner_information = request.learner_information
    session_information = request.session_information
    try:
        for name in ("learner_profile", "learner_interactions", "learner_information", "session_information"):
            val = locals()[name]
            if isinstance(val, str) and val.strip():
                try:
                    locals()[name] = ast.literal_eval(val)
                except Exception:
                    if name != "session_information":
                        locals()[name] = {"raw": val}
        learner_profile = update_learner_profile_with_llm(
            llm,
            locals()["learner_profile"],
            locals()["learner_interactions"],
            locals()["learner_information"],
            locals()["session_information"],
        )
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schedule-learning-path")
async def schedule_learning_path(request: LearningPathSchedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_count = request.session_count
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        learning_path = schedule_learning_path_with_llm(llm, learner_profile, session_count)
        logger.debug("Scheduled learning path: %s", str(learning_path)[:500])
        return learning_path
    except Exception as e:
        logger.error("Failed to schedule learning path: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reschedule-learning-path")
async def reschedule_learning_path(request: LearningPathReschedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    session_count = request.session_count
    other_feedback = request.other_feedback
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(other_feedback, str) and other_feedback.strip():
            try:
                other_feedback = ast.literal_eval(other_feedback)
            except Exception:
                pass
        learning_path = reschedule_learning_path_with_llm(
            llm, learning_path, learner_profile, session_count, other_feedback
        )
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/explore-knowledge-points")
async def explore_knowledge_points(request: KnowledgePointExplorationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    if isinstance(learner_profile, str) and learner_profile.strip():
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learning_path, str) and learning_path.strip():
        learning_path = ast.literal_eval(learning_path)
    if isinstance(learning_session, str) and learning_session.strip():
        learning_session = ast.literal_eval(learning_session)
    try:
        knowledge_points = explore_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session)
        return knowledge_points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-point")
async def draft_knowledge_point(request: KnowledgePointDraftingRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_point = request.knowledge_point
    use_search = request.use_search
    try:
        knowledge_draft = draft_knowledge_point_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_point, use_search)
        return {"knowledge_draft": knowledge_draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-points")
async def draft_knowledge_points(request: KnowledgePointsDraftingRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    try:
        knowledge_drafts = draft_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, allow_parallel, use_search)
        return {"knowledge_drafts": knowledge_drafts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/integrate-learning-document")
async def integrate_learning_document(request: LearningDocumentIntegrationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_drafts = request.knowledge_drafts
    output_markdown = request.output_markdown
    try:
        learning_document = integrate_learning_document_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts, output_markdown)
        return {"learning_document": learning_document}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-document-quizzes")
async def generate_document_quizzes(request: KnowledgeQuizGenerationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_document = request.learning_document
    single_choice_count = request.single_choice_count
    multiple_choice_count = request.multiple_choice_count
    true_false_count = request.true_false_count
    short_answer_count = request.short_answer_count
    try:
        document_quiz = generate_document_quizzes_with_llm(llm, learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count)
        return {"document_quiz": document_quiz}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tailor-knowledge-content")
async def tailor_knowledge_content(request: TailoredContentGenerationRequest):
    llm = get_llm()
    learning_path = request.learning_path
    learner_profile = request.learner_profile
    learning_session = request.learning_session
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    try:
        tailored_content = create_learning_content_with_llm(
            llm, learner_profile, learning_path, learning_session, allow_parallel=allow_parallel, with_quiz=with_quiz, use_search=use_search
        )
        return {"tailored_content": tailored_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-synthetic-sheet-data")
async def generate_synthetic_sheet_data(request: SyntheticSheetDataGenerationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        result = generate_synthetic_spreadsheet_data_with_llm(
            llm,
            user_request=request.user_request,
            row_count=request.row_count,
            columns=request.columns,
            constraints=request.constraints,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "together": "TOGETHER_API_KEY",
    "ollama": None,  # no key needed
}

ENV_FILE = Path(__file__).parent / ".env"


def _update_env_file(key: str, value: str) -> None:
    """Update or add a key=value line in the backend .env file."""
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, "r") as f:
            content = f.read()
        # Ensure file ends with newline so appended lines don't concatenate
        if content and not content.endswith("\n"):
            content += "\n"
        lines = content.splitlines(keepends=True)
    new_lines = []
    key_found = False
    for line in lines:
        stripped = line.rstrip("\n").rstrip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            if not key_found:  # only keep first occurrence; drop duplicates
                new_lines.append(f"{key}={value}\n")
            key_found = True
        else:
            new_lines.append(line)
    if not key_found:
        new_lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)


@app.post("/configure-provider")
async def configure_provider(request: ConfigureProviderRequest):
    """Save a provider API key (and optional base URL) to backend/.env and reload env vars."""
    provider = request.provider.lower()
    env_key = PROVIDER_ENV_KEYS.get(provider)
    if env_key is None and provider != "ollama":
        return JSONResponse(status_code=400, content={"detail": f"Unknown provider: {provider}"})
    try:
        if env_key:
            _update_env_file(env_key, request.api_key)
        if request.base_url:
            base_url_key = f"{provider.upper()}_BASE_URL"
            _update_env_file(base_url_key, request.base_url)
        load_dotenv(dotenv_path=ENV_FILE, override=True)
        return {"status": "ok", "provider": provider}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/configured-providers")
async def configured_providers():
    """Return list of provider names that have a non-empty API key configured."""
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    result = []
    for provider, env_key in PROVIDER_ENV_KEYS.items():
        if env_key is None:
            # ollama: always available (no key needed)
            if provider == "ollama":
                result.append(provider)
        elif os.environ.get(env_key):
            result.append(provider)
    return {"providers": result}


if __name__ == "__main__":
    server_cfg = app_config.get("server", {})
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = int(app_config.get("server", {}).get("port", 5000))
    log_level = str(app_config.get("log_level", "debug")).lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
