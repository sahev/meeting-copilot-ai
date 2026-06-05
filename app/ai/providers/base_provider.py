from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAiProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, payload: dict) -> str:
        raise NotImplementedError

    @property
    def total_consumed_tokens(self) -> int:
        return 0
