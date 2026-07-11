# Credit Intelligence Implementation Plan

This document adapts `docs/credit-intelligence-mvp.md` to Albumary's current
SQLite/FastAPI/React architecture. It deliberately narrows the MVP into small
validation steps. The first implementation should prove the app has enough
reliable credit data before adding public navigation, graph-style path finding,
or broad schema changes.

## Review Corrections

The initial plan was too ambitious in a few places:

- It proposed permanent normalized credit tables before proving the current
  embedded credit data is good enough.
- It introduced service/repository/schema names for the whole future feature
  too early.
- It placed public frontend work too soon after the first backend API, without
  a manual result-quality gate.
- It allowed album connection and multi-step path work before validating basic
  recurrence quality.
- It treated a queryable credit projection as a foregone conclusion instead of
  an outcome of the audit.

The revised plan below keeps each phase small enough to stop, inspect output,
and decide whether to continue. Permanent schema should follow evidence from
the audit, not precede it.

## Completion Notes Convention

After each phase is completed, add a results section that records:

- what changed
- validation commands and representative output
- outcomes against the overall Credit Intelligence goal
- unresolved data-quality or product issues
- anything Jacob should independently inspect when back at a computer
- concrete next steps and what each step enables for the overall feature

Keep this section factual. Do not bury manual review items in chat history.

## Current Manual Review Checklist

When back at a computer, inspect these before or during Phase 2 review:

- Open refreshed album pages and confirm track credits still display normally:
  `Night Time, My Time`, `Cascade`, `Trouble Will Find Me`, `Hounds of Love`,
  and `Goodbye Yellow Brick Road`.
- Decide whether the malformed `“Awaken, My Love!”` metadata row should be
  repaired before broader refresh/projection work.
- Review a dry-run Phase 1C sample and confirm the selected refresh categories
  feel useful:
  `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._credit_refresh_experiment --user-slug jacob --limit 25`
- After Phase 2 projection exists, manually inspect top recurring contributors
  before any public UI or ranking page is built.

## Current Architecture and Data

Albumary already has these relevant pieces:

- `albums`: shared album metadata. Credit data currently lives inside
  `albums.metadata_json`, especially `tracklist[*].credits`.
- `user_albums`: user-scoped album membership plus tags, ratings, and notes.
- `album_listens`: user-scoped completed album listen rows with `listened_at`
  and `source`.
- `album_metadata_cache`: cached metadata used by import matching; useful for
  diagnostics, not a user-facing source of truth.
- `imported_listening_events`: raw imported listens, matched to albums when
  possible.
- `spotify_streaming_events`: raw Spotify Extended Streaming History rows with
  track-level `ms_played` and Spotify identifiers.

The Connections MVP should prioritize metadata relationships across albums,
independent of how often an album has been played. Listen history remains part
of the broader app, but Credit Intelligence ranking and presentation should not
use album listen counts unless a future phase explicitly re-approves a separate
listening-history insight.

## Current Credit Shape

Credit ingestion currently happens in `album_metadata_service.py`:

- `_extract_tracks_and_credits()` walks MusicBrainz release media and tracks.
- `_extract_recording_credits()` reads recording-level artist relationships and
  work-level artist relationships.
- Credits are stored as tuple-like arrays:
  `[person_name, raw_credit_type, attributes_string]`.
- `recording_mbid` is stored per track.
- Contributor MusicBrainz artist MBIDs are not stored.
- Release-level and release-group-level relationships are requested by
  `musicbrainz_client.py`, but are not projected into the stored tracklist
  credit shape.
- `frontend/src/services/albumNormalizer.jsx` derives album-level
  `album_credits` by de-duplicating track credits client-side.

This means Albumary can currently display some album credits, but cannot yet
reliably answer person-centric questions without additional data shaping.

## Constraints for the MVP

- Do not add a graph database.
- Do not add full-library graph visualization.
- Do not build multi-step paths until recurrence and direct shared-credit
  quality have been manually reviewed.
- Do not make live MusicBrainz calls from tests.
- Do not let name-only person matching silently drive public rankings without
  quality flags.
- Do not make a catalog-wide MusicBrainz refresh part of the first credit
  phases. Audit stored data first; then selectively refresh a representative
  sample if needed.
- Do not use raw Spotify streaming rows for ranking until a later phase decides
  how they should relate to completed album listens.
- Keep user scoping explicit in every API and query.
- Database migrations create schema only. They must not make MusicBrainz calls
  or run expensive catalog-wide credit projections during application startup.

## Data-Quality Questions to Answer First

Before adding UI, the audit must answer:

- How many user-library albums have a non-empty tracklist?
- How many have any stored credits?
- Which raw roles are present most often?
- Which roles are useful enough to normalize for a first ranking?
- How many credits are name-only because contributor MBIDs are missing?
- Are primary artists, band members, ensembles, or generic performer roles
  overwhelming the top contributors?
- Are compilations, soundtracks, live releases, deluxe releases, or bonus
  tracks creating noisy links?
- Are obvious recurring producers/writers/engineers visible in the current
  stored data?
- Are there enough albums with credit coverage to justify a public Connections
  page?

## Minimal Role and Identity Approach

The first useful implementation does not need a complete person model.

Initial identity:

- Use MusicBrainz contributor artist MBID when available in newly extracted
  credits.
- For existing stored credits, use a normalized name key and mark the identity
  as `normalized_name` or `unresolved`.
- Do not merge unresolved name keys into MBID-backed people unless a later
  refresh proves they match.
- Store an explicit `identity_resolution` value such as `mbid`,
  `normalized_name`, or `unresolved`.
- Store an `ingestion_version` or equivalent source marker so legacy projected
  facts are not treated as equivalent to enriched future rows.

Initial role buckets:

- `producer`
- `writer_composer`
- `mixing_mastering`
- `engineering`
- `performer`
- `primary_artist`
- `other`

This is intentionally smaller than the MVP's long-term taxonomy. Split
`mixing` from `mastering`, or `recording_engineering` from other engineering,
only after the audit shows the raw roles support it.

Role priority should begin as broad eligibility tiers, not tuned decimal
weights:

- Tier 1: producer, composer, writer, featured performer.
- Tier 2: performer, mixer, recording engineer, mastering.
- Tier 3: assistant, miscellaneous, and other low-signal technical roles.

Initial rankings should be transparent counts with filters and flags. More
precise scoring can wait until real audit output shows where it is needed.

## Artist Identity for Counts

Distinct primary-artist counts should use the most stable available identity:

- Prefer `albums.artist_mbid`.
- Fall back to a normalized album-artist key.
- Use the album artist display string only as a final fallback.

This matters for collaborations, aliases, backing bands, orchestras,
various-artists releases, and albums where the display string changes while the
MusicBrainz artist identity is the same.

## Ranking Weighting

Initial weighting should use only metadata relationships from albums in the
user's library:

- Recurrence: distinct albums in the user's library where the contributor has a
  meaningful credit.
- Breadth: distinct primary artists connected by that contributor.
- Explanation: roles, representative artists, representative albums, identity
  quality, and credit quality.

Album listen counts, ratings, tags, notes, raw imported events, and raw Spotify
streaming events are out of scope for Credit Intelligence ranking.

## Meaningful-Credit Rules

Do not enforce one universal track-share threshold. Start with role-aware
eligibility:

- Producer, mixer, and mastering credits at album or release scope can be
  meaningful even without broad stored track coverage.
- Performer credits should usually require at least two tracks or 25% of album
  tracks.
- Featured performer credits can be meaningful on one track.
- Assistant and miscellaneous technical roles should require broader coverage
  or be excluded from default rankings.
- Compilations should be excluded from default insight rankings initially.
- Deluxe/remastered duplicate editions should be deduplicated to the release
  group or existing album-concept level where possible.
- Live albums and soundtracks should be flagged and inspected, not universally
  excluded.

Default recurring and hidden-connector sections should exclude primary artists.
Primary artists can still appear in album detail context, path explanations, or
a future optional artist-focused view.

## Performance Boundaries

- Public credit endpoints should query projected tables, not deserialize every
  album's `metadata_json` at request time.
- Representative albums should be limited in SQL where practical.
- Any future path search must operate on a user-scoped filtered graph.
- Do not precompute all album-pair paths.
- Rebuild/projection work should run through an explicit operational script,
  admin command, or controlled service command, not normal app startup.

## Phase 1A: Audit Current Stored Credits

Goal: inspect the credit data that already exists without changing schema or
application behavior.

Work:

- Add or run a one-time audit script that reads `albums.metadata_json` and joins
  to `user_albums` and `album_listens`.
- Parse the existing `[name, role, attributes]` credit arrays.
- Produce a report for one user and optionally all users.
- Include coverage counts, top raw roles, top name-only contributors, albums
  with no tracklist, albums with no credits, and albums with unusually many
  unique credited people.
- Include a draft recurrence list using name-only identity, clearly labeled as
  audit-only.

No schema changes. No API. No frontend. No MusicBrainz refresh.

Acceptance criteria:

- The audit can be run repeatedly without writing data.
- The report explains credit coverage and obvious noise sources.
- The report includes enough representative rows to manually judge whether
  stored credits are useful.
- A go/no-go decision is made before Phase 1B.
- Initial role bucket mapping and noisy-role candidates are documented.
- A small set of representative albums is identified for possible later
  selective refresh.

Expected files:

- Add `one_time_scripts/_audit_credit_intelligence.py`, or keep this as a
  temporary local analysis script if not ready to commit.
- Add focused tests only if the parser/reporting logic is committed.

Status: completed on 2026-07-03.

Implemented files:

- `one_time_scripts/_audit_credit_intelligence.py`
- `tests/test_credit_intelligence_audit_script.py`

Validation commands:

- `./.venv/bin/python -m unittest tests.test_credit_intelligence_audit_script -v`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._audit_credit_intelligence --user-slug jacob`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._audit_credit_intelligence --all-users`

Representative Jacob output:

- Albums in library: 458.
- Albums with completed listens: 66; completed listen rows: 95.
- Albums with tracklists: 434 (94.8%).
- Albums with stored credits: 364 (79.5%).
- Stored credit rows parsed: 37,273; name-only rows: 37,273.
- Top raw roles: `instrument` (9,445), `producer` (5,450),
  `work writer` (4,985), `vocal` (3,477), `engineer` (3,462),
  `mix` (3,157), `work composer` (2,169), `recording` (1,779),
  `work lyricist` (1,308).
- Initial role buckets: `other` (10,974), `writer_composer` (8,462),
  `producer` (5,450), `engineering` (5,241), `performer` (3,916),
  `mixing_mastering` (3,202), `primary_artist` (28).
- Noisy-role candidates surfaced by the audit: `programming` (316),
  `misc` (64), `work translator` (1), `work misc` (1).
- Draft audit-only recurrence examples: Manny Marroquin, `[traditional]`,
  Serban Ghenea, Chris Galland, Brian Eno, Dave Fridmann, Rick Rubin.

Representative albums for possible selective refresh:

- John Martyn - `Solid Air`: unparseable/no tracklist, 5 listens.
- Courtney Barnett - `Tell Me How You Really Feel`: unparseable/no tracklist,
  3 listens.
- Radiohead - `Kid A`: unparseable/no tracklist, 3 listens.
- Nivhek - `After Its Own Death / Walking in a Spiral Towards the House`:
  tracklist present but no credits, 4 listens.
- Barker - `Stochastic Drift`: tracklist present but no credits, 2 listens.
- Ella Fitzgerald - `The Ella Fitzgerald Songbook`: 526 credits and 167 unique
  credited names.
- Beyonce - `Lemonade`: 372 credits and 146 unique credited names.
- 2Pac - `Me Against the World`: 184 credits and 92 unique credited names.
- Joan Baez - `Joan Baez`: 51 credits and 21 unique credited names, 4 listens.
- Sky Ferreira - `Night Time, My Time`: 220 credits and 15 unique credited
  names, 4 listens.
- William Tyler - `Modern Country`: 21 credits and 3 unique credited names,
  3 listens.

Unresolved data-quality issues:

- Existing stored credits are all name-only. Contributor MusicBrainz artist
  MBIDs are unavailable in the current `tracklist[*].credits` shape.
- Some `albums.metadata_json` values are present but not parseable as UTF-8 JSON
  through the normal SQLAlchemy JSON loader. The audit now handles these rows
  defensively and reports them as unparseable metadata.
- `instrument` is the largest raw role and currently lands in `other`; it needs
  implementation judgment before default rankings.
- `other` is the largest bucket because arranger, copyright, orchestra,
  remixer, sampled-from, and similar roles are not yet split.
- Highly credited albums, compilations, deluxe/live-like releases, and
  songbook-style releases can dominate name-only recurrence.
- Recurrence can duplicate album examples when multiple local album rows share
  a concept or release group.
- Public ranking remains inappropriate until identity, noisy-role filtering,
  and representative refresh results are reviewed.

User-confirmed ranking guardrails:

- Broad `instrument` handling should use implementation judgment. Default
  ranking should avoid letting generic instrument credits overpower clearer
  producer, writer, engineering, mixing/mastering, and specific performer
  signals.
- Hidden-connector and default recurring-contributor views should exclude
  primary artists or obvious band-member self-connections only when that can be
  detected reliably and consistently across albums. If reliable detection is not
  available, prefer keeping the row with a visible flag over silently excluding
  it.
- Highly credited albums should not be excluded solely because they have many
  credited people.
- No special treatment is needed for compilations, songbooks, soundtracks, live
  albums, deluxe editions, or remasters at this stage. The working assumption is
  that these should not be present in the curated album data; if the audit finds
  examples, treat them as data cleanup candidates rather than ranking-category
  rules.

Phase 1A decision:

- Conditional go for Phase 1B planning only. Stored credits are useful enough to
  justify a queryable projection experiment, but not clean enough for public
  rankings without MBID-aware identity flags, explicit role filtering, and
  exclusion/flagging rules for noisy release types.

Phase 1A results and follow-ups:

- Outcome for the overall feature: the stored credit data is substantial enough
  to justify Credit Intelligence work, but existing identity quality is
  name-only and must be flagged.
- What changed: a read-only audit script and parser/reporting tests were added.
- Independent review: scan the audit report for whether recurrence examples and
  noisy-role candidates feel musically meaningful.
- Next step enabled: Phase 1B enriched ingestion, so future metadata writes can
  preserve MBID-backed contributor identity instead of only normalized names.
- Carry-forward issue: malformed `metadata_json` and broad `instrument` roles
  must be treated as quality flags before public rankings.

