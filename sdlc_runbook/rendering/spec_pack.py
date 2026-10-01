"""Spec pack: the approved run as a set of Markdown files for spec-driven development.

Any coding agent given this pack should build the same thing: the tech stack, coding
standards, interfaces, files, steps and tests are all fixed in writing.

  AGENTS.md           how a coding agent must use the pack
  constitution.md     tech stack, project conventions and coding standards (non-negotiable)
  requirements.md     functional and non-functional requirements, assumptions, open questions
  design.md           components, data flow, key decisions, risks
  tasks.md            ordered task list with dependencies and links to each task spec
  tasks/T-xxx.md      one detailed specification per task
  traceability.md     requirement -> component -> task -> spec matrix
"""
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .markdown_renderer import _cell, traceability_rows


def _bullets(items: list, empty: str = "_None._") -> list[str]:
    return [f"- {i}" for i in items] if items else [empty]


def _table(headers: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._"]
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


def task_spec_markdown(spec: dict, task: dict | None = None, standards: dict[str, dict] | None = None) -> str:
    """One task's specification. `task` is the approved backlog entry (for estimate/category)."""
    task = task or {}
    standards = standards or {}
    lines = [
        f"# {spec['task_id']}: {spec['title']}",
        "",
        f"**Traces to:** {', '.join(spec['traces_to']) or '—'}  ",
        f"**Depends on:** {', '.join(spec['depends_on']) or 'none'}  ",
        f"**Estimate:** {task.get('estimate', '—')} · **Category:** {task.get('category', '—')} · "
        f"**Components:** {', '.join(task.get('component_ids', [])) or '—'}",
        "",
        "## Objective", "", spec["objective"], "",
        "## Context", "", spec["context"], "",
        "## Scope", "", "**In scope**", "", *_bullets(spec["scope_in"]), "",
        "**Out of scope**", "", *_bullets(spec["scope_out"]), "",
        "## Files", "",
        *_table(["Path", "Action", "Purpose"], [[f"`{f['path']}`", f["action"], f["purpose"]] for f in spec["files"]]),
        "",
        "## Interfaces", "",
    ]
    if spec["interfaces"]:
        for i in spec["interfaces"]:
            lines += [f"### {i['kind'].upper()} · {i['name']}", "", "```text", i["contract"], "```", ""]
    else:
        lines += ["_None._", ""]
    lines += [
        "## Data model", "",
        *_table(["Entity", "Fields", "Notes"], [[d["entity"], "<br>".join(d["fields"]), d["notes"]] for d in spec["data_model"]]),
        "",
        "## Implementation steps", "",
        *[f"{n}. {step}" for n, step in enumerate(spec["implementation_steps"], 1)],
        "",
        "## Error handling", "", *_bullets(spec["error_handling"]), "",
        "## Coding standards to follow", "",
        *_bullets([f"**{sid}**: {standards.get(sid, {}).get('title', '')}".rstrip(": ") for sid in spec["coding_standards"]]),
        "",
        "## Test cases", "",
        *_table(["ID", "Type", "Given", "When", "Then"],
                [[t["id"], t["type"], t["given"], t["when"], t["then"]] for t in spec["test_cases"]]),
        "",
        "## Acceptance criteria", "", *[f"- [ ] {a}" for a in spec["acceptance_criteria"]], "",
        "## Definition of done", "", *[f"- [ ] {d}" for d in spec["definition_of_done"]], "",
        "## Open questions", "", *_bullets(spec["open_questions"], "_None. Do not guess; raise anything unclear._"), "",
    ]
    return "\n".join(lines)


def _agents_md(title: str, stack: dict | None, task_ids: list[str]) -> str:
    stack_name = stack["name"] if stack else "see constitution.md"
    return "\n".join([
        f"# AGENTS.md: how to build {title}",
        "",
        "This pack is the complete, approved specification. Implement it exactly; do not redesign it.",
        "",
        "## Read first",
        "",
        "1. `constitution.md`: tech stack, project layout and coding standards. These are non-negotiable.",
        "2. `requirements.md` and `design.md`: what is being built and why.",
        "3. `tasks.md`: the order of work. Then the spec for your task in `tasks/`.",
        "",
        "## Rules",
        "",
        f"- Use only the {stack_name} stack and the libraries named in `constitution.md`.",
        "- Implement one task at a time, in the order in `tasks.md`, respecting `Depends on`.",
        "- Create and change only the files listed in the task spec. If another file must change, stop and say why.",
        "- Match every interface contract exactly (names, paths, fields, types, status codes).",
        "- Write every listed test case first, then the code to make it pass. Name tests after the case ids.",
        "- Follow each coding standard the task cites (STD-CODE-xx) and the constitution's conventions.",
        "- Do not invent requirements. If something is ambiguous or missing, list it under open questions instead of guessing.",
        "- Use synthetic data only. Never add secrets or personal data to code, tests or fixtures.",
        "- A task is done only when every acceptance criterion and definition-of-done item is checked.",
        "",
        "## Commits",
        "",
        "One branch per task: `<task-id>-<short-description>`. Reference the task id in every commit message.",
        "",
        "## Tasks in this pack",
        "",
        *[f"- [{tid}](tasks/{tid}.md)" for tid in task_ids],
        "",
    ])


def _constitution_md(stack: dict | None, standards: list[dict], nfrs: list[dict]) -> str:
    lines = ["# Constitution", "", "Rules every task must follow. A change that breaks one of these is not done.", ""]
    if stack:
        lines += [f"## Tech stack: {stack['name']}", "",
                  *_table(["Layer", "Choice"], [[k.capitalize(), v] for k, v in stack["layers"].items()]),
                  "", "## Project conventions", "", *_bullets(stack["conventions"]), ""]
    lines += ["## Coding standards", ""]
    for doc in standards:
        lines += [f"### {doc['id']}: {doc['title']}", "", doc["content"], ""]
    if not standards:
        lines += ["_No coding standards were available when this pack was built._", ""]
    if nfrs:
        lines += ["## Non-functional requirements (apply to every task)", "",
                  *_bullets([f"**{n['id']}** ({n['category']}): {n['text']}" for n in nfrs]), ""]
    return "\n".join(lines)


def _requirements_md(req: dict) -> str:
    return "\n".join([
        f"# Requirements: {req.get('title', '')}", "",
        "## Functional requirements", "",
        *_table(["ID", "Priority", "Requirement"],
                [[f["id"], f["priority"], f["text"]] for f in req.get("functional_requirements", [])]),
        "", "## Non-functional requirements", "",
        *_table(["ID", "Category", "Requirement"],
                [[n["id"], n["category"], n["text"]] for n in req.get("non_functional_requirements", [])]),
        "", "## Assumptions", "", *_bullets(req.get("assumptions", [])),
        "", "## Open questions", "", *_bullets(req.get("open_questions", [])), "",
    ])


def _design_md(design: dict) -> str:
    return "\n".join([
        "# Design", "", design.get("overview", ""), "",
        "## Components", "",
        *_table(["ID", "Name", "Responsibility", "Satisfies"],
                [[c["id"], c["name"], c["responsibility"], ", ".join(c["satisfies"])] for c in design.get("components", [])]),
        "", "## Data flow", "", *[f"{n}. {s}" for n, s in enumerate(design.get("data_flow", []), 1)],
        "", "## Key decisions", "",
        *_table(["Decision", "Rationale"], [[d["decision"], d["rationale"]] for d in design.get("key_decisions", [])]),
        "", "## Risks", "", *_bullets(design.get("risks", [])), "",
    ])


def _tasks_md(tasks: list[dict], specs: dict[str, dict]) -> str:
    rows = []
    for t in tasks:
        spec = specs.get(t["id"], {})
        rows.append([f"[{t['id']}](tasks/{t['id']}.md)", t["title"], ", ".join(spec.get("depends_on", [])) or "—",
                     t.get("estimate", ""), ", ".join(t.get("traces_to", [])) or "—"])
    return "\n".join(["# Tasks", "", "Implement in this order.", "",
                      *_table(["Task", "Title", "Depends on", "Estimate", "Traces to"], rows), ""])


def _traceability_md(outputs: dict[str, dict], specs: dict[str, dict]) -> str:
    rows = traceability_rows(outputs)
    table = [[r["id"], r["text"], ", ".join(r["components"]) or "—",
              ", ".join(f"[{t}](tasks/{t}.md)" for t in r["tasks"]) or "—",
              str(sum(len(specs.get(t, {}).get("test_cases", [])) for t in r["tasks"]))] for r in rows]
    return "\n".join(["# Traceability", "",
                      *_table(["Requirement", "Description", "Components", "Task specs", "Test cases"], table), ""])


def build_spec_pack(run_id: str, outputs: dict[str, dict], tech_stack: dict | None,
                    documents: dict[str, dict], spec_stage_id: str = "specification",
                    collect_as: str = "specs") -> dict[str, str]:
    """Return {relative path: markdown} for the whole pack."""
    req = outputs.get("requirements", {})
    design = outputs.get("design", {})
    tasks = outputs.get("tasks", {}).get("tasks", [])
    specs = {s["task_id"]: s for s in outputs.get(spec_stage_id, {}).get(collect_as, [])}
    coding = sorted((d for d in documents.values() if d.get("category") == "coding"), key=lambda d: d["id"])
    title = req.get("title") or "the solution"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    files = {
        "AGENTS.md": _agents_md(title, tech_stack, [t["id"] for t in tasks]),
        "constitution.md": _constitution_md(tech_stack, coding, req.get("non_functional_requirements", [])),
        "requirements.md": _requirements_md(req),
        "design.md": _design_md(design),
        "tasks.md": _tasks_md(tasks, specs),
        "traceability.md": _traceability_md(outputs, specs),
    }
    tasks_by_id = {t["id"]: t for t in tasks}
    for task_id, spec in specs.items():
        files[f"tasks/{task_id}.md"] = task_spec_markdown(spec, tasks_by_id.get(task_id), documents)
    files["README.md"] = (f"# Spec pack: {title}\n\nRun `{run_id}`, built {built}.\n\n"
                          "Start with [AGENTS.md](AGENTS.md).\n")
    return files


def write_spec_pack_zip(path: Path, files: dict[str, str], folder: str) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in sorted(files.items()):
            z.writestr(f"{folder}/{name}", text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path
