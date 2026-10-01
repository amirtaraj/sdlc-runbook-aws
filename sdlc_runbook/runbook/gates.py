"""Quality-gate engine: machine checks declared in RUNBOOK.md, run on every stage output.

Paths are dotted and lists flatten, so `tasks.traces_to` is every requirement id any task
traces to. `@stage.path` reads another stage's approved output; if that stage has no
approved output yet, the gate is skipped (reported as passed with a note).
"""
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from .estimates import estimate_to_hours


@dataclass(frozen=True)
class GateResult:
    check: str
    args: str
    description: str
    passed: bool
    detail: str


class _Skip(Exception):
    pass


def _flatten(value, parts: list[str]) -> list:
    if isinstance(value, list):
        return [v for item in value for v in _flatten(item, parts)]
    if not parts:
        return [value]
    if isinstance(value, dict):
        return _flatten(value.get(parts[0]), parts[1:]) if parts[0] in value else []
    return []


def _resolve(path: str, output: dict, approved: dict[str, dict]) -> list:
    if path.startswith("@"):
        stage, _, rest = path[1:].partition(".")
        if stage not in approved:
            raise _Skip(f"no approved {stage} output")
        return _flatten(approved[stage], rest.split(".") if rest else [])
    return _flatten(output, path.split("."))


def _preview(values, limit: int = 5) -> str:
    values = sorted(str(v) for v in values)
    more = f" (+{len(values) - limit} more)" if len(values) > limit else ""
    return ", ".join(values[:limit]) + more


def _required(args, output, approved):
    values = _resolve(args, output, approved)
    ok = bool(values) and all(v not in (None, "", []) and (not isinstance(v, str) or v.strip()) for v in values)
    return ok, "present" if ok else f"'{args}' is empty"


def _id_format(args, output, approved):
    path, pattern = args.split(maxsplit=1)
    rx = re.compile(pattern)
    bad = [v for v in _resolve(path, output, approved) if not isinstance(v, str) or not rx.fullmatch(v)]
    return not bad, "all match" if not bad else f"bad ids: {_preview(bad)}"


def _unique(args, output, approved):
    dupes = [v for v, n in Counter(map(str, _resolve(args, output, approved))).items() if n > 1]
    return not dupes, "no duplicates" if not dupes else f"duplicates: {_preview(dupes)}"


def _refs(args, output, approved):
    """`refs: A in B` or `refs: A in B, C`: every id at A exists in at least one of the listed paths."""
    left, right = (p.strip() for p in args.split(" in ", 1))
    known: set[str] = set()
    for path in (p.strip() for p in right.split(",")):
        known |= set(map(str, _resolve(path, output, approved)))
    unknown = set(map(str, _resolve(left, output, approved))) - known
    return not unknown, "all references resolve" if not unknown else f"unknown ids: {_preview(unknown)}"


def _covered(args, output, approved):
    left, right = (p.strip() for p in args.split(" by ", 1))
    missing = set(map(str, _resolve(left, output, approved))) - set(map(str, _resolve(right, output, approved)))
    return not missing, "all covered" if not missing else f"not covered: {_preview(missing)}"


def _max_days(args, output, approved):
    path, limit = args.split()
    over = []
    for v in _resolve(path, output, approved):
        hours = estimate_to_hours(str(v))
        if hours is None or hours / 8 > float(limit):
            over.append(v)
    return not over, f"all within {limit}d" if not over else f"over {limit}d or unreadable: {_preview(over)}"


def _count(args, output, approved):
    path, low, high = args.split()
    n = len(_resolve(path, output, approved))
    ok = int(low) <= n <= int(high)
    return ok, f"{n} item(s)" if ok else f"{n} item(s), expected {low}-{high}"


def _each_count(args, output, approved):
    """`each_count: <list path> <field> <min> <max>`: every item's <field> list has min..max entries."""
    path, field, low, high = args.split()
    bad = []
    for index, item in enumerate(_resolve(path, output, approved)):
        if not isinstance(item, dict):
            continue
        n = len(item.get(field) or [])
        if not int(low) <= n <= int(high):
            label = item.get("task_id") or item.get("id") or f"#{index + 1}"
            bad.append(f"{label} ({n})")
    return not bad, f"every item has {low}-{high} {field}" if not bad else f"outside {low}-{high}: {_preview(bad)}"


CHECKS: dict[str, Callable] = {
    "required": _required,
    "id_format": _id_format,
    "unique": _unique,
    "refs": _refs,
    "covered": _covered,
    "max_days": _max_days,
    "count": _count,
    "each_count": _each_count,
}


def run_gates(gates, output: dict, approved: dict[str, dict]) -> list[GateResult]:
    results = []
    for gate in gates:
        try:
            passed, detail = CHECKS[gate.check](gate.args, output, approved)
        except _Skip as e:
            passed, detail = True, f"skipped: {e}"
        except (ValueError, re.error) as e:
            passed, detail = False, f"gate misconfigured: {e}"
        results.append(GateResult(gate.check, gate.args, gate.description, passed, detail))
    return results