## Phase 1B: Preserve Better Credit Facts on New Metadata Lookups

Goal: improve future credit ingestion without requiring a full projection
schema yet.

Work:

- Update credit extraction in `album_metadata_service.py` to preserve
  contributor MusicBrainz artist MBID when present.
- Preserve attributes as structured data instead of only a comma-separated
  string for newly refreshed metadata.
- Preserve enough scope to tell `recording` credits from `work` credits.
- Mark newly extracted rows with an enriched ingestion version/source marker.
- Keep backward compatibility with existing frontend normalization and existing
  metadata JSON.
- Add tests for old credit tuple compatibility and new structured credit
  shape.

Still no public UI, no ranking API, and no catalog-wide refresh.

Acceptance criteria:

- Existing album state responses remain frontend-compatible.
- New metadata records can distinguish resolved MBID contributors from
  unresolved name-only contributors.
- Existing stored albums do not need immediate refresh to keep the app working.
- Legacy projected credits and enriched future credits have distinct confidence
  or ingestion markers.
- Unit tests mock MusicBrainz data and do not hit the network.

Expected files:

- Modify `album_metadata_service.py`.
- Possibly modify `backend/app/schemas.py` only if the response contract needs
  to admit the structured credit shape explicitly.
- Update `frontend/src/services/albumNormalizer.jsx` only if required to keep
  album credit display compatible.
- Update `tests/test_album_metadata_service.py`.

Status: completed on 2026-07-03.

Implemented files:

- `album_metadata_service.py`
- `frontend/src/services/albumNormalizer.jsx`
- `frontend/src/services/albumNormalizer.test.jsx`
- `tests/test_album_metadata_service.py`
- `tests/test_credit_intelligence_audit_script.py`
- `one_time_scripts/_audit_credit_intelligence.py`

Implementation notes:

- Newly extracted MusicBrainz credits are stored as structured objects instead
  of tuple-like arrays.
- Enriched credit rows include `name`, `artist_mbid`, `role`,
  `raw_credit_type`, structured `attributes`, `source_scope`,
  `identity_resolution`, and `ingestion_version`.
- `source_scope` distinguishes recording-level relationships from work-level
  relationships while preserving legacy display role strings such as
  `work composer`.
- `identity_resolution` is `mbid` when MusicBrainz provides a contributor
  artist MBID, otherwise `normalized_name`.
- `ingestion_version` is currently `musicbrainz_credit_v2`, so future projected
  facts can distinguish enriched rows from legacy tuple-shaped rows.
- Frontend album normalization accepts both legacy arrays and enriched objects,
  then exposes display credits as `[name, role, detail]` arrays so current
  components remain compatible.
- The Phase 1A audit parser accepts both legacy arrays and enriched objects so
  the audit can compare mixed legacy/refreshed libraries later.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_album_metadata_service tests.test_credit_intelligence_audit_script -v`
- `npm --prefix frontend run test -- albumNormalizer.test.jsx`
- `make test`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run lint`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._audit_credit_intelligence --user-slug jacob --json`

Representative enriched credit output:

```json
[
  {
    "name": "Producer One",
    "artist_mbid": "artist-1",
    "role": "producer",
    "raw_credit_type": "producer",
    "attributes": ["co"],
    "source_scope": "recording",
    "identity_resolution": "mbid",
    "ingestion_version": "musicbrainz_credit_v2"
  },
  {
    "name": "Composer One",
    "artist_mbid": null,
    "role": "work composer",
    "raw_credit_type": "composer",
    "attributes": [],
    "source_scope": "work",
    "identity_resolution": "normalized_name",
    "ingestion_version": "musicbrainz_credit_v2"
  }
]
```

Phase 1B decision:

- Go for Phase 1C selective refresh planning. New lookups now preserve the
  identity and scope fields needed to compare legacy stored credits against
  enriched refreshed credits without adding public APIs or projection schema.

Phase 1B results and follow-ups:

- Outcome for the overall feature: future MusicBrainz metadata writes can now
  produce high-confidence contributor facts with MBID identity, relationship
  scope, structured attributes, and an ingestion marker.
- What changed: metadata extraction now emits enriched credit objects, while
  frontend normalization keeps album credit display compatible with both old and
  new shapes.
- Independent review: open a refreshed album and verify credits still look like
  ordinary track credits in the UI.
- Next step enabled: Phase 1C selective refresh, so real albums can be compared
  before adding projection tables.
- Carry-forward issue: existing library rows remain legacy until refreshed, so
  Phase 2 must support mixed legacy/enriched data.

## Phase 1C: Selective Refresh Experiment

Goal: quantify how much enriched ingestion improves credit quality before
planning a full backfill.

Work:

- Select roughly 20-50 representative albums from Phase 1A: high-listen albums,
  sparse-credit albums, noisy-credit albums, and albums expected to have known
  behind-the-scenes contributors.
- Refresh only that sample through the normal metadata path.
- Compare legacy projected credit quality with enriched extracted credit
  quality.
- Record whether MBID coverage, role clarity, and useful recurring
  contributors improve enough to justify broader refresh work.

Acceptance criteria:

- The sample refresh does not become a required app startup or migration step.
- Differences between legacy projection and enriched ingestion are visible in
  an audit report.
- A decision is made on whether Phase 2 should support legacy-only facts,
  enriched facts, or both.

Status: completed on 2026-07-04.

Implemented files:

- `one_time_scripts/_credit_refresh_experiment.py`
- `tests/test_credit_refresh_experiment_script.py`

Operational notes:

- A live database backup was created before applying the experiment:
  `/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data/spotify_tracker.sqlite.bak-credit-phase1c-20260704-001021`.
- The experiment script is dry-run by default and uses a read-only query engine
  for candidate selection.
- Real MusicBrainz refreshes require `--apply` and go through
  `metadata_refresh_service.refresh_album_record()`, preserving the existing
  resolver thresholds, retries, rate limiting, and repository merge behavior.
- `--album-id` can be passed multiple times for small resumable batches. This
  was added after the initial 25-album batch proved too slow for one live run.

Commands used:

- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._credit_refresh_experiment --user-slug jacob --limit 25`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._credit_refresh_experiment --user-slug jacob --limit 25 --apply`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._credit_refresh_experiment --user-slug jacob --apply --album-id 687 --album-id 43 --album-id 815`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._credit_refresh_experiment --user-slug jacob --apply --album-id 365 --album-id 147 --album-id 217 --album-id 675 --album-id 360`

Representative dry-run sample:

- 25 selected albums.
- 2,330 legacy credit rows.
- 0 structured credits.
- 0 MBID-backed credits.
- Included unparseable metadata, tracklists with no credits, high-credit-volume
  albums, and high-listen covered albums.

Live refresh result:

- 20 targeted refresh attempts were made across the interrupted 25-album batch
  and two smaller resumable batches.
- 19 refreshes succeeded.
- 1 refresh failed: Childish Gambino - `“Awaken, My Love!”` failed with an
  unterminated JSON string while reading existing local metadata.
- Elton John - `Goodbye Yellow Brick Road` refreshed successfully and merged
  into existing album id `824`.
- Comparing the pre-run backup to current data found 18 same-id newly enriched
  albums plus the `Goodbye Yellow Brick Road` merge.
- Same-id newly enriched albums moved from 2,813 legacy credit rows, 0
  structured rows, and 0 MBID-backed rows to 2,975 structured rows, 2,975
  scoped rows, and 2,975 MBID-backed rows.
- The merged `Goodbye Yellow Brick Road` row now has 181 structured/scoped/MBID
  backed credit rows.

Representative refreshed albums:

- Sky Ferreira - `Night Time, My Time`: 220 -> 220 credits, 220 MBID-backed.
- The National - `Sleep Well Beast`: 836 -> 890 credits, 890 MBID-backed.
- Beck - `Sea Change`: 167 -> 167 credits, 167 MBID-backed.
- Beyonce - `Lemonade`: 372 -> 372 credits, 372 MBID-backed.
- Floating Points - `Cascade`: 0 -> 70 credits, 70 MBID-backed.
- Bridget St. John - `Songs for the Gentle Man`: 0 -> 2 credits,
  2 MBID-backed.
- The National - `Trouble Will Find Me`: 76 -> 105 credits, 105 MBID-backed.
- Arcade Fire - `The Suburbs`: 74 -> 74 credits, 74 MBID-backed.
- Eric Clapton - `Unplugged`: 229 -> 221 credits, 221 MBID-backed.
- Kate Bush - `Hounds of Love`: 197 -> 197 credits, 197 MBID-backed.
- The Jimi Hendrix Experience - `Electric Ladyland`: 140 -> 167 credits,
  167 MBID-backed.
- The Flaming Lips - `Oczy Mlody`: 146 -> 152 credits, 152 MBID-backed.

Unresolved data-quality issues from the experiment:

- Existing malformed `metadata_json` can still block refreshes before the
  remote lookup result is written. `“Awaken, My Love!”` is a concrete example.
- Large one-shot refresh batches are too slow and opaque for MusicBrainz-backed
  work; future operational scripts should favor small explicit batches or
  progress logging.
- Legacy and enriched rows will coexist for a long time unless a broader
  backfill is explicitly run.
- Some refreshed albums change credit counts materially, so Phase 2 should not
  assume legacy and enriched facts are equivalent evidence.

Phase 1C decision:

- Go for Phase 2 with support for both legacy and enriched facts. Enriched rows
  are clearly better for identity and source-scope quality, but the library will
  remain mixed. The projection should preserve `ingestion_version`,
  `identity_resolution`, `person_mbid`, `source_scope`, and quality flags so
  rankings can prefer enriched data without discarding legacy coverage.

Phase 1C results and follow-ups:

- Outcome for the overall feature: real refreshed albums produced structured,
  scoped, MBID-backed credits, proving enriched ingestion is useful enough to
  feed a queryable projection.
- What changed: a dry-run-first refresh experiment script was added, and a
  representative live sample was refreshed after creating a database backup.
- Independent review: when back at a computer, open the refreshed album pages
  listed above and confirm they still display normally.
- Next step enabled: Phase 2 `album_credit_facts`, which will make recurrence
  and person-detail queries possible without deserializing every album's
  `metadata_json` at request time.
- Carry-forward issue: repair or explicitly flag malformed local metadata,
  including Childish Gambino - `“Awaken, My Love!”`, before broad refresh or
  public ranking work.
- Operational lesson: future live MusicBrainz work should use small
  `--album-id` batches or progress logging; 25-album apply batches are too
  opaque and slow.

## Phase 2: Minimal Queryable Credit Projection

Goal: create the smallest persisted read model needed for recurrence queries,
after Phase 1A proves the data is worth projecting.

Prefer one table first:

### `album_credit_facts`

Suggested columns:

- `id`
- `album_id`
- `person_key`
- `person_name`
- `person_mbid` nullable
- `identity_resolution`: `mbid`, `normalized_name`, or `unresolved`
- `ingestion_version`
- `raw_role`
- `role_bucket`
- `source_scope`
- `recording_mbid` nullable
- `track_count`
- `album_track_count`
- `track_share`
- `quality_flags_json`
- `created_at`
- `updated_at`

This table is an album-person-role aggregate, not a full graph model. It can be
rebuilt from `albums.metadata_json`. Do not add separate `credit_people`,
`album_track_credits`, or path tables unless this table proves insufficient.
Aggregation can happen in SQL or temporary audit views until the quality logic
stabilizes.

Work:

- Add the model and idempotent SQLite migration.
- Add a rebuild script/service that deletes and rebuilds facts for selected
  albums or all albums.
- Explicitly support legacy projection from `[name, role, attributes_string]`
  and enriched ingestion from structured credits.
- Compute conservative role buckets and quality flags.
- Mark weak facts instead of deleting raw credit information from album
  metadata.

Acceptance criteria:

- Rebuild is idempotent.
- Migration tests pass.
- Facts can be traced back to album metadata.
- The audit report can be re-run from `album_credit_facts` and compared with
  Phase 1A output.
- Migration creates schema only and does not perform projection or remote API
  work.
- No public API or frontend route is added yet.

Expected files:

- Modify `backend/app/models.py`.
- Modify `backend/app/migrations.py`.
- Add `backend/app/services/credit_fact_service.py` or equivalent small module.
- Add `one_time_scripts/_rebuild_credit_facts.py`.
- Add tests for migration and rebuild behavior.

Status: completed on 2026-07-04.

Implemented files:

- `backend/app/models.py`
- `backend/app/migrations.py`
- `backend/app/services/credit_fact_service.py`
- `one_time_scripts/_rebuild_credit_facts.py`
- `one_time_scripts/_audit_credit_facts.py`
- `tests/test_credit_fact_service.py`
- `tests/test_sqlite_migrations.py`

Implementation notes:

- Added the `album_credit_facts` table as a rebuildable album-person-role
  aggregate.
- Migration creates schema and indexes only. It does not parse metadata, call
  MusicBrainz, or populate facts during app startup.
- Projection supports both legacy tuple credits and enriched object credits.
- Facts preserve `person_key`, `person_name`, optional `person_mbid`,
  `identity_resolution`, `ingestion_version`, `raw_role`, `role_bucket`,
  `source_scope`, optional single `recording_mbid`, `track_count`,
  `album_track_count`, `track_share`, and quality flags.
- Legacy facts use `legacy_tuple_credit_v1`; enriched facts preserve
  `musicbrainz_credit_v2`.
- Generic `instrument` facts are bucketed as `other` and flagged
  `generic_instrument`, so they can be down-ranked later instead of dominating
  performer results.
- Primary-artist candidates are flagged only when the contributor MBID matches
  `albums.artist_mbid` or the normalized contributor name matches the album
  artist name.
- Malformed `metadata_json` rows are skipped and counted during rebuild rather
  than aborting the whole projection.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_credit_fact_service tests.test_sqlite_migrations.SqliteMigrationTests.test_create_schema_creates_album_credit_facts_idempotently -v`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._rebuild_credit_facts`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._rebuild_credit_facts --apply`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python -m one_time_scripts._audit_credit_facts --user-slug jacob`
- `make test`

Representative rebuild output:

```text
Credit Fact Rebuild Applied
- albums considered: 776
- deleted facts: 8733
- inserted facts: 8733
- skipped metadata parse errors: 259
- total persisted facts: 8733
```

Representative Jacob fact audit:

```text
Credit Facts Audit
User: Jacob (jacob)
- Albums in library: 509
- Albums with completed listens: 128; completed listen rows: 180
- Albums with projected facts: 365
- Projected fact rows: 8265

