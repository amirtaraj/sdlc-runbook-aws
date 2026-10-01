import unittest

from sdlc_runbook.exceptions import ConfigError, SchemaError
from sdlc_runbook.runbook import GateSpec, load_runbook, run_gates
from sdlc_runbook.runbook.estimates import estimate_to_hours
from sdlc_runbook.runbook.parser import parse_runbook
from sdlc_runbook.schemas import validate

MINIMAL = """# Runbook
## Global rules
Be good.

## Stage: first
- Title: First
- Reads: requirement

### Purpose
Do one thing.

### Instructions
Carefully.

### Output schema
```json
{"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}}}}
```

### Quality gates
- `required: items` - has items
"""


class ParserTests(unittest.TestCase):
    def test_real_runbook_loads(self):
        rb = load_runbook()
        self.assertEqual([s.id for s in rb.stages], ["classification", "requirements", "design", "tasks", "specification"])
        spec = rb.stage("specification")
        self.assertEqual((spec.for_each, spec.item_name, spec.collect_as), (("tasks", "tasks"), "task", "specs"))
        self.assertEqual(list(spec.item_schema["properties"])[:2], ["refusal", "task_id"])
        self.assertEqual(list(spec.schema["properties"]), ["refusal", "specs"])
        self.assertNotIn("refusal", spec.schema["properties"]["specs"]["items"]["properties"])
        self.assertIn("Refuse", rb.global_rules)
        tasks = rb.stage("tasks")
        self.assertEqual(tasks.reads, ["requirements", "design", "tech_stack", "knowledge_base", "estimation_baseline"])
        self.assertEqual(rb.stage("classification").edit_mode, "clarify")
        self.assertIn("max_days", [g.check for g in tasks.gates])

    def test_schema_is_strict_and_has_refusal(self):
        stage = parse_runbook(MINIMAL).stages[0]
        schema = stage.schema
        self.assertEqual(list(schema["properties"]), ["refusal", "items"])
        self.assertEqual(schema["required"], ["refusal", "items"])
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["items"]["items"]["additionalProperties"])
        validate({"refusal": {"refused": False, "reason": ""}, "items": [{"id": "x"}]}, schema)
        with self.assertRaises(SchemaError):
            validate({"refusal": {"refused": "no", "reason": ""}, "items": []}, schema)

    def test_rejects_bad_runbooks(self):
        for broken, message in (
            (MINIMAL.replace("- Reads: requirement", "- Reads: later_stage"), "Reads"),
            (MINIMAL.replace("`required: items`", "`frobnicate: items`"), "quality gate"),
            (MINIMAL.replace("```json", "```text"), "json block"),
            (MINIMAL.replace("## Global rules", "## Rules"), "Global rules"),
            (MINIMAL.replace("- Title: First", "- Colour: blue"), "unknown setting"),
            (MINIMAL.replace("- Reads: requirement", "- Reads: requirement\n- For each: tasks"), "For each"),
        ):
            with self.assertRaises(ConfigError, msg=message) as ctx:
                parse_runbook(broken)
            self.assertIn(message, str(ctx.exception))


class GateTests(unittest.TestCase):
    def gate(self, check: str, args: str, output: dict, approved: dict | None = None):
        return run_gates([GateSpec(check, args, "")], output, approved or {})[0]

    def test_checks(self):
        out = {"tasks": [{"id": "T-001", "traces_to": ["FR-001"], "estimate": "2d"},
                         {"id": "T-002", "traces_to": ["FR-009"], "estimate": "5d"}]}
        approved = {"requirements": {"functional_requirements": [{"id": "FR-001"}, {"id": "FR-002"}]}}
        self.assertTrue(self.gate("required", "tasks", out).passed)
        self.assertTrue(self.gate("id_format", r"tasks.id T-\d{3}", out).passed)
        self.assertTrue(self.gate("unique", "tasks.id", out).passed)
        refs = self.gate("refs", "tasks.traces_to in @requirements.functional_requirements.id", out, approved)
        self.assertFalse(refs.passed)
        self.assertIn("FR-009", refs.detail)
        covered = self.gate("covered", "@requirements.functional_requirements.id by tasks.traces_to", out, approved)
        self.assertFalse(covered.passed)
        self.assertIn("FR-002", covered.detail)
        self.assertFalse(self.gate("max_days", "tasks.estimate 3", out).passed)
        self.assertTrue(self.gate("count", "tasks 1 5", out).passed)

    def test_refs_accepts_several_targets(self):
        approved = {"requirements": {"functional_requirements": [{"id": "FR-001"}],
                                     "non_functional_requirements": [{"id": "NFR-002"}]}}
        out = {"components": [{"satisfies": ["FR-001", "NFR-002"]}]}
        args = "components.satisfies in @requirements.functional_requirements.id, @requirements.non_functional_requirements.id"
        self.assertTrue(self.gate("refs", args, out, approved).passed)
        out["components"][0]["satisfies"].append("NFR-999")
        result = self.gate("refs", args, out, approved)
        self.assertFalse(result.passed)
        self.assertIn("NFR-999", result.detail)

    def test_each_count_checks_every_item(self):
        out = {"specs": [{"task_id": "T-001", "test_cases": [1, 2, 3]}, {"task_id": "T-002", "test_cases": [1]}]}
        result = self.gate("each_count", "specs test_cases 3 12", out)
        self.assertFalse(result.passed)
        self.assertIn("T-002 (1)", result.detail)
        out["specs"][1]["test_cases"] = [1, 2, 3, 4]
        self.assertTrue(self.gate("each_count", "specs test_cases 3 12", out).passed)

    def test_missing_upstream_stage_skips_the_gate(self):
        result = self.gate("covered", "@design.components.id by tasks.component_ids", {"tasks": []})
        self.assertTrue(result.passed)
        self.assertIn("skipped", result.detail)

    def test_estimate_parsing(self):
        self.assertEqual(estimate_to_hours("4h"), 4)
        self.assertEqual(estimate_to_hours("1.5d"), 12)
        self.assertEqual(estimate_to_hours("2 days"), 16)
        self.assertIsNone(estimate_to_hours("a while"))


if __name__ == "__main__":
    unittest.main()
