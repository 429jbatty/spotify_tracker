# Testing

Backend tests use Python `unittest`. Frontend verification uses Vite build and
ESLint scripts.

## Commands

```bash
make test
```

```bash
cd frontend
npm run build
npm run lint
```

`npm run lint` may report existing shadcn/Radix fast-refresh export warnings in
UI primitive files.

## Coverage Map

- `tests/test_tracking.py`: album progress and completion behavior.
- `tests/test_album_metadata_service.py`: MusicBrainz matching and metadata
  shaping.
- `tests/test_metadata_refresh_service.py`: metadata refresh preservation and
  failure behavior.
- `tests/test_sqlite_state_repository.py`: SQLite state round trips and album
  mutations.
- `tests/test_sqlite_migrations.py`: schema/migration compatibility.
- `tests/test_api_album_state.py`: album-state API behavior.
- `tests/test_api_album_actions.py`: manual album, listen, refresh, merge,
  tag, feedback, and delete actions.
- `tests/test_multi_user_album_state.py`: user-scoped isolation.
- `tests/test_spotify_tracking_service.py`: user-scoped Spotify tracking.
- `tests/test_spotify_oauth_service.py`: OAuth callback and credential storage.
- `tests/test_artwork_cache_service.py`: artwork download/cache behavior.
- `tests/test_admin_user_service.py`: user deletion behavior.
- `tests/test_album_state_contract.py`: frontend-facing album-state contract.
- `tests/test_api_health.py`: app import and health check.

## Expectations

- Mock Spotify, MusicBrainz, and network-bound artwork calls.
- Add migration tests for any model/table changes.
- Add API tests for any changed request/response contract.
- Add repository tests for persistence behavior and user scoping.
- Add frontend build/lint verification for meaningful frontend changes.
- Documentation-only changes do not require the app test suite, but should pass
  Markdown link/path sanity checks and `git diff --check`.
