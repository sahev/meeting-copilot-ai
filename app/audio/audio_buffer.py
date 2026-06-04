from __future__ import annotations

import queue
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AudioChunk:
    wav_bytes: bytes
    started_at: datetime
    ended_at: datetime
    sample_rate: int
    channels: int
    sample_width: int
    rms: float

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()


class AudioChunkQueue:
    def __init__(self, maxsize: int = 8) -> None:
        self._queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=maxsize)

    def put(self, chunk: AudioChunk, timeout: float = 1.0) -> None:
        self._queue.put(chunk, timeout=timeout)

    def get(self, timeout: float = 0.5) -> AudioChunk:
        return self._queue.get(timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()

    def size(self) -> int:
        return self._queue.qsize()
