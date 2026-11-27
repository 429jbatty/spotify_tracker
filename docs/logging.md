# Logging and observability

This is the application logging guide for contributors and agents. For setup,
service management, access, and recovery, see the
[observability runbook](../deploy/observability/README.md).

## Status and infrastructure

The API and worker configure structlog and Python logging to emit JSON lines.
Request, Spotify sync, and import boundaries bind correlation context. Existing
standard-library messages are rendered as JSON; some legacy `print` output
remains plain text. Event coverage is evolving and not all fields below appear
on every event. Configuration lives in `backend/app/logging_config.py`.

Production flow: **API or worker → systemd journal → Grafana Alloy → Loki →
Grafana Explore**. Alloy attaches `app=albumary`, `environment=production`,
and `service=api` or `service=worker`. It forwards journal messages without
converting them to JSON.

Local development normally logs to the terminal. An
[optional Alloy collector](../deploy/observability/README.md#optional-local-development)
can forward local files to the same Loki with `environment=development`; it is
not required for normal development. Loki is configured for 30-day production
and 3-day development retention. Recovery after an outage is best effort, and
the app must continue working when observability services are unavailable.

Schema startup failures emit `database_schema_initialization_failed` with the
sanitized database error fields used by the maintenance dashboard. An Alembic
command failure or migration-lock timeout reports its error type.

## Logging practices

Use one JSON object per event and one physical line per record, including
exception details. Prefer UTC timestamps, stable `snake_case` event names, and
consistent field types. Common fields to consider:

| Field | Purpose |
| --- | --- |
| `timestamp`, `level`, `event` | When it happened, severity, and stable event name. |
| `logger` | Module or logger name, when useful. |
| `user_id`, `request_id` | User and request context when needed. |
| `sync_run_id`, `import_session_id` | Correlate a sync run or import session. |
| `duration_ms` | Completed operation duration in milliseconds. |

Use these names for new events. Include only relevant fields, use internal IDs instead of
personal details where practical, and avoid unbounded lists or whole objects.
For example:

```json
{"timestamp":"2026-01-01T12:00:00Z","level":"info","event":"spotify_sync_completed","user_id":42,"sync_run_id":"example-run","tracks_fetched":12,"albums_completed":1,"duration_ms":842}
```

Log meaningful starts, outcomes, failures, and summaries—not every row or
track. Use `debug` for normally disabled diagnostics, `info` for operation
summaries, `warning` for recoverable problems, and `error` for failures. Log a
traceback at the boundary that owns a failure, without duplicating it at every
layer. Expected validation failures do not automatically need error tracebacks.
Persistent import status and user-facing progress belong in the application
data model, not exclusively in logs.

Choose events by the question they answer: record boundaries, significant
branch decisions, fallbacks, and outcomes that help diagnose failures or explain
why data changed. Prefer one summary with measured counts over repeated progress
messages. Use `warning` for degraded behavior such as a catalog fallback or a
possibly truncated Spotify page; use `error` for an operation that failed, and
`info` for expected outcomes and resumptions. Do not promote normal partial
listens or review candidates to errors. Include the failing stage and elapsed
time when known; emit a traceback once at the owning boundary.

Name counts for their actual units: source rows, unique track IDs, album-session
candidates, or persisted listens. Do not imply a job marked `completed` created
a listen for every play. Last.fm's current duplicate summary can include invalid
rows, so do not report it as a pure duplicate count. Candidate-outcome events and `import_finished.candidate_summary_scope`
identify when candidate counts cover only a resumed or repaired subset. Timers must bracket
actual work: `preparing_spotify_history` covers file preparation, JSON parsing is
included in `storing_streaming_events`, and `matching_cached_albums` includes
grouping and matching. A full 50-item Spotify page whose oldest play is newer than the watermark
indicates possible—not confirmed—truncation; the initial sync has no watermark.
`source_rows_reported` reflects the import summary and, for Last.fm, can be
the source-reported available count rather than the number fetched. Sync failure context includes the phase and whether the
album-state save completed; it does not claim a failed save could not partially
commit. Treat historical logs emitted before these changes accordingly.

## Bind context to a unit of work

Structlog's `merge_contextvars` processor and a context manager attach identifiers to compatible log events
throughout a request, sync, or import:

```python
import structlog
from structlog.contextvars import bound_contextvars

log = structlog.get_logger(__name__)

with bound_contextvars(user_id=user_id, import_session_id=session_id):
    log.info("import_started", source="spotify_zip")
    process_import()
    log.info("import_completed", imported_count=imported_count)
```

The context is restored on exit. Reset it for independent operations and test
that concurrent users cannot leak context to one another. FastAPI sync/async,
thread, and background-task boundaries can affect propagation; pass IDs
explicitly to independently scheduled work and bind them there.

`backend/app/logging_config.py` configures JSON formatting, context merging,
redaction, and Python/Uvicorn logging for both the API and worker.
`backend/app/request_logging.py` is API middleware: it binds a request ID and
records the method, matched route template, status, and duration. Legacy
`print` output remains plain text.

Uvicorn's default access log is disabled because it can include query strings;
the request middleware supplies the safer request event. For an unhandled
request exception, the middleware logs the traceback while the request ID is
bound, then re-raises it. A filter in `logging_config.py` suppresses Uvicorn's
second copy of that traceback; other Uvicorn errors still use the JSON logger.
Keep both sides covered by tests when changing this behavior.

## Sensitive data

Never log passwords, tokens, authorization codes or headers, API keys,
cookies, session secrets, or credential-bearing URLs. Avoid raw request and
response bodies and full external API payloads. Query strings and exception
messages can also contain secrets, including in Uvicorn and third-party logs.
Allowlist useful fields and apply redaction where needed; do not rely on
redaction or LAN restrictions alone.

## Querying and testing

Loki indexes the small set of stream labels above. Parse JSON fields at query
time; do not add high-cardinality IDs or URLs as indexed labels. For example, a Grafana Explore query is:

```logql
{app="albumary", environment="production", service="worker"}
| json
| event="spotify_sync_completed"
```

Legacy plain-text lines will not match that structured query. Before adding
or changing logs, inventory the affected flow and define useful events rather
than converting messages mechanically. Verify:

- Success and failure records have the expected fields, types, severity,
  context, and exception details without duplicates.
- Context stays isolated across users and relevant async, thread, and
  background-job boundaries; sensitive values do not appear in logs.
- API and worker entry points emit the intended levels and JSON, and logging
  or collector outages do not break app behavior.
- A representative JSON event passes through the production journal or optional
  dev collector and can be queried in Grafana. Unit tests must not depend on
  live external APIs or observability services.

Update this guide when the logging configuration or event contract changes.
Use the runbook for infrastructure and recovery checks.
