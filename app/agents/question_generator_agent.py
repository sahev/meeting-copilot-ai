from __future__ import annotations

import logging

from pydantic import ValidationError

from app.ai.providers.base_provider import BaseAiProvider
from app.agents.json_utils import parse_json_object
from app.context.meeting_context import GeneratedQuestions, MeetingContext
from app.services.prompt_loader import PromptLoader


LOGGER = logging.getLogger(__name__)


class QuestionGeneratorAgent:
    name = "question_generator"

    def __init__(self, prompt_loader: PromptLoader, provider: BaseAiProvider) -> None:
        self._prompt_loader = prompt_loader
        self._provider = provider

    def generate_questions(self, current_context: MeetingContext, meeting_topic: str | None = None) -> GeneratedQuestions:
        prompt = self._prompt_loader.render(
            "question_generator",
            current_context=current_context.model_dump_json(exclude={"raw_transcript_tail"}),
            new_transcript="",
            meeting_topic=meeting_topic or current_context.current_topic,
        )
        payload = {
            "current_context": current_context.model_dump(mode="json", exclude={"raw_transcript_tail"}),
            "meeting_topic": meeting_topic or current_context.current_topic,
        }
        last_error: Exception | None = None
        for attempt in range(1, 3):
            raw_response = self._provider.generate(prompt, payload)
            try:
                return GeneratedQuestions.model_validate(parse_json_object(raw_response))
            except (ValueError, ValidationError) as exc:
                last_error = exc
                LOGGER.exception("QuestionGeneratorAgent received invalid JSON on attempt %s.", attempt)

        assert last_error is not None
        raise RuntimeError("AI provider returned invalid questions JSON. Questions were not changed.") from last_error
