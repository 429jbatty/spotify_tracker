"""Canonical identity helpers for persisted album entities.

Raw events deliberately keep their source text.  These helpers are only for
the shared album row that derived listens attach to.
"""

from unidecode import unidecode


def normalize_album_text(value: str | None) -> str:
    """Return a punctuation- and case-insensitive identity component."""
    text = unidecode(str(value or "").casefold())
    return "".join(character for character in text if character.isalnum())


def normalized_artist_title_identity(artist: str | None, name: str | None) -> str:
    """Return the exact normalized fallback identity for an album."""
    return f"{normalize_album_text(artist)}\x1f{normalize_album_text(name)}"


def release_group_identity(value: str | None) -> str | None:
    normalized = str(value or "").strip().casefold()
    return normalized or None
