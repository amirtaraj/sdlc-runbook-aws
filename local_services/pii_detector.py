"""Heuristic PII detector returning Azure AI Language-style entities.

Covers structured identifiers well (email, phone, card numbers with a Luhn check, US SSN,
Indian Aadhaar and PAN, IP addresses, IBAN) and person names only in common explicit
phrasings ("my name is ...", "Mr. ..."). Swap in Azure AI Language for model-based
detection of names, addresses and more.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    text: str
    category: str
    offset: int
    length: int
    confidence: float


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card(match: re.Match) -> bool:
    digits = re.sub(r"\D", "", match.group(0))
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


_RULES: list[tuple[str, re.Pattern, float, object]] = [
    ("Email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.95, None),
    ("CreditCardNumber", re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), 0.9, _card),
    ("USSocialSecurityNumber", re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"), 0.85, None),
    ("INAadharNumber", re.compile(r"(?<!\d)(?<!\d[ -])[2-9]\d{3}[ -]\d{4}[ -]\d{4}(?![ -]?\d)"), 0.8, None),
    ("INPermanentAccount", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), 0.8, None),
    # Boundaries: not inside a longer digit run or a decimal; a trailing full stop is fine.
    ("PhoneNumber", re.compile(r"(?<![\w.])(?<!\d[ -])(?:\+\d{1,3}[ -]?)?(?:\(\d{2,4}\)[ -]?)?\d{3,5}[ -]\d{3,5}(?:[ -]\d{3,4})?(?!\w)(?![ -]?\d)(?!\.\d)"), 0.8, None),
    ("PhoneNumber", re.compile(r"(?<![\w.])\+\d{10,13}(?!\w)(?!\.\d)"), 0.8, None),
    ("IPAddress", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"), 0.8, None),
    ("InternationalBankingAccountNumber", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), 0.75, None),
    ("Person", re.compile(r"\b(?i:my name is|i am|i'm|named|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"), 0.7, None),
    ("Person", re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"), 0.7, None),
]


def detect_pii(text: str) -> list[Entity]:
    entities: list[Entity] = []
    taken: list[tuple[int, int]] = []
    for category, pattern, confidence, check in _RULES:
        for m in pattern.finditer(text):
            if check and not check(m):
                continue
            start, end = m.span(1) if category == "Person" and m.groups() else m.span()
            if any(start < e and s < end for s, e in taken):
                continue  # first (more specific) rule wins on overlapping spans
            taken.append((start, end))
            entities.append(Entity(text[start:end], category, start, end - start, confidence))
    return sorted(entities, key=lambda e: e.offset)


def redact(text: str, entities: list[Entity]) -> str:
    chars = list(text)
    for e in entities:
        chars[e.offset:e.offset + e.length] = "*" * e.length
    return "".join(chars)
