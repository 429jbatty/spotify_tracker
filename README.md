# Spotify Tracker

A personal album-listening tracker. The backend pulls recent Spotify plays,
marks albums complete when enough tracks were heard, enriches albums with
MusicBrainz metadata and cover art, and serves the data to a React/Vite
frontend through FastAPI.

## Architecture

SQLite is the runtime source of truth.

```text
Spotify tracking job per connected user
  -> SQLite
  -> FastAPI /api/users/{user}/album-state
  -> React frontend
```

Key backend paths:

- `main.py`: compatibility wrapper for default-user Spotify tracking.
- `backend/app/services/spotify_tracking_service.py`: user-scoped Spotify tracking.
- `backend/app/jobs/track_all_users.py`: scheduled multi-user tracking entrypoint.
- `tracking.py`: album progress and completion logic.
- `album_metadata_service.py`: MusicBrainz lookup and metadata shaping.
- `metadata_refresh_service.py`: targeted metadata refresh logic.
- `backend/app/main.py`: FastAPI app entrypoint.
- `backend/app/routers/album_state.py`: `/api/album-state`.
- `backend/app/repositories/sqlite_state_repository.py`: SQLite read/write logic.
- `backend/app/models.py`: SQLAlchemy table definitions.

Key frontend paths:

- `frontend/src/App.jsx`: loads album state and renders pages.
- `frontend/src/services/albumApi.js`: calls the backend API.
- `frontend/vite.config.js`: proxies `/api` to FastAPI during local dev.

## Data Storage

The app uses `DATA_DIR` for runtime data. If `DATA_DIR` is unset, it defaults
to the repo-local `data/` directory for development. For deployment, point it
outside the repo:

```bash
DATA_DIR=/srv/spotify_tracker/data
```

Default database path:

```text
$DATA_DIR/spotify_tracker.sqlite
```

Main tables:

- `albums`: album metadata and MusicBrainz identifiers.
- `users`: no-password app profiles.
- `user_albums`: which shared albums belong to each user's library.
- `album_listens`: user-scoped completed album listens.
- `albums_in_progress`: user-scoped partial Spotify listening sessions.
- `user_app_state`: user-scoped values such as `last_checked`.
- `user_spotify_credentials`: per-user Spotify refresh tokens and sync status.
- `app_state`: legacy app-level values retained for migration compatibility.

Inspect the database with:

```bash
sqlite3 "$DATA_DIR/spotify_tracker.sqlite"
```

Useful SQLite shell commands:

```sql
.tables
.schema albums
.headers on
.mode column
```

Example queries:

```sql
SELECT album_key, artist, name, release_year
FROM albums
ORDER BY artist, name
LIMIT 20;
```

```sql
SELECT u.slug, a.album_key, l.listened_at
FROM album_listens l
JOIN albums a ON a.id = l.album_id
JOIN users u ON u.id = l.user_id
ORDER BY l.listened_at DESC
LIMIT 20;
```

## Setup

Create and activate a Python virtual environment, then install backend
dependencies:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

This frontend uses Vite 7, which requires Node `20.19+` or `22.12+`.

## Configuration

The app reads environment variables from the shell and `.env`.

Important variables:

- `DATA_DIR`: runtime data directory. Defaults to repo-local `data/`.
- `DATABASE_URL`: optional SQLite URL override. Defaults to
  `sqlite:///$DATA_DIR/spotify_tracker.sqlite`.
- `MEDIA_DIR`: optional media directory override. Defaults to `$DATA_DIR/media`.
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`:
  app-level Spotify OAuth settings.

Spotify refresh tokens are not stored in `.env`. Every user, including `jacob`,
stores their refresh token in SQLite through the in-app Spotify connect flow.

## Common Commands

Run backend tests:

```bash
make test
```

Start FastAPI:

```bash
make api
```

API URLs:

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/album-state
http://127.0.0.1:8000/api/users
http://127.0.0.1:8000/api/users/jacob/album-state
```

Run the frontend in another terminal:

```bash
cd frontend
npm run dev
```

If your shell defaults to an older Node, use the installed Node 22 runtime:

```bash
cd frontend
PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH" npm run dev
```

Run Spotify tracking and write to SQLite:

```bash
make track
```

Run Spotify tracking for all users with connected Spotify accounts:

```bash
make track-all
```

Refresh configured album metadata:

```bash
make refresh-metadata
```

The refresh script is configured in `one_time_scripts/_refresh_metadata.py`.
Keep `REFRESH_ALL = False` for targeted refreshes. Setting it to `True` will
attempt to refresh every completed album.

Delete a user and all dependent rows:

```bash
./.venv/bin/python -m one_time_scripts._delete_user <user-slug>
```

To allow deleting the default seeded user:

```bash
./.venv/bin/python -m one_time_scripts._delete_user <user-slug> --force-default-user
```

## Local Development Flow

Typical two-terminal workflow:

```bash
# terminal 1, repo root
make api
```

```bash
# terminal 2
cd frontend
PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH" npm run dev
```

The Vite dev server serves the React app and proxies `/api` requests to
FastAPI on port `8000`.

## Multi-User Spotify Tracking

The frontend starts with a no-password user picker. Each user has independent
listen history, in-progress album state, Spotify credentials, and `last_checked`
cursor. Album metadata, MusicBrainz IDs, and cached artwork are shared.

Connect Spotify for a user from the app header after selecting that user. The
OAuth callback stores the user's refresh token in SQLite. The app-level Spotify
client ID, secret, and redirect URI still come from environment variables.

For a Proxmox VM or LXC deployment, run the multi-user tracker with a systemd
timer rather than inside the FastAPI process. Example unit files:

```ini
# /etc/systemd/system/spotify-tracker-worker.service
[Unit]
Description=Spotify Tracker multi-user sync

[Service]
Type=oneshot
WorkingDirectory=/path/to/spotify_tracker
EnvironmentFile=/path/to/spotify_tracker/.env
ExecStart=/path/to/spotify_tracker/.venv/bin/python -m backend.app.jobs.track_all_users
```

```ini
# /etc/systemd/system/spotify-tracker-worker.timer
[Unit]
Description=Run Spotify Tracker multi-user sync every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable it with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-tracker-worker.timer
```

## Current Notes

- SQLite is the default runtime backend.
- Legacy JSON support remains for import/export and fallback inspection.
- `npm run build` works with Node 22.
- `npm run lint` currently reports existing shadcn/Radix fast-refresh export
  warnings in UI component files.
