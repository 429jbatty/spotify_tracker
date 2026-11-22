# Logging implementation plan

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Logging infrastructure, request logs, Spotify sync and import events | Implemented; coverage can be refined |
| 1 | Manual album and listen actions | Implemented and validated |
| 2 | Ratings and notes | Not started |
| 3 | Tags | Not started |
| 4 | User-activity dashboard and validation | Not started |
| 5 | Metadata matching, refresh, and artwork | Not started; some existing warnings |
| 6 | External-service reliability | Not started; some existing fallback events |
| 7 | Authentication and Spotify connections | Not started |
| 8 | Persistence and maintenance | Not started; some existing warnings |

Implement and review each phase separately. Phases 1–4 form the user-activity
MVP; prioritize later phases based on actual diagnostic needs. Event names and
fields below are **proposals**, not a claim that they already exist. Follow
[logging.md](logging.md) for format, severity, context, privacy, and tests; use
the [observability runbook](../deploy/observability/README.md) for infrastructure.
Update the table when implementation status changes.

## Phase 0: Existing foundation

The API and worker emit JSON logs with request, sync-run, or import-session
context where configured. Scheduled Spotify sync and background imports have
start, outcome, failure, and selected fallback/summary events. HTTP request
logs include method, route template, status, and duration; they are not product
interaction events and do not by themselves identify an authenticated user.
Some existing warnings remain unstructured, and individual functions can run
in either the API or worker process.

## Shared rules for phases 1–3

The goal is to understand album-collection activity from **committed changes**,
not request counts. Start with user-scoped routes in
`backend/app/routers/users.py` and their service and repository methods. Check
compatibility endpoints and other entry points so a successful change emits one
event without duplicates. Do not emit successful-action events for rejected,
failed, or no-op writes. Capture identifiers needed for deletion before the
write if the entity may no longer exist afterward.

Use the affected profile's `user_id` and canonical `album_id`; include an actor
account ID only if needed and reliably available. Album metadata is shared,
while collection activity is user-scoped. Keep `request_id` where it propagates,
bind profile context at the actual execution boundary, and test concurrent
user isolation across FastAPI sync/async boundaries. IDs, titles, and tag names
belong in event fields rather than indexed Loki labels.

These are best-effort logs, not an audit trail or mutation source of truth.
**The agreed MVP retention is 30 days.** Dashboard counts represent recent,
observed profile activity, not exact counts of distinct people. Any durable
analytics or explicit user notice is a separate decision. Never log note text,
credentials, tokens, request bodies, or full external payloads.

### Committed change facts

Determine before/after values and construct change facts **inside the same
transaction that performs the write**. Serialize concurrent updates before
reading prior values (for SQLite, an appropriately placed write transaction
such as `BEGIN IMMEDIATE`) or use an equivalent atomic conditional update.
Do not compare a route-level pre-read and post-read across separate transactions:
another request could change the same album between them. Preserve repository
and API behavior, including user scoping and existing response contracts.
Acquire the write lock only immediately before mutation reads and writes, after
any external metadata lookup has completed. Authorization and repository setup
may already start a session transaction, so explicitly design the session/transaction
boundary before using `BEGIN IMMEDIATE`; do not accidentally commit unrelated
work or hold the SQLite writer lock across network calls. Exercise lock contention,
rollback, and authorization behavior in tests.

Use existing feature boundaries; avoid unrelated architecture changes solely for
logging. Keep event policy and emission out of persistence where practical, and
defer or simplify an event if accurate reporting would require an invasive redesign.

Make the write boundary return or otherwise expose immutable, minimal change
facts only after its commit succeeds; a small internal result type or helper is
appropriate. Emit events at a single owning boundary after commit. Preserve
`request_id` where available and bind the profile context at that boundary.
Tests must cover rollback/failure, concurrent updates, and multiple entry points.
Logging is best effort: do not undo a committed write or report it as failed
because log emission fails, and do not claim exactly-once delivery.

For the MVP, include `profile_slug` as a snapshot alongside `user_id` in
action events, so the dashboard can identify the affected profile without a
Loki-to-database join. Use the authorized, resolved profile rather than an
untrusted request value. A later rename or deletion leaves the historical slug
as it was at the time; it is not a verified human identity. Profile slugs are
personal data and follow the same access and retention rules as album fields.

Include `album_id`, `album_artist`, and `album_title` snapshots in
user-action events, including removals. Capture the snapshot before deletion:
the last profile's removal can delete the shared album, so an ID alone may no
longer resolve. These are personal listening data: keep them in log fields,
restrict access, and retain for only the agreed window. `user_id` means the
affected profile, not necessarily a distinct human actor.

## Phase 1: Manual album and listen actions

**Goal:** see whether people manually add or remove albums and listens.

| Event | When to emit |
| --- | --- |
| `album_manually_added` | A manual action creates the profile's album membership. This can reuse an existing shared album. |
| `album_removed` | A manual action removes the profile's album membership. It may also remove that profile's listens and, if unowned, shared metadata; it does not mean other profiles were deleted. |
| `album_listen_added` | A manual action actually creates a listen, including one supplied during manual album creation. |
| `album_listen_removed` | A manual action actually deletes a listen. Removing an album should not generate a separate event for every listen removed with it. |

