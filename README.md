# Spotify Tracker

A personal album-listening tracker. The backend pulls recent Spotify plays,
marks albums complete when enough tracks were heard, enriches albums with
MusicBrainz metadata and cover art, and serves the data to a React/Vite
frontend through FastAPI.

## Architecture

SQLite is the runtime source of truth.

```text
Spotify tracking job
  -> SQLite
  -> FastAPI /api/album-state
  -> React frontend
```

The old `album_state.json` flow is now migration and backup tooling only. The
frontend no longer reads the static JSON file directly.

Key backend paths:

- `main.py`: runs Spotify tracking and writes state.
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

Default database:

```text
data/spotify_tracker.sqlite
```

Main tables:

- `albums`: album metadata and MusicBrainz identifiers.
- `album_listens`: one row per completed album listen.
- `albums_in_progress`: partial Spotify listening sessions.
- `app_state`: app-level values such as `last_checked`.

Inspect the database with:

```bash
sqlite3 data/spotify_tracker.sqlite
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
SELECT a.album_key, l.listened_at
FROM album_listens l
JOIN albums a ON a.id = l.album_id
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

- `DATABASE_URL`: SQLite URL. Defaults to `sqlite:///data/spotify_tracker.sqlite`.
- `ALBUM_STATE_BACKEND`: defaults to `sqlite`. Use `json` only for legacy reads.
- `STATE_FILE`: legacy JSON input path.
- `EXPORT_STATE_FILE`: JSON backup output path.
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`,
  `SPOTIFY_REFRESH_TOKEN`: Spotify API credentials.

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

Refresh configured album metadata:

```bash
make refresh-metadata
```

The refresh script is configured in `one_time_scripts/_refresh_metadata.py`.
Keep `REFRESH_ALL = False` for targeted refreshes. Setting it to `True` will
attempt to refresh every completed album.

## JSON Migration And Backups

Import the legacy JSON state into SQLite:

```bash
make import-json-to-sqlite
```

Export the current SQLite state to JSON:

```bash
make export-sqlite-to-json
```

Default export path:

```text
data/exports/album_state_export.json
```

`data/exports/` and SQLite database files are ignored by git.

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

## Current Notes

- SQLite is the default runtime backend.
- Legacy JSON support remains for import/export and fallback inspection.
- `npm run build` works with Node 22.
- `npm run lint` currently reports existing shadcn/Radix fast-refresh export
  warnings in UI component files.
