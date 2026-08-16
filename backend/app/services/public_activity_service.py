from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumListen, User, UserAlbum


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
    session: Session,
    *,
    featured_limit: int = 6,
    activity_limit: int = SPLASH_RECENT_ACTIVITY_LIMIT,
) -> dict:
    users = _featured_users(session, limit=featured_limit)
    return {
        "featured_users": users,
        "recent_activity": recent_activity(session, limit=activity_limit),
    }


def recent_listened_albums(session: Session, limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(limit, 10))
    rows = session.execute(
        select(
            AlbumListen,
            Album.id,
            Album.album_key,
            Album.artist,
            Album.name,
            Album.image_url,
            Album.local_image_path,
            User,
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .join(User, User.id == AlbumListen.user_id)
        .where(User.is_active.is_(True))
        .order_by(AlbumListen.listened_at.desc(), AlbumListen.id.desc())
        .limit(bounded_limit)
    )

    return [
        _public_album_payload(
            listen,
            album_id=album_id,
            album_key=album_key,
            artist=artist,
            name=name,
            image_url=image_url,
            local_image_path=local_image_path,
            user=user,
        )
        for (
            listen,
            album_id,
            album_key,
            artist,
            name,
            image_url,
            local_image_path,
            user,
        ) in rows
    ]


def _public_album_payload(
    listen: AlbumListen,
    *,
    album_id: int,
    album_key: str,
    artist: str,
    name: str,
    image_url: str | None,
    local_image_path: str | None,
    user: User,
) -> dict:
    return {
        "listen_id": listen.id,
        "listener_display_name": user.display_name,
        "listened_at": listen.listened_at,
        "album_id": album_id,
        "album_key": album_key,
        "artist": artist,
        "name": name,
        "image_url": _display_image_url(image_url, local_image_path),
    }


def recent_activity(
    session: Session,
    limit: int = SPLASH_RECENT_ACTIVITY_LIMIT,
) -> list[dict]:
    bounded_limit = max(1, min(limit, SPLASH_RECENT_ACTIVITY_LIMIT))
    rows = session.execute(
        select(
            AlbumListen,
            Album.artist,
            Album.name,
            Album.image_url,
            Album.local_image_path,
            User,
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .join(User, User.id == AlbumListen.user_id)
        .where(User.is_active.is_(True))
        .order_by(func.julianday(AlbumListen.listened_at).desc(), AlbumListen.id.desc())
        .limit(bounded_limit)
    )

    return [
        _recent_listen_activity_payload(
            listen,
            artist=artist,
            name=name,
            image_url=image_url,
            local_image_path=local_image_path,
            user=user,
        )
        for listen, artist, name, image_url, local_image_path, user in rows
    ]


def _featured_users(session: Session, limit: int) -> list[dict]:
    bounded_limit = max(1, min(limit, 12))
    rows = session.execute(
        select(
            User,
            func.count(distinct(UserAlbum.album_id)).label("total_albums"),
            func.count(distinct(AlbumListen.id)).label("total_listens"),
            func.max(AlbumListen.listened_at).label("last_updated"),
        )
        .select_from(User)
        .outerjoin(UserAlbum, UserAlbum.user_id == User.id)
        .outerjoin(AlbumListen, AlbumListen.user_id == User.id)
        .where(User.is_active.is_(True))
        .group_by(User.id)
        .having(func.count(distinct(UserAlbum.album_id)) > 0)
        .order_by(func.max(AlbumListen.listened_at).desc().nullslast(), User.id.asc())
        .limit(bounded_limit)
    )

    payloads = []
    for user, total_albums, total_listens, last_updated in rows:
        total_album_count = int(total_albums or 0)
        total_listen_count = int(total_listens or 0)
        replay_rate_30d = _user_replay_rate_30d(session, user.id)
        top_artist = _top_artist_metric(session, user.id)
        payloads.append({
            "slug": user.slug,
            "display_name": user.display_name,
            "public_display_name": _public_display_name(user),
            "profile_url": f"/{user.slug}",
            "recent_album_covers": _recent_album_covers(session, user.id),
            "total_albums": total_album_count,
            "total_listens": total_listen_count,
            "replay_rate_30d": replay_rate_30d,
            "top_artist": top_artist["name"] if top_artist else None,
            "top_artist_listen_count": top_artist["listen_count"] if top_artist else None,
            "top_album": _top_album_metric(session, user.id),
            "most_listened_era": _most_listened_era(session, user.id),
            "most_replayed_recently": _most_replayed_recently(session, user.id),
            "last_updated": last_updated,
        })
    return payloads


def _recent_album_covers(session: Session, user_id: int, limit: int = 5) -> list[str]:
    rows = session.execute(
        select(Album.id, Album.image_url, Album.local_image_path)
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .where(AlbumListen.user_id == user_id)
        .order_by(AlbumListen.listened_at.desc(), AlbumListen.id.desc())
        .limit(max(1, min(limit, 8)))
    )
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


def _user_replay_rate_30d(session: Session, user_id: int) -> float | None:
    listen_rows = session.execute(
        select(AlbumListen.album_id, AlbumListen.listened_at)
        .where(AlbumListen.user_id == user_id)
        .order_by(AlbumListen.album_id.asc(), AlbumListen.listened_at.asc())
    ).all()
    listens_by_album = {}
    for album_id, listened_at in listen_rows:
        listens_by_album.setdefault(album_id, []).append(listened_at)

    if not listens_by_album:
        return None

    replayed_within_30d = 0
    for listened_values in listens_by_album.values():
        parsed_dates = [_parse_datetime(value) for value in listened_values]
        parsed_dates = [value for value in parsed_dates if value is not None]
        if len(parsed_dates) < 2:
            continue
        if any(
            0 <= (current - previous).days <= 30
            for previous, current in zip(parsed_dates, parsed_dates[1:])
        ):
            replayed_within_30d += 1

    return round(replayed_within_30d / len(listens_by_album), 2)


def _top_artist_metric(session: Session, user_id: int) -> dict | None:
    row = session.execute(
        select(
            Album.artist,
            func.count(AlbumListen.id).label("listen_count"),
            func.max(AlbumListen.listened_at).label("latest_listen"),
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .where(AlbumListen.user_id == user_id)
        .group_by(Album.artist)
        .order_by(
            func.count(AlbumListen.id).desc(),
            func.max(AlbumListen.listened_at).desc(),
            Album.artist.asc(),
        )
        .limit(1)
    ).first()
    if not row:
        return None
    artist, listen_count, _latest_listen = row
    return {"name": artist, "listen_count": int(listen_count or 0)}


def _top_album_metric(session: Session, user_id: int) -> dict | None:
    row = session.execute(
        select(
            Album.name,
            Album.artist,
            func.count(AlbumListen.id).label("listen_count"),
            func.max(AlbumListen.listened_at).label("latest_listen"),
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .where(AlbumListen.user_id == user_id)
        .group_by(Album.id, Album.name, Album.artist)
        .order_by(
            func.count(AlbumListen.id).desc(),
            func.max(AlbumListen.listened_at).desc(),
            Album.name.asc(),
        )
        .limit(1)
    ).first()
    if not row:
        return None
    title, artist, listen_count, _latest_listen = row
    return {
        "title": title,
        "artist": artist,
        "listen_count": int(listen_count or 0),
    }


def _most_listened_era(session: Session, user_id: int) -> dict | None:
    rows = session.execute(
        select(
            Album.release_year,
            func.count(AlbumListen.id).label("listen_count"),
            func.max(AlbumListen.listened_at).label("latest_listen"),
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .where(AlbumListen.user_id == user_id, Album.release_year.is_not(None))
        .group_by(Album.release_year)
    ).all()
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


def _most_replayed_recently(
    session: Session,
    user_id: int,
    *,
    window_days: int = 30,
) -> dict | None:
    rows = session.execute(
        select(
            Album.id,
            Album.name,
            Album.artist,
            AlbumListen.listened_at,
        )
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .where(AlbumListen.user_id == user_id)
        .order_by(Album.id.asc(), AlbumListen.listened_at.asc())
    ).all()
    parsed_rows = []
    for album_id, title, artist, listened_at in rows:
        parsed_date = _parse_datetime(listened_at)
        if parsed_date is None:
            continue
        parsed_rows.append((album_id, title, artist, parsed_date))
    if not parsed_rows:
        return None

    latest_listen = max(row[3] for row in parsed_rows)
    window_start = latest_listen - timedelta(days=window_days)
    albums = {}
    for album_id, title, artist, listened_at in parsed_rows:
        if listened_at < window_start or listened_at > latest_listen:
            continue
        album = albums.setdefault(
            album_id,
            {"title": title, "artist": artist, "listens": []},
        )
        album["listens"].append(listened_at)

    candidates = []
    for album in albums.values():
        sorted_listens = sorted(album["listens"])
        replay_count = max(0, len(sorted_listens) - 1)
        if replay_count == 0:
            continue
        candidates.append({
            "title": album["title"],
            "artist": album["artist"],
            "replay_count": replay_count,
            "window_days": window_days,
            "_latest_listen": sorted_listens[-1],
        })

    if not candidates:
        return None

    top_replay = max(
        candidates,
        key=lambda item: (item["replay_count"], item["_latest_listen"], item["title"]),
    )
    return {
        "title": top_replay["title"],
        "artist": top_replay["artist"],
        "replay_count": top_replay["replay_count"],
        "window_days": top_replay["window_days"],
    }


def _recent_listen_activity_payload(
    listen: AlbumListen,
    *,
    artist: str,
    name: str,
    image_url: str | None,
    local_image_path: str | None,
    user: User,
) -> dict:
    public_name = _public_display_name(user)
    return {
        "listen_id": listen.id,
        "type": "listen",
        "user_display_name": user.display_name,
        "public_user_display_name": public_name,
        "album_title": name,
        "artist_name": artist,
        "album_cover_url": _display_image_url(image_url, local_image_path),
        "text": f"{public_name} listened to {name}.",
        "timestamp": listen.listened_at,
        "profile_url": f"/{user.slug}",
    }


def _display_image_url(
    image_url: str | None,
    local_image_path: str | None,
) -> str | None:
    if local_image_path:
        filename = local_image_path.removeprefix("artwork/").lstrip("/")
        return f"{ARTWORK_URL_PREFIX}{filename}"
    return image_url


def _public_display_name(user: User) -> str:
    for value in (user.slug, user.display_name):
        normalized = (value or "").strip().lower()
        if normalized in PUBLIC_DISPLAY_NAME_OVERRIDES:
            return PUBLIC_DISPLAY_NAME_OVERRIDES[normalized]
    return user.display_name


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
