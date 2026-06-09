from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass

from app.audio.audio_buffer import AudioChunk
from app.config import Settings


LOGGER = logging.getLogger(__name__)

TECHNICAL_MEETING_INITIAL_PROMPT_TEMPLATE = (
    "This is a technical meeting in {language_name}. The discussion may include software development, "
    "requirements, business rules, bugs, APIs, databases, integrations, refinement, acceptance criteria, "
    "architecture, tests, technical impacts, observability, permissions, logs, and delivery risks."
)

LANGUAGE_NAMES = {
    "pt": "Brazilian Portuguese",
    "pt-br": "Brazilian Portuguese",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
}


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    started_at: float
    ended_at: float


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    segments: list[TranscriptSegment]


class WhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._load_lock = threading.Lock()
        self._initial_prompt = _resolve_initial_prompt(settings)

    def load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper is required for real local transcription.") from exc

            LOGGER.info(
                "Loading faster-whisper model '%s' for language '%s' on %s with compute type %s.",
                self._settings.whisper_model_size,
                self._settings.whisper_language,
                self._settings.whisper_device,
                self._settings.whisper_compute_type,
            )
            self._model = WhisperModel(
                self._settings.whisper_model_size,
                device=self._settings.whisper_device,
                compute_type=self._settings.whisper_compute_type,
            )

    def transcribe(self, chunk: AudioChunk) -> TranscriptResult | None:
        if chunk.rms < self._settings.audio_silence_rms_threshold:
            LOGGER.info("Ignoring silent audio chunk, RMS %.1f.", chunk.rms)
            return None

        self.load()
        assert self._model is not None

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(chunk.wav_bytes)
                temp_path = temp_file.name

            segments_iterator, _info = self._model.transcribe(
                temp_path,
                language=self._settings.whisper_language,
                task="transcribe",
                initial_prompt=self._initial_prompt,
                vad_filter=True,
                beam_size=5,
            )
            segments = [
                TranscriptSegment(text=segment.text.strip(), started_at=segment.start, ended_at=segment.end)
                for segment in segments_iterator
                if segment.text and segment.text.strip()
            ]
            text = " ".join(segment.text for segment in segments).strip()
            if not text:
                LOGGER.info("Ignoring empty transcription result.")
                return None
            LOGGER.info("Transcribed audio chunk: %s", text)
            return TranscriptResult(text=text, segments=segments)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    LOGGER.warning("Could not delete temporary WAV file: %s", temp_path)


def _resolve_initial_prompt(settings: Settings) -> str:
    language_name = _resolve_language_name(settings.whisper_language)
    return TECHNICAL_MEETING_INITIAL_PROMPT_TEMPLATE.format(language_name=language_name)


def _resolve_language_name(language_code: str) -> str:
    normalized = language_code.strip().casefold()
    if normalized in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[normalized]
    base_language = normalized.split("-", maxsplit=1)[0]
    return LANGUAGE_NAMES.get(base_language, language_code)
