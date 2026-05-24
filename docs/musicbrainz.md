# MusicBrainz Metadata

Album metadata and artwork are retrieved from MusicBrainz and the Cover Art
Archive. The frontend should not call MusicBrainz directly.

This document describes how lookup works today. It is intentionally descriptive,
not aspirational: if the current behavior is flawed, that flaw is documented
here so future changes can target it directly.

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

## MusicBrainz Terms Used By This App

MusicBrainz's model is more precise than the word "album." The app has to map
that model into a single album record.

| Term | MusicBrainz meaning | How this app uses it |
| --- | --- | --- |
| `MBID` | A stable MusicBrainz identifier for an entity. | Stored as `artist_mbid`, `release_group_mbid`, `release_mbid`, and `recording_mbid`. |
| `Artist` | A person, group, orchestra, fictional artist, or other credited creator/performer. | Used for artist search and canonical album artist. |
| `Artist credit` | The credited display name for an entity, possibly including multiple artists and join phrases. | The app reads the first release-group artist credit and stores its display name as canonical `artist`. |
| `Release group` | The abstract concept of an album/single/EP across editions. | The app searches release groups first and stores the selected release-group MBID as the shared album identity from MusicBrainz. |
| `Primary type` | Release-group type such as `Album`, `Single`, `EP`, `Broadcast`, or `Other`. | Last.fm import only derives new album listens from MusicBrainz metadata when `primary_type == "Album"`. |
| `Secondary type` | Extra release-group classification such as `Compilation`, `Soundtrack`, `Live`, `Remix`, etc. | Currently stored but not strongly used in ranking. This is a known weakness for import matching. |
| `Release` | A concrete issued product/version: country, date, barcode, label, media format, packaging, cover art, and tracklist can differ. | The app chooses one release inside the selected release group to get release MBID, label, cover art, media, recordings, and tracklist. |
| `Status` | How official a release is, e.g. `Official`, `Promotion`, `Bootleg`, `Pseudo-Release`. | The client browses official releases for a release group and the normal metadata path prefers official summaries. |
| `Medium` | A disc, digital medium, vinyl side grouping, or similar container inside a release. | The app walks each release medium to build one flattened album `tracklist`. |
| `Track` | A position/title on a medium. A track points to a recording. | The app stores track position and title in album metadata. |
| `Recording` | A distinct audio recording that may appear as tracks on multiple releases. | The app stores `recording_mbid` per track and reads recording-level artist relationships for credits. |
| `Work` | The underlying composition/song that recordings can perform. | The app follows recording-to-work relationships to pull work-level artist credits such as composers. |
| `Relationship` | A typed link between MusicBrainz entities, optionally with attributes. | The app reads artist relationships from recordings and works into per-track credit tuples. |
| `Cover Art Archive` | The image service linked to MusicBrainz releases and release groups. | The app first asks for release cover art, then falls back to release-group cover art. |

The most important distinction is release group vs release. A release group is
the concept, like "Purple Rain." A release is one concrete edition of that
concept, such as a US LP, a CD reissue, a digital edition, or a deluxe edition.
The app searches release groups to identify the concept, then chooses a release
because tracklists and labels live at release level.

## Low-Level API Wrapper

`musicbrainz_client.py` wraps `musicbrainzngs` and centralizes network behavior:

- Sets a MusicBrainz user agent.
- Applies a process-wide socket timeout of 20 seconds.
- Serializes calls through a lock and waits about 1.1 seconds between requests.
- Retries most wrapped MusicBrainz calls up to 5 times on
  `musicbrainzngs.NetworkError`.
- Uses MusicBrainz JSON-like dictionaries returned by `musicbrainzngs`.

The wrapper methods used by album lookup are:

| Wrapper | MusicBrainz operation | Important request details |
| --- | --- | --- |
| `search_release_groups(artist, album)` | Search release groups. | Uses `releasegroup=album`, `artist=artist`, `limit=10`. |
| `get_release_group_by_id(release_group_mbid)` | Lookup one release group. | Includes `artist-credits`, `tags`, and `url-rels`. |
| `get_releases_for_group(release_group_mbid)` | Browse releases in a release group. | Includes `artist-credits`, `labels`, and `media`; asks for official releases; limit 100. |
| `get_release_by_id(release_id)` | Lookup one full release. | Includes recordings, labels, tags, artist credits, release relationships, release-group relationships, work relationships, URL relationships, and recording-level relationships. |
| `get_cover_art_url(release_mbid, release_group_mbid)` | Cover Art Archive lookup. | Tries release images first, then release-group images. |
| `search_release_by_spotify_url(spotify_url)` | Search releases by linked URL. | Uses a release search query shaped as `url:"<spotify_url>"`. |

## Public Metadata Entry Points

There are two album metadata entry points in `album_metadata_service.py`.

### `get_album_metadata(artist, album, spotify_url=None)`

