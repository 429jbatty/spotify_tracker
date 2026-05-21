import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings
from backend.app.schemas import BugReportCreate


MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
PNG_DATA_URL_PREFIX = "data:image/png;base64,"


@dataclass(frozen=True)
class StoredBugReport:
    id: str
    created_at: str
    report_path: str
    screenshot_path: str


def store_bug_report(settings: Settings, request: BugReportCreate) -> StoredBugReport:
    screenshot_bytes = _decode_png_data_url(request.screenshot_data_url)
    report_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    reports_dir = Path(settings.data_dir) / "bug_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    screenshot_filename = f"{report_id}.png"
    report_filename = f"{report_id}.json"
    screenshot_path = reports_dir / screenshot_filename
    report_path = reports_dir / report_filename

    screenshot_path.write_bytes(screenshot_bytes)
    report_path.write_text(
        json.dumps(
            {
                "id": report_id,
                "created_at": created_at,
                "description": request.description,
                "page_url": request.page_url,
                "screenshot_source": request.screenshot_source,
                "user_agent": request.user_agent,
                "user_slug": request.user_slug,
                "viewport": (
                    request.viewport.model_dump()
                    if request.viewport is not None
                    else None
                ),
                "screenshot_file": screenshot_filename,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return StoredBugReport(
        id=report_id,
        created_at=created_at,
        report_path=f"bug_reports/{report_filename}",
        screenshot_path=f"bug_reports/{screenshot_filename}",
    )


def _decode_png_data_url(data_url: str) -> bytes:
    if not data_url.startswith(PNG_DATA_URL_PREFIX):
        raise ValueError("Screenshot must be a PNG data URL.")

    encoded = data_url.removeprefix(PNG_DATA_URL_PREFIX)
    try:
        screenshot_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Screenshot data is not valid base64.") from exc

    if not screenshot_bytes:
        raise ValueError("Screenshot is empty.")
    if len(screenshot_bytes) > MAX_SCREENSHOT_BYTES:
        raise ValueError("Screenshot is larger than the 5 MB limit.")

    return screenshot_bytes
