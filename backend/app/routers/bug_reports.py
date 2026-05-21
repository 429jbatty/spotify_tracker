from fastapi import APIRouter, HTTPException, status

from backend.app.config import get_settings
from backend.app.schemas import BugReportCreate, BugReportResponse
from backend.app.services.bug_report_service import StoredBugReport, store_bug_report


router = APIRouter(prefix="/bug-reports", tags=["bug-reports"])


@router.post("", response_model=BugReportResponse, status_code=status.HTTP_201_CREATED)
def create_bug_report(request: BugReportCreate) -> StoredBugReport:
    settings = get_settings()
    try:
        return store_bug_report(settings, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
