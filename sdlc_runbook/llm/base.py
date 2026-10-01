"""LLM client interface. Agents depend on this, not on a specific provider."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    def complete_json(self, deployment: str, messages: list[dict], schema_name: str, schema: dict,
                      max_tokens: int) -> LLMResult:
        """Return a completion constrained to `schema`, with token usage."""
        ...