Role buckets:
- writer_composer: 2663
- other: 2221
- performer: 1019
- producer: 993
- engineering: 860
- mixing_mastering: 509

Identity resolution:
- normalized_name: 7693
- mbid: 564
- unresolved: 8
```

Unresolved data-quality issues:

- 259 albums were skipped because stored metadata could not be parsed for
  projection.
- The projected Jacob library is still mostly legacy/name-only facts:
  7,701 legacy facts and 564 enriched facts.
- `high_credit_album`, `low_track_share`, `single_track_credit`,
  `generic_instrument`, and `primary_artist_candidate` are flags only. Phase 3
  must decide how to filter or rank them.
- The top fact-audit contributors still include primary-artist or band-member
  cases such as Red Hot Chili Peppers/Led Zeppelin members. These should be
  flagged or filtered only when reliable.

Phase 2 decision:

- Go for Phase 3 backend APIs. The read model now exists and can be rebuilt
  idempotently. Phase 3 should query `album_credit_facts` rather than
  deserializing `albums.metadata_json` at request time.

Phase 2 results and follow-ups:

- Outcome for the overall feature: Credit Intelligence now has a persisted
  queryable layer that can support recurring-contributor and person-detail
  queries.
- What changed: schema, migration, rebuild service, rebuild script, fact audit
  script, and focused migration/rebuild tests were added.
- Independent review: run the fact audit and scan top contributors for obvious
  noisy or primary-artist-dominated results before public UI work.
- Next step enabled: Phase 3 recurring contributor and person-detail APIs,
  which can now query projected facts efficiently and preserve user scoping.
- Carry-forward issue: malformed metadata and mostly legacy/name-only coverage
  mean Phase 3 responses must expose quality flags and insufficient-data states.

## Phase 3: Recurrence and Person Detail APIs

Goal: expose the first backend insight plus enough detail to validate why each
contributor appears.

Work:

- Add a user-scoped API endpoint for recurring contributors only, for example
  `/api/users/{user_slug}/connections/recurring`.
- Add a user-scoped person detail endpoint keyed by `person_key`.
- Query `album_credit_facts` joined to `user_albums` and `albums`.
- Exclude or down-rank facts with quality flags such as unresolved-only,
  single-track-only, compilation-heavy, or primary-artist-only depending on the
  audit findings.
- Return structured facts, not generated prose: person name/key,
  `identity_resolution`, role bucket, connected album count, distinct primary
  artist count, representative artists, representative albums, and quality
  flags.
- Let the frontend assemble text such as "Producer on 8 albums by 4 artists in
  your library."

Do not add listening impact, hidden connectors, album pair selection, or
frontend navigation in this phase.

Acceptance criteria:

- Endpoint returns deterministic ranked results for a user.
- Same database with two users cannot leak another user's listen/library data.
- Sparse users get an empty or low-coverage response with a reason.
- Person detail only shows albums in the current user's library.
- Tests cover role filtering, unresolved identity handling, distinct
  primary-artist identity, and user scoping.

Expected files:

- Add `backend/app/routers/credit_intelligence.py`.
- Register router in `backend/app/main.py`.
- Add minimal response schemas in `backend/app/schemas.py` or a focused schema
  module.
- Add small query/service code. Avoid broad abstractions until a second insight
  needs them.
- Add `tests/test_api_credit_intelligence.py`.

Status: completed on 2026-07-04.

Implemented files:

- `backend/app/services/credit_intelligence_service.py`
- `backend/app/routers/credit_intelligence.py`
- `backend/app/schemas.py`
- `backend/app/main.py`
- `tests/test_api_credit_intelligence.py`

Implementation notes:

- Added backend-only, user-scoped endpoints:
  `/api/users/{user_slug}/connections/recurring` and
  `/api/users/{user_slug}/connections/people/{person_key}`.
- Queries read from `album_credit_facts` joined through `user_albums` and
  `albums`. The endpoints do not deserialize `albums.metadata_json` and do not
  call MusicBrainz.
- Recurring contributor results require at least two connected albums.
- Default recurring results exclude facts flagged `primary_artist_candidate`,
  `unresolved_identity`, or `generic_instrument`, plus the `primary_artist`
  role bucket. Name-only legacy facts are still allowed, but their quality flags
  are returned.
- Default recurring results also exclude common non-person labels such as
  `[traditional]` and require at least two distinct primary artists, so same-band
  discography members do not dominate the main Connections ranking.
- Person detail uses the same user-library scope but does not apply the default
  noise filter, so the caller can inspect the contributor's full projected
  footprint for that user.
- Ranking is deterministic: connected album count, distinct primary artist
  count, contributor name, then contributor key.
- Sparse or low-coverage users receive an `insufficient_data_reason` such as
  `empty_library`, `no_projected_credit_facts`,
  `low_credit_fact_coverage`, or `no_recurring_contributors_after_filters`.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
- `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
- `make test`
- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python - <<'PY' ...`

Representative Jacob API output:

```text
GET /api/users/jacob/connections/recurring?limit=5
status 200
coverage {'library_album_count': 509, 'albums_with_facts': 365,
'projected_fact_count': 8265, 'coverage_ratio': 0.7170923379174853}
insufficient_data_reason None
- Manny Marroquin | albums 13 | artists 13 | listens 0 |
  roles {'mixing_mastering': 12, 'engineering': 1}
- Chris Galland | albums 9 | artists 9 | listens 0 |
  roles {'mixing_mastering': 7, 'engineering': 2}
- Serban Ghenea | albums 9 | artists 7 | listens 0 |
  roles {'mixing_mastering': 9}
- [traditional] | albums 8 | artists 8 | listens 1 |
  roles {'writer_composer': 17}
- John Hanes | albums 8 | artists 7 | listens 0 |
  roles {'mixing_mastering': 5, 'engineering': 4}

GET /api/users/jacob/connections/people/name:manny marroquin
status 200
person Manny Marroquin albums 13
```

Unresolved data-quality issues:

- Current top Jacob results are still dominated by legacy/name-only
  mixing/mastering/engineering credits. They are plausible but should be judged
  manually before a public UI treats them as high-confidence insights.
- `[traditional]` appears as a recurring writer. This may be technically
  accurate metadata, but probably needs product treatment before it becomes a
  surfaced "person" connection.
- Connections results are intentionally based on library membership and credit
  metadata, not completed album listen counts.
- Phase 3 did not address the 259 malformed metadata rows or mostly
  legacy/name-only projection coverage carried forward from Phase 2.

Phase 3 results and follow-ups:

- Outcome for the overall feature: Credit Intelligence now has stable backend
  API contracts for the first usable insight, recurring contributors, and for
  inspecting why a contributor appears.
- What changed: added a focused read service, router, Pydantic response
  schemas, app router registration, and API tests for ranking, filtering,
  unresolved handling, distinct primary-artist counting, sparse states, and
  user scoping.
- Independent review: run the recurring endpoint for `jacob` and scan the top
  10-25 names for whether they feel useful enough to show in the app.
- Next step enabled: Phase 3.5 manual result-quality gate, which decides
  whether the backend results are good enough to design a UI or need more
  filtering first.
- Carry-forward issue: before Phase 4, decide how to treat non-person
  contributors such as `[traditional]` and whether mixing/mastering-heavy
  results should be grouped, filtered, or clearly labeled.

## Phase 3.5: Manual Result-Quality Gate

Goal: prevent tests from becoming the only definition of quality.

Review at least:

- Top 25 recurring contributors overall.
- Top 15 producers.
- Top 15 performers.
- Top 15 engineers/mixers.
- Several person-detail outputs.
- Results for sparse and dense libraries, if multiple users have enough data.

Do not begin public frontend work until:

- Obvious duplicate contributors are controlled or flagged.
- Primary artists do not dominate default rankings.
- Results can be explained cleanly from structured facts.
- A substantial majority of top results appear musically meaningful.
- Known noisy sources, especially compilations and one-track generic roles, are
  excluded or flagged.

Status: completed on 2026-07-04.

Implemented files:

- `backend/app/services/credit_intelligence_service.py`
- `tests/test_api_credit_intelligence.py`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Reviewed the top 25 recurring contributors, top role-specific contributors,
  and several person-detail payloads against the local Jacob dataset.
- Tightened the default recurring endpoint after the review:
  non-person labels such as `[traditional]` are excluded from default rankings,
  and default recurring contributors must span at least two distinct primary
  artists.
- Kept person-detail behavior broad. Excluded default contributors can still be
  inspected directly if a caller already has the `person_key`.
- Did not add UI, role-filter endpoints, listening impact, album pairs, graph
  paths, or new projection tables.

Validation commands:

- `DATA_DIR=/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data ./.venv/bin/python - <<'PY' ...`
- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
- `make test`

Representative Jacob output after gate filters:

```text
GET /api/users/jacob/connections/recurring?limit=25
coverage {'library_album_count': 509, 'albums_with_facts': 365,
'projected_fact_count': 8265, 'coverage_ratio': 0.7170923379174853}
insufficient_data_reason None
01. Manny Marroquin | albums=13 | artists=13 |
    roles {'mixing_mastering': 12, 'engineering': 1}
02. Chris Galland | albums=9 | artists=9 |
    roles {'mixing_mastering': 7, 'engineering': 2}
03. Serban Ghenea | albums=9 | artists=7 |
    roles {'mixing_mastering': 9}
04. John Hanes | albums=8 | artists=7 |
    roles {'mixing_mastering': 5, 'engineering': 4}
05. Tom Lord-Alge | albums=8 | artists=5 |
    roles {'mixing_mastering': 8}
```

Role-specific review summary:

- Producers looked useful after the cross-artist filter. Top examples included
  Max Martin, Metro Boomin, Murda Beatz, Dave Fridmann, Frank Dukes, Glyn Johns,
  Tom Wilson, and Rick Rubin.
- Performers improved substantially after same-primary-artist contributors were
  filtered out. The remaining list looked more like cross-artist features or
  collaborations, but still includes legacy/name-only uncertainty.
- Engineers and mixers are the strongest recurring signal by volume. This is
  musically meaningful, but it may not be what a user expects first from a
  "Connections" page unless roles are obvious in the UI.
- Writers are much cleaner after excluding `[traditional]`, with Max Martin,
  Rick Nowels, George/Ira Gershwin, Metro Boomin, Scott Storch, Ted Koehler, and
  Dr. Dre near the top.

Unresolved data-quality issues:

- Results remain mostly legacy/name-only, so the first UI should expose role and
  quality context rather than presenting the list as complete or authoritative.
- Mixing/mastering/engineering still dominate the default ranking. This is
  acceptable for the first UI only if role labels are prominent; a role-filtered
  view is likely a near-term follow-up.
- Some meaningful same-artist recurring contributors are intentionally hidden
  from the default ranking. This is a product choice for a cross-artist
  Connections page, not a deletion of the underlying data.
- Phase 3.5 did not resolve malformed metadata rows carried forward from Phase
  2.

Phase 3.5 decision:

- Go for Phase 4 UI. The backend results are explainable enough for a first
  Connections page, provided the UI makes coverage, roles, and uncertainty
  visible.

Phase 3.5 results and follow-ups:

- Outcome for the overall feature: the first Credit Intelligence insight passed
  a manual quality gate and now has stricter default ranking rules.
- What changed: default recurrence ranking now removes common non-person labels
  and same-primary-artist-only contributors.
- Independent review: after the UI exists, scan whether the first page feels too
  engineer/mixer-heavy in practice.
- Next step enabled: Phase 4 First Connections UI, which will expose the
  recurring contributor API in the app without adding listening impact or graph
  path features.
- Carry-forward issue: add role grouping or filtering soon if the default page
  feels too broad.

## Phase 4: First Connections UI

Goal: add one frontend page that displays recurring contributors and person
detail only after the manual quality gate passes.

Work:

- Add `PROFILE_ROUTES.connections`.
- Add a nav item labeled `Connections`.
- Add `PageConnections.jsx`.
- Add `fetchRecurringContributors()` to `albumApi.js`.
- Render recurring contributor cards and insufficient-data states.
- Link representative albums to the existing album panel behavior where useful.
- Add a person detail experience using the existing route, sheet, or panel
  pattern that best fits the application. A sheet may be enough initially;
  defer a dedicated route unless direct linking or richer navigation becomes
  necessary.

Do not add listening impact, album-pair suggestions, or finder UI yet.

Acceptance criteria:

- `/:userSlug/connections` loads for the selected user.
- The page is useful with just recurring contributors or clearly explains why
  there is not enough credit data.
- Every displayed contributor can be inspected through the person detail
  experience.
- The page does not imply complete credit coverage.
- `npm run build` and relevant frontend tests pass.

Expected files:

- Modify `frontend/src/routing.js`.
- Modify `frontend/src/components/universalHeader.jsx`.
- Add `frontend/src/components/PageConnections.jsx`.
- Optionally add small components under
  `frontend/src/components/connections/`.
- Modify `frontend/src/services/albumApi.js`.

Status: completed on 2026-07-04.

Implemented files:

- `frontend/src/routing.js`
- `frontend/src/routing.test.js`
- `frontend/src/services/albumApi.js`
- `frontend/src/components/universalHeader.jsx`
- `frontend/src/components/PageConnections.jsx`
- `frontend/src/components/connections/ConnectionSummaryCard.jsx`
- `frontend/src/components/connections/connectionFormatters.js`
- `frontend/src/components/connections/connectionFormatters.test.js`
- `frontend/src/App.jsx`
- `backend/app/schemas.py`
- `tests/test_album_state_contract.py`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Added `/:userSlug/connections` as a profile route and a Connections nav item.
- Added API client methods for recurring contributors and contributor detail.
- Added the first Connections page with coverage stats, recurring contributor
  cards, role summaries, quality flags, and insufficient-data states.
- Added a person-detail sheet that fetches `/connections/people/{person_key}`
  and lists the user's connected albums.
- Album rows in the person-detail sheet open the existing routed album panel,
  so Phase 4 reuses the current album inspection workflow instead of adding a
  separate detail route.
- Rendered QA found that enriched object credits broke the existing
  `AlbumTrack.credits` API schema. Updated the backend schema to accept mixed
  legacy tuple credits and enriched credit objects.
- Did not add listening impact, album-pair suggestions, graph/path finding, or
  role-filter endpoints.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_album_state_contract tests.test_api_album_state tests.test_api_credit_intelligence -v`
- `make test`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run lint`
- Rendered browser QA against
  `http://127.0.0.1:5173/jacob/connections` with the backend at
  `http://127.0.0.1:8000`.

Representative rendered output:

