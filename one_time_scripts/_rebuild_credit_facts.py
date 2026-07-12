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
from backend.app.models import AlbumCreditFact
from backend.app.services.credit_fact_service import (
    preview_credit_facts,
    rebuild_credit_facts,
)


def format_preview(facts: list[AlbumCreditFact]) -> str:
    role_counts = Counter(fact.role_bucket for fact in facts)
    identity_counts = Counter(fact.identity_resolution for fact in facts)
    ingestion_counts = Counter(fact.ingestion_version for fact in facts)
    flag_counts = Counter(
        flag for fact in facts for flag in (fact.quality_flags_json or [])
    )
    lines = [
        "Credit Fact Rebuild Preview",
        f"- facts: {len(facts)}",
        f"- albums: {len({fact.album_id for fact in facts})}",
        "",
        "Role buckets:",
        *_format_counts(role_counts),
        "",
        "Identity resolution:",
        *_format_counts(identity_counts),
        "",
        "Ingestion versions:",
        *_format_counts(ingestion_counts),
        "",
        "Quality flags:",
        *_format_counts(flag_counts),
        "",
        "No data was written. Re-run with --apply to rebuild persisted facts.",
    ]
    return "\n".join(lines)


def format_apply_result(session, result) -> str:
    persisted_count = session.scalar(select(func.count(AlbumCreditFact.id)))
    return "\n".join(
        [
            "Credit Fact Rebuild Applied",
            f"- albums considered: {len(result.album_ids)}",
            f"- deleted facts: {result.deleted_count}",
            f"- inserted facts: {result.inserted_count}",
            f"- skipped metadata parse errors: {result.skipped_parse_error_count}",
            f"- total persisted facts: {persisted_count}",
        ]
    )


def _format_counts(counter: Counter) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- {key}: {count}" for key, count in counter.most_common()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or rebuild album_credit_facts from stored album metadata.",
    )
    parser.add_argument("--database-url", default=None, help="Override database URL.")
    parser.add_argument(
        "--album-id",
        action="append",
        type=int,
        default=[],
        help="Rebuild facts for one album id. Can be passed multiple times.",
    )
    parser.add_argument("--apply", action="store_true", help="Write rebuilt facts.")
    args = parser.parse_args()

    database_url = args.database_url or get_settings().database_url
    engine = create_schema(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    album_ids = args.album_id or None

    with session_factory() as session:
        if args.apply:
            result = rebuild_credit_facts(session, album_ids=album_ids)
            print(format_apply_result(session, result))
        else:
            facts = preview_credit_facts(session, album_ids=album_ids)
            print(format_preview(facts))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
