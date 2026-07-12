# AGENTS.md

This repo is a personal album-listening tracker. The backend tracks Spotify
plays, decides when an album listen is complete, enriches albums with
MusicBrainz metadata and cover art, persists everything in SQLite, and exposes
the data to a React/Vite frontend.

## Architecture Map

```text
Spotify tracking job
  -> tracking.py completion logic
  -> album_metadata_service.py / musicbrainz_client.py enrichment
  -> backend/app/repositories/sqlite_state_repository.py
  -> SQLite
  -> FastAPI routers in backend/app/routers
  -> frontend/src/services/albumApi.js
  -> React pages and components
```

SQLite is the runtime source of truth. Album metadata is shared across users;
listen history, in-progress albums, Spotify credentials, tags, ratings, notes,
and app state are user-scoped.

## Where To Change Things

- API routes: add or modify endpoints in `backend/app/routers/`, keeping route
  handlers thin.
- Backend business logic: use `backend/app/services/` or the existing root
  service modules when the behavior already lives there.
- Persistence: change `backend/app/models.py`, `backend/app/migrations.py`, and
  `backend/app/repositories/` together. Do not bypass repository behavior for
  normal app writes.
- Spotify tracking: start in `backend/app/services/spotify_tracking_service.py`,
  `backend/app/jobs/`, and `tracking.py`.
- MusicBrainz metadata: use `album_metadata_service.py` for matching/shaping
  and `musicbrainz_client.py` for API calls, retries, and rate limiting.
- Artwork caching: use `backend/app/services/artwork_cache_service.py` and the
  `MEDIA_DIR`/`DATA_DIR` settings.
- Imports: use `backend/app/routers/imports.py` for HTTP boundaries and
  `backend/app/services/import_service.py` for Last.fm, Spotify ZIP, review,
  diagnostics, and cleanup behavior.
- Public activity and splash data: use `backend/app/routers/public.py` and
  `backend/app/services/public_activity_service.py`.
- API contracts: update `backend/app/schemas.py` and the matching frontend API
  usage in `frontend/src/services/albumApi.js`.
- Frontend views: page-level components live in `frontend/src/components/`;
  shared UI primitives live in `frontend/src/components/ui/`.
- Frontend feature folders: use `components/discovery/`,
  `components/dataQuality/`, `components/importHistory/`, `components/search/`,
  `components/splash/`, and `components/timeline/` for feature-specific UI.

## Backend Standards

- Keep FastAPI routers small: validate input, load dependencies, call services
  or repositories, and translate expected errors into HTTP responses.
- Keep database access in repositories or explicit migration/admin scripts.
- Preserve user scoping. A change to album listens, in-progress state, tags,
  ratings, notes, or Spotify credentials must not affect another user.
- Preserve shared album identity. `albums.album_key` is the canonical
  artist/title key, while MusicBrainz IDs and cached artwork are shared
  metadata.
- Keep migrations idempotent. `create_schema()` is used by app startup and
  tests, so schema changes must tolerate existing databases.
- Do not make ad hoc MusicBrainz calls from route handlers or frontend code.
- Import flows should store raw source events first, derive album-listen
  candidates second, and send uncertain but plausible candidates to review
  instead of silently creating or dropping listens.
- `backend/app/services/import_service.py` is a high-risk module. Keep edits
  focused, preserve resumable import statuses, and cover Last.fm/Spotify ZIP
  changes with import tests.

## Frontend Standards

- Use `frontend/src/services/albumApi.js` for backend requests.
- Normalize backend album state through `frontend/src/services/albumNormalizer.jsx`
  before page components consume it.
- Prefer small, reusable components. Split large feature code into helpers under
  `components/utils/` or feature-specific component folders.
- Use existing shadcn/Radix-style UI primitives in `components/ui/` before
  adding new primitives.
- Keep data mutation flows explicit: call the API service, then refresh album
  state through the page-level callback.
- Avoid adding global state unless prop/state flow becomes genuinely
  unmanageable.
- Keep user-scoped routes as the normal frontend path. Default/global album
  endpoints exist for compatibility, but active profile views should prefer
  `/api/users/{user_slug}/...` through `albumApi.js`.

## Testing Expectations

- Run `make test` for backend behavior changes.
- Run `npm run build` and `npm run lint` from `frontend/` for meaningful
  frontend changes. Existing shadcn/Radix fast-refresh warnings may appear in
  lint.
- Add or update tests when changing completion logic, repository persistence,
  migrations, API contracts, MusicBrainz matching, artwork caching, or
  user-scoped behavior.
- Prefer mocking external APIs in tests. Do not make live MusicBrainz or Spotify
  requests from unit tests.

## Sharp Edges

- The root modules are still active. `main.py`, `tracking.py`,
  `album_metadata_service.py`, `metadata_refresh_service.py`, and
  `musicbrainz_client.py` are not dead code.
- Metadata refresh must preserve listen history and user-specific fields.
- Artwork URLs can be remote or local. API output should prefer usable local
  media URLs when cached artwork exists.
- Last.fm username imports and Spotify Extended Streaming History ZIP imports
  are implemented. CSV, Google Sheets, or other import sources should be added
  as separate source-specific flows that reuse the existing import/review model.
