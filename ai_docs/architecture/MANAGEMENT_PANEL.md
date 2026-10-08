---
title: Management panel architecture
status: accepted
last_updated: 2026-10-09
---

# Management panel — D-533

## Compact redesign override — D-536

The [compact execution plan](../delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md)
owns TASK-0940–0943 and supersedes archive-only structural retention.
Preview-bound POST delete/update mutations use both local/public prefixes.
Restricted SECURITY DEFINER purge uses fixed search_path and explicit grants;
SECURITY INVOKER immutable triggers require effective owner identity and
transaction-local maintenance mode. GUC alone cannot bypass immutability,
and independent session audit remains protected. Minimal pure-delete receipts
stay retryable; former scoped responses are redacted. Read-only migration
preview precedes owner-run receipt backfill. Unique migration after0151
remains independent of Mumie; second integrator reconciles the two heads.
Shared UI gains small tiles, atomic modals and optional compact search ports,
preserving ordinary search/share defaults. Cached nullable pin investment/cash
uses frozen results and bounded read-only legacy fallback, never another
calculator. No production migration/deletion or API/Admin lifecycle authorized.

### TASK-0940 storage and transport contract

Migration `0152_management_compact_panel` follows `0151_super_game_roles`.
It introduces `management_mutation_previews`, receipt scope fields and the
restricted `management_purge_scope(uuid,uuid,uuid[])` function. The ownership
manifest is `management-control-plane-v3`; schema readiness expects this head.
Provisioning checks function ownership, fixed search_path, security mode and
the purge EXECUTE boundary in addition to existing role restrictions.

Both management prefixes expose POST point/machine `delete-preview` and
`delete`, plus machine `update-preview`. The latter wraps the intended machine
or assignment command in `command`. Optional machine `gameIds` leaves games
unchanged when absent; removing existing assignments requires `previewToken`.
An empty new machine does not purge anything and needs no deletion preview.

Preview tokens contain 256 random bits, live for ten minutes and are stored
only as SHA-256 hashes. Actor/action/scope/body and structural/history
fingerprints bind confirmation to the preview. Creating a preview removes at
most 100 expired rows belonging to that actor. Operation/session identity is
checked before retry; an exact pure-delete receipt is returned even if its
parent was subsequently deleted. Redacted older mutations fail with
`MANAGEMENT_TARGET_DELETED`; unclassifiable legacy receipts fail with
`MANAGEMENT_LEGACY_RECEIPT_REDACTED`.

Purge and frozen-result dedup acquire the same advisory digest lock. Purge
locks digests in sorted order and checks references across all management
scopes before deleting a result. Ordinary app DML cannot bypass immutable
history by setting the maintenance GUC. Session audit never uses the purge
bypass. API dependencies flush and revalidate a public session before commit.

The read-only `scripts/preview_management_receipt_migration.py` reports four
backfill categories on an unchanged single-head 0151 database, without dumping
responses or credentials. Applying the backfill requires a separate operator
decision. Pin metadata uses `domain/management_pin_metrics.py`, verified
against the existing TypeScript chart helpers with shared golden fixtures.
Legacy missing metadata is filled from frozen payloads only, with at most six
payload reads per selected machine/game list and no GET writes.

See [requirements](../requirements/MANAGEMENT_PANEL.md) and
[accepted execution plan](../delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md).

## Responsibility and data ownership

New domain/application/repository modules own points/machines/assignments and
machine/game/stake saves. New shared public metadata tables use stable UUIDs,
additive Alembic migrations, preserved history and no image blobs. Existing game
registry/routing remains authoritative for eligibility/read/write availability.
Mutations validate ancestry and live eligibility under transactional locks.
Save, clear, refresh and current game operations require active attachment.
Archived saved history remains readable without current game operations.
Explicit structural delete/detach removes its scoped history under D-536.

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
or destructive downgrade after user records exist. Explicit D-536 scope purge
is the sole structural retention exception. Expiry preserves history.
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

## T3 shared selection ports

`BoardSearchWorkspace` optionally accepts a fixed stake, saved selection,
controlled draft callbacks and an explicit asynchronous Save callback. The host
resolves Save only after its durable receipt; failure leaves the full draft dirty.
Saved starts load by trusted sequence without selecting the first ranked hit.
Controlled pins store spin positions, including zero and losing spins; numeric
values derive from the latest calculation and inaccessible pins remain explicit.

Hosts provide a stable machine/game/stake `scopeKey`. Background saved-result
identity changes within that scope do not remount or replace a draft. Explicit
Open/Search again/Clear transitions require the host discard guard and a deliberate
new workspace identity. Without a scopeKey, saved-selection identity is the
optional mount key. Page-exit warnings and dirty callbacks cover outer navigation.
Current symbol corrections remain immediate; recalculation refreshes values without
changing the trusted start/context or controlled pins. Both board modals calculate
fixed-stake amounts using the freshly loaded rules, including a changed spin cost.

