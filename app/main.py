from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt

from app.agents.context_builder_agent import ContextBuilderAgent
from app.agents.question_generator_agent import QuestionGeneratorAgent
from app.agents.summary_agent import SummaryAgent
from app.ai.ai_client import build_ai_provider
from app.audio.audio_buffer import AudioChunkQueue
from app.audio.capture import WasapiLoopbackCapture
from app.config import load_settings
from app.config import PROJECT_ROOT
from app.context.context_builder import ContextPipeline
from app.context.meeting_context import MeetingContext
from app.context.context_store import MeetingContextStore
from app.diagnostics import render_diagnostics, run_diagnostics
from app.services.agent_registry import AgentRegistry
from app.services.prompt_loader import PromptLoader
from app.storage.sqlite_repository import SQLiteRepository, write_summary_file
from app.transcription.whisper_transcriber import WhisperTranscriber
from app.ui.console import ThreadSafeConsoleState, render_console


logging.basicConfig(
    filename="meeting_copilot.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

console = Console()


class MeetingRuntime:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.audio_queue = AudioChunkQueue()
        self.console_state = ThreadSafeConsoleState()
        self.capture = WasapiLoopbackCapture(self.settings, self.audio_queue, on_error=self._capture_error)
        self.transcriber = WhisperTranscriber(self.settings)
        self.provider = build_ai_provider(self.settings)
        self.repository = SQLiteRepository(self.settings.database_path)
        self.meeting_id = self.repository.create_meeting(self.settings.meeting_topic)
        self.context_store = MeetingContextStore()
        self.prompt_loader = PromptLoader(PROJECT_ROOT / "app" / "prompts")
        self.registry = AgentRegistry()
        self.context_builder_agent = ContextBuilderAgent(self.prompt_loader, self.provider)
        self.question_generator_agent = QuestionGeneratorAgent(self.prompt_loader, self.provider)
        self.summary_agent = SummaryAgent(self.prompt_loader, self.provider)
        self.registry.register("context_builder", self.context_builder_agent)
        self.registry.register("question_generator", self.question_generator_agent)
        self.registry.register("summary", self.summary_agent)
        self.context_pipeline = ContextPipeline(self.context_store, self.context_builder_agent)
        self.last_question_generation_at = 0.0
        self.summary_path: Path | None = None
        self._stopped = False
        self._stop_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

    def start(self) -> None:
        self.stop_event.clear()
        self.console_state.update(capturing=True, transcribing=False, meeting_started_at=time.monotonic())
        self.capture.start()
        self.worker = threading.Thread(target=self._transcription_loop, name="transcription-worker", daemon=True)
        self.worker.start()
        try:
            self._run_live_view()
        finally:
            self.stop()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True

        self.stop_event.set()
        self.console_state.update(capturing=False, transcribing=False)
        self.capture.stop()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=10)

        try:
            self._finalize_meeting()
        finally:
            self.repository.finish_meeting(self.meeting_id)

    def _transcription_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                chunk = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                self.console_state.update(audio_queue_size=self.audio_queue.size())
                continue

            try:
                self.console_state.update(transcribing=True, audio_queue_size=self.audio_queue.size())
                result = self.transcriber.transcribe(chunk)
                if result:
                    self.console_state.add_transcript(result.text)
                    self.repository.add_transcription(self.meeting_id, result.text)
            except Exception as exc:
                logging.exception("Transcription failed.")
                self.console_state.update(error=str(exc))
                result = None
            finally:
                self.audio_queue.task_done()
                self.console_state.update(transcribing=False, audio_queue_size=self.audio_queue.size())

            if result:
                try:
                    self._process_context(result.text)
                except Exception as exc:
                    logging.exception("Context pipeline failed.")
                    self.console_state.update(error=f"Context pipeline failed: {exc}")

    def _capture_error(self, exc: Exception) -> None:
        self.console_state.update(capturing=False, error=str(exc))
        self.stop_event.set()

    def _process_context(self, transcript: str) -> None:
        self.console_state.update(updating_context=True)
        try:
            context = self.context_pipeline.process_transcript(transcript, self.settings.meeting_topic)
            self.repository.save_context_snapshot(self.meeting_id, context)
            self.console_state.update(meeting_context=context)
        finally:
            self._sync_consumed_tokens()
            self.console_state.update(updating_context=False)

        elapsed = time.monotonic() - self.last_question_generation_at
        if elapsed < self.settings.question_generation_interval_seconds:
            return

        if not _has_clear_question_context(context):
            logging.info("Skipping question generation because the context is not mature enough yet.")
            return

        self.console_state.update(generating_questions=True)
        try:
            questions = self.question_generator_agent.generate_questions(context, self.settings.meeting_topic)
            updated_context = self.context_store.merge_questions(questions)
            self.repository.save_generated_questions(self.meeting_id, questions)
            self.repository.save_context_snapshot(self.meeting_id, updated_context)
            self.last_question_generation_at = time.monotonic()
            self.console_state.update(
                meeting_context=updated_context,
                generated_questions=updated_context.generated_questions,
            )
        finally:
            self._sync_consumed_tokens()
            self.console_state.update(generating_questions=False)

    def _finalize_meeting(self) -> None:
        context = self.context_store.snapshot()
        if not context.raw_transcript_tail:
            logging.info("No transcripts were captured; skipping final summary generation.")
            return

        self.console_state.update(generating_summary=True)
        try:
            markdown = self.summary_agent.summarize(context, self.settings.meeting_topic)
            summary_path = write_summary_file(self.settings.summaries_dir, self.meeting_id, markdown)
            self.summary_path = summary_path
            self.repository.save_summary(self.meeting_id, markdown, summary_path)
            self.repository.save_context_snapshot(self.meeting_id, context)
            self.console_state.update(summary_path=str(summary_path))
            console.print(f"[green]Summary saved:[/green] {summary_path}")
        except Exception as exc:
            logging.exception("Final summary generation failed.")
            self.console_state.update(error=f"Final summary failed: {exc}")
            console.print(f"[red]Final summary failed:[/red] {exc}")
        finally:
            self._sync_consumed_tokens()
            self.console_state.update(generating_summary=False)

    def _run_live_view(self) -> None:
        with Live(render_console(self.console_state.snapshot()), console=console, refresh_per_second=4) as live:
            try:
                while not self.stop_event.is_set():
                    live.update(render_console(self.console_state.snapshot()))
                    time.sleep(0.25)
            except KeyboardInterrupt:
                console.print("\nFinishing meeting...")
                self.stop()

    def _sync_consumed_tokens(self) -> None:
        self.console_state.update(consumed_tokens=self.provider.total_consumed_tokens)


