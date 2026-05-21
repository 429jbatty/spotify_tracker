# Architecture

Spotify Tracker is split into a FastAPI/SQLite backend and a React/Vite
frontend. The backend owns tracking, metadata enrichment, persistence, and API
contracts. The frontend owns user selection, navigation, filtering, display,
and manual album actions.

## Runtime Flow

```text
Spotify recent plays
  -> backend/app/jobs/track_all_users.py or main.py
  -> backend/app/services/spotify_tracking_service.py
  -> tracking.py
  -> album_metadata_service.py
  -> backend/app/repositories/sqlite_state_repository.py
  -> SQLite
  -> backend/app/main.py FastAPI app
  -> frontend/src/services/albumApi.js
  -> React components
```

The scheduled tracking job runs outside the FastAPI request path. FastAPI reads
and mutates already-persisted state, while the worker periodically updates that
state from Spotify.

## Source Layout

- `backend/app/main.py`: FastAPI app factory and router registration.
- `backend/app/routers/`: HTTP endpoints for health, album state, album
  actions, users, and Spotify OAuth/sync.
- `backend/app/services/`: backend services for user admin, Spotify tracking,
  Spotify OAuth, and artwork caching.
- `backend/app/repositories/`: SQLite-backed persistence.
- `backend/app/models.py`: SQLAlchemy table definitions.
- `backend/app/schemas.py`: Pydantic request and response contracts.
- `backend/app/jobs/`: command-line worker entrypoints.
- Root modules such as `tracking.py`, `album_metadata_service.py`,
  `metadata_refresh_service.py`, and `musicbrainz_client.py`: active legacy
  service modules used by jobs, services, and one-time scripts.
- `frontend/src/`: React app, API client, hooks, components, and UI primitives.
- `one_time_scripts/`: operational scripts for targeted metadata refreshes,
  artwork caching, and user deletion.
- `deploy/`: systemd, Caddy, environment, and deploy-script templates.

## User Model

The app supports multiple no-password users. Album metadata is shared, but each
user has independent completed listens, in-progress Spotify tracking state,
Spotify credentials, `last_checked` cursor, tags, ratings, and notes.

Keep this split central when changing backend code. Most album metadata edits
are shared; most listen and feedback edits are user-specific.
