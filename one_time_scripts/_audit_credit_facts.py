import argparse
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.models import Album, AlbumCreditFact, AlbumListen, User, UserAlbum


def build_fact_audit(session, user_slug: str) -> dict:
    user = session.scalars(select(User).where(User.slug == user_slug)).first()
    if user is None:
        raise ValueError(f"Unknown user slug: {user_slug}")

    library_album_count = session.scalar(
        select(func.count(UserAlbum.id)).where(UserAlbum.user_id == user.id)
    )
    listened_album_count = session.scalar(
        select(func.count(func.distinct(AlbumListen.album_id))).where(
            AlbumListen.user_id == user.id
        )
    )
    total_listen_count = session.scalar(
        select(func.count(AlbumListen.id)).where(AlbumListen.user_id == user.id)
    )
    facts = session.execute(
        select(AlbumCreditFact, Album.artist, Album.name)
        .join(Album, Album.id == AlbumCreditFact.album_id)
        .join(UserAlbum, UserAlbum.album_id == Album.id)
        .where(UserAlbum.user_id == user.id)
        .order_by(AlbumCreditFact.person_name, Album.artist, Album.name)
    ).all()

    album_ids_with_facts = {fact.album_id for fact, _artist, _name in facts}
    role_buckets = Counter(fact.role_bucket for fact, _artist, _name in facts)
    identity_resolution = Counter(fact.identity_resolution for fact, _artist, _name in facts)
    ingestion_versions = Counter(fact.ingestion_version for fact, _artist, _name in facts)
    flags = Counter(
        flag
        for fact, _artist, _name in facts
        for flag in (fact.quality_flags_json or [])
    )
    contributors = {}
    for fact, artist, name in facts:
        contributor = contributors.setdefault(
            fact.person_key,
            {
                "name": fact.person_name,
                "albums": set(),
                "artists": set(),
                "roles": Counter(),
                "flags": Counter(),
            },
        )
        contributor["albums"].add(fact.album_id)
        contributor["artists"].add(artist)
        contributor["roles"][fact.role_bucket] += 1
        contributor["flags"].update(fact.quality_flags_json or [])

    top_contributors = sorted(
        contributors.values(),
        key=lambda item: (
            -len(item["albums"]),
            -len(item["artists"]),
            item["name"].casefold(),
        ),
    )[:20]

    return {
        "user_slug": user.slug,
        "display_name": user.display_name,
        "library_album_count": library_album_count or 0,
        "listened_album_count": listened_album_count or 0,
        "total_listen_count": total_listen_count or 0,
        "album_count_with_facts": len(album_ids_with_facts),
        "fact_count": len(facts),
        "role_buckets": role_buckets,
        "identity_resolution": identity_resolution,
        "ingestion_versions": ingestion_versions,
        "quality_flags": flags,
        "top_contributors": top_contributors,
    }


def format_fact_audit(report: dict) -> str:
    lines = [
        "Credit Facts Audit",
        f"User: {report['display_name']} ({report['user_slug']})",
        f"- Albums in library: {report['library_album_count']}",
        f"- Albums with completed listens: {report['listened_album_count']}; completed listen rows: {report['total_listen_count']}",
        f"- Albums with projected facts: {report['album_count_with_facts']}",
        f"- Projected fact rows: {report['fact_count']}",
        "",
        "Role buckets:",
        *_format_counts(report["role_buckets"]),
        "",
        "Identity resolution:",
        *_format_counts(report["identity_resolution"]),
        "",
        "Ingestion versions:",
        *_format_counts(report["ingestion_versions"]),
        "",
        "Quality flags:",
        *_format_counts(report["quality_flags"]),
        "",
        "Top contributors by distinct albums:",
    ]
    if not report["top_contributors"]:
        lines.append("- none")
    for item in report["top_contributors"]:
        roles = ", ".join(
            f"{role}:{count}" for role, count in item["roles"].most_common(3)
        )
        lines.append(
            f"- {item['name']}: albums={len(item['albums'])}; "
            f"artists={len(item['artists'])}; roles={roles}"
        )
    return "\n".join(lines)


def _format_counts(counter: Counter) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- {key}: {count}" for key, count in counter.most_common()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit user credit coverage from album_credit_facts.",
    )
    parser.add_argument("--user-slug", required=True)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    database_url = args.database_url or get_settings().database_url
    engine = create_schema(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        print(format_fact_audit(build_fact_audit(session, args.user_slug)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
