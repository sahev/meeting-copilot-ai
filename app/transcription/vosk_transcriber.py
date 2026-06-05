from __future__ import annotations

import io
import json
import logging
import sys
import wave
from array import array

from app.audio.audio_buffer import AudioChunk
from app.config import Settings
from app.transcription.whisper_transcriber import TranscriptResult, TranscriptSegment


LOGGER = logging.getLogger(__name__)

VOSK_SAMPLE_RATE = 16_000


class VoskTranscriber:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        if self._settings.vosk_model_path is None:
            raise RuntimeError("Set VOSK_MODEL_PATH to use the Vosk transcription provider.")
        if not self._settings.vosk_model_path.exists():
            raise RuntimeError(f"Vosk model path does not exist: {self._settings.vosk_model_path}")
        try:
            from vosk import Model
        except ImportError as exc:
            raise RuntimeError("vosk is required for Vosk transcription. Run pip install -r requirements.txt.") from exc

        LOGGER.info("Loading Vosk model from '%s'.", self._settings.vosk_model_path)
        self._model = Model(str(self._settings.vosk_model_path))

    def transcribe(self, chunk: AudioChunk) -> TranscriptResult | None:
        if chunk.rms < self._settings.audio_silence_rms_threshold:
            LOGGER.info("Ignoring silent audio chunk, RMS %.1f.", chunk.rms)
            return None

        self.load()
        assert self._model is not None

        try:
            from vosk import KaldiRecognizer
        except ImportError as exc:
            raise RuntimeError("vosk is required for Vosk transcription. Run pip install -r requirements.txt.") from exc

        pcm = _wav_to_vosk_pcm(chunk.wav_bytes)
        recognizer = KaldiRecognizer(self._model, VOSK_SAMPLE_RATE)
        recognizer.SetWords(True)

        for offset in range(0, len(pcm), 4_000):
            recognizer.AcceptWaveform(pcm[offset : offset + 4_000])

        result = json.loads(recognizer.FinalResult())
        text = str(result.get("text") or "").strip()
        if not text:
            LOGGER.info("Ignoring empty Vosk transcription result.")
            return None

        LOGGER.info("Transcribed audio chunk with Vosk: %s", text)
        return TranscriptResult(
            text=text,
            segments=[
                TranscriptSegment(
                    text=text,
                    started_at=0.0,
                    ended_at=chunk.duration_seconds,
                )
            ],
        )


def _wav_to_vosk_pcm(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())

    samples = _decode_pcm_samples(pcm, sample_width, channels)
    if channels > 1:
        samples = _mix_to_mono(samples, channels)
    if sample_rate != VOSK_SAMPLE_RATE:
        samples = _resample_nearest(samples, sample_rate, VOSK_SAMPLE_RATE)

    output = array("h", samples)
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


def _decode_pcm_samples(pcm: bytes, sample_width: int, channels: int) -> list[int]:
    if sample_width == 1:
        return [(sample - 128) << 8 for sample in pcm]
    if sample_width == 2:
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tolist()
    if sample_width in {3, 4}:
        samples: list[int] = []
        for offset in range(0, len(pcm), sample_width):
            raw = pcm[offset : offset + sample_width]
            if len(raw) != sample_width:
                continue
            value = int.from_bytes(raw, byteorder="little", signed=True)
            samples.append(_clamp_int16(value >> ((sample_width - 2) * 8)))
        return samples
    raise RuntimeError(f"Unsupported WAV sample width for Vosk transcription: {sample_width}")


def _mix_to_mono(samples: list[int], channels: int) -> list[int]:
    mono: list[int] = []
    for offset in range(0, len(samples), channels):
        frame = samples[offset : offset + channels]
        if len(frame) == channels:
            mono.append(_clamp_int16(round(sum(frame) / channels)))
    return mono


def _resample_nearest(samples: list[int], source_rate: int, target_rate: int) -> list[int]:
    if not samples:
        return []
    target_length = max(1, round(len(samples) * target_rate / source_rate))
    return [samples[min(len(samples) - 1, int(index * source_rate / target_rate))] for index in range(target_length)]


def _clamp_int16(value: int) -> int:
    return max(-32768, min(32767, value))
