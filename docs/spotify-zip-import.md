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

## Source Traceability

Spotify ZIP imports store source metadata on the import session:

- original uploaded filename
- uploaded byte size
- SHA-256 of the uploaded ZIP bytes
- ZIP member count after validation
- duplicate import session ID when the same user previously completed an import
  with the same SHA-256

Each persisted raw play also stores the ZIP member path and JSON array index.
The diagnostics endpoint can use those fields to report literal source
locations for a specific artist/album without retaining the uploaded ZIP.

Use these fields first when reconciling an import discrepancy. The filename is
only a label; the SHA-256 proves whether the app processed the same ZIP being
inspected later. Row provenance proves which ZIP member and array index
contributed to a candidate listen.

## Diagnostics

Use the import diagnostics endpoint for album-specific investigations:

```text
GET /api/users/{user_slug}/imports/{import_session_id}/diagnostics?artist={artist}&album={album}
```

The response is intended to answer "what did this import actually read and why
did it create or skip listens?" without re-parsing the source ZIP. It should
include:

- raw row count and timestamp range for the requested artist/album
- grouped album-session candidates
- matched, missing, and expected tracks for each candidate
- source row locations using `source_file` and `source_index`
- imported listening-event IDs, final statuses, and created listen IDs

If the diagnostic data disagrees with a local CSV, compare the session
SHA-256 before investigating completion logic. A source mismatch can otherwise
look like a matching bug.

## Album Matching

Spotify provides album and artist names in the export. When app-level Spotify
catalog credentials are configured, the importer also resolves unique Spotify
track URIs in batches and uses Spotify's own album identity for completion:

- resolve unique Spotify track URIs through Spotify catalog metadata, not per row
- group resolved raw plays by Spotify album ID
- split each Spotify album group into 48-hour sessions
- count unique Spotify tracks in the session against Spotify album
  `total_tracks`
- require the app's album completion threshold
- use MusicBrainz for album metadata/artwork enrichment after Spotify proves
  completion
- fall back to normalized artist/album names and cached/local MusicBrainz
  tracklists when Spotify catalog lookup is unavailable or a track is unresolved
- preserve MusicBrainz album-type guardrails so singles, EPs, and low-confidence
  matches do not silently become album listens
- send uncertain but plausible sessions to review

Spotify URI is still the raw dedupe key when present. For completion, resolved
Spotify catalog data is authoritative for Spotify-sourced listens; MusicBrainz is
the enrichment source rather than the source of the Spotify album track count.

## Progress States

| Status | Meaning |
| --- | --- |
| `queued` | Import session exists; worker has not started. |
| `validating_zip` | ZIP structure and safety limits are being checked. |
| `parsing_spotify_history` | Spotify JSON files/rows are being streamed. |
| `storing_streaming_events` | Raw plays are being batch inserted. |
| `resolving_spotify_catalog` | Unique Spotify track URIs are being resolved to source album metadata. |
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

Keep the SQLite path optimized before considering a database migration. The
importer should short-circuit Spotify catalog sessions that are clearly below
the completion threshold, update candidate progress at coarse intervals, and
bulk-persist actionable album-session rows. Revisit Postgres only if a
75k-100k row Spotify ZIP still spends more than 2-3 minutes in local import
processing after excluding Spotify catalog and MusicBrainz network time.

Raw insert batch size must stay below SQLite's bind-parameter limit. When new
columns are added to `spotify_streaming_events`, recalculate:

```text
rows per batch * inserted columns per row
```

and keep it under the runtime SQLite limit with margin. A failure immediately
after `storing_streaming_events` starts, with zero raw rows persisted, can be a
`too many SQL variables` insert failure rather than a bad ZIP.

## Failed Import Triage

For a failed Spotify ZIP import, inspect in this order:

1. `import_sessions`: status, `error_message`, source filename, byte size,
   SHA-256, member count, duplicate session, and `artifact_path` if retained.
2. `import_session_logs`: last successful stage and full traceback when stored.
3. Raw counts for `spotify_streaming_events` by `import_session_id`.
4. Parser output from the uploaded ZIP: member count, audio JSON member count,
   parsed row count, skipped missing-track rows, and timestamp range.
5. If raw storage failed, check insert batch size against SQLite variable
   limits before assuming the data is malformed.
6. If completion looks wrong, use the diagnostics endpoint and source row
   locations before making claims about missing or ghost listens.

Do not mutate the runtime database during investigation unless the user has
explicitly asked to repair or delete the failed session.

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
