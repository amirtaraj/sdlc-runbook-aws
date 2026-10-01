import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from sdlc_runbook.interfaces.api import create_app
from sdlc_runbook.pipeline import RunStatus

from .fakes import ACTOR, CANNED, FakeLLM, make_factory, mock_auth_header

REQUIREMENT = "Build a leave tracker so employees can request leave and managers can approve it."

TWO_TASKS = {"tasks": [
    {**CANNED["tasks_output"]["tasks"][0]},
    {"id": "T-002", "title": "Build approval UI", "description": "Manager approval screen", "category": "frontend",
     "component_ids": ["C-01"], "traces_to": ["FR-002"], "acceptance_criteria": ["Manager can approve"], "estimate": "1d"},
]}


def spec_calls(llm: FakeLLM) -> int:
    return llm.calls.count("specification_output")


class SpecificationStageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_to_specification(self, llm: FakeLLM, stack: str | None = None):
        factory = make_factory(self.tmp, llm)
        s = factory.create(REQUIREMENT, created_by=ACTOR, tech_stack_id=stack)
        s.start()
        for _ in range(4):
            s.approve(ACTOR)
        self.assertEqual(s.current_stage, "specification")
        return s

    def test_one_spec_per_task_with_stack_and_all_coding_standards(self):
        llm = FakeLLM(overrides={"tasks_output": [TWO_TASKS]})
        s = self.run_to_specification(llm)
        self.assertEqual(spec_calls(llm), 2)
        self.assertEqual([x["task_id"] for x in s.current_output["specs"]], ["T-001", "T-002"])
        payload = llm.payloads["specification_output"]
        self.assertEqual(set(payload), {"requirements", "design", "tasks", "tech_stack", "coding_standards", "task"})
        self.assertEqual([d["id"] for d in payload["coding_standards"]],
                         [f"STD-CODE-0{i}" for i in range(1, 9)])
        self.assertTrue(all(g.passed for g in s.current_gates), [g for g in s.current_gates if not g.passed])

    def test_edit_naming_a_task_regenerates_only_that_spec(self):
        llm = FakeLLM(overrides={"tasks_output": [TWO_TASKS]})
        s = self.run_to_specification(llm)
        before = spec_calls(llm)
        s.edit("T-002: show pending requests first", ACTOR)
        self.assertEqual(spec_calls(llm) - before, 1)
        specs = {x["task_id"]: x for x in s.current_output["specs"]}
        self.assertTrue(specs["T-002"]["objective"].endswith("(revised)"))
        self.assertFalse(specs["T-001"]["objective"].endswith("(revised)"))

        s.edit("Use UTC everywhere", ACTOR)  # no task named -> every spec revised
        self.assertEqual(spec_calls(llm) - before, 3)

    def test_gates_catch_thin_specs_and_unknown_standards(self):
        thin = {"test_cases": [], "coding_standards": ["STD-CODE-99"]}
        s = self.run_to_specification(FakeLLM(overrides={"specification_output": [thin]}))
        failed = {g.check: g.detail for g in s.failed_gates}
        self.assertIn("each_count", failed)
        self.assertIn("STD-CODE-99", failed["refs"])

    def test_chosen_stack_reaches_design_and_specs(self):
        llm = FakeLLM()
        s = self.run_to_specification(llm, stack="dotnet-react")
        self.assertEqual(s.tech_stack["id"], "dotnet-react")
        self.assertIn(".NET", llm.payloads["design_output"]["tech_stack"]["layers"]["backend"])
        self.assertIn(".NET", llm.payloads["specification_output"]["tech_stack"]["layers"]["backend"])

    def test_unknown_stack_is_rejected(self):
        with self.assertRaises(KeyError):
            make_factory(self.tmp, FakeLLM()).create(REQUIREMENT, created_by=ACTOR, tech_stack_id="cobol")

    def test_spec_pack_contents(self):
        s = self.run_to_specification(FakeLLM(overrides={"tasks_output": [TWO_TASKS]}))
        s.approve(ACTOR)
        self.assertIs(s.status, RunStatus.COMPLETED)
        with zipfile.ZipFile(s.spec_pack_path) as z:
            names = {n.split("/", 1)[1] for n in z.namelist()}
            read = lambda name: z.read(f"spec-pack-{s.run_id}/{name}").decode("utf-8")  # noqa: E731
            self.assertEqual(names, {"README.md", "AGENTS.md", "constitution.md", "requirements.md", "design.md",
                                     "tasks.md", "traceability.md", "tasks/T-001.md", "tasks/T-002.md"})
            constitution = read("constitution.md")
            self.assertIn("Python · FastAPI · React", constitution)
            self.assertIn("### STD-CODE-02: Error handling", constitution)
            self.assertIn("NFR-001", constitution)
            t1 = read("tasks/T-001.md")
            for expected in ("# T-001: Build API", "### API · POST /leave-requests", "T-001-TC-02",
                             "**STD-CODE-05**: API design conventions", "- [ ] POST /leave-requests returns 201"):
                self.assertIn(expected, t1)
            self.assertIn("[T-002](tasks/T-002.md)", read("tasks.md"))
            self.assertIn("Use only the Python · FastAPI · React stack", read("AGENTS.md"))


class SpecificationApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(make_factory(Path(self._tmp.name), FakeLLM())))
        self.client.headers.update(mock_auth_header())

    def tearDown(self):
        self._tmp.cleanup()

    def test_tech_stacks_and_spec_pack_download(self):
        stacks = self.client.get("/tech-stacks").json()
        self.assertEqual(stacks["default"], "python-fastapi-react")
        self.assertIn("java-spring-angular", [x["id"] for x in stacks["stacks"]])

        bad = self.client.post("/runs", json={"requirement_text": REQUIREMENT, "tech_stack_id": "cobol"})
        self.assertEqual(bad.status_code, 422)

        run = self.client.post("/runs", json={"requirement_text": REQUIREMENT, "tech_stack_id": "node-nestjs-react"}).json()
        self.assertEqual(run["tech_stack"], {"id": "node-nestjs-react", "name": "Node.js · NestJS · React"})
        for _ in range(5):
            run = self.client.post(f"/runs/{run['run_id']}/approve").json()
        self.assertEqual(run["status"], "completed")
        resp = self.client.get(f"/runs/{run['run_id']}/spec-pack")
        self.assertEqual(resp.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            self.assertTrue(any(n.endswith("tasks/T-001.md") for n in z.namelist()))


if __name__ == "__main__":
    unittest.main()
