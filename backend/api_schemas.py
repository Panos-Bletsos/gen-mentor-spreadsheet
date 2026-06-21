
from pydantic import BaseModel
from typing import Any, Optional
from fastapi import File, UploadFile, Form


class BaseRequest(BaseModel):
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    method_name: str = "genmentor"


class ChatWithAutorRequest(BaseRequest):

    messages: str
    learner_profile: str = ""
    mode: str = "general"
    exercise_context: Optional[dict] = None
    exercise_id: Optional[str] = None
    lifecycle: Optional[str] = None  # e.g. "exercise_completed"


class LearningGoalRefinementRequest(BaseRequest):

    learning_goal: str
    learner_information: str = ""


class Goal2KnowledgePrestrionRequest(BaseRequest):

    learning_goal: str = Form(...),
    cv: UploadFile = File(...)


class SkillGapIdentificationRequest(BaseRequest):

    learning_goal: str
    learner_information: str
    skill_requirements: Optional[str] = None


class LearnerProfileInitializationWithInfoRequest(BaseRequest):

    learning_goal: str
    learner_information: str
    skill_gaps: str


class LearnerProfileInitializationRequest(BaseRequest):

    learning_goal: str
    skill_requirements: str
    skill_gaps: str
    cv_path: str


class LearnerProfileUpdateRequest(BaseRequest):

    learner_profile: str
    learner_interactions: str
    learner_information: str = ""
    session_information: str = ""


class LearningPathSchedulingRequest(BaseRequest):

    learner_profile: str
    session_count: int


class LearningPathReschedulingRequest(BaseRequest):
    
    learner_profile: str
    learning_path: str
    session_count: int = -1
    other_feedback: str = ""


class TailoredContentGenerationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str


class KnowledgePerspectiveExplorationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str


class KnowledgePerspectiveDraftingRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    knowledge_perspective: str
    use_search: bool = True


class KnowledgeDocumentIntegrationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    drafts_of_perspectives: str


class PointPerspectivesDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    use_search: bool
    allow_parallel: bool
 

class KnowledgeQuizGenerationRequest(BaseModel):

    learner_profile: str
    learning_document: str
    single_choice_count: int = 3
    multiple_choice_count: int = 0
    true_false_count: int = 0
    short_answer_count: int = 0


class TailoredContentGenerationRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    use_search: bool = True
    allow_parallel: bool = True
    with_quiz: bool = True


class KnowledgePointExplorationRequest(BaseModel):
    
    learner_profile: str
    learning_path: str
    learning_session: str


class KnowledgePointDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    knowledge_point: str
    use_search: bool


class KnowledgePointsDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    use_search: bool
    allow_parallel: bool


class LearningDocumentIntegrationRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    knowledge_drafts: str
    output_markdown: bool = False


class SyntheticSheetDataGenerationRequest(BaseRequest):

    user_request: str
    row_count: int = 20
    columns: Optional[list[str]] = None
    constraints: str = ""


class StartExerciseRequest(BaseRequest):
    topic: Any  # str or dict (ExerciseTopic)
    learner_profile: Any = ""
    brainstorming_history: list = []
    extra_context: str = ""
    skill_gaps: list = []  # per-skill current→required deltas from skill gap analysis


class DeriveKnowledgePointsRequest(BaseModel):
    learner_profile: Any = ""
    learning_path: Any = []
    learning_session: Any = {}


class DeriveKnowledgePointsResponse(BaseModel):
    knowledge_points: list


class ToolCallResult(BaseModel):
    """One tool call made by the LLM during a chat turn."""
    name: str
    args: dict


class ChatWithTutorResponse(BaseModel):
    """Response from /chat-with-tutor endpoint."""
    response: str
    tool_calls: list[ToolCallResult] = []


class ConfigureProviderRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None
