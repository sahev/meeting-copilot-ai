from __future__ import annotations

from pydantic import BaseModel, Field


class ContextUpdate(BaseModel):
    current_topic: str = ""
    topics: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    technical_impacts: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    test_suggestions: list[str] = Field(default_factory=list)


class GeneratedQuestions(BaseModel):
    followup_questions: list[str] = Field(default_factory=list)
    risk_questions: list[str] = Field(default_factory=list)
    technical_questions: list[str] = Field(default_factory=list)
    acceptance_criteria_questions: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)

    def merge(self, other: "GeneratedQuestions") -> None:
        for field_name in self.model_fields:
            setattr(self, field_name, _dedupe(getattr(self, field_name), getattr(other, field_name)))


class MeetingContext(ContextUpdate):
    generated_questions: GeneratedQuestions = Field(default_factory=GeneratedQuestions)
    raw_transcript_tail: list[str] = Field(default_factory=list)

    def add_transcript(self, text: str, max_items: int = 20) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self.raw_transcript_tail.append(cleaned)
        self.raw_transcript_tail = self.raw_transcript_tail[-max_items:]

    def merge_update(self, update: ContextUpdate) -> None:
        if update.current_topic.strip():
            self.current_topic = update.current_topic.strip()

        for field_name in ContextUpdate.model_fields:
            if field_name == "current_topic":
                continue
            current_items = getattr(self, field_name)
            new_items = getattr(update, field_name)
            setattr(self, field_name, _dedupe(current_items, new_items))

    def merge_questions(self, questions: GeneratedQuestions) -> None:
        self.generated_questions.merge(questions)


def _dedupe(current_items: list[str], new_items: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*current_items, *new_items]:
        cleaned = " ".join(item.strip().split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged
