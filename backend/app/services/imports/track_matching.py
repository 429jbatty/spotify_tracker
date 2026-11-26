"""Track evidence from names, Spotify identities and combined MusicBrainz titles."""

import re

from backend.app.services.import_parsers import clean_text


def normalize_track_name(value):
    return re.sub(r"[^a-z0-9]+", " ", (clean_text(value) or "").casefold()).strip()


def track_identity(event):
    uri = clean_text(event.raw_payload.get("_spotify_track_uri"))
    return uri.casefold() if uri else normalize_track_name(event.track)


def compare_tracklist(tracklist, played_names):
    expected, partial = set(), []
    matched = 0
    for track in tracklist:
        title = clean_text(track.get("title"))
        name = normalize_track_name(title)
        if not name:
            continue
        expected.add(name)
        if name in played_names:
            matched += 1
            continue
        if " / " in title:
            parts = [normalize_track_name(part) for part in title.split(" / ")]
            parts = [part for part in parts if part]
            if len(parts) > 1:
                if all(part in played_names for part in parts):
                    matched += 1
                elif any(part in played_names for part in parts):
                    partial.append(title)
    return matched, len(expected), partial
