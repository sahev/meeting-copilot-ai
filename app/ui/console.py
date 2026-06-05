from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.context.meeting_context import GeneratedQuestions, MeetingContext
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class ConsoleState:
    capturing: bool = False
    transcribing: bool = False
    meeting_started_at: float | None = None
    consumed_tokens: int = 0
    updating_context: bool = False
    generating_questions: bool = False
    generating_summary: bool = False
    last_transcript: str = ""
    summary_path: str = ""
    audio_queue_size: int = 0
    transcripts: list[str] = field(default_factory=list)
    meeting_context: MeetingContext = field(default_factory=MeetingContext)
    generated_questions: GeneratedQuestions = field(default_factory=GeneratedQuestions)
    ai_status: str = "Press Ctrl+G to send recent context to AI."
    error: str | None = None


class ThreadSafeConsoleState:
    def __init__(self) -> None:
        self._state = ConsoleState()
        self._lock = threading.Lock()

    def update(self, **kwargs: object) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._state, key, value)

    def add_transcript(self, text: str, max_items: int = 8) -> None:
        with self._lock:
            self._state.last_transcript = text
            self._state.transcripts.append(text)
            self._state.transcripts = self._state.transcripts[-max_items:]

    def snapshot(self) -> ConsoleState:
        with self._lock:
            return ConsoleState(
                capturing=self._state.capturing,
                transcribing=self._state.transcribing,
                meeting_started_at=self._state.meeting_started_at,
                consumed_tokens=self._state.consumed_tokens,
                updating_context=self._state.updating_context,
                generating_questions=self._state.generating_questions,
                generating_summary=self._state.generating_summary,
                last_transcript=self._state.last_transcript,
                summary_path=self._state.summary_path,
                audio_queue_size=self._state.audio_queue_size,
                transcripts=list(self._state.transcripts),
                meeting_context=self._state.meeting_context.model_copy(deep=True),
                generated_questions=self._state.generated_questions.model_copy(deep=True),
                ai_status=self._state.ai_status,
                error=self._state.error,
            )


def render_console(state: ConsoleState) -> Group:
    status = Table.grid(padding=(0, 2))
    status.add_column(style="bold")
    status.add_column()
    status.add_row("Capturing", "yes" if state.capturing else "no")
    status.add_row("Transcribing", "yes" if state.transcribing else "no")
    status.add_row("Consumed tokens", _format_tokens(state.consumed_tokens))
    status.add_row("Meeting duration", _format_duration(state.meeting_started_at))
    status.add_row("AI status", state.ai_status)

    transcript_table = Table.grid()
    transcript_table.add_column()
    if state.transcripts:
        for text in state.transcripts:
            transcript_table.add_row(text)
    else:
        transcript_table.add_row(Text("Waiting for real meeting audio...", style="dim"))

    panels = [
        Panel(status, title="STATUS", border_style="cyan"),
        Panel(_render_context(state.meeting_context), title="CONTEXT", border_style="blue"),
        Panel(_render_questions(state.generated_questions), title="GENERATED QUESTIONS", border_style="yellow"),
        Panel(transcript_table, title="TRANSCRIPT TAIL", border_style="magenta"),
    ]
    if state.error:
        panels.append(Panel(Text(state.error, style="red"), title="ERROR", border_style="red"))

    return Group(
        *panels,
        Text("Press F8 or Ctrl+G to generate questions. Press Ctrl+C to finish the current meeting.", style="dim"),
    )


def _render_context(context: MeetingContext) -> Table:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Current topic", context.current_topic or "-")
    table.add_row("Requirements", _compact_list(context.requirements))
    table.add_row("Rules", _compact_list(context.business_rules))
    table.add_row("Decisions", _compact_list(context.decisions))
    table.add_row("Risks", _compact_list(context.risks))
    table.add_row("Open questions", _compact_list(context.open_questions))
    return table


def _render_questions(questions: GeneratedQuestions) -> Table:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Follow-up", _compact_list(questions.followup_questions))
    table.add_row("Technical", _compact_list(questions.technical_questions))
    table.add_row("Acceptance", _compact_list(questions.acceptance_criteria_questions))
    table.add_row("Risks", _compact_list(questions.risk_questions))
    table.add_row("Improvements", _compact_list(questions.improvement_suggestions))
    return table


def _compact_list(items: list[str], limit: int = 4) -> str:
    if not items:
        return "-"
    visible = items[-limit:]
    return "\n".join(f"- {item}" for item in visible)


def _format_tokens(tokens: int) -> str:
    if tokens < 1_000:
        return str(tokens)
    if tokens < 10_000:
        value = tokens / 1_000
        return f"{value:.1f}k".replace(".0k", "k")
    return f"{round(tokens / 1_000)}k"


def _format_duration(started_at: float | None) -> str:
    if started_at is None:
        return "00:00"
    elapsed_seconds = max(0, int(time.monotonic() - started_at))
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"
