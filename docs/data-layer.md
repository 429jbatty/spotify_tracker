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
- `users`: listening profiles with optional Google account ownership and a Spotify sync eligibility flag.
- `user_albums`: per-user album membership, tags, rating, and notes.
- `album_listens`: per-user completed album listen timestamps.
- `albums_in_progress`: per-user partial Spotify listening sessions.
- `user_app_state`: per-user state values such as `last_checked`.
- `user_spotify_credentials`: per-user Spotify refresh tokens and sync status.

## Ownership

- SQLAlchemy models live in `backend/app/database/models/`.
- Engine creation, session factory configuration, and SQLite pragmas live in
  `backend/app/database/engine.py`.
- Schema initialization lives in `backend/app/database/schema.py`. SQLite
  startup seeds the default profile and ensures unique indexes for known release
  groups and assigned profile owners. Starting the app on a current database
  preserves its data, including older credit formats.
- `AlbumCatalog(session)` owns shared album identity, metadata, artwork and
  physical cleanup of eligible catalog entries.
- `AlbumLibrary(session, user)` owns a profile's collection, listens and
  annotations. Library commands that change shared metadata rebuild credit
  facts in the same transaction.
- `AlbumStateRepository(session, user)` loads or replaces a profile's complete
  snapshot, including its tracking cursor and in-progress albums. Snapshot
  reads retrieve memberships and ordered listens in two queries. Import
  matching reads its own catalog projection without loading listens or feedback.
- User lookup/creation belongs in `backend/app/database/repositories/user_repository.py`.
- Spotify credential persistence belongs in
  `backend/app/database/repositories/spotify_credentials_repository.py`.

## Engine and session lifetime

The API creates one SQLite engine and session factory per application. Routes
get that factory through `backend/app/dependencies.py` and open a session
for each unit of work. Import workers use the same factory and start a new
session inside each worker thread. Startup resumes eligible imports using
that factory. Shutdown disposes the API engine. Jobs interrupted by process
exit resume from durable checkpoints when eligible. In-memory databases lend
their single connection to one session at a time so each transaction is isolated.

Standalone commands may run before the API starts. In
`backend/app/job_database.py`, `job_session_factory()` initializes the configured
database once and disposes its engine when the command ends. The Spotify batch
uses it for profile discovery, a fresh session per profile, and a separate
session to record an individual sync failure. Single-session commands can use
`job_session()`.

The Spotify sync HTTP handler opens a short session to authorize the owner and
passes the same application factory to tracking. Album state and sync status
are committed separately.

## Repository Rules

- Preserve the distinction between shared album metadata and user-scoped state.
- Keep save/load behavior frontend-compatible with `AlbumState` in
  `backend/app/schemas.py`.
- Preserve listen history when refreshing metadata.
- Preserve local artwork paths when refreshed metadata only changes remote data.
- Keep queries and bulk writes in repositories. Services own workflow decisions
  and can stage field changes on records loaded in their unit of work.
- Resolve the profile in the caller and pass the attached `User` to the library
  or snapshot repository. Authorized routes reuse the profile returned by the
  ownership check. Catalog-only jobs require a session.
- Pass the same session when several operations share a transaction. Manual
  album changes take the SQLite write lock after enrichment and emit activity
  after commit. Import candidate and review workflows commit library writes
  before saving the current result on the import row.
- Snapshot replacement and profile deletion can remove catalog entries with
  no memberships. Import cleanup also requires that no global listens remain.
- Explicit maintenance scripts may query the database directly for scoped
  audits, migrations, and repairs.

## Media Storage

`MEDIA_DIR` defaults under `DATA_DIR`. Cached artwork is served from FastAPI at:

```text
/media/artwork
```

The API may expose both remote and local artwork fields. Frontend display code
should use the normalized image URL returned through album state rather than
building media paths itself.

## Artwork Backfill

Spotify and Last.fm imports use MusicBrainz metadata for album matching, but
skip Cover Art Archive lookups during import matching so large imports stay
fast. Albums created from those import matches can therefore have MusicBrainz
release IDs and tracklists while still missing artwork.

Use the artwork backfill command to repair those rows from stored MusicBrainz
IDs only. It does not rerun full metadata refresh and should not change
canonical artist/title, release dates, labels, tracklists, tags, ratings, notes,
or listen history.

Dry-run is the default:

```bash
DATA_DIR=/opt/spotify_tracker/data make backfill-artwork
```

Before applying changes in production, back up the SQLite database:

```bash
sqlite3 /opt/spotify_tracker/data/spotify_tracker.sqlite \
  ".backup /opt/spotify_tracker/data/spotify_tracker.sqlite.bak-artwork-$(date +%Y%m%d-%H%M%S)"
```

Apply in bounded batches:

```bash
DATA_DIR=/opt/spotify_tracker/data make backfill-artwork ARGS="--apply --limit 100"
```

Repeat the apply command until the dry-run reports few or no remaining albums.
By default, apply mode also downloads found artwork into `MEDIA_DIR/artwork` and
updates `local_image_path`; pass `ARGS="--apply --no-cache-local"` to store only
remote artwork URLs.

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
