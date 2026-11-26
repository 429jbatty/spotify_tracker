from datetime import datetime, timedelta, timezone

from backend.app.database.repositories.public_activity_repository import PublicActivityRepository, PublicListen


ARTWORK_URL_PREFIX = "/media/artwork/"
SPLASH_RECENT_ACTIVITY_LIMIT = 20
PUBLIC_DISPLAY_NAME_OVERRIDES = {
    "test": "Jacob",
    "smoke test": "Demo Listener",
    "smoke-test": "Demo Listener",
    "emily spotify": "Emily",
    "emily-spotify": "Emily",
}


def splash_payload(
    repository: PublicActivityRepository,
    *,
    featured_limit: int = 6,
    activity_limit: int = SPLASH_RECENT_ACTIVITY_LIMIT,
) -> dict:
    users = _featured_users(repository, limit=featured_limit)
    return {
        "featured_users": users,
        "recent_activity": recent_activity(repository, limit=activity_limit),
    }


def recent_listened_albums(repository: PublicActivityRepository, limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(limit, 10))
    rows = repository.recent_listens(bounded_limit)

    return [_public_album_payload(row) for row in rows]


def _public_album_payload(row: PublicListen) -> dict:
    return {
        "listen_id": row.listen_id,
        "listener_display_name": row.display_name,
        "listened_at": row.listened_at,
        "album_id": row.album_id,
        "album_key": row.album_key,
        "artist": row.artist,
        "name": row.name,
        "image_url": _display_image_url(row.image_url, row.local_image_path),
    }


def recent_activity(
    repository: PublicActivityRepository,
    limit: int = SPLASH_RECENT_ACTIVITY_LIMIT,
) -> list[dict]:
    bounded_limit = max(1, min(limit, SPLASH_RECENT_ACTIVITY_LIMIT))
    rows = repository.recent_activity(bounded_limit)

    return [_recent_listen_activity_payload(row) for row in rows]


def _featured_users(repository: PublicActivityRepository, limit: int) -> list[dict]:
    bounded_limit = max(1, min(limit, 12))
    rows = repository.featured_users(bounded_limit)

    payloads = []
    for user in rows:
        replay_rate_30d, most_replayed = _replay_metrics(repository.profile_listens(user.id))
        top_artist = _top_artist_metric(repository, user.id)
        payloads.append({
            "slug": user.slug,
            "display_name": user.display_name,
            "public_display_name": _public_display_name(user.slug, user.display_name),
            "profile_url": f"/{user.slug}",
            "recent_album_covers": _recent_album_covers(repository, user.id),
            "total_albums": int(user.total_albums or 0),
            "total_listens": int(user.total_listens or 0),
            "replay_rate_30d": replay_rate_30d,
            "top_artist": top_artist["name"] if top_artist else None,
            "top_artist_listen_count": top_artist["listen_count"] if top_artist else None,
            "top_album": _top_album_metric(repository, user.id),
            "most_listened_era": _most_listened_era(repository, user.id),
            "most_replayed_recently": most_replayed,
            "last_updated": user.last_updated,
        })
    return payloads


def _recent_album_covers(repository: PublicActivityRepository, user_id: int, limit: int = 5) -> list[str]:
    rows = repository.recent_album_covers(user_id, max(1, min(limit, 8)))
    covers = []
    seen_album_ids = set()
    for album_id, image_url, local_image_path in rows:
        if album_id in seen_album_ids:
            continue
        seen_album_ids.add(album_id)
        display_image_url = _display_image_url(image_url, local_image_path)
        if display_image_url:
            covers.append(display_image_url)
    return covers


def _top_artist_metric(repository: PublicActivityRepository, user_id: int) -> dict | None:
    row = repository.top_artist(user_id)
    if not row:
        return None
    artist, listen_count, _latest_listen = row
    return {"name": artist, "listen_count": int(listen_count or 0)}


def _top_album_metric(repository: PublicActivityRepository, user_id: int) -> dict | None:
    row = repository.top_album(user_id)
    if not row:
        return None
    title, artist, listen_count, _latest_listen = row
    return {
        "title": title,
        "artist": artist,
        "listen_count": int(listen_count or 0),
    }


def _most_listened_era(repository: PublicActivityRepository, user_id: int) -> dict | None:
    rows = repository.listened_release_years(user_id)
    if not rows:
        return None

    decades = {}
    for release_year, listen_count, latest_listen in rows:
        decade = int(release_year) // 10 * 10
        current = decades.setdefault(
            decade,
            {"label": f"{decade}s", "listen_count": 0, "_latest_listen": None},
        )
        current["listen_count"] += int(listen_count or 0)
        if (
            current["_latest_listen"] is None
            or (latest_listen is not None and latest_listen > current["_latest_listen"])
        ):
            current["_latest_listen"] = latest_listen

    top_decade = max(
        decades.items(),
        key=lambda item: (
            item[1]["listen_count"],
            item[1]["_latest_listen"] or "",
            item[0],
        ),
    )[1]
    return {
        "label": top_decade["label"],
        "listen_count": top_decade["listen_count"],
    }


def _replay_metrics(
    rows: list[tuple[int, str, str, str]],
) -> tuple[float | None, dict | None]:
    """Compute both splash replay metrics from one profile's ordered listens."""
    if not rows:
        return None, None

    albums: dict[tuple[int, str, str], list[datetime]] = {}
    for album_id, title, artist, listened_at in rows:
        dates = albums.setdefault((album_id, title, artist), [])
        parsed = _parse_datetime(listened_at)
        if parsed is not None:
            dates.append(parsed)

    replayed = sum(
        any(0 <= (current - previous).days <= 30 for previous, current in zip(dates, dates[1:]))
        for dates in albums.values()
    )
    rate = round(replayed / len(albums), 2)
    latest = max((date for dates in albums.values() for date in dates), default=None)
    if latest is None:
        return rate, None

    window_start = latest - timedelta(days=30)
    best_rank = None
    most_replayed = None
    for (_, title, artist), dates in albums.items():
        recent = [date for date in dates if date >= window_start]
        if len(recent) < 2:
            continue
        rank = (len(recent) - 1, max(recent), title)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            most_replayed = {
                "title": title, "artist": artist, "replay_count": len(recent) - 1, "window_days": 30,
            }
    return rate, most_replayed


def _recent_listen_activity_payload(row: PublicListen) -> dict:
    public_name = _public_display_name(row.slug, row.display_name)
    return {
        "listen_id": row.listen_id,
        "type": "listen",
        "user_display_name": row.display_name,
        "public_user_display_name": public_name,
        "album_title": row.name,
        "artist_name": row.artist,
        "album_cover_url": _display_image_url(row.image_url, row.local_image_path),
        "text": f"{public_name} listened to {row.name}.",
        "timestamp": row.listened_at,
        "profile_url": f"/{row.slug}",
    }


def _display_image_url(
    image_url: str | None,
    local_image_path: str | None,
) -> str | None:
    if local_image_path:
        filename = local_image_path.removeprefix("artwork/").lstrip("/")
        return f"{ARTWORK_URL_PREFIX}{filename}"
    return image_url


def _public_display_name(slug: str, display_name: str) -> str:
    for value in (slug, display_name):
        normalized = (value or "").strip().lower()
        if normalized in PUBLIC_DISPLAY_NAME_OVERRIDES:
            return PUBLIC_DISPLAY_NAME_OVERRIDES[normalized]
    return display_name


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
