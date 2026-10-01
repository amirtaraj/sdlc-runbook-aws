"""Saved runs: snapshot/restore, the DynamoDB store (with a fake client) and API restarts."""
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from sdlc_runbook.bootstrap import SessionFactory
from sdlc_runbook.config import Settings
from sdlc_runbook.exceptions import ConfigError, StorageError
from sdlc_runbook.interfaces.api import create_app
from sdlc_runbook.persistence import DynamoRunStore, MemoryRunStore
from sdlc_runbook.pipeline import RunStatus

from .fakes import ACTOR, FakeLLM, local_services_transport, make_settings, mock_auth_header
from .test_specification import TWO_TASKS

REQ = "Build a leave tracker so employees can request leave and managers can approve it."


def factory(tmp: Path, llm: FakeLLM, store) -> SessionFactory:
    return SessionFactory(make_settings(tmp), llm=llm, transport=local_services_transport(tmp), run_store=store)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_restore_mid_run_and_continue_to_completion(self):
        llm = FakeLLM(overrides={"tasks_output": [TWO_TASKS]})
        f = factory(self.tmp, llm, MemoryRunStore())
        s = f.create(REQ, created_by=ACTOR, tech_stack_id="dotnet-react")
        s.start()
        s.edit("Clarify: managers approve", ACTOR)       # classification edit -> clarification
        for _ in range(4):
            s.approve(ACTOR)
        self.assertEqual(s.current_stage, "specification")

        snap = json.loads(json.dumps(s.snapshot()))       # must survive a JSON round trip
        restored = f.restore(snap)
        self.assertEqual((restored.run_id, restored.status, restored.current_stage),
                         (s.run_id, RunStatus.PENDING_APPROVAL, "specification"))
        self.assertEqual(restored.clarifications, ["Clarify: managers approve"])
        self.assertEqual([h.stage for h in restored.history], ["classification", "requirements", "design", "tasks"])
        self.assertEqual(restored.tech_stack["id"], "dotnet-react")
        self.assertEqual(restored.usage["total_tokens"], s.usage["total_tokens"])

        before = llm.calls.count("specification_output")
        restored.edit("T-002: show pending first", ACTOR)  # targeted per-item edit after restore
        self.assertEqual(llm.calls.count("specification_output") - before, 1)
        restored.approve(ACTOR)
        self.assertIs(restored.status, RunStatus.COMPLETED)
        self.assertTrue(restored.spec_pack_path.is_file())

    def test_restored_usage_falls_back_to_saved_value(self):
        f = factory(self.tmp, FakeLLM(), MemoryRunStore())
        s = f.create(REQ, created_by=ACTOR)
        s.start()
        snap = s.snapshot()
        fresh = factory(self.tmp, FakeLLM(), MemoryRunStore())   # new process: empty live metrics
        self.assertEqual(fresh.restore(snap).usage["total_tokens"], 1500)


class FakeDynamo:
    """Minimal low-level DynamoDB client: put_item / get_item / scan with pagination."""

    def __init__(self, page_size: int = 2, fail_with: str | None = None):
        self.items: dict[str, dict] = {}
        self.page_size = page_size
        self.fail_with = fail_with

    def _check(self):
        if self.fail_with:
            err = Exception(self.fail_with)
            err.response = {"Error": {"Code": self.fail_with}}
            raise err

    def put_item(self, TableName, Item):
        self._check()
        self.items[Item["run_id"]["S"]] = Item

    def get_item(self, TableName, Key):
        self._check()
        item = self.items.get(Key["run_id"]["S"])
        return {"Item": item} if item else {}

    def scan(self, TableName, ProjectionExpression, ExpressionAttributeNames, ExclusiveStartKey=None):
        self._check()
        keys = sorted(self.items)
        start = keys.index(ExclusiveStartKey["run_id"]["S"]) + 1 if ExclusiveStartKey else 0
        page = keys[start:start + self.page_size]
        resp = {"Items": [{k: v for k, v in self.items[key].items() if k != "data"} for key in page]}
        if start + self.page_size < len(keys):
            resp["LastEvaluatedKey"] = {"run_id": {"S": page[-1]}}
        return resp