This is the full enrichment path used by normal metadata refresh and album
creation paths. It tries to return an album record with canonical artist/title,
MusicBrainz IDs, release date, label, tracklist, tags, genres, and cover art.

Internally it calls `_resolve_release(...)`, then `_build_album_record(...)`.

### `get_album_metadata_for_import_matching(artist, album)`

This is a lighter Last.fm import matching path. It returns the same album-record
shape but skips cover art lookup and uses a cheaper release selection path. The
importer mainly needs `primary_type` and `tracklist` to decide whether a
candidate Last.fm session is a completed album listen.

Because this path writes into `album_metadata_cache`, a bad or empty result can
become a persistent negative cache hit for later imports.

## Full Lookup Flow: `get_album_metadata`

`get_album_metadata` has two possible lookup paths.

### Path A: Spotify URL

When a Spotify album URL is available:

1. `search_release_by_spotify_url(spotify_url)` searches MusicBrainz releases
   for a URL relationship matching that Spotify URL.
2. If a release is found, the code reads the release's embedded
   `release-group`.
3. `get_release_group_by_id(release_group["id"])` reloads the release group
   with artist credits, tags, and URL relationships.
4. `get_release_by_id(release["id"])` loads the full release, including media,
   tracks, recordings, labels, tags, and relationship data.
5. `_safe_cover_art_url(release["id"], release_group["id"])` gets release
   cover art or falls back to release-group cover art.
6. `_build_album_record(...)` converts the selected MusicBrainz entities into
   the app's album metadata shape.

If this path finds a release, artist/album search is skipped.

### Path B: Artist/Album Search

When there is no Spotify URL match:

1. `search_release_groups(artist, album)` asks MusicBrainz for up to 10 release
   groups matching the supplied artist and album strings.
2. `choose_best_release_group(candidates, artist, album)` scores each release
   group locally.
3. If no candidate passes the local threshold, lookup returns `{}`.
4. `get_release_group_by_id(best_release_group["id"])` reloads the selected
   release group with richer fields.
5. `get_releases_for_group(best_release_group["id"])` browses releases inside
   the selected group.
6. The full path filters release summaries to `Official` status when any
   official summaries exist.
7. For every remaining release summary, the app calls:
   - `get_release_by_id(release_summary["id"])`
   - `_safe_cover_art_url(full_release["id"], best_release_group["id"])`
8. `_choose_best_enriched_release(...)` scores the full releases and picks one.
9. `_build_album_record(...)` converts the selected release group and release
   into the app's album metadata shape.

## Release Group Scoring Today

`compute_match_score(candidate, artist, album)` normalizes the input and
candidate values, then computes:

- artist score: fuzzy token-set ratio of candidate artist credit vs input
  artist
- album score: fuzzy token-set ratio of candidate release-group title vs input
  album
- final score: `album_score * 0.8 + artist_score * 0.2`

`choose_best_release_group(...)` then:

1. Scores all candidates.
2. Drops candidates below a threshold of 75.
3. Applies a type priority:
   - `Album` = 2
   - `EP` = 1
   - everything else = 0
4. Sorts by type priority first, then local fuzzy score.
5. Returns the first candidate.

Current implications:

- MusicBrainz's own search score is not used after the raw candidate list is
  returned.
- `secondary-type-list` is not considered.
- Token-set matching can over-score subset titles. For example, a title like
  `Purple Rain Debut` can score as well as `Purple Rain` because the requested
  tokens are a subset of the candidate title.
- A live album, compilation, remix, or soundtrack can outrank a plain studio
  album if local fuzzy/type scoring makes it look better.
- The code only chooses one release group. If that group cannot produce a
  usable release or tracklist, the current full path returns no metadata instead
  of trying the next high-confidence release-group candidate.

## Release Selection Today

There are two release selection functions.

### `choose_best_release(...)`

This cheaper path is used by `get_album_metadata_for_import_matching`.

It receives release summaries from `get_releases_for_group(...)`, then:

1. Keeps releases whose `status` is `Official`, falling back to all releases if
   none are official.
2. Keeps summaries whose release title exactly equals the selected release-group
   title, falling back to all official summaries if none match exactly.
3. Splits summaries by medium format:
   - any format containing `digital` goes into `digital`
   - everything else goes into `physical`
4. Prefers digital summaries if any exist; otherwise uses physical summaries.
5. Sorts by release `date`, earliest first.
6. If multiple releases share that earliest date, prefers country `US`.
7. Returns the selected release summary.

Known limitation: this path only has summary data. It does not inspect full
tracklists, cover art, labels, or relationship richness before choosing.

### `_choose_best_enriched_release(...)`

This fuller path is used by `get_album_metadata`.

It receives full releases plus cover art URLs and scores each option:

- `+40` exact normalized release title match to the release-group title
- `+20` official status on full release or summary
- `+30` cover art present
- `+10` label info present
- `+8` release date present
- `+18` track count equals the most common positive track count among
  candidates
