# Album Deduplication Script

Use `one_time_scripts/_dedupe_albums.py` to find and safely merge duplicate
album records in the SQLite database.

The script is conservative by default. Running it with no flags only reports
candidate duplicate groups and does not mutate the database.

## Basic Usage

From the repo root:

```bash
./.venv/bin/python one_time_scripts/_dedupe_albums.py
```

Against an explicit database:

```bash
./.venv/bin/python one_time_scripts/_dedupe_albums.py \
  --database-url sqlite:///data/spotify_tracker.sqlite
```

Apply safe merges:

```bash
./.venv/bin/python one_time_scripts/_dedupe_albums.py --apply
```

Refresh candidate metadata before reporting or applying:

```bash
./.venv/bin/python one_time_scripts/_dedupe_albums.py --refresh-candidates
```

Refresh candidates and then apply safe merges:

```bash
./.venv/bin/python one_time_scripts/_dedupe_albums.py \
  --refresh-candidates \
  --apply
```

## What The Report Means

The first line summarizes how many duplicate groups were found and how many are
safe for automatic apply:

```text
Duplicate groups: 3 (2 safe to apply)
```

Each group is marked as either:

- `[safe]`: eligible for `--apply`
- `[review]`: reported only; never merged automatically

Each album row includes:

- `id`: database album ID, useful for manual inspection
- `-> target`: the album that safe merges will keep
- artist and album title
- `rg`: release-group MBID when present
- `listens`: listen-row count across users
- `users`: user membership count
- `source`: album metadata source

## Safe Merge Rules

`--apply` only merges groups when the duplicate reason is one of:

- `same_release_group_mbid`: albums share the same non-null MusicBrainz
  release-group MBID.
- `exact_normalized_artist_album`: albums normalize to the exact same
  artist/title identity.

The target album is chosen by preferring:

1. albums with a MusicBrainz release-group MBID
2. albums whose source is `musicbrainz`
3. higher listen count
4. higher user membership count
5. lower album ID as a stable tiebreaker

Merging uses `SqliteStateRepository.merge_completed_album_listens(...)`, which
preserves listen history and user album membership data. Source albums are
deleted after their listens and user data are moved.

## Review-Only Matches

Near matches are reported with reason `near_normalized_artist_album` and a
similarity score. These are intentionally review-only because they can include
legitimate separate albums, artist aliases, deluxe editions, live releases, or
other cases that need human judgment.

Near-match reporting is intentionally narrow. A pair is only reported when:

- the artist names are highly similar
- the album titles are highly similar
- the albums do not both have different non-null MusicBrainz release-group MBIDs

This keeps the report focused on likely duplicate rows such as artist alias
variants, punctuation differences, or near-identical titles. It should not report
separate albums by the same artist merely because they share the artist name or
belong to the same series.

To resolve a review-only group, inspect the album IDs in the app's Data Quality
view or database, then use the existing manual merge flow if the records are
really duplicates.

## Refresh Candidates

`--refresh-candidates` attempts metadata refresh for every album currently in a
reported duplicate group, then recomputes the report.

This is useful when duplicates do not currently share a canonical key but would
collapse after MusicBrainz metadata refresh.

Refresh uses the same metadata refresh service and low-confidence safeguards as
the app. If refresh returns low-confidence metadata, the script reports a
skipped action and leaves that album unchanged.

## Recommended Production Workflow

1. Back up the production SQLite database.
2. Run a dry report:

   ```bash
   ./.venv/bin/python one_time_scripts/_dedupe_albums.py \
     --database-url sqlite:///path/to/production.sqlite
   ```

3. Review every `[safe]` group and spot-check a few `[review]` groups.
4. Optionally run refresh-only first:

   ```bash
   ./.venv/bin/python one_time_scripts/_dedupe_albums.py \
     --database-url sqlite:///path/to/production.sqlite \
     --refresh-candidates
   ```

5. Apply only safe merges:

   ```bash
   ./.venv/bin/python one_time_scripts/_dedupe_albums.py \
     --database-url sqlite:///path/to/production.sqlite \
     --apply
   ```

6. Re-run the dry report to confirm remaining groups are review-only or expected.

## Important Limits

- The script does not automatically merge near matches.
- The script does not use live review UI state.
- `--refresh-candidates` can make MusicBrainz API calls and should be run
  deliberately.
- If production data has stale or incorrect MusicBrainz IDs, review the dry-run
  output before applying.
