#!/usr/bin/env bash

set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_SERVICE="spotify-tracker-api.service"
WORKER_SERVICE="spotify-tracker-worker.service"
WORKER_TIMER="spotify-tracker-worker.timer"
WORKER_DRAIN_SECONDS=300
stage="stopping services"
starting_services=false
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

as_root() {
    if [[ $EUID -eq 0 ]]; then
        "$@"
    else
        sudo -n "$@"
    fi
}

run_with_api_environment() {
    local service_user
    if ! service_user="$(systemctl show --property=User --value "$API_SERVICE")"; then
        return 1
    fi
    if [[ -z "$service_user" ]]; then
        echo "The API service is missing its configured user." >&2
        return 1
    fi
    as_root systemd-run --pipe --collect --quiet \
        --uid="$service_user" --working-directory="$REPO_DIR" \
        --property="EnvironmentFile=$REPO_DIR/.env" -- "$REPO_DIR/.venv/bin/python" "$@"
}

wait_for_worker() {
    local deadline=$((SECONDS + WORKER_DRAIN_SECONDS))
    local state jobs
    while true; do
        if ! state="$(systemctl show --property=ActiveState --value "$WORKER_SERVICE")" ||
            ! jobs="$(systemctl list-jobs --no-pager --no-legend "$WORKER_SERVICE")"; then
            return 1
        fi
        if [[ -z "$jobs" && ( "$state" == inactive || "$state" == failed ) ]]; then
            return 0
        fi
        if (( SECONDS >= deadline )); then
            echo "The worker did not finish within $WORKER_DRAIN_SECONDS seconds." >&2
            return 1
        fi
        sleep 1
    done
}

deploy_failed() {
    local result="$1"
    trap - ERR
    echo "Deployment failed while $stage." >&2
    if $starting_services; then
        as_root systemctl stop "$WORKER_TIMER" "$API_SERVICE" || true
    fi
    systemctl --no-pager status "$API_SERVICE" "$WORKER_TIMER" "$WORKER_SERVICE" >&2 || true
    echo "See docs/deployment.md for recovery before starting the services." >&2
    exit "$result"
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

# Parse the deployment steps before git pull can replace this script.
main() {
    trap 'deploy_failed "$?"' ERR
    # Stop new timer invocations and let old code finish before changing the checkout.
    echo "==> Stopping timer and API"
    as_root systemctl stop "$WORKER_TIMER"
    as_root systemctl stop "$API_SERVICE"

    stage="waiting for the worker"
    echo "==> Waiting for any active worker to finish"
    wait_for_worker

    stage="updating the repository"
    echo "==> Updating repository"
    run_as_repo_owner "git pull --ff-only"

    stage="installing backend dependencies"
    echo "==> Installing backend dependencies"
    run_as_repo_owner "./.venv/bin/python -m pip install -r requirements.txt"

    stage="installing frontend dependencies"
    echo "==> Installing frontend dependencies"
    run_as_repo_owner "cd frontend && npm ci"

    stage="building the frontend"
    echo "==> Building frontend"
    run_as_repo_owner "cd frontend && npm run build"

    stage="applying database migrations"
    echo "==> Applying database migrations"
    run_with_api_environment -m alembic upgrade head

    stage="optimizing existing artwork"
    echo "==> Optimizing existing album artwork"
    run_with_api_environment -m one_time_scripts._cache_artwork --existing-only

    starting_services=true
    stage="starting the API"
    echo "==> Starting API"
    as_root systemctl start "$API_SERVICE"

    stage="checking API health"
    echo "==> Verifying health"
    check_health

    stage="starting the worker timer"
    echo "==> Starting worker timer"
    as_root systemctl start "$WORKER_TIMER"

    echo "Deployment complete."
}

main
