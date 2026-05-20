# Backend

The backend is a FastAPI app backed by SQLite. It also includes command-line
jobs for Spotify tracking and operational scripts for metadata/artwork
maintenance.

## App Structure

- `backend/app/main.py`: app factory, schema creation, router registration, and
  static artwork mount.
- `backend/app/config.py`: environment-backed settings.
- `backend/app/routers/album_state.py`: default album-state endpoint.
- `backend/app/routers/albums.py`: manual album creation, metadata edits,
  refresh, merge, listen mutation, tags, feedback, and delete actions.
- `backend/app/routers/users.py`: user list/create and user-scoped album state
  and album mutations.
- `backend/app/routers/spotify.py`: Spotify connect, callback, status, and sync.
- `backend/app/routers/health.py`: health check.
- `backend/app/services/`: app services for Spotify tracking/OAuth, artwork
  cache, and user administration.
- `backend/app/jobs/`: scheduled or manual tracking entrypoints.

## Request Flow

Routers should validate request models, resolve the target user/repository,
call a service or repository method, and return a schema model. Expected errors
should become clear HTTP responses; unexpected errors should not be hidden with
silent fallbacks.

Pydantic API contracts live in `backend/app/schemas.py`. Keep frontend API
usage in `frontend/src/services/albumApi.js` aligned with these contracts.

## Jobs and Scripts

- `make track`: runs `main.py`, a compatibility wrapper for default-user
  tracking.
- `make track-all`: runs `backend.app.jobs.track_all_users` for every user with
  connected Spotify credentials.
- `make refresh-metadata`: runs the targeted refresh script in
  `one_time_scripts/_refresh_metadata.py`.
- `make cache-artwork`: downloads and stores artwork through the artwork cache
  service.
- `one_time_scripts/_delete_user.py`: deletes a user and dependent data.

## Standards

- Keep route handlers thin and deterministic.
- Put business behavior in services and persistence behavior in repositories.
- Do not call Spotify or MusicBrainz directly from routers.
- Keep migrations idempotent because app startup calls schema creation.
- Treat `tracking.py`, `album_metadata_service.py`, and
  `metadata_refresh_service.py` as active backend modules, not archival files.
- Add tests for route behavior, service behavior, repository persistence, and
  migration compatibility when changing those surfaces.
