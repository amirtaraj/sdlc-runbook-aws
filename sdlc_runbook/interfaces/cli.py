"""Terminal interface: python main.py "<requirement text>"

Needs the local services running (python -m uvicorn local_services.app:app --port 8001)
unless every external API is pointed at Azure in .env. main.py is the entry point.
"""
import argparse
import getpass
import json
import sys

from ..bootstrap import SessionFactory
from ..config import Settings
from ..exceptions import AgentError, ConfigError, GuardrailViolation, InvalidAction, ServiceError
from ..pipeline import RunSession, RunStatus


def review_loop(session: RunSession, actor: str) -> None:
    """Approval gate: show each stage's output and act on a/e/r until the run ends."""
    while session.status is RunStatus.PENDING_APPROVAL:
        print(f"\n===== {session.current_stage.upper()} OUTPUT =====")
        print(json.dumps(session.current_output, indent=2, ensure_ascii=False))
        if session.current_references:
            print("Grounded on: " + ", ".join(r["id"] for r in session.current_references))
        if session.current_pii_flags:
            print(f"WARNING - possible personal data in this output: {', '.join(session.current_pii_flags)}")
        for gate in session.current_gates:
            print(f"  [{'PASS' if gate.passed else 'FAIL'}] {gate.description or gate.check}: {gate.detail}")
        if session.current_refusal:
            print(f"REFUSED by the agent: {session.current_refusal}")
        choice = input("\nApprove / Edit / Reject [a/e/r]: ").strip().lower()

        if choice in ("a", "approve"):
            if session.current_refusal:
                print("A refusal cannot be approved. Edit the request or reject.")
                continue
            override = None
            if session.failed_gates:
                override = input("Quality gates failed. Reason to override (blank to go back): ").strip()
                if not override:
                    continue
            session.approve(actor, override)
        elif choice in ("e", "edit"):
            note = input("Describe the correction: ").strip()
            if not note:
                print("No correction entered.")
                continue
            try:
                session.edit(note, actor)
            except GuardrailViolation as e:
                print("Correction blocked: " + " ".join(e.reasons))
        elif choice in ("r", "reject"):
            session.reject(actor)
        else:
            print("Please enter a, e, or r.")


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy code page; model output often has non-ASCII characters.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="AI SDLC Runbook: requirement -> design -> tasks")
    parser.add_argument("requirement", nargs="+", help="plain-text business requirement")
    parser.add_argument("--stack", default=None, help="tech-stack preset id from data/tech_stacks.json")
    args = parser.parse_args(argv)
    requirement = " ".join(args.requirement).strip()
    if not requirement:
        parser.error("requirement text is empty")

    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    actor = f"cli:{getpass.getuser()}"
    factory = SessionFactory(settings)
    print(f"Auth:   {settings.describe_auth()}")
    try:
        session = factory.create(requirement, created_by=actor, on_progress=lambda m: print(f"\n{m}", flush=True),
                                 tech_stack_id=args.stack)
    except KeyError:
        ids = ", ".join(s["id"] for s in factory.tech_stacks.list())
        print(f"Unknown tech stack '{args.stack}'. Choose one of: {ids}", file=sys.stderr)
        return 2
    except GuardrailViolation as e:
        print("Requirement blocked by guardrails:\n- " + "\n- ".join(e.reasons), file=sys.stderr)
        return 3
    print(f"Run ID: {session.run_id}")
    factory.audit.log("run_created", actor=actor, run_id=session.run_id)

    try:
        session.start()
        review_loop(session, actor)
    except (AgentError, InvalidAction, ServiceError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nRun cancelled.")
        return 130

    if session.status is RunStatus.REJECTED:
        print(f"\nRun aborted: the {session.current_stage} stage was rejected. Nothing further was generated.")
        return 1

    usage = session.usage
    print(f"\nAgent-call time: {session.agent_seconds:.1f}s | tokens: {usage['total_tokens']:,} "
          f"| est. cost: ${usage['cost_usd']:.4f}")
    print(f"Stage documents: {session.document_path.with_suffix('')}")
    print(f"Final pack:      {session.document_path}")
    if session.spec_pack_path:
        print(f"Spec pack:       {session.spec_pack_path}")
    return 0