Include `action_source="manual"` explicitly; do not derive action origin from
`AlbumListen.source`, which can reflect the album's origin instead. Existing
`_add_listen` silently ignores duplicate user/album/timestamp combinations:
HTTP success alone does not mean a listen was added. If manual creation reuses
an existing membership but adds a listen, emit only the listen event. If it
creates both membership and listen, emit both. `add_album_listen` can also
create a missing profile membership implicitly: for that manual action, emit
both the membership and listen events if both were created, and only the listen
event when the membership already existed. Both listen events include the
`listened_at` value. Never emit these manual-action events for sync or imports.
The implementation preserves response and deduplication behavior; the manual
write is serialized after metadata lookup, and events are emitted after commit.

## Phase 2: Ratings and notes

**Goal:** see whether ratings and notes are added, changed, or removed.

Proposed events are `album_rating_changed`, `album_rating_removed`,
`album_note_changed`, and `album_note_removed`, with `user_id` and `album_id`.
For changed ratings include the new numeric `rating` and a `change` value of
`added` or `updated`; for removal use `album_rating_removed` without a value.
For notes, include only `change=added` or `change=updated`, or emit
`album_note_removed`; never include text or its length. One feedback update can
affect both fields: compare persisted and normalized resulting values and emit
only events for actual committed changes. The current PUT passes both fields,
including `None` defaults, to the repository; document and preserve its actual
replacement semantics rather than assuming omitted fields are unchanged.

## Phase 3: Tags

**Goal:** understand tag usage without treating every update as an addition.

Event: `album_tags_changed`, with `user_id`, `album_id`, `added_tags`, and
`removed_tags` as lists of normalized names. The endpoint replaces a list: use
the repository's normalization for both values, compare the resulting sets,
and emit only for a real committed change. Ordering-only changes are no-ops.
Tag names can reveal personal information and follow the same retention and
access limits as other user-action fields.

## Phase 4: User-activity dashboard and validation

The dashboard must answer, for a selected environment and time range:

- Which albums were manually added or removed, and which profile was affected?
- Which albums had manual listens, ratings, notes, or tags changed, including
  added/removed tag names and rating values without exposing note text?
- How many observed actions of each type occurred, without describing those
  counts as distinct people or a guaranteed audit record?

Show event time, action, profile slug and ID, and the album artist/title snapshot;
make retention and best-effort delivery visible. Profile names are historical
snapshots, not a count or identification of unique people. Plain LogQL `| json`
skips arrays: explicitly extract `added_tags` and `removed_tags`, or display
the raw event, and verify both added and removed names are visible. Filter
production and development separately. Generate development fixture actions
with temporary databases and mocked external calls. Arrange for a `validation_run_id` field on their events at the
test harness boundary; never emit this marker on ordinary user traffic or send
the fixtures as production logs. Display or filter the marker in Grafana so
simulated entries are identifiable. Verify a new album, an existing shared
album, a duplicate listen, a deletion, a rating/note change, a tag replacement,
and no-ops. Confirm that
successful changes appear once and failed/no-op writes do not appear. Verify
that deleted album names remain visible after the source record is removed.

## Phase 5: Metadata matching, refresh, and artwork

**Goal:** explain missing or incorrect album information. Record lookup source,
cache outcome, accepted/rejected match reasons, and refresh success, skip, or
failure. Include artwork cache outcomes, unavailable artwork, download/cache
failures, and fallbacks. Manual enrichment should explain timeouts, concurrency
limits, or fallback to supplied details separately from a successful manual add.
Aggregate high-volume lookups and reuse existing warnings rather than emitting
duplicate errors. These paths can run in the API or worker.

## Phase 6: External-service reliability

Capture timeouts, rate limits, exhausted retries, and degraded fallbacks for
Spotify, MusicBrainz, and Last.fm. Log once at the boundary that owns the
outcome, without credentials, secret-bearing URLs, or raw payloads. Coordinate
with phases 0 and 5 to avoid logging the same failure multiple times. These
paths can run in the API or worker.

## Phase 7: Authentication and Spotify connections

Record useful sign-in and connection success/failure categories and access
denials without tokens, email addresses, authorization headers, or request
bodies. Decide actor/profile identification and retention before implementation.
These are API events.

## Phase 8: Persistence and maintenance

Summarize failed writes, migrations, artwork backfills, credit rebuilds, and
batch outcomes with stage and counts. Do not claim rollback if partial commits
are possible. Check how each command is run and whether its output is actually
collected; it may run in the API, worker, or a separate command.

## Validation for each phase

1. Inventory the actual transaction boundary; decide event names, fields,
   severity, and no-op behavior before implementing.
2. Add focused tests for successful commits, commit/rollback failures, no-op
   writes, concurrent updates, user isolation, context propagation, and both
   user-scoped and compatibility entry points. Mock external services.
3. Verify representative events through the development collector and Grafana;
   add panels only when events answer a defined question.
4. Update the phase status after implementation and validation.
