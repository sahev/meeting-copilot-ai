from __future__ import annotations

import threading

from app.context.meeting_context import GeneratedQuestions, MeetingContext, ContextUpdate


class MeetingContextStore:
    def __init__(self) -> None:
        self._context = MeetingContext()
        self._lock = threading.Lock()

    def add_transcript(self, text: str) -> MeetingContext:
        with self._lock:
            self._context.add_transcript(text)
            return self._context.model_copy(deep=True)

    def merge_update(self, update: ContextUpdate) -> MeetingContext:
        with self._lock:
            self._context.merge_update(update)
            return self._context.model_copy(deep=True)

    def merge_questions(self, questions: GeneratedQuestions) -> MeetingContext:
        with self._lock:
            self._context.merge_questions(questions)
            return self._context.model_copy(deep=True)

    def snapshot(self) -> MeetingContext:
        with self._lock:
            return self._context.model_copy(deep=True)
