"""Preview or rebuild credit facts as a standalone maintenance operation."""

from datetime import datetime, timezone
from typing import Iterable

import structlog
from sqlalchemy.orm import Session

from backend.app.credit_projection import ProjectedCreditFact, project_credit_facts
from backend.app.database.repositories.credit_repository import CreditRepository, RebuildResult
from backend.app.persistence_logging import database_error_fields


logger = structlog.get_logger(__name__)


def rebuild_credit_facts(
    session: Session,
    *,
    album_ids: Iterable[int] | None = None,
    commit: bool = True,
) -> RebuildResult:
    repository = CreditRepository(session)
    stage = "load"
    try:
        sources = repository.album_credit_sources(album_ids=album_ids)
        stage = "rebuild"
        result, facts = repository.clear_and_project_facts(sources)
        if result.album_ids:
            stage = "commit" if commit else "flush"
            repository.stage_facts(facts)
            if commit:
                session.commit()
            else:
                session.flush()
    except Exception as exc:
        if commit:
            logger.error("credit_facts_rebuild_failed", stage=stage, error_type=type(exc).__name__, **database_error_fields(exc))
        raise
    # An outer transaction may still roll back a flush-only rebuild.
    if commit:
        logger.info(
            "credit_facts_rebuilt", albums=len(result.album_ids), deleted=result.deleted_count,
            inserted=result.inserted_count, skipped_parse_errors=result.skipped_parse_error_count,
        )
    return result


def preview_credit_facts(
    session: Session,
    *,
    album_ids: Iterable[int] | None = None,
) -> list[ProjectedCreditFact]:
    now = datetime.now(timezone.utc).isoformat()
    sources = CreditRepository(session).album_credit_sources(album_ids=album_ids)
    return project_credit_facts(sources, now=now)