```text
Connections
509 library albums
365 with credit facts
8,265 projected facts
72% credit coverage

Top cards:
- Manny Marroquin: 13 albums, 13 artists, Mixing/mastering 12, Engineering 1
- Chris Galland: 9 albums, 9 artists, Mixing/mastering 7, Engineering 2
- Serban Ghenea: 9 albums, 7 artists, Mixing/mastering 9
```

Rendered QA checks:

- Desktop page loaded at `/jacob/connections`.
- Contributor cards rendered from the live local API.
- Manny Marroquin detail sheet opened and showed role counts, quality flags, and
  album rows.
- Clicking `Sweetener` from the detail sheet navigated to
  `/jacob/albums/47` and opened the existing album panel.
- Mobile viewport `390x844` had no horizontal overflow in the loaded coverage
  and card views.

Unresolved data-quality and UX issues:

- Default results are still mixer/engineer-heavy. The page is usable because it
  labels roles prominently, but role grouping/filtering is likely the next UI
  improvement.
- Most displayed facts are still legacy/name-only; quality badges expose this,
  but they may need friendlier wording.
- The first mobile viewport shows coverage before cards; this is acceptable, but
  the page may benefit from a tighter mobile header/summary later.

Phase 4 results and follow-ups:

- Outcome for the overall feature: Credit Intelligence is now visible in the app
  as a first-pass Connections page backed by the recurring-contributor API.
- What changed: profile routing, navigation, API client calls, page UI,
  contributor cards, person-detail sheet, album-panel handoff, formatter tests,
  and backend schema compatibility for enriched credits.
- Independent review: open `/jacob/connections`, inspect the first 10-25
  contributors, and decide whether the information is useful even if the static
  presentation needs a stronger interaction model.
- Next step enabled: Phase 5 product-rule cleanup, which removes the
  listen-weighted direction and keeps Connections focused on metadata
  relationships across albums.
- Carry-forward issue: the desired UI should become an interactive
  relationship map rather than an expanded static report.

## Phase 5: Remove Listen-Weighted Connections

Goal: keep Connections focused on metadata relationships across albums,
regardless of how often an album has been listened to.

Work:

- Remove the listen-weighted impact endpoint and frontend section.
- Remove listen-count fields from Connections API payloads.
- Remove `album_listens` joins from Credit Intelligence ranking queries.
- Keep recurring contributor ranking based on connected albums, distinct
  primary artists, contributor name, and contributor key.
- Update UI copy and this plan so later phases do not reintroduce listen-count
  ranking by accident.

Acceptance criteria:

- Connections API responses do not expose `total_listen_count` or album
  `listen_count` fields.
- Connections ranking does not query or sort by `album_listens`.
- The Connections page does not display a Listening Impact section or listen
  count metrics.
- Existing recurring contributor and person-detail behavior remains
  user-scoped and deterministic.

Status: completed on 2026-07-04.

Implemented files:

- `backend/app/services/credit_intelligence_service.py`
- `backend/app/routers/credit_intelligence.py`
- `backend/app/schemas.py`
- `tests/test_api_credit_intelligence.py`
- `frontend/src/services/albumApi.js`
- `frontend/src/components/PageConnections.jsx`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Removed `/api/users/{user_slug}/connections/listening-impact`.
- Removed listen-count schemas from Connections responses.
- Removed `album_listens` from the Credit Intelligence query path.
- Removed the frontend API client method and Listening Impact page section.
- Updated Connections cards and person detail stats to emphasize role breadth
  rather than listens.
- Updated page copy to say ranking uses connected albums, artist breadth, then
  contributor name.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
- `make test`
- `npm --prefix frontend run test`
- `npm --prefix frontend run lint`
- `npm --prefix frontend run build`
- Rendered browser QA against
  `http://127.0.0.1:5173/jacob/connections` with the backend at
  `http://127.0.0.1:8000`.

Representative Jacob API output:

```text
GET /api/users/jacob/connections/recurring?limit=3
coverage {'library_album_count': 509, 'albums_with_facts': 365,
'projected_fact_count': 8265, 'coverage_ratio': 0.7170923379174853}
insufficient None
- Manny Marroquin | albums 13 | artists 13 |
  roles {'mixing_mastering': 12, 'engineering': 1}
- Chris Galland | albums 9 | artists 9 |
  roles {'mixing_mastering': 7, 'engineering': 2}
- Serban Ghenea | albums 9 | artists 7 | roles {'mixing_mastering': 9}
payload fields omit total_listen_count and representative album listen_count
```

Rendered QA checks:

- The Connections page renders recurring contributors only.
- No Listening Impact section appears.
- Contributor cards and detail sheets do not display listen counts.
- Contributor cards and detail sheets show role breadth instead.

Unresolved data-quality and UX issues:

- Default results are still mixer/engineer-heavy because those credits are
  common and well represented in MusicBrainz-derived metadata.
- Most displayed facts are still legacy/name-only; quality badges expose this,
  but they may need friendlier wording.
- Engineering, mixing, and mastering are meaningful roles and should remain in
  the relationship model; the UI problem is static presentation, not role
  inclusion.

Phase 5 results and follow-ups:

- Outcome for the overall feature: Connections now matches the product rule
  that metadata relationships should not depend on album listen frequency.
- What changed: removed listen-weighted backend/frontend behavior and removed
  listen-count fields from the Connections API contract.
- Independent review: inspect `/jacob/connections` and confirm that the page
  feels appropriately focused on cross-album credit relationships rather than
  replay history.
- Next step enabled: Phase 6 Direct Shared-Credit Album Pairs, which tests
  whether static album-to-album suggestions are compelling enough to keep in
  the default Connections surface.
- Carry-forward issue: the desired product direction is interactive exploration
  of the credit network, not a static ranked report.

## Phase 6: Direct Shared-Credit Album Pairs

Goal: surface album pairs connected by one shared contributor.

Work:

- Add backend query for direct album-person-album relationships only.
- Start with API-generated suggested pairs before building a two-album finder.
- Prefer pairs with different primary artists and high-confidence role buckets.
- Add a small page section for "Albums connected by credits."

Acceptance criteria:

- Suggested pairs are traceable to one contributor and role.
- Same-album, duplicate-edition, and primary-artist-only links are suppressed.
- Single-track and low-share links remain eligible, with quality flags preserved
  as evidence labels.
- No multi-step paths are included.

Status: completed on 2026-07-04.

Implemented files:

- `backend/app/services/credit_intelligence_service.py`
- `backend/app/routers/credit_intelligence.py`
- `backend/app/schemas.py`
- `tests/test_api_credit_intelligence.py`
- `frontend/src/services/albumApi.js`
- `frontend/src/components/PageConnections.jsx`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Added `/api/users/{user_slug}/connections/album-pairs`.
- The endpoint builds direct album-person-album suggestions from projected
  `album_credit_facts` joined through the user's `user_albums`.
- Each result names exactly two albums, one contributor, and one role bucket.
- Pair candidates exclude default identity noise, `primary_artist` and `other`
  role buckets, non-person labels such as `[traditional]`, unresolved
  identities, generic instruments, and duplicate album editions.
- Single-track and low-track-share links are not excluded; their quality flags
  stay available for explanation and future ranking.
- Ranking prefers cross-primary-artist pairs, then stronger evidence track
  count, then role bucket, contributor name, and album labels.
- The frontend now renders a small "Albums connected by credits" section below
  recurring contributors. Each pair card links both albums to the existing album
  panel and shows the shared contributor/role.
- Did not add the Phase 7 two-album finder, hidden connectors, multi-step paths,
  path weighting, or graph visualization.

Validation commands:

- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
- `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
- `npm --prefix frontend run lint`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `make test`

Representative Jacob API output:

```text
GET /api/users/jacob/connections/album-pairs?limit=8
coverage {'library_album_count': 509, 'albums_with_facts': 365,
'projected_fact_count': 8265, 'coverage_ratio': 0.7170923379174853}
insufficient_data_reason None
- Metallica - Hardwired... to Self-Destruct <-> Red Hot Chili Peppers - I'm With You
  via Sara Lyn Killion (engineering); cross_artist=True; tracks=38
- Good Charlotte - Good Charlotte <-> Pearl Jam - Ten
  via Don Gilmore (engineering); cross_artist=True; tracks=34
- Johnny Cash - American IV: The Man Comes Around <-> Red Hot Chili Peppers - Blood Sugar Sex Magik
  via Rick Rubin (producer); cross_artist=True; tracks=32
- The Clash - London Calling <-> Sex Pistols - Never Mind the Bollocks Here's the Sex Pistols
  via Bill Price (engineering); cross_artist=True; tracks=31
```

Rendered QA checks:

- The Connections page loads recurring contributors and direct album-pair
  suggestions in one request cycle.
- The pair section appears below recurring contributors when suggestions are
  available.
- Pair cards show two album labels, a link icon, the contributor, the role, and
  the evidence track count.
- Clicking either album opens the existing album panel.

Product review outcome:

- User review found the static album-pair section technically understandable
  but not especially interesting as a default page section.
- The issue is presentation, not role inclusion. Engineering, mixing, and
  mastering credits remain interesting and should stay in the relationship
  model.
- The desired surface is an interactive node/branch map where albums,
  contributors, artists, and roles can be explored visually.
- The default Connections UI should remove or hide the static Phase 6 pair-card
  section before further product work.
- Keep the Phase 6 backend endpoint and tests for now, because the direct-pair
  query may still support graph interactions, hover details, or future focused
  lookups.

Unresolved data-quality and UX issues:

- Static pair cards make the relationships feel flat even when the underlying
  credit role is interesting.
- Evidence track count is useful context for explaining link strength, but it
  can favor long albums and deluxe editions if used too heavily in ranking.
- The page still depends heavily on legacy/name-only projected facts.

Phase 6 results and follow-ups:

- Outcome for the overall feature: Connections now shows not only recurring
  contributors, but also specific album-to-album relationships that explain how
  two albums are connected by a direct shared credit.
- What changed: added a direct pair API, response schemas, suppression/ranking
  logic, API tests, frontend API call, and a pair section on the Connections
  page.
- Independent review: completed on 2026-07-04. Static pair cards are not
  compelling enough to continue as the default surface.
- Next step enabled: Phase 7 Remove Static Pair Cards, which cleans up the
  default UI while preserving the backend endpoint.
- Carry-forward issue: design the next product step around an interactive
  connection map rather than a finder-first or static-card-first workflow.

## Phase 7: Remove Static Pair Cards

Goal: remove the Phase 6 static album-pair section from the default Connections
page without deleting the backend query work.

Work:

- Remove the "Albums connected by credits" section from
  `frontend/src/components/PageConnections.jsx`.
- Stop fetching album-pair suggestions during the default Connections page
  load.
- Keep `/api/users/{user_slug}/connections/album-pairs` and its tests in place
  for future graph-map interactions or focused lookup.
- Update the plan results section after removal.

Acceptance criteria:

- `/jacob/connections` shows the top summary and recurring contributor
  information but no static album-pair cards.
- Backend album-pair endpoint tests still pass.
- No Phase 8 graph work is started in this cleanup phase.

Status: completed on 2026-07-04.

Implemented files:

- `frontend/src/components/PageConnections.jsx`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Removed the static "Albums connected by credits" section from the default
  Connections page.
- Stopped the default Connections page load from requesting
  `/api/users/{user_slug}/connections/album-pairs`.
- Kept the backend album-pairs endpoint, schemas, and tests in place for future
  interactive map support.
- Did not start Phase 8 graph/map implementation.

Validation commands:

- `npm --prefix frontend run lint`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`

Representative rendered QA expectation:

```text
GET /api/users/jacob/connections/recurring?limit=25 -> 200
No request to /api/users/jacob/connections/album-pairs during page load
"Recurring contributors" visible
"Albums connected by credits" not present
```

Unresolved data-quality and UX issues:

- The current page is still static and list/card based.
- The recurring contributor information remains useful, but it does not yet
  satisfy the intended node/branch interaction model.
- Legacy/name-only credit facts remain a major quality caveat.

Phase 7 results and follow-ups:

- Outcome for the overall feature: the default Connections page no longer shows
  the static album-pair section that product review found uninteresting.
- What changed: the page now loads only recurring contributors again while
  preserving the direct-pair backend query for later graph interactions.
- Independent review: refresh `/jacob/connections` and confirm the top summary
  plus recurring contributor information feels like the right temporary surface.
- Next step enabled: Phase 8 Interactive Connections Map, which will turn the
  useful metadata into the intended node/branch exploration experience.

## Phase 8: Interactive Connections Map

Goal: make the main Connections experience feel like an explorable node/branch
network instead of a static report.

Work:

- Add a focused interactive graph/map surface on the Connections page.
- Start with album nodes and contributor nodes connected by meaningful projected
  credit facts.
- Include engineering, mixing, mastering, producing, writing, performing, and
  other meaningful roles. Do not demote engineering/mixing/mastering by default.
- Use role color, labels, hover/detail panels, and click interactions to explain
  the relationships.
- Let clicking a contributor highlight connected albums and show role/quality
  detail.
- Let clicking an album open the existing album panel or focus related
  contributors.
- Keep the graph scoped and curated; do not render a giant uncontrolled
  whole-library graph on first load.

Acceptance criteria:

- The graph renders quickly for Jacob's library without layout overlap.
- Users can interactively inspect at least contributors, albums, roles, and
  connected counts.
- The existing recurring contributor data remains available as a side panel,
  fallback, or supporting list.
- The graph does not use listen counts for ranking or display.
- Browser QA verifies desktop and mobile rendering, nonblank graph output, and
  working node interactions.

Status: completed on 2026-07-04.

Implemented files:

- `frontend/src/components/PageConnections.jsx`
- `frontend/src/components/connections/ConnectionsGraph.jsx`
- `frontend/src/components/connections/connectionGraphModel.js`
- `frontend/src/components/connections/ConnectionsGraph.test.jsx`
- `docs/credit-intelligence-implementation-plan.md`

Implementation notes:

- Added a focused interactive Connections map above the recurring contributor
  card grid.
- The graph uses the existing recurring-contributor API response as a curated
  source: top contributors plus representative albums.
- The graph currently limits itself to 10 contributors, 4 representative albums
  per contributor, and 28 unique album nodes so it stays legible.
- Contributor nodes, album nodes, and role-colored links are rendered in SVG.
- Selecting a contributor highlights directly connected albums and shows role,
  album, artist, quality, and connected-count details.
- Selecting an album highlights directly connected contributors and shows an
  `Open` action into the existing album panel.
