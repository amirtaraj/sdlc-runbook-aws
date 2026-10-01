"""Markdown documents, driven by each stage's schema in RUNBOOK.md.

- One document per approved stage:     output/<run_id>/<nn>-<stage>.md
- The assembled pack at completion:    output/<run_id>.md
  (every stage document in order, then the traceability matrix and references)

Rendering is generic: strings become paragraphs, enums become labelled values, string
lists become bullets and lists of objects become tables. Adding a stage to the runbook
needs no renderer change.
"""
import re
from pathlib import Path

from ..runbook import StageSpec


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _cell(value) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value) if all(not isinstance(v, (dict, list)) for v in value) \
            else "; ".join(str(v) for v in value)
    # Keep table cells on one line and stop stray pipes from breaking the table.
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _render_value(key: str, value, schema: dict, level: int) -> list[str]:
    heading = "#" * level + f" {_label(key)}"
    kind = schema.get("type")
    if kind == "string" and "enum" in schema:
        return [f"**{_label(key)}:** {value}", ""]
    if kind in ("string", "boolean"):
        return [heading, "", str(value) if value != "" else "_None._", ""]
    if kind == "array":
        items = schema.get("items", {})
        if not value:
            return [heading, "", "_None._", ""]
        if items.get("type") == "object":
            cols = list(items.get("properties", {}))
            lines = [heading, "", "| " + " | ".join(_label(c) for c in cols) + " |", "|" + "---|" * len(cols)]
            lines += ["| " + " | ".join(_cell(row.get(c, "")) for c in cols) + " |" for row in value]
            return lines + [""]
        return [heading, ""] + [f"- {v}" for v in value] + [""]
    if kind == "object":
        lines = [heading, ""]
        for k, sub in schema.get("properties", {}).items():
            lines += _render_value(k, value.get(k), sub, level + 1)
        return lines
    return [heading, "", str(value), ""]


def render_stage_body(spec: StageSpec, output: dict, level: int = 2) -> list[str]:
    if spec.for_each:
        # Per-item stages (e.g. one spec per task): a short index; full detail is in the stage document.
        items = output.get(spec.collect_as, [])
        return [f"- **{i.get('task_id', '')}** {i.get('title', '')}: {i.get('objective', '')}" for i in items] + [""]
    lines: list[str] = []
    for key, sub in spec.schema["properties"].items():
        if key != "refusal":
            lines += _render_value(key, output.get(key), sub, level)
    return lines


def traceability_rows(outputs: dict[str, dict]) -> list[dict]:
    """Requirement -> components -> tasks, from the ids the stages reference."""
    reqs = outputs.get("requirements", {}).get("functional_requirements", [])
    components = outputs.get("design", {}).get("components", [])
    tasks = outputs.get("tasks", {}).get("tasks", [])
    return [
        {
            "id": r["id"],
            "text": r["text"],
            "components": [c["id"] for c in components if r["id"] in c.get("satisfies", [])],
            "tasks": [t["id"] for t in tasks if r["id"] in t.get("traces_to", [])],
        }
        for r in reqs
    ]


class MarkdownRenderer:
    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    def render_stage(self, run_id: str, index: int, spec: StageSpec, output: dict) -> Path:
        folder = self._output_dir / run_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{index:02d}-{spec.id}.md"
        lines = [f"# {spec.title}", "", f"_Run ID: {run_id}_", ""]
        if spec.for_each:
            from .spec_pack import task_spec_markdown  # local import: spec_pack imports this module

            for item in output.get(spec.collect_as, []):
                # Demote every heading one level so each task sits under the stage title.
                lines += [re.sub(r"(?m)^#", "##", task_spec_markdown(item)), "", "---", ""]
        else:
            lines += render_stage_body(spec, output)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def render_pack(self, run_id: str, specs: list[StageSpec], outputs: dict[str, dict],
                    references: list[dict], source: dict | None = None) -> Path:
        title = outputs.get("requirements", {}).get("title") or "SDLC Runbook pack"
        lines = [f"# {title}", "", f"_Run ID: {run_id}_", ""]
        if source:
            redacted = " Personal data was redacted before analysis." if source.get("redacted") else ""
            lines += [f"_Source document: {_cell(source['filename'])} (SHA-256 {source['sha256'][:12]}…).{redacted}_", ""]
        for spec in specs:
            if spec.id in outputs:
                lines += [f"## {spec.title}", ""] + render_stage_body(spec, outputs[spec.id], level=3)

        rows = traceability_rows(outputs)
        if rows:
            lines += ["## Traceability matrix", "", "| Requirement | Description | Components | Tasks |", "|---|---|---|---|"]
            lines += [f"| {r['id']} | {_cell(r['text'])} | {_cell(r['components']) or '—'} | {_cell(r['tasks']) or '—'} |"
                      for r in rows]
            lines.append("")

        unique = {r["id"]: r["title"] for r in references}
        if unique:
            lines += ["## References", ""] + [f"- **{rid}**: {t}" for rid, t in sorted(unique.items())] + [""]

        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{run_id}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def render_spec_pack(self, run_id: str, spec_stage: StageSpec, outputs: dict[str, dict],
                         tech_stack: dict | None, documents: dict[str, dict]) -> Path:
        """Write the spec pack zip: output/<run_id>-spec-pack.zip."""
        from .spec_pack import build_spec_pack, write_spec_pack_zip

        files = build_spec_pack(run_id, outputs, tech_stack, documents, spec_stage.id, spec_stage.collect_as)
        return write_spec_pack_zip(self._output_dir / f"{run_id}-spec-pack.zip", files, f"spec-pack-{run_id}")
