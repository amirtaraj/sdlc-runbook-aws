from dataclasses import dataclass, field

# Inputs a stage can read besides earlier stages' approved outputs.
SPECIAL_INPUTS = ("requirement", "knowledge_base", "estimation_baseline", "tech_stack", "coding_standards")
EDIT_MODES = ("revise", "clarify")


@dataclass(frozen=True)
class GateSpec:
    check: str
    args: str
    description: str


@dataclass(frozen=True)
class StageSpec:
    id: str
    title: str
    purpose: str
    instructions: str
    refuse_when: str
    schema: dict                      # strict JSON schema of the stage output (aggregate for per-item stages)
    gates: list[GateSpec]
    reads: list[str]
    edit_mode: str = "revise"         # revise | clarify (edit notes become requirement clarifications)
    max_output_tokens: int = 4000
    # Per-item stages: the agent runs once per item of an earlier stage's list (e.g. once per task)
    for_each: tuple[str, str] | None = None   # (stage id, dotted path to the list), e.g. ("tasks", "tasks")
    item_name: str = "item"                   # key the current item is passed under, e.g. "task"
    collect_as: str = "items"                 # key the per-item outputs are collected under, e.g. "specs"
    item_schema: dict | None = None           # strict schema of one item's output (what the model returns)


@dataclass(frozen=True)
class Runbook:
    global_rules: str
    stages: list[StageSpec] = field(default_factory=list)

    def stage(self, stage_id: str) -> StageSpec:
        return next(s for s in self.stages if s.id == stage_id)