- small penalty when track count exceeds the preferred track count
- `+4` digital media format
- `+3` CD media format
- `+2` country is `US`, `GB`, or `XW`
- up to `+20` for relationship count

It sorts by descending score, then by earliest release date.

## Album Record Construction

`_build_album_record(release_group, release, image_url)` maps MusicBrainz data
to the app's album record.

The record fields are:

| App field | Source |
| --- | --- |
| `artist` | First release-group artist credit display name. |
| `artist_mbid` | First release-group artist credit artist ID. |
| `name` | Release-group title. |
| `primary_type` | Release-group primary type. |
| `secondary_types` | Release-group secondary type list. |
| `release_group_mbid` | Release-group ID. |
| `release_mbid` | Selected release ID. |
| `label` | First label name from selected release label info. |
| `release_year`, `release_month`, `release_day` | Split from release-group first release date. |
| `tracklist` | Flattened tracks from all selected release media. |
| `genres` | Release-group genre list. |
| `tags` | Release-group tag list. |
| `image_url` | Cover Art Archive URL, or `None` in import-matching path. |
| `source` | Always `musicbrainz`. |

Tracklist rows are built by `_extract_tracks_and_credits(release)`:

- Iterate each medium in `release["medium-list"]`.
- Iterate each medium's `track-list`.
- Store `position`.
- Store track title from `track["title"]`, falling back to
  `track["recording"]["title"]`.
- Store `recording_mbid` from the linked recording.
- Store credits extracted from recording-level and work-level relationships.

Credits are currently tuples shaped as `(artist_name, credit_type, attributes)`.
Recording-level artist relationships are used directly. Work-level artist
relationships are prefixed with `work `, for example `work composer`.

## Cover Art Lookup

Cover art lookup lives in `musicbrainz_client.py` and uses the Cover Art
Archive through `musicbrainzngs`:

1. `get_cover_art_url(release_mbid, release_group_mbid)` first asks for images
   attached to the selected release.
2. If no release image exists and a release-group MBID is available, it asks for
   release-group images.
3. `_front_cover_url_from_images(...)` prefers approved front images, then any
   front image, then any image.
4. It chooses the largest useful thumbnail in this order: `1200`, `500`,
   `large`, then the original image URL.
5. URLs are normalized from `http://` to `https://`.
6. Cover art `ResponseError` returns `None`; `NetworkError` is caught in
   `album_metadata_service._safe_cover_art_url(...)` so metadata refresh can
   continue without artwork.

## Last.fm Import Metadata Cache

Last.fm import does not call MusicBrainz for every raw scrobble. The import
service first persists raw events, groups candidate album sessions, checks
existing user albums, then checks `album_metadata_cache`.

For MusicBrainz-backed import matching:

1. The cache key is based on normalized `artist` and `album`.
2. `status = "matched"` stores the metadata JSON returned by
   `get_album_metadata_for_import_matching(...)`.
3. `status = "not_found"` stores a negative lookup.
4. Negative cache hits return `None`; they are not retried in the same import
   path.
5. Candidates with fewer than `LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS`
   unique tracks skip remote lookup.
6. Candidates with a tracklist are judged by unique scrobbled track coverage
   against the MusicBrainz tracklist.

This is why a bad release-group choice can persist as confusing review state:
if the wrong release group cannot produce a usable release/tracklist, the app
may write `not_found` for the artist/album pair and future imports will not
retry until the cache/import rows are cleared or reprocessed.

## Current Failure Modes To Understand Before Fixing

- **Subset title overmatch:** token-set fuzzy scoring can treat `Purple Rain
  Debut` as a perfect title match for `Purple Rain`.
- **Secondary types ignored:** `Live`, `Compilation`, `Soundtrack`, and
  `Remix` are stored but not strongly considered during release-group ranking.
- **MusicBrainz score ignored after search:** the API search result score is not
  part of local sorting.
- **No fallback release-group attempt:** after selecting one release group, the
  lookup does not try the next candidate if release browsing or full release
  lookup fails.
- **Import path chooses releases cheaply:** `get_album_metadata_for_import_matching`
  uses `choose_best_release(...)`, which does not inspect full tracklist quality
  before choosing a release summary.
- **Canonical metadata can differ from source text:** `_build_album_record`
  stores the MusicBrainz release-group title and first artist credit, not the
  imported/entered strings.
- **Negative cache can outlive code fixes:** after matcher changes, affected
  `album_metadata_cache` rows may need to be cleared for retesting.

## Source Notes

Official MusicBrainz docs that define the terms used above:

- MusicBrainz terminology: https://musicbrainz.org/doc/Terminology
- Release groups: https://musicbrainz.org/doc/Release_Group
- Releases, media, and tracklists: https://musicbrainz.org/doc/Release
- Artist credits: https://musicbrainz.org/doc/Artist_Credits
- MusicBrainz API: https://musicbrainz.org/doc/MusicBrainz_API
- MusicBrainz API search fields: https://musicbrainz.org/doc/MusicBrainz_API/Search

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
