---
title: Management panel architecture
status: accepted
last_updated: 2026-10-07
---

# Management panel — D-533

See [requirements](../requirements/MANAGEMENT_PANEL.md) and
[accepted execution plan](../delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md).

## Responsibility and data ownership

New domain/application/repository modules own points/machines/assignments and
machine/game/stake saves. New shared public metadata tables use stable UUIDs,
additive Alembic migrations, preserved history and no image blobs. Existing game
registry/routing remains authoritative for eligibility/read/write availability.
Mutations validate ancestry and live eligibility under transactional locks.
Save, clear, refresh and current game operations require active attachment.
Archived/detached saved history remains readable without current game operations.

Immutable compact result versions include numeric payout rows, start symbols,
published rules and data fingerprint; identical semantic results are shared.
Current slot key is machine/game/stake_grosze. Slot revision changes on save,
clear or actual result change. Operation UUID binds actor/target/body; exact retry
returns prior receipt and conflicts fail closed. Structural/save/correction audit
commits atomically with the corresponding mutation. Failed writes never audit
success. Refresh records only semantic changes, not repeated unchanged reads.

## Existing services and optional UI ports

Use BoardSearchService, BoardSearchApproximateWinService, existing board detail/
crop renderer and human symbol writer. Add optional controlled saved selection,
fixed stake, range and pins to BoardSearchWorkspace/ApproximateWinBalanceChart;
default Admin/one-game share behavior remains tested. Both new clients use this
same UI and generated backend contract. Game navigation prevents stale replies
from leaking state across machines/slots. Full result arrays are loaded on demand,
not in point lists/six-card summaries. Refresh queue concurrency is at most2.

## HTTP and session boundary

Local `/api/v1/admin/management/...` owns management and link administration.
Separate `/api/v1/management-public/...` accepts only panel capability sessions
through Reviewer's allowlisted `/management-api` proxy. Its game-bound operations
verify machine/game association. This independent multi-game session purpose
never widens board_search_share_sessions or reviewer access sessions.

Reuse code/token cryptographic primitives and existing ingress controller,
with independent purpose/cookie and server-side expiry/revoke/attempt counters.
Lock/revalidate the session across public mutation commit; verify secrets are
absent from audit/public responses. No Admin API catch-all proxy. Public board
detail/correction uses position/opaque version rather than internal review IDs.
Correct game-store binding remains required when delegating to domain writers.

## Durability and operations

PC/API/DB availability is required for online search and writes. Agents never
start/stop/restart API/Admin absent a separate current instruction. Migration and
live rollout are handed to the user; isolated DB/test-process restart verifies
persistence without lifecycle changes to user services. Saved history has no GC
or destructive downgrade after user records exist. Expiry preserves history.
Future server deployment is separate and must explicitly place backend/data;
front-end hosting alone does not create offline-computer availability.

## T1 implementation

`domain/management.py` defines transport-independent commands and records.
`application/management.py`, `storage/management_repository.py` and
`api/management.py` implement the local structural operations. Migration
`0148_management_points_machines` creates shared points, machines, retained
assignments, operation receipts and immutable journal records. An independent
`management-control-plane-v1` ownership manifest extends the exhaustive mapping
check without modifying frozen game-store lifecycle manifests.

Structural routes use a public metadata `Session`; game-bound T2 routes require
their own single-game `GameStorageSession`. The operation UUID advisory lock
precedes point/machine locks. Exact retries return their stored response before
revision validation; a changed actor, target or command cannot reuse the UUID.
New assignments lock and validate live active games. Previously attached games
that later become inactive remain attached until explicit detachment.

The FastAPI dependency commits with `scope="function"` before sending success.
The Admin tab uses generated contracts and persists an uncertain command in
per-tab session storage. Reload retries the same UUID/body; an ambiguous server
or transport failure does not discard its identity. Definite validation/conflict
responses require refreshed data before a new operation.

## T2 transaction boundaries

Mutations use READ COMMITTED so an operation waiting on the UUID advisory lock
can observe the preceding committed receipt. A separate bounded, read-only
REPEATABLE READ `GameStorageSession`, using the same application engine/role,
captures numeric rows, published rules and start symbols from one coherent read
instant. It does not write or use owner privileges. Eligibility, slot revision,
result version, receipt and journal remain protected by the primary mutation
transaction. Later recalculation can detect data committed after that instant.
Immediate symbol corrections and their before/after audit share the primary
transaction; recalculation follows their commit.

Migration `0149_management_stake_saves` adds slots, immutable result versions and
search contexts, and extends the journal with game/stake/result references.
Compact card summaries contain at most256 chart points plus exact pin values
and the published spin cost. Full payout rows are loaded only through an opened
result. Restoring the exact current slot/context/start under CAS permits range/
pin changes by another authorized actor without repeating top-hit selection.
History routes bypass implicit current-game routing; current game adapters bind
their read/write game scope explicitly. The public T5 adapter must additionally
sanitize search responses and install commit-bound capability revalidation.
