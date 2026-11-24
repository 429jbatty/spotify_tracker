# Application boundaries

**Status: proposed direction.** This is a guide for reviewing and simplifying
Albumary, not a claim that every existing module already follows it. Preserve
current behavior while moving toward it; make deliberate changes to transaction
or product behavior separately.

## Intended flow

```text
React view → frontend API service → HTTP router → application workflow
                                                 ├→ domain calculations
                                                 ├→ external-service client
                                                 └→ repositories → database
```

Jobs and commands enter the same workflows at their own entry points. Dependencies
are supplied at the edge; lower-level persistence code does not call back into
application workflows. Shared album metadata and user-scoped library data remain
separate concepts across every layer.

| Level | Knows and does | Should not own |
| --- | --- | --- |
| Frontend views | Interaction, presentation, and page-level refresh | SQL, database sessions, or direct provider access for stored album state |
| Frontend API/normalization | HTTP requests and consistent frontend album shapes | UI-specific state or database implementation |
| HTTP routers | HTTP validation, authentication/authorization, dependency setup, responses and expected error translation | SQL, provider calls, or detailed business workflows |
| Job/command entry points | Configuration, resource lifetime, starting a workflow, reporting outcomes | Duplicate business rules or ad hoc runtime persistence |
| Application workflows/services | Coordinate use cases, permissions already established by the entry point, domain rules, external lookups, and meaningful transaction checkpoints | SQL, engine construction, connection pragmas, or provider-specific HTTP details |
| Domain calculations | Transform inputs into results, such as credit facts or matching decisions | Opening sessions, writing data, HTTP or hidden external calls |
| Repositories | User-scoped and shared data access, queries, persistence operations and SQLite-specific implementation details | HTTP responses, external API calls, or orchestration of unrelated workflows |
| Database models/infrastructure | Table definitions; engine/session creation, schema initialization and SQLite settings | Product workflows or presentation |
| External clients | Provider-specific requests, retries, rate limits and responses | Direct application database writes or decisions belonging to a workflow |

## Transactions and sessions

- The API app or standalone job owns the engine; each request, worker or job
  unit owns its session. Never share a session across concurrent threads.
- A workflow decides which related operations must succeed or fail together and
  where durable checkpoints occur. Repositories participate in the same unit of
  work; their methods must clearly state whether they stage, flush or commit.
- Prefer an explicit unit-of-work/transaction boundary over passing raw sessions
  through business logic. It may wrap SQLAlchemy; do not introduce a framework
  or duplicate data classes merely to hide imports. Decide the smallest useful
  interface from actual workflows before standardizing it.
- The current implementation does not consistently meet this target. In
  particular, some repository methods commit internally and import services
  also commit at checkpoints. Do not move commits mechanically: preserve import
  recovery, logging, user scoping and credit projection until their behavior is
  characterized and deliberately changed.

## Concrete example: album credits

Album writes stage credit facts through
[`CreditRepository`](../backend/app/database/repositories/credit_repository.py).
It flushes pending album changes before loading credit sources and flushes the
replacement facts in the same transaction. The album write still commits the
transaction. The [credit projection](../backend/app/credit_projection.py) takes
loaded metadata and a timestamp and returns the calculated facts.

The [standalone maintenance workflow](../backend/app/services/credit_fact_service.py)
uses the same repository and calculation for rebuilds. Its preview reads sources
and calculates facts without writing.

## Explicit exceptions and practical tests

- Schema initialization, future migrations, and intentional one-off audit/repair
  scripts may use database-specific SQL directly. Tests may seed and inspect data.
- Purpose-built bulk/read queries are appropriate where they express a real
  access rule or avoid excessive database calls. Do not replace them with many
  tiny generic operations purely for consistency.
- Database records or sessions currently cross some service boundaries. Evaluate
  each case by whether a simpler contract improves clarity and testability; do
  not claim SQLite independence or force a wholesale conversion.
- Audit by workflow: trace entry point → service → repository, identify direct
  SQL, ownership of sessions/commits, reverse dependencies and provider calls;
  classify an intentional exception or a concrete simplification. Preserve
  same-transaction behavior and add focused tests before moving boundaries.
