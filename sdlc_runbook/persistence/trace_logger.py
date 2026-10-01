"""Append-only JSONL run log: one entry per decided stage.

Besides the stage output and decision, each entry records `actor` (who decided),
`gates_failed` (quality gates that did not pass) and `gate_override` (the reason given
when approving despite them).
"""
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Decision = Literal["approved", "edited", "rejected"]


@dataclass(frozen=True)
class TraceEntry:
    run_id: str
    stage: str
    output: dict
    decision: Decision
    edit_note: str | None = None
    actor: str | None = None
    gate_override: str | None = None
    gates_failed: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TraceLogger:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def log(self, entry: TraceEntry) -> None:
        record = {
            "run_id": entry.run_id,
            "stage": entry.stage,
            "timestamp": entry.timestamp,
            "output": entry.output,
            "decision": entry.decision,
            "edit_note": entry.edit_note,
            "actor": entry.actor,
            "gates_failed": entry.gates_failed,
            "gate_override": entry.gate_override,
        }
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
