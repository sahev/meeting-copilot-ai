from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAiProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, payload: dict) -> str:
        raise NotImplementedError
