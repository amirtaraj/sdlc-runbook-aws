"""Heuristic prompt-injection / jailbreak detector.

Pattern-based, so it catches common, explicit attacks (instruction overrides, role
hijacking, prompt extraction, fake system markers) but not subtle or novel ones. Swap in
Azure AI Content Safety Prompt Shields for model-based detection.
"""
import re

_PATTERNS = [
    # Instruction override
    r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the|system)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|guidelines|directions|constraints)\b",
    r"\bnew (instructions?|rules?)\s*[:\-]",
    # Role hijacking / jailbreak personas
    r"\byou are (now|no longer)\b",
    r"\b(act|behave|respond) as (if you (are|were)|an? )?(unrestricted|unfiltered|jailbroken|evil|dan)\b",
    r"\b(do anything now|developer mode|jailbreak|jail-break|god mode)\b",
    r"\bpretend\b[^.\n]{0,40}\b(no|without)\b[^.\n]{0,20}\b(rules|restrictions|limits|filters|guidelines)\b",
    # Prompt / secret extraction
    r"\b(reveal|print|show|repeat|output|leak|tell me)\b[^.\n]{0,30}\b(system prompt|your (instructions|prompt|rules)|hidden (prompt|instructions))\b",
    r"\b(api[_ -]?key|password|secret|credentials?)\b[^.\n]{0,20}\b(you (have|know|were given)|in your (prompt|context))\b",
    # Fake role / system markers
    r"<\s*/?\s*(system|assistant|im_start|im_end)\s*>",
    # "System:" alone is a normal heading in requirement documents; only flag it when
    # followed by instruction-like wording aimed at the model.
    r"^\s*(system|assistant)\s*:\s*(you are|you must|ignore|disregard|from now on|new instructions)\b",
    r"\[\s*(system|inst)\s*\]",
    r"#{2,}\s*(system prompt|system instructions?|instructions? for the (ai|assistant|model))\b",
    # Output-format hijack aimed at the model itself (not a system requirement like "respond in XML")
    r"\b(you|the (ai|assistant|model))\b[^.\n]{0,20}\b(must|should)\b[^.\n]{0,20}\b(respond|reply|answer|output)\b[^.\n]{0,20}\b(only|just)\b[^.\n]{0,20}\b(plain text|prose)\b",
    r"\b(stop|don't|do not)\b[^.\n]{0,15}\b(returning|producing|outputting)\b[^.\n]{0,10}\bjson\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _PATTERNS]


def detect_attack(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED) if text else False
