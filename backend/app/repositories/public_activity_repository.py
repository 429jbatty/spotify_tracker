from typing import NamedTuple

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumListen, User, UserAlbum


class PublicListen(NamedTuple):
    listen_id: int
    listened_at: str
    album_id: int
    album_key: str
    artist: str
    name: str
    image_url: str | None
    local_image_path: str | None
    slug: str
    display_name: str


class FeaturedProfile(NamedTuple):
    id: int
    slug: str
    display_name: str
    total_albums: int
    total_listens: int
    last_updated: str | None


class PublicActivityRepository:
    def __init__(self, session: Session):
        self.session = session

    def recent_listens(self, limit: int) -> list[PublicListen]:
        return self._recent_listens(limit, AlbumListen.listened_at.desc())

    def recent_activity(self, limit: int) -> list[PublicListen]:
        return self._recent_listens(limit, func.julianday(AlbumListen.listened_at).desc())

    def _recent_listens(self, limit: int, listened_at_order) -> list[PublicListen]:
        rows = self.session.execute(
            select(
                AlbumListen.id,
                AlbumListen.listened_at,
                Album.id,
                Album.album_key,
                Album.artist,
                Album.name,
                Album.image_url,
                Album.local_image_path,
                User.slug,
                User.display_name,
            )
            .select_from(AlbumListen)
            .join(Album, Album.id == AlbumListen.album_id)
            .join(User, User.id == AlbumListen.user_id)
            .where(User.is_active.is_(True))
            .order_by(listened_at_order, AlbumListen.id.desc())
            .limit(limit)
        )
        return [PublicListen(*row) for row in rows]

    def featured_users(self, limit: int) -> list[FeaturedProfile]:
        rows = self.session.execute(
            select(
                User.id,
                User.slug,
                User.display_name,
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
            .limit(limit)
        )
        return [FeaturedProfile(*row) for row in rows]

    def recent_album_covers(self, user_id: int, limit: int) -> list[tuple[int, str | None, str | None]]:
        return [tuple(row) for row in self.session.execute(
            select(Album.id, Album.image_url, Album.local_image_path)
            .select_from(AlbumListen)
            .join(Album, Album.id == AlbumListen.album_id)
            .where(AlbumListen.user_id == user_id)
            .order_by(AlbumListen.listened_at.desc(), AlbumListen.id.desc())
            .limit(limit)
        )]

    def top_artist(self, user_id: int) -> tuple[str, int, str] | None:
        row = self.session.execute(
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
        return tuple(row) if row else None

    def top_album(self, user_id: int) -> tuple[str, str, int, str] | None:
        row = self.session.execute(
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
        return tuple(row) if row else None

    def listened_release_years(self, user_id: int) -> list[tuple[int, int, str]]:
        return [tuple(row) for row in self.session.execute(
            select(
                Album.release_year,
                func.count(AlbumListen.id).label("listen_count"),
                func.max(AlbumListen.listened_at).label("latest_listen"),
            )
            .select_from(AlbumListen)
            .join(Album, Album.id == AlbumListen.album_id)
            .where(AlbumListen.user_id == user_id, Album.release_year.is_not(None))
            .group_by(Album.release_year)
        )]

    def profile_listens(self, user_id: int) -> list[tuple[int, str, str, str]]:
        return [tuple(row) for row in self.session.execute(
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
        )]
