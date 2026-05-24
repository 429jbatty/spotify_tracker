import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from unidecode import unidecode

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import metadata_refresh_service
from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.models import Album, AlbumListen, UserAlbum
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from musicbrainz_resolver import normalize


NEAR_MATCH_THRESHOLD = 92
SAFE_REASONS = {"same_release_group_mbid", "exact_normalized_artist_album"}


@dataclass(frozen=True)
class AlbumSummary:
    id: int
    artist: str
    name: str
    album_key: str
    release_group_mbid: str | None
    source: str
    listen_count: int
    user_count: int


@dataclass(frozen=True)
class DuplicateGroup:
    reason: str
    albums: tuple[AlbumSummary, ...]
    score: int | None = None

    @property
    def safe_to_apply(self) -> bool:
        return self.reason in SAFE_REASONS


def _normalized_identity(album: AlbumSummary) -> str:
    artist = normalize(album.artist)
    name = normalize(album.name)
    return f"{artist} - {name}"


def _near_identity(album: AlbumSummary) -> str:
    text = unidecode(f"{album.artist} {album.name}".casefold())
    return " ".join(text.split())


def _album_summaries(session) -> list[AlbumSummary]:
    rows = session.execute(
        select(
            Album,
            func.count(func.distinct(AlbumListen.id)).label("listen_count"),
            func.count(func.distinct(UserAlbum.id)).label("user_count"),
        )
        .outerjoin(AlbumListen, AlbumListen.album_id == Album.id)
        .outerjoin(UserAlbum, UserAlbum.album_id == Album.id)
        .group_by(Album.id)
        .order_by(Album.artist, Album.name, Album.id)
    ).all()

    return [
        AlbumSummary(
            id=album.id,
            artist=album.artist,
            name=album.name,
            album_key=album.album_key,
            release_group_mbid=album.release_group_mbid,
            source=album.source,
            listen_count=int(listen_count or 0),
            user_count=int(user_count or 0),
        )
        for album, listen_count, user_count in rows
    ]


def _group_by(items: Iterable[AlbumSummary], key_fn) -> list[tuple[str, list[AlbumSummary]]]:
    grouped: dict[str, list[AlbumSummary]] = {}
    for item in items:
        key = key_fn(item)
        if not key:
            continue
        grouped.setdefault(key, []).append(item)
    return [(key, group) for key, group in grouped.items() if len(group) > 1]


def find_duplicate_groups(session) -> list[DuplicateGroup]:
    albums = _album_summaries(session)
    groups: list[DuplicateGroup] = []
    grouped_ids: set[frozenset[int]] = set()

    for _, group in _group_by(albums, lambda album: album.release_group_mbid):
        ids = frozenset(album.id for album in group)
        grouped_ids.add(ids)
        groups.append(
            DuplicateGroup(
                reason="same_release_group_mbid",
                albums=tuple(sorted(group, key=lambda album: album.id)),
            )
        )

    for _, group in _group_by(albums, _normalized_identity):
        ids = frozenset(album.id for album in group)
        if ids in grouped_ids:
            continue
        grouped_ids.add(ids)
        groups.append(
            DuplicateGroup(
                reason="exact_normalized_artist_album",
                albums=tuple(sorted(group, key=lambda album: album.id)),
            )
        )

    for index, left in enumerate(albums):
        for right in albums[index + 1 :]:
            ids = frozenset({left.id, right.id})
            if ids in grouped_ids:
                continue
            score = fuzz.token_set_ratio(_near_identity(left), _near_identity(right))
            if score >= NEAR_MATCH_THRESHOLD:
                grouped_ids.add(ids)
                groups.append(
                    DuplicateGroup(
                        reason="near_normalized_artist_album",
                        albums=(left, right),
                        score=round(score),
                    )
                )

    return sorted(
        groups,
        key=lambda group: (
            0 if group.safe_to_apply else 1,
            group.reason,
            group.albums[0].artist.casefold(),
            group.albums[0].name.casefold(),
        ),
    )


def _merge_target(group: DuplicateGroup) -> AlbumSummary:
    return sorted(
        group.albums,
        key=lambda album: (
            album.release_group_mbid is None,
            album.source != "musicbrainz",
            -album.listen_count,
            -album.user_count,
            album.id,
        ),
    )[0]


def apply_duplicate_groups(repository: SqliteStateRepository, groups: list[DuplicateGroup]) -> list[str]:
    actions = []
    merged_ids: set[int] = set()
    for group in groups:
        if not group.safe_to_apply:
            continue
        active_albums = [album for album in group.albums if album.id not in merged_ids]
        if len(active_albums) < 2:
            continue
        active_group = DuplicateGroup(
            reason=group.reason,
            albums=tuple(active_albums),
            score=group.score,
        )
        target = _merge_target(active_group)
        for source in active_albums:
            if source.id == target.id:
                continue
            repository.merge_completed_album_listens(source.id, target.id)
            merged_ids.add(source.id)
            actions.append(
                f"merged {source.id} into {target.id} ({active_group.reason})"
            )
    return actions


def refresh_candidates(repository: SqliteStateRepository, album_ids: list[int]) -> list[str]:
    actions = []
    for album_id in album_ids:
        try:
            record = repository.get_completed_album_record_by_id(album_id)
            refreshed = metadata_refresh_service.refresh_album_record(record)
            repository.replace_completed_album_metadata_by_id_or_merge_duplicate(
                album_id,
                refreshed,
            )
            actions.append(f"refreshed {album_id}")
        except KeyError:
            actions.append(f"skipped {album_id}: already merged or missing")
        except Exception as exc:
            status = metadata_refresh_service.classify_refresh_error(exc)
            actions.append(f"skipped {album_id}: {status}: {exc}")
    return actions


def print_report(groups: list[DuplicateGroup], actions: list[str] | None = None) -> None:
    safe_count = sum(1 for group in groups if group.safe_to_apply)
    print(f"Duplicate groups: {len(groups)} ({safe_count} safe to apply)")
    if actions:
        print("\nActions:")
        for action in actions:
            print(f"- {action}")

    for group in groups:
        score = f", score={group.score}" if group.score is not None else ""
        safety = "safe" if group.safe_to_apply else "review"
        print(f"\n[{safety}] {group.reason}{score}")
        target = _merge_target(group) if group.safe_to_apply else None
        for album in group.albums:
            marker = " -> target" if target and album.id == target.id else ""
            print(
                f"- id={album.id}{marker}; {album.artist} - {album.name}; "
                f"rg={album.release_group_mbid or '-'}; listens={album.listen_count}; "
                f"users={album.user_count}; source={album.source}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report and safely merge likely duplicate albums.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply safe merges.")
    parser.add_argument(
        "--refresh-candidates",
        action="store_true",
        help="Refresh reported candidates before the final report/apply step.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override the configured database URL.",
    )
    args = parser.parse_args()

    database_url = args.database_url or get_settings().database_url
    engine = create_schema(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    actions: list[str] = []
    with session_factory() as session:
        repository = SqliteStateRepository(session)
        groups = find_duplicate_groups(session)
        if args.refresh_candidates:
            candidate_ids = sorted({album.id for group in groups for album in group.albums})
            actions.extend(refresh_candidates(repository, candidate_ids))
            groups = find_duplicate_groups(session)
        if args.apply:
            actions.extend(apply_duplicate_groups(repository, groups))
            groups = find_duplicate_groups(session)

        print_report(groups, actions)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
