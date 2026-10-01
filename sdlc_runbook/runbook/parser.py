"""Parses runbook/RUNBOOK.md into a Runbook. See the file's header for the format.

Parsing is strict: an unknown setting, input, gate check or a malformed schema fails at
startup with a clear message, rather than producing an agent with silently wrong rules.
"""
import json
import re
from pathlib import Path

from ..config import PROJECT_ROOT
from ..exceptions import ConfigError
from .gates import CHECKS
from .model import EDIT_MODES, SPECIAL_INPUTS, GateSpec, Runbook, StageSpec

DEFAULT_RUNBOOK_PATH = PROJECT_ROOT / "runbook" / "RUNBOOK.md"

REFUSAL_PROPERTY = {
    "type": "object",
    "properties": {"refused": {"type": "boolean"}, "reason": {"type": "string"}},
}

_STAGE_HEADING = re.compile(r"^## Stage:\s*([a-z][a-z0-9_]*)\s*$", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^### (.+?)\s*$", re.MULTILINE)
_SETTING = re.compile(r"^-\s+([A-Za-z ]+):\s*(.+?)\s*$")
_GATE = re.compile(r"^-\s+`([a-z_]+):\s*(.+?)`\s*(?:[-–—]\s*)?(.*)$")
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def strict_schema(schema: dict) -> dict:
    """Make every object strict (all properties required, no extras), as Structured Outputs needs."""
    schema = dict(schema)
    if schema.get("type") == "object":
        props = {k: strict_schema(v) for k, v in schema.get("properties", {}).items()}
        schema.update(properties=props, required=list(props), additionalProperties=False)
    elif schema.get("type") == "array":
        schema["items"] = strict_schema(schema["items"])
    return schema


def _sections(body: str) -> tuple[str, dict[str, str]]:
    """Split a stage body into (settings preamble, {section title: text})."""
    parts = _SECTION_HEADING.split(body)
    preamble, sections = parts[0], {}
    for title, text in zip(parts[1::2], parts[2::2]):
        sections[title.strip().lower()] = text.strip()
    return preamble, sections


def _parse_stage(stage_id: str, body: str, earlier: list[str]) -> StageSpec:
    where = f"RUNBOOK.md stage '{stage_id}'"
    preamble, sections = _sections(body)

    settings = {}
    for line in preamble.splitlines():
        if m := _SETTING.match(line.strip()):
            settings[m.group(1).strip().lower()] = m.group(2)
    unknown = set(settings) - {"title", "reads", "edit mode", "max output tokens", "for each", "item name", "collect as"}
    if unknown:
        raise ConfigError(f"{where}: unknown setting(s) {sorted(unknown)}.")

    for_each = None
    if "for each" in settings:
        target = settings["for each"].strip()
        stage_ref, _, list_path = target.lstrip("@").partition(".")
        if not target.startswith("@") or not list_path or stage_ref not in earlier:
            raise ConfigError(f"{where}: 'For each' must be @<earlier stage>.<list path>, e.g. @tasks.tasks.")
        for_each = (stage_ref, list_path)

    reads = [r.strip() for r in settings.get("reads", "").split(",") if r.strip()]
    bad_reads = [r for r in reads if r not in SPECIAL_INPUTS and r not in earlier]
    if bad_reads:
        raise ConfigError(f"{where}: 'Reads' has {bad_reads}; use {list(SPECIAL_INPUTS)} or an earlier stage id.")

    edit_mode = settings.get("edit mode", "revise").strip().lower()
    if edit_mode not in EDIT_MODES:
        raise ConfigError(f"{where}: 'Edit mode' must be one of {EDIT_MODES}.")

    schema_text = sections.get("output schema", "")
    match = _JSON_BLOCK.search(schema_text)
    if not match:
        raise ConfigError(f"{where}: '### Output schema' needs a ```json block.")
    try:
        schema = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{where}: output schema is not valid JSON ({e}).") from e
    if schema.get("type") != "object":
        raise ConfigError(f"{where}: output schema must be an object.")
    item_schema = None
    collect_as = settings.get("collect as", "items").strip()
    if for_each:
        # The runbook's schema describes ONE item; the stage output collects them under `collect_as`.
        item_schema = strict_schema({**schema, "properties": {"refusal": REFUSAL_PROPERTY, **schema.get("properties", {})}})
        item_without_refusal = strict_schema({**schema, "properties": dict(schema.get("properties", {}))})
        schema = strict_schema({"type": "object", "properties": {
            "refusal": REFUSAL_PROPERTY,
            collect_as: {"type": "array", "items": item_without_refusal},
        }})
    else:
        schema = strict_schema({**schema, "properties": {"refusal": REFUSAL_PROPERTY, **schema.get("properties", {})}})

    gates = []
    for line in sections.get("quality gates", "").splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = _GATE.match(line)
        if not m or m.group(1) not in CHECKS:
            raise ConfigError(f"{where}: cannot read quality gate {line!r}. Known checks: {sorted(CHECKS)}.")
        gates.append(GateSpec(m.group(1), m.group(2).strip(), m.group(3).strip()))

    for required in ("purpose", "instructions"):
        if not sections.get(required):
            raise ConfigError(f"{where}: missing '### {required.title()}' section.")

    return StageSpec(
        id=stage_id,
        title=settings.get("title", stage_id.replace("_", " ").title()),
        purpose=sections["purpose"],
        instructions=sections["instructions"],
        refuse_when=sections.get("refuse when", ""),
        schema=schema,
        gates=gates,
        reads=reads,
        edit_mode=edit_mode,
        max_output_tokens=int(settings.get("max output tokens", 4000)),
        for_each=for_each,
        item_name=settings.get("item name", "item").strip(),
        collect_as=collect_as,
        item_schema=item_schema,
    )


def parse_runbook(text: str) -> Runbook:
    global_match = re.search(r"^## Global rules\s*$(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    if not global_match:
        raise ConfigError("RUNBOOK.md needs a '## Global rules' section before the stages.")

    heads = list(_STAGE_HEADING.finditer(text))
    if not heads:
        raise ConfigError("RUNBOOK.md defines no '## Stage:' sections.")
    stages: list[StageSpec] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stage_id = head.group(1)
        if stage_id in (s.id for s in stages):
            raise ConfigError(f"RUNBOOK.md defines stage '{stage_id}' twice.")
        stages.append(_parse_stage(stage_id, text[head.end():end], [s.id for s in stages]))
    return Runbook(global_match.group(1).strip(), stages)


def load_runbook(path: Path = DEFAULT_RUNBOOK_PATH) -> Runbook:
    if not path.is_file():
        raise ConfigError(f"Runbook not found at {path}.")
    return parse_runbook(path.read_text(encoding="utf-8"))
