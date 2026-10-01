"""Append-only audit trail: who did what, to which run, and with what outcome.

Complements trace_log.jsonl (stage outputs and decisions) by also
recording sign-ins, denied requests, guardrail blocks, failures and publish actions.
Never pass secrets or raw user text here; guardrail findings are logged by category.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, path: Path | None):
        self._path = path
        self._lock = threading.Lock()

    def log(self, action: str, actor: str, outcome: str = "success", run_id: str | None = None, **details) -> None:
        if self._path is None:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "run_id": run_id,
            "details": details or None,
        }
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
