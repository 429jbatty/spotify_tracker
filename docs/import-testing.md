# Import Testing

Use this guide before deploying changes to Last.fm import behavior.

## Mock 500-Scrobble Test

Purpose: validate UI behavior, background progress, grouping, review display,
and cleanup without live Last.fm or MusicBrainz.

Expected fixture shape:

- 45 complete album sessions x 8 tracks = 360 scrobbles.
- 20 partial album sessions x 3 tracks = 60 scrobbles.
- 10 unresolvable album sessions x 5 tracks = 50 scrobbles.
- 30 missing-album scrobbles = 30 scrobbles.
- Total: 500 scrobbles.

Expected results:

- 45 derived album listens.
- 10 grouped review candidates.
- 30 missing-album rows.
- No live Last.fm or MusicBrainz calls.
- Import remains visible for inspection until cleanup.

## Live Small-User Test

Purpose: validate real Last.fm paging, real album names, MusicBrainz latency,
metadata cache behavior, and UI progress on a small public account.

Steps:

1. Use the real backend and real `LASTFM_API_KEY`.
2. Find a public Last.fm user with roughly 300-700 total scrobbles.
3. Back up the dev SQLite DB.
4. Ensure user `test` exists.
5. Delete only prior `test` imports for the chosen Last.fm username/session.
6. Preview from the UI and confirm the total is plausible.
7. Start background import and watch status recovery after dialog close/reopen
   and browser refresh.
8. Confirm history, album table, review queue, duplicate preview, and cleanup.

Do not import into `jacob` during validation.

## Live Scale Test

Purpose: validate behavior against a realistic larger account such as
`jbatty429`.

Run this only after the mock and small-user tests pass. The current import path
has no request-level cap for commit, so it may import all available newer
scrobbles.

Acceptance checks:

- Progress does not stall at `fetching_metadata 0/N`.
- One-track singles and MusicBrainz `Single` release groups are not created as
  album listens.
- `not_found` metadata cache rows are not retried in a tight loop.
- Review items are grouped and readable.
- Duplicate preview after import shows stored scrobbles as duplicates.
- Deleting the test import removes imported events/listens for that session.

## API Checks

```bash
curl -s http://127.0.0.1:8000/api/users/test/imports | ./.venv/bin/python -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/api/users/test/imports/review | ./.venv/bin/python -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/api/users/test/album-state | ./.venv/bin/python -m json.tool
```

## Required Test Commands

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
make test
```

Run frontend checks when UI code changes:

```bash
cd frontend
npm run build
npm run lint
```

`npm run lint` should pass without warnings before opening a PR.
