"""Build the deployment package for the EC2 proof of concept.

Run on your laptop from the project root, after building the UI:

    cd frontend && npm run build && cd ..
    python deploy/make_package.py

Creates deploy/sdlc-runbook.zip with the code AND the built UI (frontend/dist), so the
server needs only Python. Never includes .env, node_modules, run data or caches.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "sdlc-runbook.zip"

EXCLUDE_DIRS = {"node_modules", "__pycache__", "logs", "output", ".claude", ".venv", ".git", "tests"}
EXCLUDE_FILES = {".env", "trace_log.jsonl", OUT.name}
EXCLUDE_SUFFIXES = {".pyc", ".log", ".tsbuildinfo"}

if not (ROOT / "frontend" / "dist" / "index.html").is_file():
    raise SystemExit("frontend/dist is missing. Run: cd frontend && npm run build")

count = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if path.is_dir() or any(p in EXCLUDE_DIRS for p in rel.parts):
            continue
        if path.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES:
            continue
        if path.suffix in {".sh", ".service"}:
            # Runs on Linux: force LF line endings even if Windows/Git converted them to CRLF.
            z.writestr(rel.as_posix(), path.read_bytes().replace(b"\r\n", b"\n"))
        else:
            z.write(path, rel.as_posix())
        count += 1

with zipfile.ZipFile(OUT) as z:
    names = z.namelist()
assert ".env" not in names, ".env must never be packaged"
print(f"{count} files -> {OUT} ({OUT.stat().st_size // 1024} KB). .env not included.")
