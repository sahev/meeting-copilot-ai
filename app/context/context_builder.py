from __future__ import annotations

from app.agents.context_builder_agent import ContextBuilderAgent
from app.context.context_store import MeetingContextStore
from app.context.meeting_context import MeetingContext


class ContextPipeline:
    def __init__(self, store: MeetingContextStore, context_builder_agent: ContextBuilderAgent) -> None:
        self._store = store
        self._context_builder_agent = context_builder_agent

    def process_transcript(self, transcript: str, meeting_topic: str | None = None) -> MeetingContext:
        current_context = self._store.add_transcript(transcript)
        update = self._context_builder_agent.build_update(current_context, transcript, meeting_topic)
        return self._store.merge_update(update)