## T4 cards and history

The local management hierarchy injects generated-client ports into its game view.
Only the selected machine/game loads six bounded summaries. Two shared queue
workers refresh nonempty slots with AbortSignal and expected revision checks.
Cards and opened current-result identity use the same acceptance gate; historical
result identity is never automatically replaced. Full numeric rows load on demand
and paginate50. Journal pages default20 and use backend-owned action names.

Exact pending search/save/clear/correction commands remain in per-tab session
storage until a definitive response. A new command cannot replace an uncertain
operation. Explicit recovery acknowledges only the matching editor revision and
retains a subsequently modified draft. An older refresh receipt cannot revert a
newer save; it marks the retained result stale with a recheck instruction.

Machine/game identity remains stable when live eligibility changes, preserving
the draft while current mutation controls are removed. Parent and outer Admin
navigation, including popstate, require the draft discard guard. Current-data
corrections refresh summaries/journal without remounting the draft. Historical
chart/table/start symbols stay frozen; opening its editor clearly targets current
game data and formats money using the current published spin cost.

## T5 capability boundary

Migration 0150 creates independent capability sessions and their secret-free
audit. Local link administration shares the existing ingress controller;
public structure/history use metadata sessions, while current game operations
retain their explicit game-store binding. Separate access errors cannot be
swallowed as a stale recalculation result. Failed unlock attempts are persisted
without accidentally committing a denied management mutation.

The expected session UUID travels in X-Management-Session, or in the asset URL
for browser image requests. Authentication locks the originating session and
revalidates after flush before mutation commit. Actor identity includes the
session UUID even when link labels match. Public search/symbol responses expose
opaque revisions and safe display fields; they omit storage paths and secrets.

The Reviewer proxy accepts only enumerated module routes and parameters,
checks request origin and forwards only the dedicated capability cookie.
It never forwards general Admin access. A denied obsolete request cannot clear
a newer session cookie shared by another tab. Bounded streaming applies to
request and response bodies, including valid maximum-length result tables.

An ingress retention guard checks unexpired, unlocked, unrevoked panel and
board-search sessions before the final Reviewer assignment stops the tunnel.
Panel creation and this check share a transaction advisory lock covering
ingress readiness and session commit. This protects existing shared links;
it does not guarantee computer or Quick Tunnel uptime.

## T6 shared recipient interface

Management components and their CSS live in the board-search-ui package. Local
Admin keeps its configured client and local link controls in a thin wrapper;
Reviewer mounts the same hierarchy through its management gate and generated
public adapter. Neither consumer keeps manually divergent response types.
Public assets and requests retain their originating capability identity.

Session access is distinct from game/assignment eligibility. A live access fence
guards structure reads/writes, search, corrections, result loads, recovery and
late callbacks. Expiry or denial preserves the mounted dirty editor, acknowledged
history and uncertain operation. Recovery namespaces include the capability
identity and use per-tab storage. A later cookie cannot transfer an old command
to a different author. Human labels are formatted for both journal consumers;
stable session UUIDs remain part of the persisted actor/receipt identity.

Existing Admin imports are retained through compatibility wrappers. The previous
search/share workflow keeps its default behavior; focused regressions protect
its navigation, corrections, saved-selection ports and rendering.

## T7 acceptance and operations

Fresh application-role PostgreSQL processes verify retained saves/history and
capability denial independently of the original application session. Existing
archived-game deletion preflight discovers management RESTRICT references and
rejects before its destructive lifecycle. The original implementation had no
deletion mechanism; D-536 adds separately confirmed structural scope purge.

`npm run reviewer:management:browser` prepares a finite static fixture and runs
installed Chrome/Edge with its own headless profile. Actual shared React/CSS,
touch events and390px geometry protect the recipient hierarchy/search/save/open/
clear workflow. Mock transport retains the generated public shape and originating
session identity. This fixture does not start API/Admin/Reviewer/tunnel services
or exercise production assets. The runner has bounded commands, a flow deadline
and cleanup restricted to its own browser process.

Management-specific controls use existing theme variables and44px targets; the
shared board-search defaults remain unchanged. Final isolated source copies
protect the operator's running application build directories during acceptance.

See [the operator guide](../process/MANAGEMENT_PANEL_OPERATIONS.md) for the exact
migration ancestry, verified binary backups, restricted application role,
manual local/public startup, session recovery/revocation and availability limits.
Physical devices, live ingress, a computer reboot and production-data timings
remain explicit rollout gates. Automated fixtures do not imply those checks.
