from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    meeting_topic: str | None
    audio_chunk_seconds: float
    audio_frames_per_buffer: int
    audio_silence_rms_threshold: int
    transcription_provider: str
    whisper_model_size: str
    whisper_language: str
    whisper_device: str
    whisper_compute_type: str
    vosk_model_path: Path | None
    question_generation_interval_seconds: float
    database_path: Path
    summaries_dir: Path
    ai_provider: str | None
    stackspot_auth_url: str | None
    stackspot_client_id: str | None
    stackspot_client_secret: str | None
    stackspot_agent_url: str
    stackspot_agent_id: str | None
    stackspot_use_conversation: bool
    stackspot_streaming: bool
    devin_api_url: str | None
    devin_api_key: str | None
    gemini_api_url: str
    gemini_api_key: str | None
    gemini_model: str
    groq_api_url: str
    groq_api_key: str | None
    groq_model: str


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _optional_project_path(name: str) -> Path | None:
    value = _optional(name)
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    return Settings(
        meeting_topic=_optional("MEETING_TOPIC"),
        audio_chunk_seconds=_get_float("AUDIO_CHUNK_SECONDS", 5.0),
        audio_frames_per_buffer=_get_int("AUDIO_FRAMES_PER_BUFFER", 1024),
        audio_silence_rms_threshold=_get_int("AUDIO_SILENCE_RMS_THRESHOLD", 120),
        transcription_provider=os.getenv("TRANSCRIPTION_PROVIDER", "faster_whisper").strip() or "faster_whisper",
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "small").strip() or "small",
        whisper_language=os.getenv("WHISPER_LANGUAGE", "pt").strip() or "pt",
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu",
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8",
        vosk_model_path=_optional_project_path("VOSK_MODEL_PATH"),
        question_generation_interval_seconds=_get_float("QUESTION_GENERATION_INTERVAL_SECONDS", 30.0),
        database_path=PROJECT_ROOT / os.getenv("DATABASE_PATH", "meeting_copilot.db"),
        summaries_dir=PROJECT_ROOT / os.getenv("SUMMARIES_DIR", "summaries"),
        ai_provider=_optional("AI_PROVIDER"),
        stackspot_auth_url=_optional("STACKSPOT_AUTH_URL"),
        stackspot_client_id=_optional("STACKSPOT_CLIENT_ID"),
        stackspot_client_secret=_optional("STACKSPOT_CLIENT_SECRET"),
        stackspot_agent_url=os.getenv(
            "STACKSPOT_AGENT_URL",
            "https://genai-inference-app.stackspot.com",
        ).strip()
        or "https://genai-inference-app.stackspot.com",
        stackspot_agent_id=_optional("STACKSPOT_AGENT_ID"),
        stackspot_use_conversation=_get_bool("STACKSPOT_USE_CONVERSATION", False),
        stackspot_streaming=_get_bool("STACKSPOT_STREAMING", False),
        devin_api_url=_optional("DEVIN_API_URL"),
        devin_api_key=_optional("DEVIN_API_KEY"),
        gemini_api_url=os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta").strip()
        or "https://generativelanguage.googleapis.com/v1beta",
        gemini_api_key=_optional("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
        groq_api_url=os.getenv(
            "GROQ_API_URL",
            "https://api.groq.com/openai/v1/chat/completions",
        ).strip()
        or "https://api.groq.com/openai/v1/chat/completions",
        groq_api_key=_optional("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile",
    )
