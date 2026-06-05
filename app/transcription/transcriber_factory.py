from __future__ import annotations

from typing import Protocol

from app.audio.audio_buffer import AudioChunk
from app.config import Settings
from app.transcription.vosk_transcriber import VoskTranscriber
from app.transcription.whisper_transcriber import TranscriptResult, WhisperTranscriber


class Transcriber(Protocol):
    def load(self) -> None:
        raise NotImplementedError

    def transcribe(self, chunk: AudioChunk) -> TranscriptResult | None:
        raise NotImplementedError


def build_transcriber(settings: Settings) -> Transcriber:
    provider = settings.transcription_provider.casefold().replace("-", "_")
    if provider in {"faster_whisper", "whisper"}:
        return WhisperTranscriber(settings)
    if provider == "vosk":
        return VoskTranscriber(settings)
    raise RuntimeError("Unknown transcription provider. Set TRANSCRIPTION_PROVIDER to faster_whisper or vosk.")
