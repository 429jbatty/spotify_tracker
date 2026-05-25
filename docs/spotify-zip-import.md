# Spotify ZIP Import

Spotify ZIP import lets a user upload the `.zip` file Spotify sends for
Extended Streaming History. The app stores raw plays for audit and deletion,
then derives album listens from album-session candidates. Raw Spotify plays are
not album listens.

## User Flow

1. The user requests Extended Streaming History from Spotify.
2. Spotify sends a ZIP file.
3. The user uploads that ZIP in the Import History dialog under Spotify ZIP.
4. The frontend creates an import job and polls the existing import-session
   status endpoint for progress.
5. Completed, failed, review, and delete behavior use the same import history
   surfaces as other imports.

The user should not manually extract the ZIP.

## Backend Flow

1. `POST /api/users/{user_slug}/imports/spotify/upload` authenticates the user,
   validates upload size/type, stores the ZIP under `DATA_DIR/import_uploads/`,
   creates an `import_sessions` row, and returns the job response immediately.
2. A background worker validates the ZIP structure and safety limits before
   reading JSON.
3. Spotify history JSON arrays are parsed incrementally with `ijson`.
4. Normalized plays are inserted into `spotify_streaming_events` in batches with
   `INSERT OR IGNORE` semantics.
5. The worker queries deduped raw plays for the import session, groups them by
   normalized artist/album, and splits each group into 48-hour album sessions.
6. The matcher resolves sessions against existing user albums and cached/local
   metadata before any MusicBrainz lookup.
7. MusicBrainz is called only for unique uncached album candidates that have
   enough track evidence.
8. Completed sessions create `album_listens` with
   `source="spotify_import"` / `entry_source="spotify_import"`.
9. Partial sessions stay terminal/non-actionable unless they are plausible
   review candidates.
10. The temporary ZIP is deleted in the worker's cleanup path after success or
    failure.

## Data Model

- `import_sessions.artifact_path`: temporary ZIP path while the worker runs.
- `spotify_streaming_events`: raw, user-scoped Spotify plays with
  `import_session_id`, normalized fields, raw payload, and an
  `event_fingerprint`.
- `imported_listening_events`: session-level import bookkeeping and review rows
  for Spotify. Spotify import must not create one row per raw play here.
- `album_listens`: completed derived listens only.

Per-session delete removes the selected session's raw Spotify events,
Spotify-derived imported rows, and album listens created from those rows.

## ZIP Safety

The worker inspects entries without extracting to disk. It rejects:

- non-ZIP and invalid ZIP files
- absolute paths, `..`, backslash traversal, and symlinks
- too many entries
- excessive total uncompressed JSON size
- extreme compression ratios
- invalid JSON

Default limits:

- ZIP upload size: 250 MB
- total uncompressed JSON: 2 GB
- ZIP entries: 200
- temporary directory: `DATA_DIR/import_uploads/`

## Supported Files And Fields

Recognized history files include:

- `Streaming_History_Audio_*.json`
- `endsong_*.json`
- legacy `StreamingHistory*.json`

Extended Streaming History normalization:

| Spotify field | App field |
| --- | --- |
| `ts` | `played_at` |
| `ms_played` | `ms_played` |
| `master_metadata_track_name` | `track_name` |
| `master_metadata_album_artist_name` | `artist_name` |
| `master_metadata_album_album_name` | `album_name` |
| `spotify_track_uri` | `spotify_track_uri` |

Legacy fallback fields include `endTime`, `msPlayed`, `artistName`, and
`trackName`.

## Dedupe

The raw event fingerprint uses Spotify URI when present:

```text
user_id + played_at + ms_played + spotify_track_uri
```

When URI is absent, it falls back to normalized names:

```text
user_id + played_at + ms_played + normalized artist + normalized album + normalized track
```

Raw dedupe happens before album-session derivation, so duplicate upload rows do
not inflate completion evidence.

## Album Matching

Spotify provides album and artist names, but the importer still proves album
completion before writing listen history:

- group raw plays by normalized artist and album
- split each group into 48-hour sessions
- count unique played tracks in the session by Spotify URI when available,
  otherwise normalized track name
- compare the session to existing user albums or cached/local tracklists
- require the app's album completion threshold
- preserve MusicBrainz album-type guardrails so singles, EPs, and low-confidence
  matches do not silently become album listens
- send uncertain but plausible sessions to review

Spotify URI is evidence for dedupe and unique-track identity. It is not a live
Spotify lookup during import.

## Progress States

| Status | Meaning |
| --- | --- |
| `queued` | Import session exists; worker has not started. |
| `validating_zip` | ZIP structure and safety limits are being checked. |
| `parsing_spotify_history` | Spotify JSON files/rows are being streamed. |
| `storing_streaming_events` | Raw plays are being batch inserted. |
| `grouping_album_sessions` | Raw plays are becoming album-session candidates. |
| `matching_cached_albums` | Existing albums and metadata cache are being checked. |
| `fetching_metadata` | Unique uncached album candidates are using MusicBrainz. |
| `finalizing` | Summaries, statuses, and cleanup are being written. |
| `completed` | Terminal success. |
| `failed` | Terminal failure. |

Progress counts change units across the job: parsed rows, stored plays, session
candidates, and unique metadata lookups are different units.

## Performance Shape

The optimized import avoids mirroring every Spotify play into
`imported_listening_events`. For a 160k-row export:

- SQLite/local processing should usually be 60-85% faster than a per-play
  derived-row flow.
- End-to-end import should usually be 40-70% faster when MusicBrainz is not the
  dominant cost.
- End-to-end import may only be 15-35% faster when thousands of uncached
  MusicBrainz lookups dominate runtime.

The main runtime drivers are unique album count, metadata cache hit rate,
MusicBrainz rate limiting, disk speed, and transaction size.

## Validation

Backend tests:

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
./.venv/bin/python -m unittest tests.test_sqlite_migrations -v
make test
```

Run frontend checks when upload UI or progress copy changes:

```bash
cd frontend
npm run build
npm run lint
```
