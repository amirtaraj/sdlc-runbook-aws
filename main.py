"""CLI entry point: python main.py "<requirement text>"

For the web UI, run the API instead:
  python -m uvicorn local_services.app:app --port 8001
  python -m uvicorn sdlc_runbook.interfaces.api:create_app --factory --port 8000
"""
import sys

from sdlc_runbook.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