- Engineering, mixing, mastering, producing, writing, and performing all remain
  meaningful roles in the map; engineering/mixing/mastering are not hidden or
  demoted.
- The recurring contributor cards remain below the graph as a supporting list.
- Did not add a two-album finder, multi-step paths, a graph database, listen
  weighting, or a static album-pair section.

Validation commands:

- `npm --prefix frontend run lint`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
- `make test`

Representative rendered QA output:

```text
Desktop /jacob/connections:
- Connections map visible: true
- Recurring contributors visible: true
- SVG box: 1006x520
- Nodes: 36
- Links: 40
- Selecting an album changes the detail panel: true
- Album detail Open action visible after album selection: true
- Requested /album-pairs during page load: false
- Connections API errors: none

Mobile /jacob/connections:
- Connections map visible: true
- SVG box: 292x360
- Nodes: 36
- Links: 40
- Horizontal overflow: false
- Connections API errors: none
```

Unresolved data-quality and UX issues:

- The graph is curated from representative albums rather than a dedicated graph
  endpoint, so it is a first interaction layer, not the full relationship model.
- Node labels live primarily in hover/accessibility text and the detail panel;
  future iterations may need richer labels, search, or zoom once the interaction
  direction is validated.
- Legacy/name-only facts remain a major quality caveat.
- The graph layout is deterministic and lightweight, but not yet force-directed
  or user-arrangeable.

Phase 8 results and follow-ups:

- Outcome for the overall feature: Connections now has the intended
  node/branch interaction layer instead of being only a static ranked report.
- What changed: added an SVG graph component, a graph model helper, graph unit
  tests, page integration, and browser validation across desktop and mobile.
- Independent review: interact with the map on `/jacob/connections`, select
  several contributors and albums, and decide whether the curated graph feels
  closer to the intended exploration experience.
- Next step enabled: refine the graph interaction model before considering the
  Phase 9 album finder. Likely refinements include better labels, search/focus,
  a dedicated graph API, or zoom/pan if the current map feels promising.

Phase 8 graph foundation refinement completed on 2026-07-04:

- Outcome for the overall feature: the graph is no longer adapted from the
  recurring-contributor card payload. It now has a dedicated graph-shaped API
  and album artwork nodes.
- Backend changes:
  - Added `/api/users/{user_slug}/connections/graph`.
  - Added explicit graph response schemas for nodes and edges.
  - The endpoint returns contributor nodes, album nodes, role edges, local
    artwork URLs when cached, connected counts, role buckets, quality flags,
    identity resolution, and ingestion versions.
  - The endpoint remains user-scoped and does not expose listen-count fields.
- Frontend changes:
  - `PageConnections` now loads recurring contributors for the supporting card
    list and the dedicated graph payload for the map.
  - `ConnectionsGraph` renders album nodes as artwork thumbnails when an
    `image_url` is available, with a fallback node style otherwise.
  - `connectionGraphModel` now normalizes explicit backend graph nodes and
    edges rather than deriving graph data from recurring contributors.
- Validation commands:
  - `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
  - `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
  - `make test`
- Representative Jacob graph API output:

```text
GET /api/users/jacob/connections/graph?contributor_limit=12&album_limit_per_contributor=6&album_limit=48
nodes 56
edges 72
album_art_nodes 44
listen_fields False
first_album_art /media/artwork/58afd5f5-a3cb-43c4-a0dc-fd15fbfe33bf.jpg
```

- Artwork URL smoke check:

```text
GET /media/artwork/58afd5f5-a3cb-43c4-a0dc-fd15fbfe33bf.jpg -> 200 image/jpeg
```

- Automated rendered browser QA was attempted but blocked by local disk space:

```text
browserType.launch: ENOSPC: no space left on device
df showed only ~112 MB available on /System/Volumes/Data
```

- Unresolved issues:
  - Browser rendering should be rechecked after freeing local disk space.
  - The graph is still curated and deterministic; it does not yet support
    zoom, pan, or force-directed placement.
  - Album artwork coverage depends on cached or remote artwork availability.
  - Legacy/name-only credit facts remain a major quality caveat.

Phase 8 graph interaction refinement completed on 2026-07-04:

- Outcome for the overall feature: the graph now supports targeted exploration
  of direct album-contributor neighborhoods without introducing multi-step path
  finding or listen-count weighting.
- Backend changes:
  - Added optional `focus_node_id` support to
    `/api/users/{user_slug}/connections/graph`.
  - Contributor focus moves that contributor to the front of the graph result
    when the contributor is eligible for graph display.
  - Album focus moves directly connected eligible contributors to the front of
    the graph result.
  - The response remains user-scoped, direct-only, and free of listen-count
    ranking fields.
- Frontend changes:
  - Added local search for albums and contributors currently present in the
    graph payload.
  - Added `Focus` actions in the node detail panel. Focusing reloads a larger
    direct neighborhood around the selected node.
  - Fixed the initial active-edge state so the graph consistently highlights
    the effective selected/focused node.
- Validation commands:
  - `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
  - `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" frontend/node_modules/.bin/vitest run`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" frontend/node_modules/.bin/vite build`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/components/connections/connectionGraphModel.js src/components/connections/ConnectionsGraph.test.jsx src/services/albumApi.js` from `frontend/`
  - `make test`
- Representative focused graph API output from the deterministic test fixture:

```text
GET /api/users/listener/connections/graph?contributor_limit=1&album_limit_per_contributor=5&album_limit=10&focus_node_id=contributor%3Aname%3Awriter%20one
status 200
nodes 3
contributors ['Writer One']
albums ['Album One', 'Album Two']
edges 2
edge_sources ['contributor:name:writer one']
listen_fields False
```

- Validation caveats:
  - `npm` and `node` were not on PATH after the machine crash, so frontend
    validation used the bundled Codex Node runtime and local `node_modules`
    executables.
  - Full frontend lint currently fails on existing unrelated
    `react-hooks/set-state-in-effect` issues in `AlbumCreateDialog`,
    `AlbumMetadataActions`, `AlbumUserTags`, `ImportHistoryDialog`, and
    `AlbumEditForm`. Changed-file lint passes.
  - The local dev server was not running after the crash, and the local
    `data/spotify_tracker.sqlite` file was an empty 4 KB SQLite file during
    this pass, so live `/jacob/connections` browser QA and Jacob-data API
    sampling should be repeated after restoring the real local data/server.
- Independent review:
  - On `/jacob/connections`, search for a contributor or album visible in the
    graph, select it, then use `Focus`. Confirm the expanded direct neighborhood
    feels like the intended exploration pattern.
- Next step enabled: decide whether the focused direct-neighborhood graph is
  enough for the MVP, or whether the next product iteration should add zoom/pan
  and a more flexible layout before moving on to any album-finder feature.

Product direction update on 2026-07-04:

- The Connections page should become a guided graph-first discovery experience,
  not a static insight dashboard with a graph attached.
- The graph is primary because it is the main environment where discovery
  happens. It should not be primary in the sense of dumping every node onto the
  screen and asking the user to click around without guidance.
- Recurring-contributor cards remain useful, but they should become an
  alternate navigation surface that sends the user back into the graph.
- Operational metadata such as coverage counts and quality flags should move
  out of the normal user experience unless the user is in an audit or debug
  context.
- "Connect two albums" should be an entry point beside or inside the graph, not
  a separate static lower-page card section.
- Multi-step paths remain future-compatible, but the MVP should continue to
  prove direct album-contributor relationships first.

## Phase 9: Guided Graph-First Connections Page

Goal: reshape the current Connections page so the graph is the discovery
environment and the surrounding UI helps users enter, understand, and continue
exploring that graph.

Work:

- Keep the graph at the top of the page as the dominant feature.
- Replace the four operational summary cards with a compact exploration header:
  - "Explore your credit network"
  - "Follow the producers, musicians, writers, and engineers connecting your
    library."
- Add three primary exploration prompts:
  - Start with your top connector.
  - Start from an album.
  - Connect two albums.
- Default the graph to fewer, higher-value nodes.
- Highlight 3-5 suggested starting points on initial load and reduce the visual
  prominence of everything else.
- Make album/person node types visually obvious, including album artwork where
  available.
- Keep search available as a direct entry point into the graph.
- Move quality flags and ingestion/debug metadata out of the normal selected
  state UI.
- Keep recurring-contributor cards lower on the page, but make each card focus
  the graph rather than act as the primary destination.

Right-panel behavior:

- No selection:
  - Show recommended starting points.
  - Explain why each starting point is suggested.
- Person selected:
  - Explain why the person is interesting.
  - Show connected albums.
  - Show roles in plain language.
  - Suggest next nodes to inspect.
- Album selected:
  - Show important contributors.
  - Show recurring contributors connected to the album.
  - Show strongest direct outward relationships.
  - Suggest related albums.

Acceptance criteria:

- The first viewport reads as a graph-first exploration tool, not a metrics
  dashboard.
- Users can begin from a suggested connector, an album, or search.
- Selecting a node produces at least one plain-language interpretation of why
  that node matters.
- Suggested next hops are visible for person and album selections.
- Quality/debug metadata is not shown in the normal user path.
- The graph remains direct-only and does not use listen counts for ranking.
- Browser QA verifies desktop/mobile layout, no text overlap, graph interaction,
  search, focus, and recurring-card-to-graph navigation.

Phase 9 results and follow-ups:

- Completed on 2026-07-04.
- Outcome for the overall feature: the Connections page now presents the graph
  as the main discovery environment instead of opening with operational
  coverage metrics.
- What changed:
  - Replaced the top metric cards with the "Explore your credit network" header
    and three exploration prompts.
  - Added prompt entry points for top connector, starting album, and the future
    Phase 10 two-album connector.
  - Reduced the default graph request to a smaller direct-neighborhood slice.
  - Added a no-selection right-panel state with recommended starting points.
  - Added plain-language person and album interpretations in the right panel.
  - Added suggested next nodes for selected people and albums.
  - Moved quality/debug flags out of the normal graph/card selected-state UI.
  - Kept recurring-contributor cards lower on the page as alternate graph
    navigation, with `Focus graph` as the primary card action.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/components/connections/ConnectionSummaryCard.jsx src/components/connections/connectionGraphModel.js src/components/connections/ConnectionsGraph.test.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
  - `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
  - `make test`
- Representative rendered QA output, using a temporary seeded `listener`
  database and the in-app browser:

```text
Desktop /listener/connections after top-connector prompt:
hasHeader true
hasPrompts true
hasGraph true
graphNodeCount 5
graphEdgeCount 5
hasProducerInterpretation true
hasConnectedAlbums true
hasSuggestedNextNodes true
hasOperationalMetricText false
new console errors/warnings after fixed reload []

Mobile 390px /listener/connections:
hasHeader true
hasPrompts true
hasGraph true
graphRect 292x360
horizontalOverflow false
```

- Browser QA note: the browser `domSnapshot()` helper failed in this session
  with `incrementalAriaSnapshot is not a function`, so rendered QA used browser
  page evaluation, screenshots, console logs, and interactions instead.
- Unresolved issues:
  - The "Connect two albums" prompt is intentionally disabled/marked as Phase
    10; the album-to-album finder was not implemented in Phase 9.
  - Suggested next-hop logic is still simple and local to the visible direct
    graph payload.
  - The graph layout remains deterministic rather than zoomable, pannable, or
    force-directed.
  - Jacob's real local database should be restored and reviewed separately; this
    pass used a seeded test-profile database for rendered QA because the local
    `data/spotify_tracker.sqlite` was empty after the crash.
- Independent review:
  - On `/jacob/connections`, confirm the first viewport feels like a guided
    exploration surface rather than a dashboard.
  - Click `Start with your top connector`, `Start from an album`, graph nodes,
    search results, and lower `Focus graph` card actions.
  - Decide whether the right-panel explanations and suggested next nodes are
    helpful enough to keep refining, or if they need different language.
- Next step enabled: Phase 10 can turn the disabled "Connect two albums" prompt
  into a focused graph state for direct shared contributors between two albums.

## Phase 10: Graph-Integrated Album Connector

Goal: add "Connect two albums" as a graph entry point that explains direct
shared contributors between two albums inside the same discovery environment.

Work:

- Add an album-to-album entry point next to the graph prompts.
- Let the user choose two albums from the current user's library.
- Find direct shared contributors between the selected albums first.
- Render the selected albums, shared contributor nodes, and role edges in the
  graph.
- Use the right panel to explain:
  - each direct step,
  - why the path was selected,
  - any alternate direct shared contributors if available,
  - clear no-direct-connection and insufficient-data states.

Acceptance criteria:

- The result is displayed as a focused graph state, not a separate static report.
- The explanation is understandable without graph terminology.
- The finder handles no connection without inventing missing results.
- It does not search multi-step paths yet.

Phase 10 results and follow-ups:

- Completed on 2026-07-04.
- Outcome for the overall feature: the "Connect two albums" prompt is now a
  real graph entry point for direct shared contributors between two selected
  albums.
- Backend changes:
  - Added `/api/users/{user_slug}/connections/album-connection`.
  - Added `AlbumConnectionGraphResponse` and shared-contributor schemas.
  - The endpoint requires both albums to belong to the current user's library.
  - The endpoint rejects same-album comparisons.
  - The endpoint filters default identity and primary-artist noise before
    returning shared contributors.
  - No-direct-connection responses still return the two selected album nodes so
    the graph can explain what was compared.
- Frontend changes:
  - Enabled the "Connect two albums" prompt.
  - Added two album selectors and a `Show connection` action beside the graph
    prompts.
  - Added a graph path detail state for direct shared credits.
  - Added no-direct-connection copy for pairs without reliable shared
    contributors.
  - Kept the result inside the same graph surface instead of adding a separate
    static report section.
- Validation commands:
  - `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
  - `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
  - `make test`
- Representative API output from the seeded listener fixture:

```text
GET /api/users/listener/connections/album-connection?album_a_id=1&album_b_id=2
status ok
album_a Album One
album_b Album Two
shared ['Producer One', 'Writer One']
nodes 4
edges 4
no_direct_connection False
listen_fields False
```

- Representative rendered QA output, using a temporary seeded `listener`
  database and the in-app browser:

```text
Successful direct connection:
hasDirectSharedCredits true
hasPathStep true
hasWhySelected true
hasAlternatePath true
graphNodeCount 4
graphEdgeCount 4
new console errors/warnings []

No direct connection:
hasNoDirect true
hasNoDirectExplanation true
graphNodeCount 2
graphEdgeCount 0
new console errors/warnings []

