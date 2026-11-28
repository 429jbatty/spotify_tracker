# Spotify sync concurrency

Spotify tracking reads a profile snapshot in one explicit SQLite read
transaction, then ends that transaction before Spotify and MusicBrainz calls.
The snapshot includes the cursor, in-progress albums, completed library,
shared metadata visible in the library, listen history and profile feedback.

After deriving completions, `AlbumStateRepository.replace_for_sync` starts
`BEGIN IMMEDIATE`, reloads current state and compares it to the unmodified
source snapshot. The SQLite write reservation covers both the comparison and
the existing replacement commit, so another writer cannot commit between them.
A changed snapshot is rolled back without saving any sync changes.

`run_tracking_for_user` retries conflicts with a fresh session and snapshot,
up to three attempts total. Each attempt fetches using the current cursor and
reruns the existing completion logic. This preserves concurrent manual/import
additions, deletions, listens and edits, and prevents an older overlapping sync
from restoring old progress or moving the cursor backward. Writes to another
profile's history do not invalidate the snapshot; shared metadata edits do.
No database migration or long-lived database lock is required.

Provider or database failures are not retried by this conflict policy. Failed
state writes roll back, leaving the cursor available for a later retry. The
existing separate sync-success commit remains: if status recording fails after
state was saved, the next run fetches from the saved cursor. Exhausting conflict
attempts raises `SpotifySyncConflict`; the batch runner records it using its
normal sync-error path. A later scheduled or manual sync can try again.

The general `replace` method remains an authoritative snapshot operation for
explicit state replacement and compatibility callers. Spotify sync must use
the guarded read/save pair. These boundaries own their session's transaction
and must not be mixed with pending application writes.

Run the isolated provider-mocked regressions with:

```sh
.venv/bin/python -m unittest tests.test_spotify_sync_concurrency tests.test_spotify_tracking_service
```
