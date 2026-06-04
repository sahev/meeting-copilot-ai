from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass

from app.audio.audio_buffer import AudioChunk
from app.config import Settings


LOGGER = logging.getLogger(__name__)

BRAZILIAN_PORTUGUESE_INITIAL_PROMPT = (
    "Esta e uma reuniao tecnica em portugues do Brasil sobre desenvolvimento de software, "
    "requisitos, regras de negocio, bugs, APIs, banco de dados, integracoes, refinamento, "
    "criterios de aceite, arquitetura, testes e impactos tecnicos."
)


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

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is required for real local transcription.") from exc

        LOGGER.info(
            "Loading faster-whisper model '%s' on %s with compute type %s.",
            self._settings.whisper_model_size,
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
                language="pt",
                task="transcribe",
                initial_prompt=BRAZILIAN_PORTUGUESE_INITIAL_PROMPT,
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
