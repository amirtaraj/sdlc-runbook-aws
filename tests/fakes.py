"""Offline stand-ins so tests never call Azure.

- FakeLLM returns canned stage outputs.
- local_services_transport() routes the real HTTP clients into the local services app
  in-process, so guardrails, search and DevOps run end to end without a server.
"""
import base64
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from local_services.app import create_app as create_local_services
from sdlc_runbook.bootstrap import SessionFactory
from sdlc_runbook.config import AppAuthSettings, Settings
from sdlc_runbook.exceptions import AgentError
from sdlc_runbook.llm import LLMResult

NOT_REFUSED = {"refused": False, "reason": ""}

CANNED = {
    "classification_output": {
        "refusal": NOT_REFUSED,
        "project_type": "greenfield",
        "request_type": "new_product",
        "complexity": "medium",
        "clarity": "ready",
        "summary": "A leave tracker for employees and managers.",
        "clarifying_questions": [],
    },
    "requirements_output": {
        "refusal": NOT_REFUSED,
        "title": "Leave Tracker",
        "functional_requirements": [
            {"id": "FR-001", "text": "Employees can request leave", "priority": "must"},
            {"id": "FR-002", "text": "Managers can approve leave", "priority": "must"},
        ],
        "non_functional_requirements": [{"id": "NFR-001", "category": "performance", "text": "Responds within 2s"}],
        "assumptions": ["Single company"],
        "open_questions": ["Which HR system?"],
    },
    "design_output": {
        "refusal": NOT_REFUSED,
        "overview": "A small web app with an API and a database.",
        "components": [
            {"id": "C-01", "name": "API", "responsibility": "Handles leave requests", "satisfies": ["FR-001", "FR-002"]},
        ],
        "data_flow": ["User submits request", "API stores it"],
        "key_decisions": [{"decision": "Use Postgres", "rationale": "Team knows it (per STD-DATA-01)"}],
        "risks": ["HR integration unknown"],
    },
    "tasks_output": {
        "refusal": NOT_REFUSED,
        "tasks": [{
            "id": "T-001",
            "title": "Build API",
            "description": "Create the leave request endpoint | with validation",
            "category": "backend",
            "component_ids": ["C-01"],
            "traces_to": ["FR-001", "FR-002"],
            "acceptance_criteria": ["POST /leave returns 201"],
            "estimate": "1.5d",
        }],
    },
    # One task's specification; FakeLLM fills task_id/title from the task it is given.
    "specification_output": {
        "refusal": NOT_REFUSED,
        "task_id": "",
        "title": "",
        "objective": "Expose an endpoint to create leave requests.",
        "context": "First backend task; the database schema exists.",
        "traces_to": ["FR-001", "FR-002"],
        "depends_on": [],
        "scope_in": ["POST /leave-requests"],
        "scope_out": ["Approval workflow (T-002)"],
        "files": [{"path": "app/api/leave_requests.py", "action": "create", "purpose": "Router"}],
        "interfaces": [{"kind": "api", "name": "POST /leave-requests",
                        "contract": "Request {startDate: date, endDate: date} -> 201 {id: uuid} | 400 | 409"}],
        "data_model": [{"entity": "LeaveRequest", "fields": ["id: uuid (pk)", "startDate: date"], "notes": ""}],
        "implementation_steps": ["Add schema", "Add repository", "Add router", "Wire auth"],
        "error_handling": ["Overlapping dates -> 409 LEAVE_OVERLAP"],
        "coding_standards": ["STD-CODE-02", "STD-CODE-05"],
        "test_cases": [
            {"id": "T-001-TC-01", "type": "integration", "given": "valid dates", "when": "POST", "then": "201"},
            {"id": "T-001-TC-02", "type": "integration", "given": "end before start", "when": "POST", "then": "400"},
            {"id": "T-001-TC-03", "type": "unit", "given": "overlap", "when": "validate", "then": "conflict"},
        ],
        "acceptance_criteria": ["POST /leave-requests returns 201 with an id"],
        "definition_of_done": ["Tests pass", "Lint clean"],
        "open_questions": [],
    },
}

ACTOR = "mock:tester@example.com"


class FakeLLM:
    """Canned JSON per stage. Revisions append "(revised)" to the first string field.

    overrides: {schema_name: [patch, patch, ...]} dicts merged into successive responses
               for that stage (then the canned output), e.g. to simulate a refusal.
    """

    def __init__(self, bad_responses: int = 0, fail: bool = False, overrides: dict[str, list[dict]] | None = None):
        self.calls: list[str] = []
        self.payloads: dict[str, dict] = {}
        self.system_prompts: dict[str, str] = {}
        self.max_tokens: dict[str, int] = {}
        self._bad_responses = bad_responses
        self._fail = fail
        self._overrides = {k: list(v) for k, v in (overrides or {}).items()}

    def complete_json(self, deployment, messages, schema_name, schema, max_tokens):
        self.calls.append(schema_name)
        self.payloads[schema_name] = json.loads(messages[1]["content"])
        self.system_prompts[schema_name] = messages[0]["content"]
        self.max_tokens[schema_name] = max_tokens
        if self._fail:
            raise AgentError("simulated outage")
        if self._bad_responses:
            self._bad_responses -= 1
            return LLMResult("not json", 10, 2)
        data = json.loads(json.dumps(CANNED[schema_name]))
        if schema_name == "specification_output":
            task = json.loads(messages[1]["content"])["task"]  # this call's own payload (calls run in parallel)
            data.update(task_id=task["id"], title=task["title"])
        if self._overrides.get(schema_name):
            data.update(self._overrides[schema_name].pop(0))
        if messages[-1]["content"].startswith("Revise"):
            if schema_name == "tasks_output":
                data["tasks"][0]["title"] += " (revised)"
            elif schema_name == "specification_output":
                data["objective"] += " (revised)"
            else:
                key = next(k for k, v in data.items() if isinstance(v, str))
                data[key] += " (revised)"
        return LLMResult(json.dumps(data), prompt_tokens=1000, completion_tokens=500)


def local_services_transport(tmp: Path) -> httpx.MockTransport:
    client = TestClient(create_local_services(work_items_log=tmp / "work_items.jsonl"))

    def handler(request: httpx.Request) -> httpx.Response:
        resp = client.request(request.method, request.url.raw_path.decode(), content=request.content,
                              headers=dict(request.headers))
        return httpx.Response(resp.status_code, content=resp.content, headers=resp.headers)

    return httpx.MockTransport(handler)


def make_settings(tmp: Path, **overrides) -> Settings:
    return Settings(
        trace_log_path=tmp / "trace_log.jsonl",
        audit_log_path=tmp / "audit_log.jsonl",
        llm_calls_log_path=tmp / "llm_calls.jsonl",
        output_dir=tmp / "output",
        app_auth=overrides.pop("app_auth", AppAuthSettings(mock=True)),
        **overrides,
    )


def make_factory(tmp: Path, llm: FakeLLM, transport: httpx.BaseTransport | None = None) -> SessionFactory:
    return SessionFactory(make_settings(tmp), llm=llm, transport=transport or local_services_transport(tmp))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def mock_auth_header(email: str = "tester@example.com", roles: tuple[str, ...] = ("Runbook.Approver",)) -> dict:
    token = base64.urlsafe_b64encode(json.dumps({"name": "Tester", "email": email, "roles": list(roles)}).encode())
    return {"Authorization": f"Mock {token.decode().rstrip('=')}"}
