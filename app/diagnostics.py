from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import dataclass

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.config import PROJECT_ROOT, Settings
from app.storage.sqlite_repository import SQLiteRepository


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool
    detail: str


def run_diagnostics(settings: Settings) -> list[DiagnosticCheck]:
    checks: list[DiagnosticCheck] = []
    checks.append(_check_python_version())
    checks.extend(_check_python_packages())
    checks.append(_check_transcription_configuration(settings))
    checks.append(_check_prompts())
    checks.append(_check_ai_configuration(settings))
    checks.append(_check_sqlite(settings))
    checks.append(_check_summaries_dir(settings))
    checks.append(_check_wasapi_loopback_device())
    return checks


def render_diagnostics(checks: list[DiagnosticCheck]) -> Group:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", overflow="fold")
    table.add_column("Status", width=10)
    table.add_column("Detail", overflow="fold")

    for check in checks:
        status = Text("OK", style="green") if check.ok else Text("FAIL", style="red")
        table.add_row(check.name, status, check.detail)

    failed = sum(1 for check in checks if not check.ok)
    summary = Text(
        "Environment ready." if failed == 0 else f"{failed} check(s) need attention before a real meeting.",
        style="green" if failed == 0 else "yellow",
    )
    return Group(Panel(table, title="ENVIRONMENT DIAGNOSTICS", border_style="cyan"), summary)


def _check_python_version() -> DiagnosticCheck:
    version = sys.version_info
    ok = (3, 10) <= (version.major, version.minor) <= (3, 12)
    detail = f"Python {platform.python_version()} detected. Supported range: 3.10 to 3.12."
    return DiagnosticCheck("Python version", ok, detail)


def _check_python_packages() -> list[DiagnosticCheck]:
    packages = {
        "PyAudioWPatch": "pyaudiowpatch",
        "rich": "rich",
        "httpx": "httpx",
        "pydantic": "pydantic",
        "python-dotenv": "dotenv",
    }
    checks: list[DiagnosticCheck] = []
    for display_name, import_name in packages.items():
        ok = importlib.util.find_spec(import_name) is not None
        detail = "Installed." if ok else f"Missing. Run pip install -r requirements.txt with Python 3.10 to 3.12."
        checks.append(DiagnosticCheck(display_name, ok, detail))
    return checks


def _check_transcription_configuration(settings: Settings) -> DiagnosticCheck:
    provider = settings.transcription_provider.casefold().replace("-", "_")
    if provider in {"faster_whisper", "whisper"}:
        ok = importlib.util.find_spec("faster_whisper") is not None
        detail = (
            f"faster-whisper is configured with model {settings.whisper_model_size}."
            if ok
            else "Missing faster-whisper. Run pip install -r requirements.txt."
        )
        return DiagnosticCheck("Transcription provider", ok, detail)
    return DiagnosticCheck(
        "Transcription provider",
        False,
        "Set TRANSCRIPTION_PROVIDER to faster_whisper.",
    )


def _check_prompts() -> DiagnosticCheck:
    prompts_dir = PROJECT_ROOT / "app" / "prompts"
    required = ["context_builder.md", "question_generator.md", "summary.md"]
    missing = [name for name in required if not (prompts_dir / name).exists()]
    if missing:
        return DiagnosticCheck("Prompt files", False, f"Missing: {', '.join(missing)}")
    return DiagnosticCheck("Prompt files", True, f"Found {len(required)} required prompt files.")


def _check_ai_configuration(settings: Settings) -> DiagnosticCheck:
    provider = (settings.ai_provider or "").casefold()
    if provider == "stackspot":
        ok = bool(
            settings.stackspot_auth_url
            and settings.stackspot_client_id
            and settings.stackspot_client_secret
            and settings.stackspot_agent_url
            and settings.stackspot_agent_id
        )
        detail = (
            f"StackSpot Agent API is configured for agent {settings.stackspot_agent_id}."
            if ok
            else "Set STACKSPOT_AUTH_URL, STACKSPOT_CLIENT_ID, STACKSPOT_CLIENT_SECRET, and STACKSPOT_AGENT_ID."
        )
        return DiagnosticCheck("AI provider", ok, detail)
    if provider == "groq":
        ok = bool(settings.groq_api_url and settings.groq_api_key and settings.groq_model)
        detail = f"Groq is configured with model {settings.groq_model}." if ok else "Set GROQ_API_KEY and GROQ_MODEL."
        return DiagnosticCheck("AI provider", ok, detail)
    return DiagnosticCheck("AI provider", False, "Set AI_PROVIDER to stackspot or groq.")


def _check_sqlite(settings: Settings) -> DiagnosticCheck:
    try:
        SQLiteRepository(settings.database_path)
    except Exception as exc:
        return DiagnosticCheck("SQLite", False, f"Cannot initialize database: {exc}")
    return DiagnosticCheck("SQLite", True, f"Database path is usable: {settings.database_path}")


def _check_summaries_dir(settings: Settings) -> DiagnosticCheck:
    test_path = settings.summaries_dir / "diagnostics_write_test.tmp"
    try:
        settings.summaries_dir.mkdir(parents=True, exist_ok=True)
        test_path.write_text("ok", encoding="utf-8")
        if test_path.read_text(encoding="utf-8") != "ok":
            raise RuntimeError("Summary write verification read back unexpected content.")
    except Exception as exc:
        return DiagnosticCheck("Summary directory", False, f"Cannot write summaries: {exc}")

    cleanup_detail = ""
    try:
        test_path.unlink(missing_ok=True)
    except Exception as exc:
        cleanup_detail = f" Cleanup warning: {exc}"

    return DiagnosticCheck(
        "Summary directory",
        True,
        f"Summary directory is writable: {settings.summaries_dir}.{cleanup_detail}",
    )


def _check_wasapi_loopback_device() -> DiagnosticCheck:
    if importlib.util.find_spec("pyaudiowpatch") is None:
        return DiagnosticCheck("WASAPI Loopback", False, "PyAudioWPatch is not installed.")

    try:
        import pyaudiowpatch as pyaudio

        audio = pyaudio.PyAudio()
        try:
            device = _find_loopback_device(audio, pyaudio)
        finally:
            audio.terminate()
    except Exception as exc:
        return DiagnosticCheck("WASAPI Loopback", False, f"No usable loopback device detected: {exc}")

    return DiagnosticCheck("WASAPI Loopback", True, f"Detected loopback device: {device.get('name', 'unknown')}")


def _find_loopback_device(audio: object, pyaudio: object) -> dict:
    if hasattr(audio, "get_default_wasapi_loopback"):
        device = audio.get_default_wasapi_loopback()
        if device and device.get("isLoopbackDevice"):
            return device

    wasapi_info = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_output = audio.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    default_name = str(default_output.get("name", "")).lower()

    if default_output.get("isLoopbackDevice"):
        return default_output

    for device in audio.get_loopback_device_info_generator():
        name = str(device.get("name", "")).lower()
        if default_name and default_name in name:
            return device

    loopback_devices = list(audio.get_loopback_device_info_generator())
    if loopback_devices:
        return loopback_devices[0]

    raise RuntimeError("No WASAPI Loopback device found.")
