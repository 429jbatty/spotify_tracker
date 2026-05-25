---
name: spotify-import-performance-reviewer
description: Review and improve spotify_tracker Spotify ZIP import performance for large historical exports. Use when imports are slow, memory-heavy, create too many derived rows, over-call MusicBrainz, show misleading progress, or need estimates for 100k+ Spotify play rows.
---

# Spotify Import Performance Reviewer

Use this skill to keep large Spotify ZIP imports shaped around album-session
work instead of raw-row mirroring.

## Performance Model

For 160k Spotify plays, the optimized design should usually be:

- 60-85% faster for local SQLite/CPU work than per-play derived rows
- 40-70% faster end to end when MusicBrainz is not dominant
- 15-35% faster end to end when thousands of MusicBrainz calls or rate limits
  dominate

The exact runtime depends most on unique uncached album count, metadata cache
hit rate, disk speed, and SQLite transaction size.

## Review Checklist

1. Confirm the upload request only stores the ZIP and creates the job.
2. Confirm ZIP JSON is parsed as a stream with `ijson`, not loaded as a full
   in-memory list.
3. Confirm raw event inserts are batched, normally 1k-5k rows per transaction,
   and use SQLite ignore-on-conflict semantics.
4. Confirm raw events are deduped before album derivation.
5. Confirm Spotify does not create one `ImportedListeningEvent` per play.
6. Confirm album derivation queries stored raw events ordered by normalized
   artist, album, and `played_at`.
7. Confirm grouping produces one candidate per album/session, split by the
   48-hour window.
8. Confirm track evidence is counted by Spotify URI when available and
   normalized track title otherwise.
9. Confirm user albums and metadata cache are bulk-loaded or reused before any
   MusicBrainz calls.
10. Confirm MusicBrainz lookup is once per unique uncached album key, not per
    raw play or per repeated session.
11. Confirm progress counters switch units when the workflow switches from
    rows to sessions to unique metadata lookups.
12. Confirm delete uses import-session scoped bulk deletes.

## Red Flags

- `imported_listening_events` row count roughly equals Spotify play count.
- The worker commits once per Spotify play.
- The parser builds a list of all normalized events before storing them.
- MusicBrainz is called for every session of the same album.
- Partial sessions enter noisy review queues.
- Progress appears stuck because the label says rows while the worker is doing
  unique album metadata lookups.
- Delete loops over each event/listen individually when a session-scoped delete
  would be enough.

## Expected Validation

For implementation changes, add generated large-fixture tests rather than
committing large data files. Tests should prove:

- raw Spotify rows are stored and deduped correctly
- no per-play imported rows are created
- multiple sessions for one album can produce multiple listens
- partial sessions are terminal and quiet
- MusicBrainz lookup is deduped by unique album key

Run the import tests and migration tests:

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
./.venv/bin/python -m unittest tests.test_sqlite_migrations -v
```