Mobile 390px:
hasConnectorControls true
hasGraph true
graphRect 292x360
horizontalOverflow false
```

- Browser QA note: the browser automation could not use label-based
  `selectOption` reliably until explicit `htmlFor`/`id` bindings were added to
  the native selects. After that, stable `#album-connection-a` and
  `#album-connection-b` control paths passed.
- Unresolved issues:
  - The connector is direct-only; it does not search multi-step paths.
  - The endpoint may return legacy/name-only shared contributors when those pass
    the current direct-credit filters.
  - Album duplicate/disambiguation UX is still basic when two albums have the
    same displayed name and artist.
  - Jacob's real local data should be reviewed separately; rendered QA used the
    seeded listener fixture.
- Independent review:
  - On `/jacob/connections`, choose two albums known or suspected to share
    production/writing/engineering credits and check whether the path panel feels
    useful.
  - Also choose two albums that should not connect and confirm the no-direct
    explanation is clear.
- Product direction update on 2026-07-04: the direct album connector is useful
  foundation work, but the intended "Connect two albums" experience should find
  surprising indirect paths through the credit network, not only direct shared
  contributors.
- Next step enabled: Phase 11 can upgrade the album connector from direct-only
  matching to bounded multi-step album pathfinding.

## Phase 11: Multi-Step Album Pathfinding

Goal: let a user choose two albums and find short indirect credit paths between
them inside the graph discovery environment.

Work:

- Build a user-scoped in-memory graph from `album_credit_facts`.
- Use album nodes and contributor nodes.
- Use available credit facts as edges, preserving the existing default identity
  and primary-artist filters while keeping low-share and single-track credits.
- Search for bounded paths like:
  `album X -> engineer A -> album D -> producer P -> album Y`.
- Treat the existing direct shared-contributor result as the shortest path case.
- Start with a bounded MVP search, now four contributor hops maximum, rather
  than traversing the whole library indefinitely.
- Rank paths by:
  - fewer hops first,
  - stronger and more meaningful role evidence,
  - contributor identity confidence,
  - cross-album usefulness,
  - avoiding default identity and primary-artist noise.
- Return the best path plus a small number of alternates.
- Render the selected path in the graph and right panel.
- Add plain-language step explanations for every hop.
- Preserve no-path and insufficient-data states.

Acceptance criteria:

- Direct shared-contributor album results still work.
- Known two-hop and four-hop indirect album paths are found in backend tests.
- The endpoint remains user-scoped and only connects albums in the current
  user's library.
- The search is bounded and does not return uncontrolled whole-library paths.
- Default identity and primary-artist noise is excluded from path search, while
  low-share and single-track credits remain eligible.
- Every returned path explains each album, contributor, role, and why that path
  was selected.
- Desktop and mobile browser QA cover a found indirect path and a no-path state.

Phase 11 results and follow-ups:

- Completed on 2026-07-04.
- Outcome for the overall feature: "Connect two albums" now supports bounded
  indirect credit paths, so the graph can explain chains such as
  `album -> contributor -> intermediate album -> contributor -> album`.
- Backend changes:
  - Extended `/api/users/{user_slug}/connections/album-connection` without
    replacing the existing direct-shared-contributor contract.
  - Added additive response fields: `best_path`, `alternate_paths`, `no_path`,
    and `max_contributor_hops`.
  - Added a bounded path search over `album_credit_facts`.
  - Kept default identity and primary-artist exclusions in path search.
  - Changed `single_track_credit` and `low_track_share` from exclusion criteria
    into visible evidence labels, so low-share credits remain eligible.
  - Kept endpoint ownership checks so both selected albums must belong to the
    current user's library.
  - Preserved same-album rejection and direct shared-contributor behavior.
- Frontend changes:
  - Changed the prompt language from direct-only matching to direct or indirect
    credit paths.
  - Updated the graph detail panel to show direct, indirect, and no-path states.
  - Added per-step path explanations and alternate-path summaries.
  - Highlighted returned path nodes and edges when an album connection result is
    shown.
- Validation commands:
  - `./.venv/bin/python -m unittest tests.test_api_credit_intelligence -v`
  - `./.venv/bin/python -m py_compile backend/app/services/credit_intelligence_service.py backend/app/routers/credit_intelligence.py backend/app/schemas.py`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
  - `make test`
- Representative API output from the seeded listener fixture:

```text
indirect
status ok
albums Album Two => Album Four
no_direct_connection True
no_path False
best_hop_count 2
steps ['Producer One', 'Bridge Engineer']
nodes 5
edges 4

no_path
status ok
albums Album Two => Isolated Album
no_direct_connection True
no_path True
best_hop_count None
steps []
nodes 2
edges 0
```

- Validation results:
  - Focused credit-intelligence API tests passed: 14 tests.
  - Frontend unit tests passed: 6 files, 27 tests.
  - `make test` passed: 207 tests, 1 skipped.
  - Vite build passed with existing unresolved Inter font-file warnings and the
    existing large chunk warning.
- Rule update on 2026-07-04:
  - User clarified that weak credits should not be filtered out for now.
  - `single_track_credit` and `low_track_share` now remain eligible for direct
    album pairs and bounded path search.
  - These flags should be used as explanation/ranking context later, not as
    hard blockers.
  - User also clarified that longer chains are part of the intended discovery
    experience. The album pathfinder is now bounded to four contributor hops,
    which is enough for chains like
    `album -> person -> album -> person -> album -> person -> album -> person -> album`
    without making the search unbounded.
- UX update on 2026-07-04:
  - Replaced the album-connection native dropdowns with searchable album inputs
    because large libraries can have hundreds or thousands of albums.
  - The search controls filter by album and artist, render only a small result
    list, and exclude the album already selected in the opposite field.
- Browser QA note:
  - A temporary seeded backend/frontend pair served the indirect and no-path API
    states successfully.
  - The in-app browser bridge timed out while reading the current tab and while
    waiting for the seeded page, so desktop/mobile rendered browser QA was not
    completed in this pass.
- Unresolved issues:
  - The pathfinder is intentionally bounded to four contributor hops; longer
    chains are still out of scope.
  - Path ranking is heuristic, not a full weighted shortest-path model.
  - Name-only legacy contributors can still participate when they pass the
    current filters.
  - Duplicate album/disambiguation UX is still basic in the album selectors.
  - Real local data may still have no-path pairs because the current search
    remains bounded to four contributor hops.
- Independent review:
  - On `/jacob/connections`, choose albums that you suspect are connected
    through producers, writers, engineers, mixing, mastering, or musicians.
  - Confirm the right panel makes the indirect chain understandable without
    needing to interpret the graph structure manually.
  - Also choose an unrelated pair and confirm the no-path state feels clear.
- Next step enabled: Phase 12 can refine graph layout, path explanation quality,
  and next-hop suggestions now that direct and bounded indirect album paths
  exist.

## Phase 12: Interpretation And Layout Refinement

Goal: improve the graph as a guided discovery environment after the graph-first
page, direct album connector, and bounded multi-step pathfinding are validated.
This should be delivered in small passes rather than as one large redesign.
The next work is interaction polish and explanation quality, not new graph
algorithms.

Phase 12A: interaction clarity:

- Treat the three entry cards as mode selectors:
  - top contributor immediately focuses the suggested contributor;
  - start from an album activates one searchable album picker;
  - connect two albums activates the two searchable album pickers.
- Do not show the two-album connector controls until that mode is active.
- Change the graph heading with the current state, such as a contributor
  network, an album neighborhood, or a connection between two albums.
- Rename abstract actions such as `Focus` and `Inspect` to clearer
  user-facing labels such as `Show connections`, `Explore`, `View details`, or
  `Details`.
- Label the legend as `Roles in this view`, or otherwise make clear that the
  legend reflects the active graph state.
- Keep recurring-contributor cards as lower-page alternate entry points that
  send the user back into the graph.

Phase 12B: graph legibility:

- Add visible short contributor labels in focused and path views.
- Keep album artwork as the primary album-node signal.
- Make selected nodes, path endpoints, intermediate albums, and intermediate
  contributors visually distinguishable.
- Make the selected path visually heavier and fade secondary relationships more
  aggressively.
- Reduce blank space in sparse focused graphs by scaling the layout to the
  visible content.
- Evaluate zoom/pan, force-directed layout, or manual repositioning only after
  these simpler focused-view improvements are tested.

Phase 12C: explanation and continuation:

- Rewrite path explanations as a compact path first, followed by role labels
  and one concise summary.
- Avoid repeating the same path-step explanation in multiple places.
- Improve suggested next-hop logic for selected people, albums, and path
  results.
- Add clear continuation actions such as following a contributor, exploring a
  connected album, using the selected album as a path endpoint, or choosing
  another contributor.
- Consider exposing hidden-connector ideas only as graph suggestions or
  starting points, not as a separate dashboard section.

Explicitly out of scope for this refinement pass:

- Do not add a path-type selector such as "Shortest", "Strongest", or
  "Alternative" yet.
- Do not add user-facing "best path" scoring or rationale beyond the current
  plain-language explanation.
- Do not rename or rework the "top connector" concept in this pass unless a
  later product decision approves new terminology.

Acceptance criteria:

- The page helps the user decide where to go next after every selection.
- Larger neighborhoods remain legible on desktop and mobile.
- Entry controls are mode-specific, with no permanently visible redundant
  two-album selectors.
- The graph can be interpreted from the visual state before the user reads the
  full side panel.
- Path explanations are compact, readable with long album titles, and avoid
  repeated debug-like text.
- Recurring-contributor cards remain supporting entry points, not the primary
  product surface.
- Hidden connectors, if introduced, are explainable from direct relationships
  and do not surface obvious compilation, reissue, or large-ensemble artifacts.

Phase 12 results and follow-ups:

Phase 12A interaction clarity completed on 2026-07-05:

- Outcome for the overall feature: the Connections page now behaves more like a
  guided graph workspace instead of showing every entry control at once.
- What changed:
  - The three entry cards now act as mode selectors.
  - `Start with your top connector` immediately focuses that contributor in the
    graph.
  - `Start from an album` opens one searchable album input and a
    `Show connections` action.
  - `Connect two albums` opens the two searchable album inputs and the
    `Show connection` action.
  - The two-album connector controls are no longer permanently visible on first
    load.
  - The graph title now changes with state, including contributor networks,
    album neighborhoods, and album-to-album connection views.
  - The role legend is labeled `Roles in this view`.
  - Recurring-contributor card actions and graph detail actions now use
    `Show connections` and `Details` instead of `Focus graph` and `Inspect`.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 3 files, 12 tests.
  - Full frontend tests passed: 6 files, 27 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
Initial desktop state:
- header visible: true
- graph visible: true
- two-album connector inputs visible before activation: false
- start-album input visible before activation: false
- role legend says "Roles in this view": true
- old "Focus graph" / "Inspect" labels present: false

Connect-two-albums mode:
- first album input visible: true
- second album input visible: true
- start-album input visible: false
- "Show connection" action visible: true

Start-from-album mode:
- album input visible: true
- two-album connector inputs visible: false
- "Show connections" action visible: true

Top connector mode:
- graph title changed to "Manny Marroquin's network": true
- connector and start-album mode inputs hidden: true

Mobile 390px:
- graph visible: true
- graph size: 309x360
- horizontal overflow: false
- connector/start-album inputs hidden on first load: true
```

- Browser QA note: the browser `domSnapshot()` helper still fails with
  `incrementalAriaSnapshot is not a function`, so rendered QA used direct
  Playwright role locators and page evaluation instead.
- Unresolved issues:
  - Phase 12A did not change graph node labeling, path visual weight, sparse
    graph scaling, or path explanation density. Those remain Phase 12B/12C
    work.
  - Path selection terminology and "top connector" wording remain unchanged by
    design.
- Independent review:
  - On `/jacob/connections`, confirm that the initial page no longer feels
    over-instrumented.
  - Click each entry prompt and confirm the active controls match the selected
    mode.
  - Use a recurring-contributor card and graph detail action to confirm
    `Show connections` and `Details` feel clear.
- Next step enabled: Phase 12B graph legibility, especially contributor labels
  in focused/path views, stronger selected/path visual states, and sparse graph
  scaling.

Phase 12B graph legibility completed on 2026-07-05:

- Outcome for the overall feature: focused graph states and album path results
  are easier to read without relying entirely on the side panel.
- What changed:
  - Contributor labels now appear in focused contributor views and album-path
    views.
  - Sparse focused graphs use tighter dynamic radii so small neighborhoods do
    not spread across the full canvas unnecessarily.
  - Album path endpoints, intermediate albums, and intermediate contributors
    now use distinct stroke colors and stronger outlines.
  - Selected nodes have a stronger outline.
  - Path edges are visually heavier than ordinary graph edges.
  - Secondary relationships fade more aggressively in focused/path states.
  - No-path album comparison states still highlight the two compared endpoint
    albums without inventing missing path edges.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 3 files, 12 tests.
  - Full frontend tests passed: 6 files, 27 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against richer rebuilt Jacob data:

```text
Focused contributor graph:
- top connector graph title changed to Manny Marroquin's network: true
- contributor labels visible: Manny Marroquin
- selected node outline max stroke: 4.5
- inactive link opacity: 0.045
- horizontal overflow: false

Album path graph, Oh My My -> A Fever You Can't Sweat Out:
- path panel visible: true
- graph title visible: true
- contributor labels visible: John Hanes, Brendon Urie
- path edges rendered: 4
- path edge stroke width: 4.4
- endpoint/intermediate node outline max stroke: 4
- horizontal overflow: false

Mobile 390px:
- graph visible: true
- graph size: 309x360
- horizontal overflow: false
- load/error state absent after data load
```

- Browser QA note: the graph request is slower against the richer copied
  production-sized database, so rendered checks waited longer for the initial
  `/jacob/connections` data load.
- Unresolved issues:
  - Phase 12B did not reduce path explanation text density. That remains Phase
    12C.
  - Contributor labels are intentionally limited to focused/path states; the
    neutral overview still avoids labeling every contributor.
  - The graph still uses deterministic placement rather than zoom/pan or a
    force-directed layout.
- Independent review:
  - On `/jacob/connections`, start with the top connector and confirm the
    visible label and selected outline make the graph readable.
  - Connect `Oh My My` to `A Fever You Can't Sweat Out` and confirm the path
    edges and contributor labels make the chain understandable before reading
    the full side panel.
  - Try a no-path pair and confirm only the compared albums are emphasized.
