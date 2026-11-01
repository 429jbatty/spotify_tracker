"""Global album consolidation for schema migrations, without profile permissions."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumListen, ImportedListeningEvent, UserAlbum
from backend.app.services.credit_fact_service import rebuild_credit_facts


def merge_shared_album(session: Session, source: Album, target: Album) -> None:
    """Move all profiles' references; leave commit/rollback to the migration.

    A profile's existing target rating wins a conflict, matching the normal
    merge. Tags are combined and distinct notes are retained. Equal timestamps
    deduplicate only within the same profile, preserving each listen's source.
    """
    if source.id == target.id:
        raise ValueError("Cannot merge an album into itself.")

    _merge_memberships(session, source.id, target.id)
    _move_listens(session, source.id, target.id)
    session.execute(
        update(ImportedListeningEvent)
        .where(ImportedListeningEvent.album_id == source.id)
        .values(album_id=target.id)
    )
    # Flush moved associations before deleting the source so ORM cascades only
    # remove its obsolete credit projection, not the reassigned user records.
    session.flush()
    session.delete(source)
    session.flush()

    # Keep the surviving album's identity/enrichment, filling missing values.
    # Delete first so transferring an MBID cannot violate an existing index.
    for field in (
        "artist_mbid", "release_group_mbid", "release_mbid", "label",
        "release_year", "release_month", "release_day", "image_url",
        "remote_image_url", "local_image_path",
    ):
        if getattr(target, field) is None or getattr(target, field) == "":
            setattr(target, field, getattr(source, field))
    target_metadata = target.metadata_json if isinstance(target.metadata_json, dict) else {}
    source_metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
    target.metadata_json = {
        **source_metadata,
        **{key: value for key, value in target_metadata.items()
           if value not in (None, "", [], {})},
    }
    session.flush()
    rebuild_credit_facts(session, album_ids=[target.id], commit=False)


def _merge_memberships(session: Session, source_id: int, target_id: int) -> None:
    targets = {
        membership.user_id: membership
        for membership in session.scalars(
            select(UserAlbum).where(UserAlbum.album_id == target_id)
        )
    }
    for membership in session.scalars(
        select(UserAlbum).where(UserAlbum.album_id == source_id)
    ).all():
        target = targets.get(membership.user_id)
        if target is None:
            membership.album_id = target_id
            continue
        target.your_tags = list(dict.fromkeys([
            *(target.your_tags or []), *(membership.your_tags or []),
        ]))
        if target.rating is None:
            target.rating = membership.rating
        if not (target.notes or "").strip():
            target.notes = membership.notes
        elif (membership.notes or "").strip() and target.notes.strip() != membership.notes.strip():
            target.notes = f"{target.notes}\n\n{membership.notes}"
        session.delete(membership)


def _move_listens(session: Session, source_id: int, target_id: int) -> None:
    existing = set(session.execute(
        select(AlbumListen.user_id, AlbumListen.listened_at)
        .where(AlbumListen.album_id == target_id)
    ).all())
    for listen in session.scalars(
        select(AlbumListen).where(AlbumListen.album_id == source_id)
    ).all():
        key = (listen.user_id, listen.listened_at)
        if key in existing:
            session.delete(listen)
        else:
            listen.album_id = target_id
            existing.add(key)
