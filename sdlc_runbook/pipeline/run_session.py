"""One pipeline run, modelled as a state machine.

The stages, their order, inputs, rules and quality gates all come from RUNBOOK.md. Each
agent builds its input from the run context (requirement, clarifications, earlier
approved outputs). Instead of blocking on a prompt, the session pauses in
PENDING_APPROVAL and the caller drives it with approve() / edit() / reject(); the CLI and
the web API are thin adapters over this class.

Governance, per stage:
- Quality gates run on every output. Approving with a failed gate needs a written
  override reason, which is stored in the trace and audit logs.
- If the agent refuses (runbook rule broken), the output cannot be approved; the human
  edits the request or rejects the run.
- Every decision is written to the trace log (one entry per decided stage) and the
  approved output is written as that stage's document.
"""
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from ..agents import RunbookAgent, RunContext, StageInput
from ..exceptions import AgentError, InvalidAction, ServiceError
from ..guardrails import Guard
from ..observability import LLMCallRecord, MetricsRecorder
from ..persistence import TraceEntry, TraceLogger
from ..rendering import MarkdownRenderer
from ..runbook import GateResult, run_gates
from ..runbook.estimates import estimate_to_hours
from ..services import DevOpsClient
from ..services.devops import task_description_html

TITLE_MAX_CHARS = 60


class RunStatus(str, Enum):
    NOT_STARTED = "not_started"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"          # the last agent call errored; retry() re-runs the stage
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StageRecord:
    """A stage that has been decided."""

    stage: str
    output: dict
    decision: str
    edit_note: str | None
    actor: str
    gates: list[GateResult] = field(default_factory=list)
    gate_override: str | None = None
    references: list[dict] = field(default_factory=list)
    pii_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PublishedItem:
    task_id: str
    work_item_id: int
    title: str
    url: str