- Next step enabled: Phase 12C explanation and continuation, especially turning
  the path panel into a compact path-first explanation and improving suggested
  next actions from selected people, albums, and paths.

Phase 12C explanation and continuation completed on 2026-07-05:

- Outcome for the overall feature: album connection results now read as a
  compact discovery path, and selected graph states offer clearer follow-on
  actions.
- What changed:
  - Replaced repeated path-step cards with one compact path sequence:
    album, contributor, album, contributor, album.
  - Kept contributor role labels directly under contributor path chips.
  - Replaced the repeated generated step explanations with one concise summary
    such as `Connected through 2 shared-credit links across 3 albums`.
  - Added a `Continue exploring` section for album paths.
  - Added `Follow {contributor}` actions from album path results.
  - Added `Use {album} as start` from path results and `Use this album as path
    start` from selected album states.
  - The path-start action switches into the two-album connector mode and
    pre-fills the first album input.
  - Renamed selected album/person suggestion sections to `Continue exploring`.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 3 files, 12 tests.
  - Full frontend tests passed: 6 files, 27 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against richer rebuilt Jacob data:

```text
Album path graph, Oh My My -> A Fever You Can't Sweat Out:
- compact summary visible: true
- old repeated step explanation absent: true
- path title visible: true
- path sequence visible: Oh My My -> John Hanes -> Lover -> Brendon Urie -> A Fever You Can't Sweat Out
- follow action visible: Follow John Hanes
- path-start action visible: Use Oh My My as start
- horizontal overflow: false

Use path start:
- first album input visible: true
- first album input value: Oh My My · OneRepublic
- second album input visible: true
- previous path panel cleared: true
- horizontal overflow: false

Mobile 390px:
- graph visible: true
- graph size: 309x360
- horizontal overflow: false
- load/error state absent after data load
```

- Browser QA note: as in Phase 12B, checks used longer waits against the richer
  local database because the initial graph and album-connection requests are
  slower with 1,000+ library albums.
- Unresolved issues:
  - Alternate paths are still summarized by hop count only; choosing between
    alternates remains out of scope until explicitly approved.
  - The compact path sequence is text/button based, not a separate timeline
    component.
  - Search/focus and path-start actions now form the basic continuation loop,
    but there is still no role-specific continuation such as "show more mixing
    links" or hidden-connector suggestion engine.
- Independent review:
  - Connect `Oh My My` to `A Fever You Can't Sweat Out` and confirm the path
    panel now reads as a compact music relationship rather than a report.
  - Click `Follow John Hanes` or `Follow Brendon Urie` and confirm it selects
    that contributor in the graph.
  - Click `Use Oh My My as start` and confirm the connector mode opens with
    that album prefilled.
- Next step enabled: review the completed Phase 12 refinements on richer data
  and decide whether to stop at the current MVP polish or start a new phase for
  role-specific continuation suggestions, performance optimization, or alternate
  path interaction.

Phase 12D graph orientation clarity completed on 2026-07-05:

- Outcome for the overall feature: the graph now explains its own visual
  grammar and scope before the user has to infer it from the map.
- What changed:
  - Added concise graph-header copy explaining that the view is a curated slice
    of recurring contributors and representative albums, not the whole library.
  - Added a node legend for contributor circles, album artwork, bright focus
    nodes, and faded surrounding context.
  - Renamed the edge legend to `Role colors` and added copy that line color
    shows the contributor's role on that album.
  - Updated graph titles and descriptions for default, contributor-focused,
    album-focused, and album-path states.
  - Expanded contributor labels so selected, active/path, and small-graph
    contributor sets are identifiable.
  - Updated recommended starts with evidence such as album count, artist
    breadth, and connected recurring contributors.
  - Added a compact `How to explore` block to the neutral right panel.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 3 files, 12 tests.
  - Full frontend tests passed: 6 files, 27 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
Default graph:
- curated graph explanation visible: true
- node legend visible: true
- role color explanation visible: true
- recommendation evidence visible: true
- How to explore block visible: true

Focused contributor graph:
- title changed to Manny Marroquin's credit network: true
- curated/refocus copy visible: true
- Manny Marroquin contributor label visible in the SVG: true

Focused album graph:
- title changed to Albums connected to Sweetener: true
- curated album-slice copy visible: true

Album path graph, Sweetener -> 30:
- title changed to Credit path between Sweetener and 30: true
- path panel visible: true
- curated path-context copy visible: true

Mobile 390px:
- horizontal overflow: false
```

- Browser QA note: Playwright's bundled Chromium binary was missing locally, so
  rendered QA used the installed system Google Chrome executable.
- Unresolved issues:
  - The graph still explains surrounding context through legend/copy rather
    than offering a show/hide surrounding-network toggle.
  - Recommendation reasons use the counts already available in the graph nodes;
    no new backend ranking or explanation fields were added.
- Independent review:
  - Open `/jacob/connections` and confirm the graph is understandable before
    selecting anything.
  - Select a contributor and an album from recommended starts and confirm the
    title, subtitle, labels, and faded surrounding nodes make the current view
    clear.
  - Connect two visible albums and confirm the path state still reads as a
    graph-led discovery state, not a separate report.

Phase 12E contributor start search completed on 2026-07-06:

- Outcome for the overall feature: contributor-led exploration now works like
  album-led exploration instead of forcing the top connector as a one-click
  preset.
- What changed:
  - Renamed the first exploration prompt to `Start from a contributor`.
  - Added a searchable contributor input backed by the recurring contributor
    results, matching by contributor name and formatted role summary.
  - Opening contributor mode preselects the top recurring contributor, but the
    graph only refocuses after `Show connections`.
  - Removed value-based remount keys from the Connections search inputs so typed
    contributor and album queries are preserved while searching.
  - Added unit coverage for contributor search matching.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/PageConnections.test.jsx src/components/connections/contributorSearch.js src/components/connections/ConnectionsGraph.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/PageConnections.test.jsx src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" npm run test` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" npm run build` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" npm run lint` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 4 files, 15 tests.
  - Full frontend tests passed: 7 files, 30 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
  - Full frontend lint is still blocked by pre-existing
    `react-hooks/set-state-in-effect` errors in unrelated files:
    `AlbumCreateDialog.jsx`, `AlbumMetadataActions.jsx`, `AlbumUserTags.jsx`,
    `ImportHistoryDialog.jsx`, and `dataQuality/AlbumEditForm.jsx`.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
Contributor start:
- prompt visible as Start from a contributor: true
- old Start with your top connector copy absent: true
- default contributor value: Manny Marroquin
- default Show connections button enabled: true
- typed contributor query persists: manny
- dropdown result sample: Manny Marroquin; Mixing/mastering 35, Engineering 3
- selected contributor value: Manny Marroquin
- contributor graph title/copy matched Manny Marroquin focus: true

Album and path controls:
- Start from an album input visible: true
- default album value: Sweetener · Ariana Grande
- typed album query persists: sweet
- Connect two albums inputs visible: true

Responsive/browser state:
- desktop horizontal overflow: false
- mobile 390px horizontal overflow: false
- mobile graph visible: true
- browser console/page errors: none
```

- Browser QA note: the in-app browser control tool was unavailable in this
  session, so rendered QA used the bundled Playwright package with the installed
  system Google Chrome executable.
- Independent review:
  - Open `/jacob/connections`, choose `Start from a contributor`, and confirm
    the top contributor is suggested without immediately refocusing the graph.
  - Search for a contributor by name or role, select a result, then click
    `Show connections`.
  - Confirm album start and two-album connection inputs still preserve typed
    search text.

Phase 12F graph legend de-emphasis completed on 2026-07-07:

- Outcome for the overall feature: the graph keeps useful role-color reference
  information without making legend explanation compete with exploration.
- What changed:
  - Moved `Role colors` out of the graph card header and into a compact strip
    below the SVG.
  - Removed the `Node types`, `Bright = current focus`, and `Faded =
    surrounding context` legend chips.
  - Kept graph search in the header so the primary controls remain easy to
    reach.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx src/components/connections/ConnectionSummaryCard.jsx src/services/albumApi.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Changed-file lint passed.
  - Targeted frontend tests passed: 4 files, 15 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
- role colors visible: true
- role colors below graph: true
- role colors inside graph frame: true
- header contains role colors: false
- Node types copy absent: true
- Bright = current focus copy absent: true
- Faded = surrounding context copy absent: true
- desktop horizontal overflow: false
- mobile 390px horizontal overflow: false
- mobile graph visible: true
- browser console/page errors: none
```

Phase 12G selected-node detail panel cleanup completed on 2026-07-07:

- Outcome for the overall feature: selected album and contributor panels now
  read as cleaner detail cards, with long titles/actions contained inside the
  right panel instead of overlapping neighboring text.
- What changed:
  - Reworked the right-panel detail layout into bounded stacked sections for
    selected albums, selected contributors, and album paths.
  - Changed header action buttons to full-width wrapping rows in the narrow
    panel.
  - Replaced cramped inline badge lists for connected albums/contributors with
    readable stacked related-node rows.
  - Added explicit width bounds to panel shells, text blocks, action buttons,
    and suggestion rows so long names and role summaries wrap within the panel.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 15 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
- selected contributor panel present: true
- selected contributor overflowing panel items: 0
- selected album panel present: true
- selected album overflowing panel items: 0
- mobile 390px selected album overflowing panel items: 0
- desktop horizontal overflow: false
- mobile horizontal overflow: false
- browser console/page errors: none
```

Phase 12H album artwork node size tuning completed on 2026-07-07:

- Outcome for the overall feature: album artwork is easier to recognize in the
  graph without changing the graph layout or adding new clutter.
- What changed:
  - Increased album artwork node sizes from `30/34/36/40/42` to
    `36/40/44/48/50` for default, active, path, endpoint, and selected states.
  - Contributor node sizes and graph positioning were left unchanged.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 2 files, 6 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
- default graph visible: true
- rendered album image sizes: 36px and 40px
- nearest album center distance: 52px
- estimated nearest album gap after size increase: 12px
- focused contributor graph visible: true
- mobile 390px graph visible: true
- desktop horizontal overflow: false
- mobile horizontal overflow: false
- browser console/page errors: none
```

Phase 12I graph focus selection precedence completed on 2026-07-07:

- Outcome for the overall feature: starting from a searched album or contributor
  now updates the graph title and right panel to that explicit start point
  instead of keeping a stale graph-selected node.
- What changed:
  - Added a focused selection resolver for graph state.
  - Internal graph selections now carry the focus/path scope they were made in.
  - New parent-driven focus from `Start from an album` or `Start from a
    contributor` overrides stale internal graph selections.
  - In-graph clicks and graph search still update the selected node within the
    current focus scope.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/connections/connectionSelection.js src/components/PageConnections.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 19 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
- selected Sweetener via graph search first: true
- Start from an album selected value: 30 · Adele
- graph title changed to Albums connected to 30: true
- right panel changed to 30 / Adele: true
- stale Albums connected to Sweetener title absent: true
- Start from a contributor changed to contributor credit network: true
- stale album title absent after contributor start: true
- mobile 390px graph visible: true
- mobile horizontal overflow: false
- browser console/page errors: none
```

Phase 12J selected-panel explanatory copy removal completed on 2026-07-07:

- Outcome for the overall feature: selected album and contributor panels are
  more direct and less repetitive, while contributor-selected album rows now
  show the contributor's role on each album.
- What changed:
  - Removed the selected album sentence beginning `is a useful starting point
    because`.
  - Removed the selected contributor sentence beginning `stands out because`.
  - Added per-edge role labels to the selected contributor `Connected albums`
    rows, using the actual graph link role between that contributor and album.
  - Added a unit-tested helper for formatting contributor-album connection
    role labels.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/connections/connectionRoles.js src/components/connections/connectionSelection.js src/components/PageConnections.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 20 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Representative rendered QA against `http://127.0.0.1:5173/jacob/connections`:

```text
- contributor explanatory copy absent: true
- contributor connected album role labels visible: true
- sample role labels: Short n’ Sweet / Sabrina Carpenter / Mixing/mastering;
  Sweetener / Ariana Grande / Mixing/mastering
- album explanatory copy absent: true
- mobile 390px graph visible: true
- mobile horizontal overflow: false
- browser console/page errors: none
```

Phase 12K album-connection sequence layout completed on 2026-07-07:

- Outcome for the overall feature: `Connect two albums` results now read more
  like a guided chain of albums and people instead of a circular web.
- What changed:
  - Album connection graph layout now uses the ordered best path when an album
    connection result is active.
  - Best-path albums are placed on a left-to-right album lane and people are
    placed on a separate contributor lane, creating an explicit
    `album -> person -> album` sequence.
  - Non-path nodes in album connection mode are moved into subdued top/bottom
    bands so the path remains visually dominant.
  - The right-panel path rows now make people visually distinct from albums
    with indentation, person icons, and a blue-tinted row treatment.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 20 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Rendered QA note:
  - Started a current backend on `127.0.0.1:8001` and Vite on
    `127.0.0.1:5174` with `VITE_API_PROXY_TARGET=http://127.0.0.1:8001`.
  - Direct API checks for recurring contributors and the graph returned data.
  - The in-app browser page remained on `Loading connections...` during the
    visual pass, so full rendered QA of the changed graph could not be
    completed in this run.
- Suggested next step:
  - Re-run browser QA against `/jacob/connections`, select `Connect two
    albums`, and verify a direct path, an indirect path, and mobile width once
    the local browser page completes its Connections load.

Phase 12L album-node artwork shape completed on 2026-07-08:

- Outcome for the overall feature: albums in the Connections graph now read
  more like actual album artwork and are easier to distinguish from people.
- What changed:
  - Album graph nodes are larger than before.
  - Artwork-backed album nodes now render as square tiles instead of circular
    crops.
  - Album nodes without artwork use the same square shape, while contributor
    nodes remain circular.
- Validation commands:
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 20 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Rendered QA note:
  - Not rerun for this narrow SVG shape/size change.

Phase 12M graph-local search removal completed on 2026-07-08:

- Outcome for the overall feature: the graph area is quieter and no longer
  duplicates the album/contributor search controls in the exploration header.
- What changed:
  - Removed the graph-header `Find album or contributor` search input.
  - Removed the local graph search state, filtering, result list, and unused
    imports that only supported that input.
  - Kept the main searchable contributor, album, and two-album connection
    controls in `PageConnections`.
