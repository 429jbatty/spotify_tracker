# Deployment

The repo includes native Debian/Ubuntu LXC deployment templates under
`deploy/`. The deployment runs FastAPI with systemd, runs tracking through a
systemd timer, serves the built frontend, and uses Caddy as the web server.

## Layout

Recommended server checkout:

```text
/opt/spotify_tracker
```

Runtime data should live outside the code paths that are overwritten during
deploys:

```text
/opt/spotify_tracker/data
```

Back up this directory. It contains the SQLite database and cached artwork.

## Install

From the repo root on the server:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
```

Copy and edit environment settings:

```bash
cp deploy/env.example .env
```

Set `LASTFM_API_KEY` in `.env` before starting the API when Last.fm imports
are enabled. Keep the key only in the server environment file, never in the
repository or frontend build.

Install systemd units:

```bash
sudo cp deploy/spotify-tracker-api.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-tracker-api.service
sudo systemctl enable --now spotify-tracker-worker.timer
```

Install Caddy config:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Existing profile ownership and Spotify sync

Run these commands from the checkout with the API service's database settings.
Set `PROFILE_SLUG` and `GOOGLE_EMAIL` to the confirmed profile and owner.
To reserve an existing profile before the owner's first verified Google sign-in, run

```bash
./.venv/bin/python -m one_time_scripts.prebind_profile_owner "$PROFILE_SLUG" "$GOOGLE_EMAIL"
```

For an account that has already signed in, run

```bash
./.venv/bin/python -m one_time_scripts.bind_profile_owner "$PROFILE_SLUG" "$GOOGLE_EMAIL"
```

Each Google account can own one profile. Sign-in requires `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, and the registered `GOOGLE_REDIRECT_URI` (normally
`/api/auth/google/callback` on the public origin). Set `FRONTEND_ORIGIN` to
the public frontend.

Spotify live sync requires a separate grant. For an approved Spotify user with
access to the Spotify app, enable the confirmed profile, then have the owner
connect Spotify from that profile.

```bash
./.venv/bin/python - "${PROFILE_SLUG:?set PROFILE_SLUG}" <<'PY'
import sys
from sqlalchemy import update
from backend.app.database.engine import get_engine
from backend.app.database.models import User

with get_engine().begin() as connection:
    granted = connection.execute(
        update(User).where(User.slug == sys.argv[1]).values(spotify_sync_enabled=True)
    )
    if granted.rowcount != 1:
        raise RuntimeError("Expected one existing profile")
PY
```

## Updates

Deploy updates from a real server clone:

```bash
cd /opt/spotify_tracker
sudo ./deploy/deploy.sh
```

or:

```bash
sudo make deploy
```

The deploy script stops the worker timer and API, then waits up to five minutes
for a running or queued worker to finish. It fast-forwards the checkout,
installs dependencies, builds the frontend, upgrades the database using the
API service user and the checkout's `.env`, and optimizes existing local
artwork. It starts the API and checks its health before starting the timer.

Take a SQLite backup before deploying a release with schema changes. Keep
manual jobs that write to the database stopped throughout the deployment.

### Adopt an existing SQLite database

A database created before Alembic needs a one-time baseline stamp. For this
first deploy, stop the old processes before pulling the updated checkout.
The previous release's deploy script cannot perform these steps.
Run repository and database commands from `/opt/spotify_tracker` as the
service user. Use the same `.env` as both services and resolve any conflicting
shell settings for `DATABASE_URL` and `DATA_DIR` before proceeding.

```bash
cd /opt/spotify_tracker
sudo systemctl stop spotify-tracker-worker.timer
sudo systemctl stop spotify-tracker-api.service
systemctl show --property=ActiveState --value spotify-tracker-worker.service
systemctl list-jobs --no-pager --no-legend spotify-tracker-worker.service
```

Wait until the worker is `inactive` or `failed` and has no queued jobs. Then
pull the migration-enabled release and install its dependencies.

```bash
git pull --ff-only
./.venv/bin/python -m pip install -r requirements.txt
```

Resolve the configured file and back it up with SQLite's backup command.

```bash
db="$(./.venv/bin/python - <<'PYDB'
from backend.app.database.engine import get_engine, sqlite_file_path

path = sqlite_file_path(get_engine().url)
if path is None or not path.is_file():
    raise SystemExit("Expected an existing file-backed SQLite database")
print(path)
PYDB
)" || exit 1
umask 077
backup="$db.pre-alembic-$(date +%Y%m%d-%H%M%S).bak"
sqlite3 "$db" ".backup '$backup'"
sqlite3 "$backup" 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
```

The integrity check should return a single `ok` and no foreign-key violations.
Create a temporary reference database by upgrading a separate file to revision
`0001`. Compare its schema with the backup, including indexes and constraints.

```bash
comparison_dir="$(mktemp -d)"
reference="$comparison_dir/baseline.sqlite"
DATABASE_URL="sqlite:///$reference" ./.venv/bin/python -m alembic upgrade 0001
schema_query="SELECT sql FROM sqlite_schema
  WHERE sql IS NOT NULL AND name NOT GLOB 'sqlite_*' AND tbl_name <> 'alembic_version'
  ORDER BY type, name;"
sqlite3 "$reference" "$schema_query" > "$comparison_dir/baseline.sql"
sqlite3 "$backup" "$schema_query" > "$comparison_dir/existing.sql"
diff -u "$comparison_dir/baseline.sql" "$comparison_dir/existing.sql"
```

Review table and column definitions, defaults, constraints, indexes and
partial-index predicates. The SQL diff can show equivalent constraints in a
different order. If the deployed schema differs from the baseline, stop here
and plan a targeted correction. Stamp only after you have verified the match.

```bash
./.venv/bin/python -m alembic stamp 0001
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m alembic current
sudo ./deploy/deploy.sh
```

The deploy command completes the frontend build, starts the services, and
checks API health. Finish with the service checks below.

### Recover a failed deployment

The script reports the failed stage and service status. Failures before API
startup leave the API and timer stopped once quiescing has completed. If API
startup, its health check, or timer startup fails, the script attempts to
stop both services again. Check their actual status before recovery and let
any active worker finish.

For a migration failure, keep writers stopped and inspect the deploy error and
the current revision with `./.venv/bin/python -m alembic current`. Correct the
cause and rerun the deploy. For a rollback across an applied schema change,
restore the matching pre-deploy backup using SQLite and run the code that
matches that backup. A checkout alone cannot roll back SQLite schema changes.
Save a backup of the current failed-deploy database before restoring, then
verify the restored database before restarting the API and timer.

```bash
sqlite3 "$db" ".restore '$backup'"
sqlite3 "$db" 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
```

## Checks

```bash
curl http://127.0.0.1:8000/api/health
systemctl status spotify-tracker-api.service
systemctl list-timers spotify-tracker-worker.timer
journalctl -u spotify-tracker-api.service -n 100
```

See `deploy/README.md` for the template-focused deployment notes.
