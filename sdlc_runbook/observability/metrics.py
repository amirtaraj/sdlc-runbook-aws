"""AgentOps metrics: every LLM call and external API call, with latency, tokens and outcome.

Records are kept in memory for the /metrics summary and appended to a JSONL file
so nothing is lost on restart.
"""
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from ..config import price_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LLMCallRecord:
    stage: str
    deployment: str
    latency_ms: int
    success: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    run_id: str | None = None
    timestamp: str = field(default_factory=_now)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        price_in, price_out = price_for(self.deployment)
        return (self.prompt_tokens * price_in + self.completion_tokens * price_out) / 1_000_000


@dataclass(frozen=True)
class ServiceCallRecord:
    service: str      # content_safety | pii | search | devops
    operation: str
    latency_ms: int
    success: bool
    error: str | None = None
    timestamp: str = field(default_factory=_now)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def _latency_stats(latencies: list[int], successes: int) -> dict:
    count = len(latencies)
    return {
        "calls": count,
        "success_rate": round(successes / count, 3) if count else None,
        "avg_latency_ms": round(mean(latencies)) if latencies else 0,
        "p95_latency_ms": _p95(latencies),
    }


class MetricsRecorder:
    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path
        self._lock = threading.Lock()
        self._llm: list[LLMCallRecord] = []
        self._services: list[ServiceCallRecord] = []

    def record_llm_call(self, record: LLMCallRecord) -> None:
        with self._lock:
            self._llm.append(record)
            self._append({"type": "llm_call", **asdict(record), "total_tokens": record.total_tokens,
                          "cost_usd": round(record.cost_usd, 6)})

    def record_service_call(self, record: ServiceCallRecord) -> None:
        with self._lock:
            self._services.append(record)
            self._append({"type": "service_call", **asdict(record)})

    def run_usage(self, run_id: str) -> dict:
        with self._lock:
            calls = [r for r in self._llm if r.run_id == run_id]
        return {
            "llm_calls": len(calls),
            "prompt_tokens": sum(r.prompt_tokens for r in calls),
            "completion_tokens": sum(r.completion_tokens for r in calls),
            "total_tokens": sum(r.total_tokens for r in calls),
            "cost_usd": round(sum(r.cost_usd for r in calls), 6),
        }

    def summary(self) -> dict:
        with self._lock:
            llm, services = list(self._llm), list(self._services)

        by_stage = {}
        for stage in sorted({r.stage for r in llm}):
            rows = [r for r in llm if r.stage == stage]
            by_stage[stage] = {
                **_latency_stats([r.latency_ms for r in rows], sum(r.success for r in rows)),
                "total_tokens": sum(r.total_tokens for r in rows),
            }

        by_service = {}
        for name in sorted({r.service for r in services}):
            rows = [r for r in services if r.service == name]
            by_service[name] = _latency_stats([r.latency_ms for r in rows], sum(r.success for r in rows))

        return {
            "llm": {
                **_latency_stats([r.latency_ms for r in llm], sum(r.success for r in llm)),
                "prompt_tokens": sum(r.prompt_tokens for r in llm),
                "completion_tokens": sum(r.completion_tokens for r in llm),
                "total_tokens": sum(r.total_tokens for r in llm),
                "estimated_cost_usd": round(sum(r.cost_usd for r in llm), 6),
                "by_stage": by_stage,
                "recent_errors": [
                    {"stage": r.stage, "error": r.error, "timestamp": r.timestamp} for r in llm if not r.success
                ][-5:],
            },
            "services": by_service,
        }

    def _append(self, row: dict) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
