"""Composition root: builds the concrete objects and wires them together.

The runbook (RUNBOOK.md) decides which agents exist and in what order; this file only
gives each one its model deployment and the shared services. Both interfaces (CLI and
web API) get their RunSessions from here. Tests pass a fake LLM and an httpx transport
for the external APIs, so nothing real is called.
"""
from typing import Callable

import httpx

from .agents import RunbookAgent
from .config import Settings
from .guardrails import Guard
from .knowledge import EstimationBaseline, Retriever, TechStackCatalog
from .llm import AzureOpenAIClient, BedrockClient, LLMClient
from .observability import AuditLogger, MetricsRecorder
from .persistence import DynamoRunStore, MemoryRunStore, RunStore, TraceLogger
from .pipeline import RunSession
from .rendering import MarkdownRenderer
from .runbook import load_runbook
from .services import ContentSafetyClient, DevOpsClient, KnowledgeBaseClient, PiiClient


class SessionFactory:
    def __init__(self, settings: Settings, llm: LLMClient | None = None,
                 transport: httpx.BaseTransport | None = None, run_store: RunStore | None = None):
        self.settings = s = settings
        if run_store is None:
            run_store = (DynamoRunStore(s.dynamodb_table, s.aws_region) if s.run_store == "dynamodb"
                         else MemoryRunStore())
        self.run_store = run_store
        self.runbook = load_runbook(s.runbook_path)
        self.tech_stacks = TechStackCatalog(s.tech_stacks_path)
        self.metrics = MetricsRecorder(s.llm_calls_log_path)
        self.audit = AuditLogger(s.audit_log_path)
        timeout = s.service_timeout_seconds

        self.guard = Guard(
            ContentSafetyClient(s.content_safety, timeout, self.metrics, transport),
            PiiClient(s.language, timeout, self.metrics, transport),
        )
        retriever = Retriever(KnowledgeBaseClient(s.search, s.search_index, timeout, self.metrics, transport), self.guard)
        baseline = EstimationBaseline(s.estimates_dataset_path)
        self.devops = DevOpsClient(s.devops, s.devops_project, timeout, self.metrics, transport)

        if llm is None:
            llm = BedrockClient(s) if s.llm_provider == "bedrock" else AzureOpenAIClient(s)
        self.agents = [
            RunbookAgent(spec, self.runbook.global_rules, llm, s.deployment_for(spec.id), retriever, baseline)
            for spec in self.runbook.stages
        ]
        self._logger = TraceLogger(s.trace_log_path)
        self._renderer = MarkdownRenderer(s.output_dir)

    def create(self, requirement_text: str, created_by: str,
               on_progress: Callable[[str], None] | None = None, source: dict | None = None,
               tech_stack_id: str | None = None) -> RunSession:
        """Screen the requirement with the input guardrails, then build a session (not started).

        Raises KeyError for an unknown tech_stack_id; None means the catalog's default.
        """
        stack = self.tech_stacks.get(tech_stack_id)
        self.guard.check_input(requirement_text, label="The requirement")
        return RunSession(
            requirement_text, self.agents, self.guard, self._logger, self._renderer,
            self.metrics, self.devops, created_by, on_progress, source, stack,
        )

    def restore(self, snapshot: dict) -> RunSession:
        """Rebuild a saved run (e.g. after a restart) wired to this process's agents and services."""
        return RunSession.restore(snapshot, self.agents, self.guard, self._logger, self._renderer,
                                  self.metrics, self.devops)