def new_run_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunSession:
    def __init__(
        self,
        requirement_text: str,
        agents: list[RunbookAgent],
        guard: Guard,
        logger: TraceLogger,
        renderer: MarkdownRenderer,
        metrics: MetricsRecorder,
        devops: DevOpsClient,
        created_by: str,
        on_progress: Callable[[str], None] | None = None,
        source: dict | None = None,
        tech_stack: dict | None = None,
    ):
        self.run_id = new_run_id()
        self.requirement_text = requirement_text
        self.created_by = created_by
        # Uploaded document the requirement came from: filename, kind, sha256, pages, chars, redacted.
        self.source = source
        # Tech-stack preset chosen at run start (data/tech_stacks.json).
        self.tech_stack = tech_stack
        self._agents = agents
        self._guard = guard
        self._logger = logger
        self._renderer = renderer
        self._metrics = metrics
        self._devops = devops
        self._on_progress = on_progress or (lambda _msg: None)

        self.status = RunStatus.NOT_STARTED
        self.stage_index = 0
        self.current_output: dict | None = None
        self.current_gates: list[GateResult] = []
        self.current_references: list[dict] = []
        self.current_pii_flags: list[str] = []
        self.history: list[StageRecord] = []
        self.stage_documents: dict[str, Path] = {}
        self.published: list[PublishedItem] = []
        self.error: str | None = None
        self.document_path: Path | None = None
        self.spec_pack_path: Path | None = None
        self.agent_seconds = 0.0
        self.created_at = self.updated_at = _now()

        self._ctx = RunContext(requirement_text, tech_stack=tech_stack)
        # Full text of every knowledge-base document any stage used, by id (for the spec pack).
        self.documents: dict[str, dict] = {}
        self._stage_input: StageInput | None = None
        self._edit_notes: list[str] = []
        # Token usage saved with the run, used after a restart when live metrics no longer have it.
        self._saved_usage: dict | None = None

    # ---- read-only views -------------------------------------------------

    @property
    def title(self) -> str:
        text = " ".join(self.requirement_text.split())
        return text if len(text) <= TITLE_MAX_CHARS else text[: TITLE_MAX_CHARS - 1].rstrip() + "…"

    @property
    def edit_notes(self) -> list[str]:
        """Corrections applied so far to the pending stage."""
        return list(self._edit_notes)

    @property
    def clarifications(self) -> list[str]:
        return list(self._ctx.clarifications)

    @property
    def stages(self) -> list[str]:
        return [a.stage for a in self._agents]

    @property
    def current_agent(self) -> RunbookAgent | None:
        return self._agents[self.stage_index] if self.stage_index < len(self._agents) else None

    @property
    def current_stage(self) -> str | None:
        agent = self.current_agent
        return agent.stage if agent else None

    @property
    def current_refusal(self) -> str | None:
        """The agent's refusal reason if the pending output is a refusal."""
        refusal = (self.current_output or {}).get("refusal") or {}
        return (refusal.get("reason") or "The agent refused this request.") if refusal.get("refused") else None

    @property
    def failed_gates(self) -> list[GateResult]:
        return [g for g in self.current_gates if not g.passed]

    @property
    def approved_outputs(self) -> dict[str, dict]:
        return dict(self._ctx.outputs)

    @property
    def stage_specs(self):
        return [a.spec for a in self._agents]

    @property
    def usage(self) -> dict:
        live = self._metrics.run_usage(self.run_id)
        if not live["llm_calls"] and self._saved_usage:
            return dict(self._saved_usage)
        return live

    # ---- persistence -----------------------------------------------------

    def snapshot(self) -> dict:
        """Everything needed to continue this run later, as JSON-serialisable data."""
        si = self._stage_input
        return {
            "version": 1,
            "run_id": self.run_id,
            "title": self.title,
            "requirement_text": self.requirement_text,
            "created_by": self.created_by,
            "source": self.source,
            "tech_stack": self.tech_stack,
            "status": self.status.value,
            "stage_index": self.stage_index,
            "current_output": self.current_output,
            "current_gates": [vars(g) for g in self.current_gates],
            "current_references": self.current_references,
            "current_pii_flags": self.current_pii_flags,
            "history": [{**vars(r), "gates": [vars(g) for g in r.gates]} for r in self.history],
            "stage_documents": {k: str(v) for k, v in self.stage_documents.items()},
            "published": [vars(item) for item in self.published],
            "error": self.error,
            "document_path": str(self.document_path) if self.document_path else None,
            "spec_pack_path": str(self.spec_pack_path) if self.spec_pack_path else None,
            "agent_seconds": self.agent_seconds,
            "usage": self.usage,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "clarifications": list(self._ctx.clarifications),
            "outputs": self._ctx.outputs,
            "documents": self.documents,
            "edit_notes": list(self._edit_notes),
            "stage_input": None if si is None else {
                "payload": si.payload, "references": si.references, "documents": si.documents,
                "items": si.items, "gate_context": si.gate_context,
            },
        }

    @classmethod
    def restore(cls, data: dict, agents: list[RunbookAgent], guard: Guard, logger: TraceLogger,
                renderer: MarkdownRenderer, metrics: MetricsRecorder, devops: DevOpsClient) -> "RunSession":
        """Rebuild a run saved with snapshot(), wired to the current agents and services."""
        s = cls(data["requirement_text"], agents, guard, logger, renderer, metrics, devops,
                data["created_by"], None, data.get("source"), data.get("tech_stack"))
        s.run_id = data["run_id"]
        s.status = RunStatus(data["status"])
        s.stage_index = data["stage_index"]
        s.current_output = data.get("current_output")
        s.current_gates = [GateResult(**g) for g in data.get("current_gates", [])]
        s.current_references = data.get("current_references", [])
        s.current_pii_flags = data.get("current_pii_flags", [])
        s.history = [StageRecord(**{**r, "gates": [GateResult(**g) for g in r.get("gates", [])]})
                     for r in data.get("history", [])]
        s.stage_documents = {k: Path(v) for k, v in data.get("stage_documents", {}).items()}
        s.published = [PublishedItem(**item) for item in data.get("published", [])]
        s.error = data.get("error")
        s.document_path = Path(data["document_path"]) if data.get("document_path") else None
        s.spec_pack_path = Path(data["spec_pack_path"]) if data.get("spec_pack_path") else None
        s.agent_seconds = data.get("agent_seconds", 0.0)
        s._saved_usage = data.get("usage")
        s.created_at = datetime.fromisoformat(data["created_at"])
        s.updated_at = datetime.fromisoformat(data["updated_at"])
        s._ctx.clarifications = list(data.get("clarifications", []))
        s._ctx.outputs = dict(data.get("outputs", {}))
        s.documents = dict(data.get("documents", {}))
        s._edit_notes = list(data.get("edit_notes", []))
        si = data.get("stage_input")
        s._stage_input = None if si is None else StageInput(
            si["payload"], si.get("references", []), si.get("documents", []), si.get("items"),
            si.get("gate_context", {}),
        )
        return s

    # ---- actions ---------------------------------------------------------

    def start(self) -> None:
        self._require(RunStatus.NOT_STARTED)
        self._run_current_stage()

    def retry(self) -> None:
        self._require(RunStatus.FAILED)
        self._run_current_stage()

    def approve(self, actor: str, override_reason: str | None = None) -> None:
        self._require(RunStatus.PENDING_APPROVAL)
        if self.current_refusal:
            raise InvalidAction("A refused output cannot be approved. Edit the request or reject the run.")
        override_reason = (override_reason or "").strip() or None
        if self.failed_gates and not override_reason:
            names = "; ".join(g.description or g.check for g in self.failed_gates)
            raise InvalidAction(f"Quality gates failed ({names}). Edit the output, or give a reason to override.")
        self._accept("edited" if self._edit_notes else "approved", actor, override_reason if self.failed_gates else None)

    def edit(self, correction: str, actor: str) -> None:
        self._require(RunStatus.PENDING_APPROVAL)
        correction = correction.strip()
        if not correction:
            raise InvalidAction("Correction text is empty.")
        self._guard.check_input(correction, label="The correction")
        agent = self.current_agent

        if agent.edit_mode == "clarify":
            # The note becomes part of the requirement for every later stage, and the stage re-assesses.
            self._ctx.clarifications.append(correction)
            self._edit_notes.append(correction)
            self._run_current_stage()
            return

        self._on_progress(f"[{agent.stage}] revising with {agent.deployment}...")
        # On failure the previous output stays in place so the human can try again.
        revised = self._timed(lambda: agent.revise(self._stage_input, self.current_output, correction, self._on_call))
        self._edit_notes.append(correction)
        self._set_output(revised)

    def reject(self, actor: str) -> None:
        self._require(RunStatus.PENDING_APPROVAL)
        self._record("rejected", actor)
        self.status = RunStatus.REJECTED

    def publish(self, actor: str) -> list[PublishedItem]:
        """Simulated action: create one Azure DevOps work item per approved task."""
        self._require(RunStatus.COMPLETED)
        if self.published:
            raise InvalidAction("This backlog has already been published.")
        items = []
        try:
            for task in self._ctx.outputs.get("tasks", {}).get("tasks", []):
                item = self._devops.create_task(
                    title=f"{task['id']} {task['title']}",
                    description_html=task_description_html(task["description"], task["acceptance_criteria"]),
                    tags=["sdlc-runbook", self.run_id, *task.get("traces_to", [])],
                    estimate_hours=estimate_to_hours(task["estimate"]),
                )
                items.append(PublishedItem(task["id"], item.id, item.title, item.url))
        except ServiceError as e:
            self.error = f"Publishing stopped after {len(items)} work item(s): {e}"
            self.published = items
            raise
        self.published = items
        self.error = None
        self.updated_at = _now()
        return items

    # ---- internals -------------------------------------------------------

    def _accept(self, decision: str, actor: str, gate_override: str | None) -> None:
        agent = self.current_agent
        self._record(decision, actor, gate_override)
        self._ctx.outputs[agent.stage] = self.current_output
        self.stage_documents[agent.stage] = self._renderer.render_stage(
            self.run_id, self.stage_index + 1, agent.spec, self.current_output
        )
        self._edit_notes = []
        self.current_output = None
        self.current_gates = []
        self.stage_index += 1

        if self.current_agent is None:
            references = [r for rec in self.history for r in rec.references]
            self.document_path = self._renderer.render_pack(
                self.run_id, [a.spec for a in self._agents], self._ctx.outputs, references, self.source
            )
            spec_stage = next((a.spec for a in self._agents if a.spec.for_each), None)
            if spec_stage and spec_stage.id in self._ctx.outputs:
                self.spec_pack_path = self._renderer.render_spec_pack(
                    self.run_id, spec_stage, self._ctx.outputs, self.tech_stack, self.documents
                )
            self.status = RunStatus.COMPLETED
        else:
            self._run_current_stage()

    def _run_current_stage(self) -> None:
        agent = self.current_agent
        self._on_progress(f"[{agent.stage}] running with {agent.deployment}...")
        try:
            self._stage_input = agent.prepare_input(self._ctx)
            output = self._timed(lambda: agent.run(self._stage_input, self._on_call))
        except AgentError:
            self.status = RunStatus.FAILED
            raise
        self._set_output(output)
        self.status = RunStatus.PENDING_APPROVAL

    def _set_output(self, output: dict) -> None:
        agent = self.current_agent
        self.current_output = output
        self.current_references = self._stage_input.references if self._stage_input else []
        refused = bool((output.get("refusal") or {}).get("refused"))
        gate_inputs = {**self._ctx.outputs, **(self._stage_input.gate_context if self._stage_input else {})}
        self.current_gates = [] if refused else run_gates(agent.spec.gates, output, gate_inputs)
        for doc in (self._stage_input.documents if self._stage_input else []):
            self.documents[doc["id"]] = doc
        self.current_pii_flags = self._guard.scan_output(output).pii_categories

    def _on_call(self, record: LLMCallRecord) -> None:
        self._metrics.record_llm_call(LLMCallRecord(**{**record.__dict__, "run_id": self.run_id}))

    def _timed(self, fn: Callable[[], dict]) -> dict:
        started = time.perf_counter()
        try:
            result = fn()
        except AgentError as e:
            self.error = str(e)
            raise
        finally:
            self.agent_seconds += time.perf_counter() - started
            self.updated_at = _now()
        self.error = None
        return result

    def _record(self, decision: str, actor: str, gate_override: str | None = None) -> None:
        note = "\n".join(self._edit_notes) or None
        self.history.append(StageRecord(
            self.current_stage, self.current_output, decision, note, actor,
            list(self.current_gates), gate_override, list(self.current_references), list(self.current_pii_flags),
        ))
        self._logger.log(TraceEntry(
            self.run_id, self.current_stage, self.current_output, decision, note, actor,
            gate_override=gate_override,
            gates_failed=[g.description or g.check for g in self.current_gates if not g.passed],
        ))
        self.updated_at = _now()

    def _require(self, status: RunStatus) -> None:
        if self.status is not status:
            raise InvalidAction(f"Cannot do that while the run is {self.status.value}.")
