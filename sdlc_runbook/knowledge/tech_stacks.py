"""Tech-stack presets the user picks from at run start (data/tech_stacks.json).

The chosen stack is passed to Design, Tasks and Specification, so every spec names the
same technologies, layout and conventions, which keeps different coding agents consistent.
"""
import json
from pathlib import Path

from ..exceptions import ConfigError


class TechStackCatalog:
    def __init__(self, path: Path):
        if not path.is_file():
            raise ConfigError(f"Tech-stack catalog not found at {path}.")
        stacks = json.loads(path.read_text(encoding="utf-8"))
        if not stacks:
            raise ConfigError("The tech-stack catalog is empty.")
        for s in stacks:
            if not {"id", "name", "layers", "conventions"} <= s.keys():
                raise ConfigError(f"Tech stack {s.get('id', '?')} needs id, name, layers and conventions.")
        self._stacks = {s["id"]: s for s in stacks}
        self.default_id = stacks[0]["id"]

    def list(self) -> list[dict]:
        return list(self._stacks.values())

    def get(self, stack_id: str | None) -> dict:
        stack = self._stacks.get(stack_id or self.default_id)
        if stack is None:
            raise KeyError(stack_id)
        return stack
