"""One generic agent, configured entirely by its stage section in RUNBOOK.md.

The runbook decides the prompt (global rules + stage purpose, instructions and refusal
rules), the output schema, the inputs, and the output size. This class only builds the
input, calls the model, validates the JSON (re-prompting once) and records metrics.

Per-item stages ("For each: @tasks.tasks") call the model once per item, in parallel, and
collect the results under the stage's `collect_as` key. An edit that names item ids (for
example "T-003: use pagination") regenerates only those items.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from typing import Callable

from ..exceptions import AgentError, SchemaError
from ..knowledge import EstimationBaseline, Retriever
from ..knowledge.retriever import as_prompt_context
from ..llm import LLMClient
from ..observability import LLMCallRecord
from ..runbook import StageSpec
from ..schemas import validate
from .context import RunContext, StageInput

# Output contract appended to every stage prompt.
_JSON_CONTRACT = "Return only valid JSON matching this exact schema. No prose, no markdown fences, no commentary."
_QUERY_MAX_CHARS = 1500
_PARALLEL_ITEMS = 4
_ITEM_ID = re.compile(r"\b[A-Z]{1,4}-\d{2,4}\b")

OnCall = Callable[[LLMCallRecord], None]


def _text_of(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() if k != "refusal" for s in _text_of(v)]
    if isinstance(value, list):
        return [s for v in value for s in _text_of(v)]
    return []


def _resolve(value, path: str):
    for part in path.split("."):
        value = value.get(part, []) if isinstance(value, dict) else []
    return value if isinstance(value, list) else []


class RunbookAgent:
    def __init__(self, spec: StageSpec, global_rules: str, llm: LLMClient, deployment: str,
                 retriever: Retriever | None = None, baseline: EstimationBaseline | None = None):
        self.spec = spec
        self._global_rules = global_rules
        self._llm = llm
        self.deployment = deployment
        self._retriever = retriever
        self._baseline = baseline

    @property
    def stage(self) -> str:
        return self.spec.id

    @property
    def edit_mode(self) -> str:
        return self.spec.edit_mode

    @property
    def _call_schema(self) -> dict:
        """What one model call returns: the item schema for per-item stages, else the stage schema."""
        return self.spec.item_schema or self.spec.schema

    @cached_property
    def system_prompt(self) -> str:
        s = self.spec
        refuse = f"\n\n## Refuse when\n{s.refuse_when}" if s.refuse_when else ""
        per_item = (
            f"\n\nYou are called once per {s.item_name}; the current one is under \"{s.item_name}\" in the "
            f"user message. Return the output for that {s.item_name} only."
            if s.for_each else ""
        )
        return (
            f"# Runbook global rules\n{self._global_rules}\n\n"
            f"# Your stage: {s.title}\n\n## Purpose\n{s.purpose}\n\n## Instructions\n{s.instructions}{refuse}{per_item}\n\n"
            f"{_JSON_CONTRACT}\n{json.dumps(self._call_schema, indent=2)}"
        )

    # ---- input -------------------------------------------------------------

    def prepare_input(self, ctx: RunContext) -> StageInput:
        payload: dict = {}
        references: list[dict] = []
        documents: list[dict] = []
        gate_context: dict = {}
        for source in self.spec.reads:
            if source == "requirement":
                payload["requirement_text"] = ctx.requirement_text
                payload["clarifications"] = ctx.clarifications
            elif source == "tech_stack" and ctx.tech_stack:
                payload["tech_stack"] = {k: ctx.tech_stack[k] for k in ("name", "layers", "conventions")}
            elif source == "knowledge_base" and self._retriever:
                docs = self._retriever.retrieve(self._query(ctx))
                payload["reference_standards"] = as_prompt_context(docs)
                references += [{"id": d.id, "title": d.title} for d in docs]
                documents += [vars(d) for d in docs]
            elif source == "coding_standards" and self._retriever:
                docs = self._retriever.by_category("coding")
                payload["coding_standards"] = as_prompt_context(docs)
                references += [{"id": d.id, "title": d.title} for d in docs]
                documents += [vars(d) for d in docs]
                gate_context["standards"] = {"ids": [d.id for d in docs]}
            elif source == "estimation_baseline" and self._baseline:
                payload["estimation_baseline"] = self._baseline.summary()
            elif source in ctx.outputs:
                payload[source] = ctx.outputs[source]

        items = None
        if self.spec.for_each:
            stage_ref, list_path = self.spec.for_each
            items = _resolve(ctx.outputs.get(stage_ref, {}), list_path)
        return StageInput(payload, references, documents, items, gate_context)

    def _query(self, ctx: RunContext) -> str:
        """Search query from the stage's purpose and the most recent approved outputs it reads."""
        parts = [self.spec.title, self.spec.purpose]
        for source in reversed(self.spec.reads):
            if source in ctx.outputs:
                parts += _text_of(ctx.outputs[source])
        if len(" ".join(parts)) < 200:
            parts.append(ctx.requirement_text)
        return " ".join(parts)[:_QUERY_MAX_CHARS]

    # ---- calls -------------------------------------------------------------

    def run(self, stage_input: StageInput, on_call: OnCall) -> dict:
        if stage_input.items is None:
            return self._call(self._messages(stage_input.payload), on_call)
        jobs = [self._messages(self._item_payload(stage_input, item)) for item in stage_input.items]
        return self._collect(self._parallel(jobs, on_call))

    def revise(self, stage_input: StageInput, previous: dict, correction: str, on_call: OnCall) -> dict:
        if stage_input.items is None:
            return self._call(self._revision(self._messages(stage_input.payload), previous, correction), on_call)

        previous_items = list(previous.get(self.spec.collect_as, []))
        named = set(_ITEM_ID.findall(correction))
        targets = [i for i, item in enumerate(stage_input.items) if not named or item.get("id") in named]
        if not targets:
            targets = list(range(len(stage_input.items)))
        jobs = [
            self._revision(self._messages(self._item_payload(stage_input, stage_input.items[i])),
                           previous_items[i] if i < len(previous_items) else {}, correction)
            for i in targets
        ]
        revised = self._parallel(jobs, on_call)
        merged = [{"refusal": {"refused": False, "reason": ""}, **p} for p in previous_items]
        for i, result in zip(targets, revised):
            if i < len(merged):
                merged[i] = result
            else:
                merged.append(result)
        return self._collect(merged)

    def _item_payload(self, stage_input: StageInput, item: dict) -> dict:
        return {**stage_input.payload, self.spec.item_name: item}

    def _messages(self, payload: dict) -> list[dict]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    @staticmethod
    def _revision(messages: list[dict], previous: dict, correction: str) -> list[dict]:
        return messages + [
            {"role": "assistant", "content": json.dumps(previous, ensure_ascii=False)},
            {
                "role": "user",
                "content": "Revise your previous output according to this correction, keeping everything "
                f"else that is still valid:\n{correction}\n\nReturn the complete revised JSON.",
            },
        ]

    def _parallel(self, jobs: list[list[dict]], on_call: OnCall) -> list[dict]:
        if not jobs:
            return []
        with ThreadPoolExecutor(max_workers=min(_PARALLEL_ITEMS, len(jobs))) as pool:
            return list(pool.map(lambda messages: self._call(messages, on_call), jobs))

    def _collect(self, results: list[dict]) -> dict:
        """Aggregate per-item outputs; any refused item makes the whole stage a refusal."""
        refused = [r for r in results if (r.get("refusal") or {}).get("refused")]
        refusal = {"refused": False, "reason": ""}
        if refused:
            first = refused[0]
            label = first.get("task_id") or first.get("id") or self.spec.item_name
            refusal = {"refused": True, "reason": f"{label}: {first['refusal'].get('reason', '')}".strip()}
        items = [{k: v for k, v in r.items() if k != "refusal"} for r in results]
        output = {"refusal": refusal, self.spec.collect_as: items}
        validate(output, self.spec.schema)
        return output

    def _call(self, messages: list[dict], on_call: OnCall) -> dict:
        """Call the model, parse and validate; re-prompt once on invalid JSON."""
        schema, name = self._call_schema, f"{self.stage}_output"
        for attempt in (1, 2):
            started = time.perf_counter()
            try:
                result = self._llm.complete_json(self.deployment, messages, name, schema, self.spec.max_output_tokens)
            except AgentError as e:
                on_call(self._record(started, success=False, error=str(e)))
                raise
            try:
                data = json.loads(result.text)
                validate(data, schema)
            except (json.JSONDecodeError, SchemaError) as e:
                on_call(self._record(started, False, result.prompt_tokens, result.completion_tokens, f"invalid JSON: {e}"))
                if attempt == 2:
                    raise AgentError(f"{self.spec.title} agent returned invalid JSON twice ({e}).") from e
                messages = messages + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content": f"That was not valid JSON matching the schema ({e}). "
                                                "Return only the corrected JSON."},
                ]
                continue
            on_call(self._record(started, True, result.prompt_tokens, result.completion_tokens))
            return data

    def _record(self, started: float, success: bool, prompt_tokens: int = 0,
                completion_tokens: int = 0, error: str | None = None) -> LLMCallRecord:
        return LLMCallRecord(
            stage=self.stage,
            deployment=self.deployment,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=success,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=error,
        )
