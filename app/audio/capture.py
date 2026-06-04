from __future__ import annotations

import io
import logging
import math
import threading
import wave
from array import array
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.audio.audio_buffer import AudioChunk, AudioChunkQueue
from app.config import Settings


LOGGER = logging.getLogger(__name__)


class WasapiLoopbackCapture:
    def __init__(
        self,
        settings: Settings,
        output_queue: AudioChunkQueue,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._settings = settings
        self._output_queue = output_queue
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            import pyaudiowpatch  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("PyAudioWPatch is required for real WASAPI Loopback capture.") from exc
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="wasapi-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _capture_loop(self) -> None:
        try:
            self._run_capture_loop()
        except Exception as exc:
            LOGGER.exception("WASAPI loopback capture failed.")
            if self._on_error:
                self._on_error(exc)

    def _run_capture_loop(self) -> None:
        import pyaudiowpatch as pyaudio

        audio = pyaudio.PyAudio()
        stream = None
        try:
            device = self._find_default_loopback_device(audio, pyaudio)
            channels = max(1, int(device.get("maxInputChannels") or device.get("maxOutputChannels") or 2))
            sample_rate = int(device.get("defaultSampleRate") or 44100)
            sample_width = audio.get_sample_size(pyaudio.paInt16)
            frames_per_buffer = self._settings.audio_frames_per_buffer
            frames_per_chunk = max(1, int(sample_rate * self._settings.audio_chunk_seconds))

            LOGGER.info(
                "Capturing WASAPI loopback from '%s' at %s Hz, %s channel(s).",
                device.get("name"),
                sample_rate,
                channels,
            )

            stream = audio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=int(device["index"]),
                frames_per_buffer=frames_per_buffer,
            )

            current_frames: list[bytes] = []
            current_frame_count = 0
            chunk_started_at = datetime.now()

            while not self._stop_event.is_set():
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                current_frames.append(data)
                current_frame_count += frames_per_buffer

                if current_frame_count < frames_per_chunk:
                    continue

                ended_at = datetime.now()
                pcm_bytes = b"".join(current_frames)
                rms = _calculate_rms(pcm_bytes)
                wav_bytes = _build_wav_bytes(pcm_bytes, channels, sample_width, sample_rate)
                chunk = AudioChunk(
                    wav_bytes=wav_bytes,
                    started_at=chunk_started_at,
                    ended_at=ended_at,
                    sample_rate=sample_rate,
                    channels=channels,
                    sample_width=sample_width,
                    rms=rms,
                )

                try:
                    self._output_queue.put(chunk, timeout=1.0)
                    LOGGER.info("Captured %.1fs audio chunk, RMS %.1f.", chunk.duration_seconds, rms)
                except Exception:
                    LOGGER.exception("Audio queue is full; dropping captured chunk.")

                current_frames = []
                current_frame_count = 0
                chunk_started_at = datetime.now()
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio.terminate()

    def _find_default_loopback_device(self, audio: Any, pyaudio: Any) -> dict[str, Any]:
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

        raise RuntimeError("No WASAPI Loopback device was found. This app requires real Windows output audio.")


def _build_wav_bytes(pcm_bytes: bytes, channels: int, sample_width: int, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _calculate_rms(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return 0.0
    samples = array("h")
    samples.frombytes(pcm_bytes)
    if not samples:
        return 0.0
    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / len(samples))
