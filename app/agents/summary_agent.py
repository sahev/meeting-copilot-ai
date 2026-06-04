from __future__ import annotations

from app.ai.providers.base_provider import BaseAiProvider
from app.context.meeting_context import MeetingContext
from app.services.prompt_loader import PromptLoader


class SummaryAgent:
    name = "summary"

    def __init__(self, prompt_loader: PromptLoader, provider: BaseAiProvider) -> None:
        self._prompt_loader = prompt_loader
        self._provider = provider

    def summarize(self, current_context: MeetingContext, meeting_topic: str | None = None) -> str:
        prompt = self._prompt_loader.render(
            "summary",
            current_context=current_context.model_dump_json(),
            new_transcript="",
            meeting_topic=meeting_topic or current_context.current_topic,
        )
        payload = {
            "current_context": current_context.model_dump(mode="json"),
            "meeting_topic": meeting_topic or current_context.current_topic,
        }
        return self._provider.generate(prompt, payload).strip()