- Validation commands:
  - `rg -n "Find album or contributor|Search graph nodes|searchTerm|searchResults" frontend/src/components/connections/ConnectionsGraph.jsx frontend/src/components/PageConnections.jsx`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/connections/ConnectionsGraph.jsx src/components/PageConnections.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vite build` from `frontend/`
- Validation results:
  - No leftover graph-local search references were found.
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 20 tests.
  - Vite build passed with existing Inter font-file warnings and the existing
    large chunk warning.
- Rendered QA note:
  - Not rerun for this narrow UI removal.

Phase 12N refocus label cleanup completed on 2026-07-08:

- Outcome for the overall feature: graph refocus actions use clearer, shorter
  language.
- What changed:
  - Renamed visible `Show connections` buttons to `Refocus`.
  - Updated the matching contributor-card icon button aria-label from `Show
    connections for...` to `Refocus on...`.
- Validation commands:
  - `rg -n "Show connections|show connections" frontend/src/components/PageConnections.jsx frontend/src/components/connections`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/eslint src/components/PageConnections.jsx src/components/connections/ConnectionsGraph.jsx src/components/connections/ConnectionSummaryCard.jsx` from `frontend/`
  - `PATH="/Users/jacobbattenberg/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node_modules/.bin/vitest run src/components/connections/ConnectionsGraph.test.jsx src/components/connections/connectionFormatters.test.js src/components/PageConnections.test.jsx src/routing.test.js` from `frontend/`
- Validation results:
  - No remaining `Show connections` text in Connections components.
  - Targeted lint passed.
  - Targeted frontend tests passed: 4 files, 20 tests.
- Rendered QA note:
  - Not rerun for this label-only change.

Phase 12O exploration workflow clarity completed on 2026-07-11:

- Outcome for the overall feature: graph exploration and album-to-album pathfinding now have separate, plainly named entry points.
- What changed:
  - Removed the selected-album and path-result `Use this album as path start` shortcuts and their frontend state wiring.
  - Kept `Connect two albums` as the single, explicit workflow for finding a direct or indirect credit path between specific albums.
  - Renamed graph-centering actions from `Refocus` to `Explore from here` across the explorer controls, graph detail panel, and recurring-contributor cards.
  - Renamed `Start from an album` to `Explore an album`.
  - Added concise helper copy explaining that exploring rebuilds the graph around the chosen album or contributor and its connected credits.
- Independent review:
  - Select an album and confirm `Explore from here` reloads the graph around that album.
  - Open `Connect two albums` and confirm both albums are chosen only through its two searchable inputs.
  - Confirm no path-start button appears in selected-album or path-result panels.

Phase 12P graph interaction modernization completed on 2026-07-11:

- Outcome for the overall feature: the credit graph now responds to curiosity before a user commits to selecting a node.
- What changed:
  - Added transient pointer-hover and keyboard-focus preview state without changing selected-node state or refetching graph data.
  - Hovering or focusing a node gently enlarges it, reinforces its outline, brightens its immediate credit links and neighbors, and fades unrelated graph content.
  - Added a compact in-graph preview showing album title/artist or contributor name/primary role.
  - Kept click, Enter, and Space selection behavior unchanged; the side panel remains driven by the selected node.
  - Added reduced-motion transition fallbacks and retained tap-only mobile behavior.
- Validation:
  - Added a frontend test confirming preview relationships are combined with, rather than replacing, selected-node relationships.
  - Confirmed keyboard Enter selection opens the existing contributor detail panel in the rendered app.
  - Confirmed desktop graph loading and mobile-width overflow checks remain clean.

Phase 12Q graph detail hierarchy completed on 2026-07-11:

- Outcome for the overall feature: selected-node details read as one calm, structured panel instead of a stack of equally weighted white boxes.
- What changed:
  - Promoted `Explore from here` to the primary action; kept album opening and contributor details as quieter secondary actions.
  - Unified contributor metrics into a single muted, divided stats strip.
  - Grouped connected items in soft-muted list surfaces and gave continuation suggestions a restrained primary tint.
  - Kept the enclosing sidebar card, typography, spacing scale, and existing app color system intact.
- Validation:
  - Targeted frontend lint and tests passed.
  - Production build passed with the existing font-file and bundle-size warnings.
  - Rendered selected-contributor review passed; 390px mobile width has no horizontal overflow.

Phase 12R bounded album-connection search completed on 2026-07-11:

- Outcome for the overall feature: album-to-album discovery remains interactive, but no longer looks hung or incorrectly reports an unfinished search as no connection.
- What changed:
  - Replaced unbounded queue-front traversal with a deque-based search that tracks equivalent traversal state and returns the first credible indirect path.
  - Added a 20-second server-side deadline and additive response metadata for completed versus limited searches, elapsed time, and limit reason.
  - Preserved `no_path` exclusively for completed searches; deadline-limited searches now communicate uncertainty instead.
  - Added elapsed foreground status, longer-than-usual guidance, a cancel control, stale-response protection, and distinct limited-path/limit-reached copy.
- Validation:
  - Credit-intelligence API tests passed, including direct, indirect, completed no-path, and time-limited states.
  - Focused frontend tests, lint, and production build passed.
  - Flower Boy to Hounds of Love returned a three-hop path in approximately 4.9 seconds on the local Jacob library, with a note that alternatives were not fully explored.

Phase 12V bounded alternate-path restoration completed on 2026-07-11:

- Outcome for the overall feature: album-to-album searches once again return a best path plus meaningful alternatives without removing the time safeguard.
- What changed:
  - Continued breadth-first traversal after the first match and capped results at four unique paths: one best path and three alternates.
  - Restored path deduplication by album sequence and contributor sequence, with deterministic final ranking.
  - Returned multiple shared contributors as distinct direct one-hop paths.
  - Replaced the ambiguous `path_found` limited reason with `result_limit`; `time_limit` now preserves any paths confirmed before the deadline.
  - Updated frontend copy for time-limited partial results and result-capped searches.
- Validation:
  - Credit-intelligence API suite passed: 17 tests.
  - Full frontend suite passed: 9 files and 47 tests.
  - Targeted Connections lint and Python compilation passed.
- Representative output:
  - The indirect-path fixture returned four unique paths, with one `best_path`, three `alternate_paths`, and `search_limited_reason=result_limit`.
  - The direct-path fixture returned its second shared contributor as a one-hop alternate.
- Independent testing:
  - Connect two albums with several routes and confirm the path panel reports available alternates.
  - Connect albums with multiple direct shared contributors and confirm the additional contributors are described as direct alternatives.
- Suggested next step:
  - Address production-readiness finding #2 by bounding server work independently of client cancellation and measuring representative large-library concurrency.

Phase 12W bounded server-work hardening completed on 2026-07-11:

- Outcome for the overall feature: album path requests now have deterministic CPU and memory work budgets in addition to a shorter wall-clock failsafe, so abandoned or adversarial searches cannot occupy a worker for the former 20-second window without bounds.
- What changed:
  - Reduced the wall-clock failsafe from 20 seconds to 5 seconds.
  - Added caps for dequeued states, examined edges, queue size, and albums expanded per high-degree contributor.
  - Added deadline and work-budget checks inside the contributor-to-album expansion loop.
  - Extracted graph preparation from traversal and returned graph-build time, states, edges, and maximum queue size as diagnostics.
  - Added precise `state_limit`, `edge_limit`, `queue_limit`, and `expansion_limit` response reasons while preserving confirmed partial paths.
  - Added plain-language frontend explanations for incomplete bounded searches.
- Validation:
  - Credit-intelligence API suite passed: 18 tests, including a forced deterministic state-budget stop.
  - Targeted frontend status tests and lint passed.
  - Python compilation and diff checks passed.
- Representative output:
  - A local Jacob-library request for album IDs 1 and 2 returned two confirmed paths and stopped at `queue_limit` in about 2.0 seconds wall time.
  - Diagnostics reported approximately 0.37 seconds of graph preparation, 196 dequeued states, 28,265 examined edges, and a maximum queue size of 20,000.
- Unresolved issue:
  - An in-process graph cache was intentionally deferred. Credit-fact changes, album presentation metadata, and user-library membership do not currently share a reliable revision token, so a cache could serve stale graph data. The deterministic budgets provide the production safety guarantee independently of client cancellation.
- Independent testing:
  - Run several simultaneous album-pair requests against a large library and confirm each completes or returns a limited partial result within five seconds without degrading health/API requests.
- Suggested next step:
  - Add a durable graph revision/invalidation mechanism before introducing cross-request caching, then benchmark whether the graph-build savings justify its complexity.

Phase 12X Connections component integration coverage completed on 2026-07-11:

- Outcome for the overall feature: the page's critical API and request-lifecycle behavior is now exercised through the real `PageConnections` component rather than only pure helpers and graph-model tests.
- What changed:
  - Added React Testing Library, user-event, jest-dom, and jsdom as development-only test dependencies.
  - Added component integration coverage for initial loading, initial failure, album selection and request arguments, successful results, limited results, cancellation with late-response suppression, retry after failure, and selected-user changes.
  - Added explicit cleanup that aborts an active album-connection request on unmount or user change.
  - Gated recurring-contributor and graph payloads by `user_slug` so old-user data cannot remain visible while the next user's data loads.
- Validation:
  - Full frontend suite passed: 9 files and 52 tests.
  - Targeted PageConnections lint and diff checks passed.
- Unresolved issues:
  - The component suite intentionally mocks the large SVG graph renderer; graph geometry and mobile overflow remain browser-smoke responsibilities.
  - Contributor-detail request cancellation remains a separate lifecycle improvement because it is outside the album-connection production finding addressed here.
- Independent testing:
  - Open `/jacob/connections`, start and cancel an album search, switch profiles if available, and confirm no prior profile's graph flashes during the new load.
- Suggested next step:
  - Add the component integration suite to CI if frontend tests are not already a required check, and retain desktop plus 390px browser smoke coverage for SVG layout.

## Deferred Until Explicitly Approved

Phase 12S progressive-disclosure exploration hierarchy completed on 2026-07-11:

- Outcome for the overall feature: the graph and its stateful explanation panel now read as the primary discovery workspace, while contributor browsing remains available as a quieter restart path.
- What changed:
  - Replaced the always-visible full recurring-contributor card directory with four compact `More starting points` actions and an explicit `Browse all contributors` reveal.
  - Kept directory ranking language tied to connected albums and artist breadth, explicitly excluding listen count.
  - Merged duplicated selected-node description and continuation lists into one actionable list: albums expose `Explore through these contributors`, and contributors expose `Explore these albums`.
  - Limited related-node lists to four entries initially with local `Show more` disclosure.
  - Moved contributor metrics behind an `About this contributor` disclosure while preserving the primary `Explore from here` action and contributor detail sheet.
- Validation:
  - Targeted Connections lint passed.
  - Full frontend suite passed: 9 files and 46 tests.
  - Production build passed with the existing font-file and bundle-size warnings.
- Independent testing:
  - Open `/jacob/connections`, confirm the first view ends with four compact starting points, expand and collapse the contributor directory, and select album and contributor nodes to confirm each sidebar has one non-repeating related-node list.
  - At mobile width, confirm the starting points stack and both disclosure controls remain within the viewport.
- Suggested next step:
  - Perform a rendered interaction review of direct, indirect, limited, and no-path states to decide whether alternate-path copy also benefits from a dedicated disclosure after observing real result density.

Phase 12T contributor-directory navigation feedback completed on 2026-07-11:

- Outcome for the overall feature: choosing a compact contributor now visibly returns the user to the graph that is being rebuilt, instead of updating content above an unchanged viewport.
- What changed:
  - Added a graph-section anchor and smooth return-to-graph behavior to compact contributor selections.
  - Added an explicit accessible `Explore from ...` label to each compact contributor action.
- Validation:
  - Targeted Connections lint passed.
  - Full frontend suite passed: 9 files and 46 tests.
  - Production build passed with the existing font-file and bundle-size warnings.
- Independent testing:
  - Expand `Browse all contributors`, choose a contributor near the bottom of the directory, and confirm the viewport returns to the graph while the focused contributor network loads.

Phase 12U in-place graph refresh status completed on 2026-07-11:

- Outcome for the overall feature: contributor-driven graph refreshes now provide immediate, localized feedback without removing the previous graph or shifting the page.
- What changed:
  - Preserved the current graph during a focused-network request.
  - Added a subtle translucent graph overlay with a compact spinner and `Updating graph…` status.
  - Blocked graph interactions while the replacement network is loading and exposed the request state with `aria-busy` and a polite status announcement.
  - Kept the original standalone loading state for the initial page request, before a graph exists.
- Validation:
  - Targeted Connections lint passed.
  - Full frontend suite passed: 9 files and 46 tests.
  - Production build passed with the existing font-file and bundle-size warnings.
- Independent testing:
  - Choose a contributor from `More starting points` or the expanded directory and confirm the old graph remains visible beneath the status until the focused graph replaces it.

- Unbounded path search or weighted shortest-path optimization beyond the
  bounded MVP.
- Separate `credit_people` and track-level credit tables.
- Full role taxonomy beyond the initial buckets.
- Raw Spotify `ms_played` weighting.
- Ratings/tags as ranking signals.
- Public contributor pages.
- Giant uncontrolled whole-library graph visualization.

These may become useful later, but the app should not pay their complexity cost
until simpler credit insights are proven valuable.

## Decisions Before Implementation

- Is Phase 1A's current stored credit coverage good enough to continue?
- What minimum credit coverage justifies adding a main-nav Connections page?
- Which raw roles should be included in the first public recurrence ranking?
- Is a one-table `album_credit_facts` projection enough for the first two
  insights?
- Before frontend implementation, should person detail be a route, sheet, or
  panel inside the Connections page?

Resolved now:

- Use MBID identity when available, normalized-name fallback for audit and
  provisional insights, and explicit `identity_resolution` in projected data.
- Do not require MBIDs for every public insight, but filter or down-rank
  unresolved ambiguous names.
- Do not refresh the full catalog initially. Audit stored data first, then
  selectively refresh a representative sample.
- Exclude primary artists from default recurring and hidden-connector sections.
- Use role-aware meaningful-credit rules instead of one universal track-share
  threshold.
- Exclude compilations from default rankings initially; flag live albums and
  soundtracks for review.
- Use only `all` and `1y` listening ranges for the MVP.
- Leave ratings out of MVP scoring.
- Use explicit rebuild/update logic before trying to synchronously maintain
  projections during every metadata refresh.

## Recommended Next Step

Implement Phase 12A next, then validate the rendered page before continuing to
12B or 12C. The feature now has direct and bounded indirect album paths, so the
highest-leverage next work is reducing competing entry controls and making the
active graph state unmistakable. After that, improve graph legibility and then
the continuation loop.
