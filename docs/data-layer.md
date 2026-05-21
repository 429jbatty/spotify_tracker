# Data Layer

SQLite is the runtime source of truth. The default database path is derived from
`DATA_DIR`:

```text
$DATA_DIR/spotify_tracker.sqlite
```

If `DATA_DIR` is unset, development uses a repo-local `data/` directory. For
deployment, set `DATA_DIR` outside the repo and back it up.

## Main Tables

- `albums`: shared album metadata, MusicBrainz identifiers, release dates,
  source, metadata JSON, and artwork fields.
- `users`: no-password app profiles.
- `user_albums`: per-user album membership, tags, rating, and notes.
- `album_listens`: per-user completed album listen timestamps.
- `albums_in_progress`: per-user partial Spotify listening sessions.
- `user_app_state`: per-user state values such as `last_checked`.
- `user_spotify_credentials`: per-user Spotify refresh tokens and sync status.
- `app_state`: legacy app-level state retained for migration compatibility.

## Ownership

- Models live in `backend/app/models.py`.
- Schema creation and migration compatibility live in
  `backend/app/database.py` and `backend/app/migrations.py`.
- Runtime reads/writes should go through repositories in
  `backend/app/repositories/`, especially `SqliteStateRepository`.
- User lookup/creation belongs in `backend/app/repositories/user_repository.py`.
- Spotify credential persistence belongs in
  `backend/app/repositories/spotify_credentials_repository.py`.

## Repository Rules

- Preserve the distinction between shared album metadata and user-scoped state.
- Keep save/load behavior frontend-compatible with `AlbumState` in
  `backend/app/schemas.py`.
- Preserve listen history when refreshing metadata.
- Preserve local artwork paths when refreshed metadata only changes remote data.
- Avoid direct SQL writes from routers. Use repositories, services, migrations,
  or explicit one-time scripts.

## Media Storage

`MEDIA_DIR` defaults under `DATA_DIR`. Cached artwork is served from FastAPI at:

```text
/media/artwork
```

The API may expose both remote and local artwork fields. Frontend display code
should use the normalized image URL returned through album state rather than
building media paths itself.

## Inspecting Data

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
