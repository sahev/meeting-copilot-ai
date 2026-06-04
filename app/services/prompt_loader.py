from __future__ import annotations

from pathlib import Path


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]

        prompt_path = self._prompts_dir / f"{name}.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        prompt = prompt_path.read_text(encoding="utf-8")
        self._cache[name] = prompt
        return prompt

    def render(self, name: str, **placeholders: object) -> str:
        prompt = self.load(name)
        for key, value in placeholders.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
        return prompt

    def reload(self, name: str | None = None) -> None:
        if name is None:
            self._cache.clear()
            return
        self._cache.pop(name, None)
