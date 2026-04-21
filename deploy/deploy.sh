#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="spotify-tracker-api.service"
HEALTH_URL="http://127.0.0.1:8000/api/health"

cd "$REPO_DIR"

run_as_repo_owner() {
    local cmd="$1"
    if [[ $EUID -eq 0 ]]; then
        local owner
        owner="$(stat -c '%U' "$REPO_DIR")"
        runuser -u "$owner" -- bash -lc "cd '$REPO_DIR' && $cmd"
    else
        bash -lc "cd '$REPO_DIR' && $cmd"
    fi
}

restart_service() {
    if [[ $EUID -eq 0 ]]; then
        systemctl restart "$SERVICE_NAME"
    else
        sudo -n systemctl restart "$SERVICE_NAME"
    fi
}

check_health() {
    local attempts=0
    until curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge 15 ]]; then
            return 1
        fi
        sleep 1
    done
}

echo "==> Updating repository"
run_as_repo_owner "git pull --ff-only"

echo "==> Installing backend dependencies"
run_as_repo_owner "./.venv/bin/python -m pip install -r requirements.txt"

echo "==> Installing frontend dependencies"
run_as_repo_owner "cd frontend && npm ci"

echo "==> Building frontend"
run_as_repo_owner "cd frontend && npm run build"

echo "==> Restarting API"
restart_service

echo "==> Verifying health"
check_health

echo "Deployment complete."
