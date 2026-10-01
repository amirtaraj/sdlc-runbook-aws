"""Azure AI Content Safety - Prompt Shields.

POST {endpoint}/contentsafety/text:shieldPrompt?api-version=2024-09-01

Long input is checked in pieces of at most 10,000 characters (the service's limit).
"""
from dataclasses import dataclass

from ..config import ServiceEndpoint
from ..observability import MetricsRecorder
from .chunking import split_text
from .http import ServiceHttpClient

API_VERSION = "2024-09-01"
MAX_PROMPT_CHARS = 10_000


@dataclass(frozen=True)
class ShieldResult:
    user_prompt_attack: bool
    document_attacks: list[bool]

    @property
    def attack_detected(self) -> bool:
        return self.user_prompt_attack or any(self.document_attacks)


class ContentSafetyClient:
    def __init__(self, config: ServiceEndpoint, timeout: float, metrics: MetricsRecorder | None = None, transport=None):
        headers = {"Ocp-Apim-Subscription-Key": config.api_key} if config.api_key else {}
        self._http = ServiceHttpClient("content_safety", config.endpoint, headers, timeout, metrics, transport)

    def shield_prompt(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
        body = self._http.post(
            "shieldPrompt",
            "/contentsafety/text:shieldPrompt",
            params={"api-version": API_VERSION},
            json={"userPrompt": user_prompt, "documents": documents or []},
        )
        return ShieldResult(
            user_prompt_attack=bool(body.get("userPromptAnalysis", {}).get("attackDetected")),
            document_attacks=[bool(d.get("attackDetected")) for d in body.get("documentsAnalysis", [])],
        )

    def attack_in(self, text: str) -> bool:
        """Prompt-shield text of any length, piece by piece."""
        return any(self.shield_prompt(chunk).user_prompt_attack for _, chunk in split_text(text, MAX_PROMPT_CHARS))
