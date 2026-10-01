#!/usr/bin/env bash
# One-time setup on a fresh Amazon Linux 2023 EC2 instance.
# Usage (on the server, from the folder holding sdlc-runbook.zip):  bash setup.sh
set -euo pipefail

APP_DIR=/opt/sdlc-runbook
ZIP=~/sdlc-runbook.zip

echo "== 0/5 Adding 2 GB of swap (lets the 1 GB t3.micro install packages without running out of memory)"
if [ ! -f /swapfile ]; then
  sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo "/swapfile swap swap defaults 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 1/5 Installing Python and unzip"
sudo dnf install -y python3.12 python3.12-pip unzip || sudo dnf install -y python3.11 python3.11-pip unzip
PY=$(command -v python3.12 || command -v python3.11)
echo "Using $PY"

echo "== 2/5 Unpacking the app into $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER":"$USER" "$APP_DIR"
unzip -oq "$ZIP" -d "$APP_DIR"

echo "== 3/5 Creating a Python virtual environment and installing packages"
"$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "== 4/5 Settings file"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Created $APP_DIR/.env from the example. EDIT IT NOW: nano $APP_DIR/.env"
else
  echo ".env already exists; leaving it unchanged."
fi

echo "== 5/5 Installing the two background services"
sudo cp "$APP_DIR/deploy/ec2/sdlc-local-services.service" /etc/systemd/system/
sudo cp "$APP_DIR/deploy/ec2/sdlc-api.service" /etc/systemd/system/
sudo sed -i "s#__USER__#$USER#g" /etc/systemd/system/sdlc-local-services.service /etc/systemd/system/sdlc-api.service
sudo systemctl daemon-reload
sudo systemctl enable sdlc-local-services sdlc-api

echo
echo "Done. Next:"
echo "  1. nano $APP_DIR/.env        (set LLM_PROVIDER, AWS_REGION, BEDROCK_MODEL_ID, RUN_STORE, DYNAMODB_TABLE)"
echo "  2. sudo systemctl restart sdlc-local-services sdlc-api"
echo "  3. curl http://localhost:8000/health"
