#!/usr/bin/env bash
# Deploy a new version. Upload the new sdlc-runbook.zip to ~ first, then:  bash update.sh
# Keeps .env, logs/, output/ and trace_log.jsonl. Runs in progress are lost (they live in memory).
set -euo pipefail

APP_DIR=/opt/sdlc-runbook
ZIP=~/sdlc-runbook.zip

echo "== Stopping services"
sudo systemctl stop sdlc-api sdlc-local-services

echo "== Unpacking new version (your .env and run data are kept)"
rm -rf "$APP_DIR/frontend/dist"
unzip -oq "$ZIP" -d "$APP_DIR"
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "== Starting services"
sudo systemctl start sdlc-local-services sdlc-api
sleep 3
curl -fsS http://localhost:8000/health && echo && echo "Update OK"
