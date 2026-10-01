"""AI guardrails around every model call.

Input (requirement text and every edit correction) - blocked if any check fails:
  1. size limit
  2. secrets / credentials (local patterns: keys, tokens, passwords, connection strings)
  3. PII (Azure AI Language) - the checklist forbids PII and customer data in this solution
  4. prompt injection / jailbreak (Azure AI Content Safety Prompt Shields)

Retrieved knowledge-base passages are screened for indirect prompt injection before
they reach a prompt; flagged passages are dropped.

Output: each stage's output is scanned for PII and flagged (not blocked), so the human
reviewer sees the warning at the approval gate.

Fail closed: if a guardrail service cannot be reached, input is blocked rather than let through.
"""
import re
from dataclasses import dataclass, field

from ..exceptions import GuardrailViolation, ServiceError
from ..services import ContentSafetyClient, KnowledgeDoc, PiiClient

# Matches the document extractor's limit, so an uploaded document can become the requirement.
MAX_INPUT_CHARS = 200_000

# Categories that are not personal data and commonly appear in requirements.
ALLOWED_PII_CATEGORIES = {"Organization", "DateTime", "Quantity", "URL"}

_SECRET_PATTERNS = [
    ("an API key or token", re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("a JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("a password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S{4,}")),
    ("a connection string or account key", re.compile(r"(?i)(AccountKey|SharedAccessKey|client_secret)\s*=\s*\S{8,}")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


@dataclass(frozen=True)
class GuardReport:
    """What a check found. Categories only - never the matched text itself."""

    pii_categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentReview:
    """Guardrail review of an uploaded document, before it becomes a requirement.

    blocking: problems redaction cannot fix (credentials, prompt injection, check unavailable).
    pii_categories / redacted_text: personal data found, and the text with it masked as
    [Category] placeholders, which the user may choose to continue with.
    """

    blocking: list[str]
    pii_categories: list[str]
    redacted_text: str | None


def redact(text: str, entities) -> str:
    """Replace each entity span with a [Category] placeholder (overlaps merged, left to right)."""
    out, cursor = [], 0
    for e in sorted(entities, key=lambda e: e.offset):
        if e.offset < cursor:
            continue
        out += [text[cursor:e.offset], f"[{e.category}]"]
        cursor = e.offset + e.length
    out.append(text[cursor:])
    return "".join(out)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


class Guard:
    def __init__(self, content_safety: ContentSafetyClient, pii: PiiClient):
        self._content_safety = content_safety
        self._pii = pii

    def check_input(self, text: str, label: str = "Input") -> GuardReport:
        """Raise GuardrailViolation if `text` must not be sent to the model."""
        reasons: list[str] = []
        if len(text) > MAX_INPUT_CHARS:
            raise GuardrailViolation([f"{label} is longer than {MAX_INPUT_CHARS:,} characters."])

        reasons += self._secret_reasons(text, label)
        try:
            categories = self._pii_categories(text)
            if categories:
                reasons.append(
                    f"{label} appears to contain personal data ({', '.join(categories)}). "
                    "Use synthetic or anonymised examples only."
                )
            if self._content_safety.attack_in(text):
                reasons.append(f"{label} looks like a prompt-injection or jailbreak attempt.")
        except ServiceError as e:
            raise GuardrailViolation([f"Guardrail check could not run, so the input was blocked: {e}"]) from e

        if reasons:
            raise GuardrailViolation(reasons)
        return GuardReport()

    def review_document(self, text: str) -> DocumentReview:
        """Screen an uploaded document. Never raises: returns what blocks it and what can be redacted."""
        label = "The document"
        blocking = self._secret_reasons(text, label)
        try:
            if self._content_safety.attack_in(text):
                blocking.append(f"{label} contains text that looks like a prompt-injection or jailbreak attempt.")
            entities = [e for e in self._pii.detect(text) if e.category not in ALLOWED_PII_CATEGORIES]
        except ServiceError as e:
            return DocumentReview([f"Guardrail check could not run, so the document was blocked: {e}"], [], None)
        categories = sorted({e.category for e in entities})
        return DocumentReview(blocking, categories, redact(text, entities) if entities else None)

    @staticmethod
    def _secret_reasons(text: str, label: str) -> list[str]:
        return [f"{label} appears to contain {what}. Remove credentials before submitting."
                for what, pattern in _SECRET_PATTERNS if pattern.search(text)]

    def screen_documents(self, docs: list[KnowledgeDoc]) -> list[KnowledgeDoc]:
        """Drop retrieved passages that carry an indirect prompt-injection attack."""
        if not docs:
            return docs
        try:
            result = self._content_safety.shield_prompt("", [d.content for d in docs])
        except ServiceError:
            return []  # fail closed: no grounding rather than unscreened grounding
        return [d for d, attacked in zip(docs, result.document_attacks) if not attacked]

    def scan_output(self, output: dict) -> GuardReport:
        """Flag PII in a stage output. Returns categories for the reviewer; never blocks."""
        try:
            return GuardReport(pii_categories=self._pii_categories("\n".join(_strings(output))))
        except ServiceError:
            return GuardReport(pii_categories=["scan unavailable"])

    def _pii_categories(self, text: str) -> list[str]:
        if not text.strip():
            return []
        found = {e.category for e in self._pii.detect(text)}
        return sorted(found - ALLOWED_PII_CATEGORIES)
