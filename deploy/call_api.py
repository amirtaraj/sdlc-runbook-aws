"""Example client for the SDLC Runbook API (mock sign-in mode).

Read-only checks (free, no model calls):
    python deploy/call_api.py --base-url http://<server>:8000

Full run, auto-approving every stage and downloading the spec pack (uses the model, a few cents):
    python deploy/call_api.py --base-url http://<server>:8000 --full-run

Needs only `httpx` (already in requirements.txt).
"""
import argparse
import base64
import json
import sys

import httpx

REQUIREMENT = (
    "Employees need a web app to request annual leave. Line managers approve or reject requests, "
    "and HR can see a weekly dashboard of who is out."
)


def mock_auth_header(email: str, role: str) -> dict:
    """Mock sign-in: base64url-encoded JSON identity. Only works when the server has MOCK_AUTH=yes."""
    identity = json.dumps({"name": email.split("@")[0], "email": email, "roles": [role]})
    token = base64.urlsafe_b64encode(identity.encode()).decode().rstrip("=")
    return {"Authorization": f"Mock {token}"}


def show(label: str, resp: httpx.Response) -> dict:
    print(f"{label}: HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--email", default="demo.approver@example.com")
    p.add_argument("--full-run", action="store_true", help="start a run and approve every stage (calls the model)")
    p.add_argument("--stack", default=None, help="tech stack id, e.g. python-fastapi-react")
    args = p.parse_args()

    # Model calls can take a minute (the Specification stage writes one spec per task), so allow 5 minutes.
    with httpx.Client(base_url=args.base_url, headers=mock_auth_header(args.email, "Runbook.Approver"),
                      timeout=300) as api:
        health = show("GET /health", api.get("/health"))
        print("  ", health)
        stacks = show("GET /tech-stacks", api.get("/tech-stacks"))
        print("   stacks:", ", ".join(s["id"] for s in stacks["stacks"]))
        runbook = show("GET /runbook", api.get("/runbook"))
        print("   stages:", " -> ".join(s["title"] for s in runbook["stages"]))
        runs = show("GET /runs", api.get("/runs"))
        print(f"   {len(runs)} run(s) in history")

        if not args.full_run:
            print("\nRead-only checks passed. Add --full-run to run the whole pipeline.")
            return 0

        run = show("\nPOST /runs", api.post("/runs", json={"requirement_text": REQUIREMENT, "tech_stack_id": args.stack}))
        run_id = run["run_id"]
        while run["status"] == "pending_approval":
            failed = [g for g in run["gates"] if not g["passed"]]
            print(f"   stage {run['stage']}: {len(run['gates']) - len(failed)}/{len(run['gates'])} gates passed")
            if run["refusal"]:
                print("   refused:", run["refusal"])
                return 1
            body = {"override_reason": "Automated example run"} if failed else {}
            run = show(f"POST /runs/{run_id}/approve", api.post(f"/runs/{run_id}/approve", json=body))

        print("   final status:", run["status"], "| error:", run["error"])
        if run["status"] != "completed":
            return 1
        print(f"   tokens: {run['usage']['total_tokens']:,} | est. cost: ${run['usage']['cost_usd']:.4f}")
        pack = api.get(f"/runs/{run_id}/spec-pack")
        pack.raise_for_status()
        out = f"{run_id}-spec-pack.zip"
        with open(out, "wb") as f:
            f.write(pack.content)
        print(f"GET /runs/{run_id}/spec-pack: saved {out} ({len(pack.content) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
