from collections.abc import Iterable


USER_TAG_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "sound_traits": (
        ("atmospheric", "Atmospheric"),
        ("punchy", "Punchy"),
        ("lush", "Lush"),
        ("raw", "Raw"),
        ("hazy", "Hazy"),
        ("sleek", "Sleek"),
        ("layered", "Layered"),
        ("groove-heavy", "Groove-heavy"),
        ("sparse", "Sparse"),
        ("noisy", "Noisy"),
    ),
    "emotional_tone": (
        ("melancholic", "Melancholic"),
        ("nostalgic", "Nostalgic"),
        ("euphoric", "Euphoric"),
        ("tense", "Tense"),
        ("reflective", "Reflective"),
        ("bittersweet", "Bittersweet"),
        ("playful", "Playful"),
        ("romantic", "Romantic"),
        ("defiant", "Defiant"),
        ("lonely", "Lonely"),
        ("hopeful", "Hopeful"),
    ),
    "album_qualities": (
        ("cohesive", "Cohesive"),
        ("addictive", "Addictive"),
        ("ambitious", "Ambitious"),
        ("polished", "Polished"),
        ("experimental", "Experimental"),
        ("accessible", "Accessible"),
        ("rewarding", "Rewarding"),
        ("timeless", "Timeless"),
        ("uneven", "Uneven"),
        ("distinctive", "Distinctive"),
    ),
}

ALLOWED_USER_TAGS = {
    tag_id
    for tags in USER_TAG_GROUPS.values()
    for tag_id, _label in tags
}


def normalize_user_tags(values: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_value in values or []:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        if value not in ALLOWED_USER_TAGS:
            raise ValueError(f"Unsupported user tag: {value}")
        seen.add(value)
        normalized.append(value)

    return normalized
