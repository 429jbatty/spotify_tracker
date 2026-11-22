# Last.fm Import

Last.fm import stores raw scrobbles first, then derives album listens only when
the import can prove a completed album listen. Raw scrobbles are not album
listens.

## Flow

1. The React UI submits preview or commit requests through
   `frontend/src/services/albumApi.js`.
2. `backend/app/routers/imports.py` validates the user and delegates to
   `backend/app/services/import_service.py`.
3. Preview calls Last.fm with a bounded page/row limit and does not call
   MusicBrainz.
4. Commit creates an `import_sessions` row with `queued` status and starts a
   background worker.
5. The worker fetches Last.fm scrobbles since the latest stored scrobble for
   that source username.
6. Raw events are persisted in `imported_listening_events`; rows without album
   names are stored as `ignored_missing_album`.
7. Album-bearing rows are grouped by artist/album and split into 48-hour
   candidate sessions.
8. The first match pass uses existing user albums and the persistent
   `album_metadata_cache`; it does not call MusicBrainz.
9. The remote metadata pass only handles candidates that still need tracklists
   and are eligible for MusicBrainz lookup.
10. A candidate creates an `album_listens` row only when it passes the album
    completion and album-type rules below.

## Status Lifecycle

| Status | Meaning |
| --- | --- |
| `queued` | Import session exists; background worker has not started. |
| `fetching_lastfm` | Worker is paging through Last.fm recent tracks. |
| `storing_scrobbles` | Normalized raw scrobbles are being persisted. |
| `grouping_album_sessions` | Album candidates are being grouped/split. |
| `matching_cached_albums` | Existing albums and metadata cache are being used. |
| `fetching_metadata` | Eligible unresolved candidates are using MusicBrainz. |
| `finalizing` | Summaries and final event statuses are being written. |
| `completed` | Terminal success. |
| `failed` | Terminal failure; inspect backend logs and session summary. |

## Domain Rules

- Only full album listens should create `album_listens` rows.
- Album completion is based on unique normalized scrobbled tracks compared to
  the matched tracklist. The threshold is `ALBUM_COMPLETION_THRESHOLD`.
- Last.fm candidate sessions use a 48-hour window.
- Uncached Last.fm candidates with fewer than
  `LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS` unique tracks skip remote
  MusicBrainz lookup and become `partial_listen`.
- Existing user albums with tracklists are trusted as user-curated data and can
  match even when the candidate is short.
- New MusicBrainz-derived Last.fm album listens require release-group
  `primary_type == "Album"`.
- MusicBrainz `Single`, EP-style, or short non-album releases must not become
  new album listens just because they match 100% of a one-track tracklist.
- Old cached metadata without `primary_type` must have at least
  `LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS` tracks before it can derive a new
  album listen.
- `album_metadata_cache.status = "not_found"` is a negative cache hit and must
  not be retried during the same import path.

## Matching Decision Path

The import review queue does not mean "this is not an album." It means the
import could not automatically prove that a Last.fm scrobble session should
become an album listen.

For each album-bearing group of scrobbles, the importer:

1. Groups rows by source user, artist, and album.
2. Splits those rows into 48-hour candidate sessions.
3. Counts unique normalized scrobbled tracks in each session.
4. Checks whether the user already has a matching album with a trusted
   tracklist.
5. Checks `album_metadata_cache` for a MusicBrainz-derived tracklist or a
   negative `not_found` result.
6. Calls MusicBrainz only when no cache row exists and the session has enough
   unique tracks to justify remote lookup.
7. Compares unique scrobbled tracks to the matched tracklist.
8. Creates an album listen only when the matched track ratio meets
   `ALBUM_COMPLETION_THRESHOLD` and MusicBrainz classifies the release group as
   an album.

This means a famous album can still land in review if the importer cannot load
the tracklist. It also means a famous album can be correctly identified but
still become `partial_listen` if only a few tracks were scrobbled.

## Metadata matching and negative cache

The resolver favors exact normalized titles and penalizes extra title words.
It can try additional candidates when a release lacks a usable tracklist. A
negative `album_metadata_cache` entry can persist from an earlier lookup, so a
matcher improvement alone does not automatically repair existing cache rows.
Investigate the relevant cache and import session before any scoped reprocessing.

## Persistence

- `import_sessions` tracks source username, status, progress, and summary.
- `imported_listening_events` stores raw Last.fm rows and per-event match
  status.
- `album_metadata_cache` stores MusicBrainz matches and negative lookups.
- `albums` stores shared album metadata.
- `user_albums` and `album_listens` are user-scoped derived album-listen state.

## Common Failure Modes

- Progress stuck at `fetching_metadata` with `0/N`: check whether MusicBrainz
  calls are blocked and whether `not_found` cache rows are being retried.
- Songs/singles appear as albums: verify MusicBrainz `primary_type` and
  tracklist length; singles should remain `partial_listen`.
- Import rerun finds no rows: the prior session may have already persisted raw
  events. Delete the broken test import session before retrying.
- Review list has duplicate-looking albums: distinguish raw scrobble rows,
  candidate sessions, and album-level review grouping. Multiple sessions for
  the same album are legitimate listens, but the review UI should make that
  grouping explicit.

## Safe Debug Queries

Set `TRACKER_DB` to the dev database file. Use the first query to identify the
test import, then set `SESSION_ID` to its numeric ID.

```bash
sqlite3 -readonly "${TRACKER_DB:?set TRACKER_DB}" \
  "select s.id, s.source_user_id, s.status, s.session_name, json_extract(s.summary_json,'$.progress_label'), json_extract(s.summary_json,'$.progress_current'), json_extract(s.summary_json,'$.progress_total') from import_sessions s join users u on u.id=s.user_id where u.slug='test' order by s.id desc limit 5;"
```

```bash
sqlite3 -readonly "${TRACKER_DB:?set TRACKER_DB}" \
  "select match_status, count(*) from imported_listening_events where import_session_id=${SESSION_ID:?set SESSION_ID} group by match_status order by match_status;"
```

```bash
sqlite3 -readonly "${TRACKER_DB:?set TRACKER_DB}" \
  "select artist, album, status, json_extract(metadata_json,'$.primary_type'), json_array_length(json_extract(metadata_json,'$.tracklist')) from album_metadata_cache order by updated_at desc limit 20;"
```

Only delete imports for `test` during validation unless the user explicitly
approves another user. Set `ALBUMARY_TOKEN` to the profile owner’s session token:

```bash
curl -X DELETE -H "Authorization: Bearer $ALBUMARY_TOKEN" \
  "http://127.0.0.1:8000/api/users/test/imports/${SESSION_ID:?set SESSION_ID}"
```

## Verification

Run the backend import tests after any Last.fm import logic change:

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
make test
```

For UI behavior, start the backend and Vite, select user `test`, then test
preview, background import, progress recovery, review grouping, duplicate
preview, and cleanup.
