import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from sdlc_runbook.interfaces.api import create_app

from .fakes import FakeLLM, make_factory, mock_auth_header, read_jsonl

REQ = {"requirement_text": "Build a leave tracker so employees can request leave and managers approve it."}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def client(self, llm: FakeLLM | None = None) -> TestClient:
        c = TestClient(create_app(make_factory(self.tmp, llm or FakeLLM())))
        c.headers.update(mock_auth_header())
        return c

    def test_runbook_endpoint_lists_stages_with_schemas_and_gates(self):
        stages = self.client().get("/runbook").json()["stages"]
        self.assertEqual([s["id"] for s in stages], ["classification", "requirements", "design", "tasks", "specification"])
        self.assertEqual((stages[4]["for_each"], stages[4]["collect_as"]), (True, "specs"))
        self.assertIn("refusal", stages[0]["schema"]["properties"])
        self.assertTrue(stages[3]["gates"])

    def test_chat_flow_to_completed_document_and_publish(self):
        c = self.client()
        run = c.post("/runs", json=REQ).json()
        self.assertEqual((run["status"], run["stage"]), ("pending_approval", "classification"))
        self.assertTrue(all(g["passed"] for g in run["gates"]))
        rid = run["run_id"]

        run = c.post(f"/runs/{rid}/approve").json()
        self.assertEqual(run["stage"], "requirements")
        run = c.post(f"/runs/{rid}/edit", json={"correction_text": "tweak"}).json()
        self.assertTrue(run["output"]["title"].endswith("(revised)"))
        self.assertEqual(run["edit_notes"], ["tweak"])

        run = c.post(f"/runs/{rid}/approve").json()
        self.assertEqual(run["stage"], "design")
        self.assertTrue(run["references"])
        run = c.post(f"/runs/{rid}/approve", json={}).json()
        self.assertEqual(run["stage"], "tasks")

        self.assertEqual(c.get(f"/runs/{rid}/document").status_code, 409)
        self.assertEqual(c.get(f"/runs/{rid}/documents/design").status_code, 200)
        run = c.post(f"/runs/{rid}/approve").json()
        self.assertEqual(run["stage"], "specification")
        self.assertEqual([s["task_id"] for s in run["output"]["specs"]], ["T-001"])
        self.assertEqual(c.get(f"/runs/{rid}/spec-pack").status_code, 409)
        run = c.post(f"/runs/{rid}/approve").json()
        self.assertEqual(run["status"], "completed")
        self.assertTrue(run["spec_pack_available"])
        self.assertEqual([h["decision"] for h in run["history"]], ["approved", "edited", "approved", "approved", "approved"])
        self.assertTrue(run["document_markdown"].startswith("# Leave Tracker (revised)"))
        self.assertIn("## Traceability matrix", run["document_markdown"])
        self.assertGreater(run["usage"]["total_tokens"], 0)

        doc = c.get(f"/runs/{rid}/document")
        self.assertEqual(doc.status_code, 200)
        self.assertIn("attachment", doc.headers["content-disposition"])

        run = c.post(f"/runs/{rid}/publish").json()
        self.assertEqual(run["published"][0]["work_item_id"], 1001)
        self.assertEqual(c.post(f"/runs/{rid}/publish").status_code, 409)

        actions = [e["action"] for e in read_jsonl(self.tmp / "audit_log.jsonl")]
        for expected in ("run_created", "stage_edit", "stage_approve", "document_download", "backlog_publish"):
            self.assertIn(expected, actions)

    def test_requires_sign_in_and_role(self):
        c = self.client()
        c.headers.pop("Authorization")
        self.assertEqual(c.get("/runs").status_code, 401)
        self.assertEqual(c.get("/health").status_code, 200)
        self.assertEqual(c.get("/auth/config").json()["mode"], "mock")

        c.headers.update(mock_auth_header(roles=("Runbook.Viewer",)))
        self.assertEqual(c.get("/runs").status_code, 200)
        self.assertEqual(c.post("/runs", json=REQ).status_code, 403)
        denied = [e for e in read_jsonl(self.tmp / "audit_log.jsonl") if e["outcome"] == "denied"]
        self.assertEqual([e["action"] for e in denied], ["auth_denied", "permission_denied"])

    def test_gate_override_via_api(self):
        uncovered = {"components": [{"id": "C-01", "name": "API", "responsibility": "x", "satisfies": ["FR-001"]}]}
        c = self.client(FakeLLM(overrides={"design_output": [uncovered]}))
        rid = c.post("/runs", json=REQ).json()["run_id"]
        c.post(f"/runs/{rid}/approve")
        run = c.post(f"/runs/{rid}/approve").json()
        self.assertEqual([g["check"] for g in run["gates"] if not g["passed"]], ["covered"])
        self.assertEqual(c.post(f"/runs/{rid}/approve").status_code, 409)
        run = c.post(f"/runs/{rid}/approve", json={"override_reason": "Out of scope for v1"}).json()
        self.assertEqual(run["stage"], "tasks")
        self.assertEqual(run["history"][-1]["gate_override"], "Out of scope for v1")
        actions = [e["action"] for e in read_jsonl(self.tmp / "audit_log.jsonl")]
        self.assertIn("stage_approve_override", actions)

    def test_guardrail_block_is_422_with_reasons(self):
        resp = self.client().post("/runs", json={"requirement_text": "Email jane.doe@contoso.com about leave."})
        self.assertEqual(resp.status_code, 422)
        detail = resp.json()["detail"]
        self.assertEqual(detail["code"], "guardrail_blocked")
        self.assertIn("Email", detail["reasons"][0])

    def test_list_runs_newest_first(self):
        c = self.client()
        first = c.post("/runs", json=REQ).json()["run_id"]
        second = c.post("/runs", json={"requirement_text": "Second " + "leave tracker " * 10}).json()["run_id"]
        runs = c.get("/runs").json()
        self.assertEqual([r["run_id"] for r in runs], [second, first])
        self.assertLessEqual(len(runs[0]["title"]), 60)

    def test_invalid_action_is_409_and_unknown_run_is_404(self):
        c = self.client()
        rid = c.post("/runs", json=REQ).json()["run_id"]
        self.assertEqual(c.post(f"/runs/{rid}/reject").json()["status"], "rejected")
        self.assertEqual(c.post(f"/runs/{rid}/approve").status_code, 409)
        self.assertEqual(c.get("/runs/nope").status_code, 404)

    def test_model_failure_is_reported_on_the_run(self):
        run = self.client(FakeLLM(fail=True)).post("/runs", json=REQ).json()
        self.assertEqual(run["status"], "failed")
        self.assertIn("simulated outage", run["error"])

    def test_metrics_report_status_latency_and_tokens(self):
        c = self.client()
        c.post("/runs", json=REQ)
        m = c.get("/metrics").json()
        self.assertEqual(m["runs"]["total"], 1)
        self.assertEqual(m["llm"]["calls"], 1)
        self.assertEqual(m["llm"]["success_rate"], 1.0)
        self.assertEqual(m["llm"]["total_tokens"], 1500)
        self.assertIn("classification", m["llm"]["by_stage"])
        self.assertIn("pii", m["services"])

    def test_security_headers_present(self):
        headers = self.client().get("/health").headers
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertIn("default-src 'self'", headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
