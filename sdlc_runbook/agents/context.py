"""What agents can see about the run so far, and what they hand back to the session."""
from dataclasses import dataclass, field


@dataclass
class RunContext:
    requirement_text: str
    clarifications: list[str] = field(default_factory=list)
    outputs: dict[str, dict] = field(default_factory=dict)   # approved output per stage
    tech_stack: dict | None = None                            # preset chosen at run start


@dataclass(frozen=True)
class StageInput:
    payload: dict                                              # sent to the model as the user message
    references: list[dict] = field(default_factory=list)       # knowledge-base docs used: {id, title}
    documents: list[dict] = field(default_factory=list)        # same docs in full: {id, title, category, content}
    items: list[dict] | None = None                            # per-item stages: one model call per item
    gate_context: dict = field(default_factory=dict)           # extra @paths for quality gates, e.g. standards
