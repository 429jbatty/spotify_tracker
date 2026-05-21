# MusicBrainz Metadata

Album metadata and artwork are retrieved from MusicBrainz and the Cover Art
Archive. The frontend should not call MusicBrainz directly.

## Main Modules

- `musicbrainz_client.py`: low-level MusicBrainz API calls, user agent, rate
  limiting, retries, release-group search, release lookup, cover art lookup,
  and Spotify URL search.
- `album_metadata_service.py`: normalization, fuzzy matching, release-group
  selection, release selection, tracklist/credit extraction, and album-record
  shaping.
- `metadata_refresh_service.py`: refresh orchestration that updates stored
  metadata while preserving listen history and user data.
- `backend/app/services/artwork_cache_service.py`: downloads remote artwork
  into local media storage and records `local_image_path`.

## Lookup Flow

Metadata lookup prefers a Spotify URL when one is supplied. Otherwise it:

1. Searches MusicBrainz release groups by artist and album.
2. Scores candidates with normalized artist/title fuzzy matching.
3. Prefers album release groups over EPs and lower-priority types.
4. Loads candidate releases for the chosen group.
5. Chooses a release using status, title match, artwork, label/date presence,
   track count, media format, country, and relationship richness.
6. Builds the album record used by SQLite and API responses.

## Stored Fields

The album record may include canonical artist/title, artist MBID,
release-group MBID, release MBID, label, release date parts, tracklist,
genres, tags, remote artwork URL, local artwork path, and source.

`albums.metadata_json` stores additional metadata while first-class columns
hold fields needed for lookup, display, and filtering.

## Failure Behavior

- A failed MusicBrainz match should return an empty metadata record or a clear
  service-level error, depending on the caller.
- Cover art lookup failure should not prevent metadata refresh.
- Refresh logic must preserve listen history, user tags, ratings, notes, and
  useful existing artwork fields when refreshed values are missing.
- Unit tests should mock MusicBrainz and Cover Art Archive calls.

## Operational Notes

Use `make refresh-metadata` for targeted refreshes configured in
`one_time_scripts/_refresh_metadata.py`. Keep broad refreshes deliberate because
MusicBrainz is rate-limited and external metadata can change canonical album
identity.