class DynamoStoreTests(unittest.TestCase):
    def snapshot(self, run_id: str, status: str = "pending_approval") -> dict:
        return {"run_id": run_id, "title": f"Run {run_id}", "status": status,
                "updated_at": "2026-10-01T10:00:00+00:00", "outputs": {"big": "x" * 50_000}}

    def test_save_load_and_list_across_pages(self):
        fake = FakeDynamo(page_size=2)
        store = DynamoRunStore("sdlc-runbook-runs", "us-east-1", client=fake)
        for rid in ("r1", "r2", "r3"):
            store.save(self.snapshot(rid))
        item = fake.items["r1"]
        self.assertEqual(item["status"], {"S": "pending_approval"})
        self.assertLess(len(item["data"]["B"]), 5_000)                       # compressed
        self.assertEqual(json.loads(gzip.decompress(item["data"]["B"]))["run_id"], "r1")
        self.assertEqual(store.load("r2")["outputs"]["big"], "x" * 50_000)
        self.assertIsNone(store.load("missing"))
        self.assertEqual(sorted(r["run_id"] for r in store.list_summaries()), ["r1", "r2", "r3"])

    def test_errors_are_explained(self):
        for code, hint in (("ResourceNotFoundException", "doesn't exist"), ("AccessDeniedException", "IAM role")):
            store = DynamoRunStore("t", "us-east-1", client=FakeDynamo(fail_with=code))
            with self.assertRaises(StorageError) as ctx:
                store.load("r1")
            self.assertIn(hint, str(ctx.exception))


class ApiRestartTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = MemoryRunStore()   # stands in for DynamoDB, shared across "restarts"

    def tearDown(self):
        self._tmp.cleanup()

    def server(self) -> TestClient:
        c = TestClient(create_app(factory(self.tmp, FakeLLM(), self.store)))
        c.headers.update(mock_auth_header())
        return c

    def test_runs_survive_a_restart(self):
        first = self.server()
        rid = first.post("/runs", json={"requirement_text": REQ}).json()["run_id"]
        first.post(f"/runs/{rid}/approve")

        second = self.server()           # new process: nothing in memory
        self.assertEqual([r["run_id"] for r in second.get("/runs").json()], [rid])
        run = second.get(f"/runs/{rid}").json()
        self.assertEqual((run["stage"], len(run["history"])), ("requirements", 1))
        for _ in range(4):
            run = second.post(f"/runs/{rid}/approve").json()
        self.assertEqual(run["status"], "completed")
        self.assertEqual(second.get(f"/runs/{rid}/spec-pack").status_code, 200)
        self.assertEqual(second.get("/metrics").json()["runs"]["by_status"]["completed"], 1)

    def test_storage_outage_does_not_break_the_run(self):
        broken = DynamoRunStore("t", "us-east-1", client=FakeDynamo(fail_with="ThrottlingException"))
        c = TestClient(create_app(factory(self.tmp, FakeLLM(), broken)))
        c.headers.update(mock_auth_header())
        run = c.post("/runs", json={"requirement_text": REQ}).json()
        self.assertEqual(run["status"], "pending_approval")          # still works in memory
        self.assertEqual([r["run_id"] for r in c.get("/runs").json()], [run["run_id"]])


class StoreConfigTests(unittest.TestCase):
    def from_env(self, env):
        with mock.patch.dict(os.environ, {"MOCK_AUTH": "yes", **env}, clear=True):
            return Settings.from_env(env_file=None)

    def test_store_settings(self):
        self.assertEqual(self.from_env({}).run_store, "memory")
        s = self.from_env({"RUN_STORE": "dynamodb", "DYNAMODB_TABLE": "sdlc-runbook-runs", "AWS_REGION": "us-east-1"})
        self.assertEqual((s.run_store, s.dynamodb_table), ("dynamodb", "sdlc-runbook-runs"))
        with self.assertRaises(ConfigError):
            self.from_env({"RUN_STORE": "dynamodb", "AWS_REGION": "us-east-1"})
        with self.assertRaises(ConfigError):
            self.from_env({"RUN_STORE": "postgres"})


if __name__ == "__main__":
    unittest.main()
