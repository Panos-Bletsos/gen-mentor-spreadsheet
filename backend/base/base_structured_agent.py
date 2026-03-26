import logging
import time
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from base.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BaseStructuredAgent(BaseAgent):
    """Agent that returns validated Pydantic models via provider-native structured output.

    Subclasses must set `output_schema` to a Pydantic BaseModel class.
    invoke() bypasses create_agent() + preprocess_response() and instead uses
    LangChain's model.with_structured_output() for provider-native JSON responses.
    """

    output_schema: type[BaseModel]  # Subclasses MUST set this as a class variable

    def __init__(self, model: BaseChatModel, system_prompt: Optional[str] = None, **kwargs):
        super().__init__(model=model, system_prompt=system_prompt, jsonalize_output=False, **kwargs)

    def invoke(self, input_dict: dict, task_prompt: Optional[str] = None) -> BaseModel:
        """Invoke with provider-native structured output.

        Returns: validated instance of self.output_schema (e.g. ExercisePlan, JudgeQualityResult)
        """
        agent_name = self.__class__.__name__
        logger.info("AGENT    %s.invoke starting (structured)", agent_name)
        start = time.time()
        try:
            messages = self._build_messages(input_dict, task_prompt)
            structured_model = self._model.with_structured_output(self.output_schema)
            result = structured_model.invoke(messages)
            duration = time.time() - start
            logger.info("AGENT    %s.invoke completed (%.1fs, structured)", agent_name, duration)
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error("AGENT    %s.invoke failed (%.1fs): %s", agent_name, duration, e)
            raise
