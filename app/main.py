from __future__ import annotations

import logging
import msvcrt
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
from app.context.meeting_context import ContextUpdate, MeetingContext
from app.context.context_store import MeetingContextStore
from app.diagnostics import render_diagnostics, run_diagnostics
from app.services.agent_registry import AgentRegistry
from app.services.prompt_loader import PromptLoader
from app.storage.sqlite_repository import SQLiteRepository, write_summary_file
from app.transcription.transcriber_factory import build_transcriber
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
        self.transcriber = build_transcriber(self.settings)
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
        self.last_context_refresh_at = time.monotonic()
        self.pending_context_transcripts: list[str] = []
        self.pending_context_lock = threading.Lock()
        self.question_generation_lock = threading.Lock()
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
                    self._queue_transcript_for_context(result.text)
            except Exception as exc:
                logging.exception("Transcription failed.")
                self.console_state.update(error=str(exc))
                result = None
            finally:
                self.audio_queue.task_done()
                self.console_state.update(transcribing=False, audio_queue_size=self.audio_queue.size())

            if result:
                try:
                    self._maybe_refresh_context()
                except Exception as exc:
                    logging.exception("Context pipeline failed.")
                    self.console_state.update(error=f"Context pipeline failed: {exc}")

    def _capture_error(self, exc: Exception) -> None:
        self.console_state.update(capturing=False, error=str(exc))
        self.stop_event.set()

    def _queue_transcript_for_context(self, transcript: str) -> None:
        cleaned = transcript.strip()
        if not cleaned:
            return
        with self.pending_context_lock:
            self.pending_context_transcripts.append(cleaned)

    def _maybe_refresh_context(self, force: bool = False) -> None:
        elapsed = time.monotonic() - self.last_context_refresh_at
        if not force and elapsed < self.settings.context_refresh_interval_seconds:
            return

        with self.pending_context_lock:
            batch = list(self.pending_context_transcripts)
            transcript = "\n".join(batch).strip()

        if not transcript:
            self.last_context_refresh_at = time.monotonic()
            return

        self.console_state.update(updating_context=True)
        try:
            context = self.context_pipeline.process_transcript(transcript, self.settings.meeting_topic)
            self.repository.save_context_snapshot(self.meeting_id, context)
            self.console_state.update(meeting_context=context)
            with self.pending_context_lock:
                del self.pending_context_transcripts[: len(batch)]
            self.last_context_refresh_at = time.monotonic()
        finally:
            self._sync_consumed_tokens()
            self.console_state.update(updating_context=False)

    def _request_question_generation(self) -> None:
        if self.question_generation_lock.locked():
            self.console_state.update(ai_status="Question generation is already running.")
            return

        worker = threading.Thread(target=self._generate_questions_from_recent_contexts, name="question-worker", daemon=True)
        worker.start()

    def _generate_questions_from_recent_contexts(self) -> None:
        if not self.question_generation_lock.acquire(blocking=False):
            return

        sent_at = time.strftime("%H:%M:%S")
        self.console_state.update(
            ai_status=f"Sent recent context to AI at {sent_at}.",
            generating_questions=True,
        )
        try:
            recent_contexts = self.repository.get_recent_context_snapshots(
                self.meeting_id,
                self.settings.question_context_snapshot_limit,
            )
            if not recent_contexts:
                snapshot = self.context_store.snapshot()
                if _has_clear_question_context(snapshot):
                    recent_contexts = [snapshot]

            if not recent_contexts:
                self.console_state.update(ai_status="No structured context available to send yet.")
                return

            context = _combine_recent_contexts(recent_contexts)
            if not _has_clear_question_context(context):
                logging.info("Skipping question generation because the context is not mature enough yet.")
                self.console_state.update(ai_status="Recent context is not mature enough for questions yet.")
                return

            questions = self.question_generator_agent.generate_questions(context, self.settings.meeting_topic)
            updated_context = self.context_store.merge_questions(questions)
            self.repository.save_generated_questions(self.meeting_id, questions)
            self.repository.save_context_snapshot(self.meeting_id, updated_context)
            self.console_state.update(
                meeting_context=updated_context,
                generated_questions=updated_context.generated_questions,
                ai_status=f"AI returned questions at {time.strftime('%H:%M:%S')}.",
            )
        except Exception as exc:
            logging.exception("Question generation failed.")
            self.console_state.update(error=f"Question generation failed: {exc}", ai_status="Question generation failed.")
        finally:
            self._sync_consumed_tokens()
            self.console_state.update(generating_questions=False)
            self.question_generation_lock.release()

    def _finalize_meeting(self) -> None:
        try:
            self._maybe_refresh_context(force=True)
        except Exception as exc:
            logging.exception("Final context refresh failed.")
            self.console_state.update(error=f"Final context refresh failed: {exc}")

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
                    if _question_shortcut_pressed():
                        self._request_question_generation()
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


def _combine_recent_contexts(contexts: list[MeetingContext]) -> MeetingContext:
    combined = MeetingContext()
    for context in contexts:
        update = ContextUpdate.model_validate(context.model_dump(exclude={"generated_questions", "raw_transcript_tail"}))
        combined.merge_update(update)
        for transcript in context.raw_transcript_tail:
            combined.add_transcript(transcript)
    return combined


def _question_shortcut_pressed() -> bool:
    pressed = False
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key in {"\x00", "\xe0"}:
            scan_code = msvcrt.getwch() if msvcrt.kbhit() else ""
            pressed = pressed or scan_code == "B"  # F8 on Windows terminals.
            continue
        if key == "\x03":
            raise KeyboardInterrupt
        pressed = pressed or key == "\x07"  # Ctrl+G.
    return pressed


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