def _has_clear_question_context(context: MeetingContext) -> bool:
    signal_fields = [
        "requirements",
        "business_rules",
        "decisions",
        "risks",
        "open_questions",
        "acceptance_criteria",
        "technical_impacts",
        "integrations",
        "dependencies",
        "test_suggestions",
    ]
    signal_count = sum(len(getattr(context, field_name, [])) for field_name in signal_fields)
    has_topic = bool(getattr(context, "current_topic", "").strip())
    has_recent_transcript = len(getattr(context, "raw_transcript_tail", [])) >= 2
    return signal_count >= 2 and (has_topic or has_recent_transcript)


def main() -> None:
    while True:
        console.print("\n[bold]Meeting Copilot CLI[/bold]")
        console.print("1. start")
        console.print("2. finish")
        console.print("3. check env")
        console.print("4. quit")
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4"], default="1")

        if choice == "1":
            runtime: MeetingRuntime | None = None
            try:
                runtime = MeetingRuntime()
                runtime.start()
            except Exception as exc:
                logging.exception("Meeting runtime failed.")
                console.print(f"[red]Error:[/red] {exc}")
                if runtime is not None:
                    runtime.stop()
        elif choice == "2":
            console.print("[yellow]No active meeting in the menu. Start a meeting and press Ctrl+C to finish it.[/yellow]")
        elif choice == "3":
            try:
                settings = load_settings()
                console.print(render_diagnostics(run_diagnostics(settings)))
            except Exception as exc:
                logging.exception("Diagnostics failed.")
                console.print(f"[red]Diagnostics failed:[/red] {exc}")
        elif choice == "4":
            console.print("Goodbye.")
            break


if __name__ == "__main__":
    main()
