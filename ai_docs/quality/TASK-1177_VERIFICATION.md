---
title: TASK-1177 — Symbol review and freeze verification
status: active
last_updated: 2026-11-10
---

# TASK-1177 — Verification

## Changes and evidence

Bulk retains one transaction per board, ownership before row locks, exact
crop/revision checks, audit events and durable replay. It locks targets with
one SELECT per board and advances counters with committed transitions, with
whole-target reconciliation at batch boundaries. Search projection cleanup
now explicitly scopes game_id. The unchanged current-owner SQL guard is
evaluated once per board, not once per symbol; explicit game constants prune
other games' partitions.

Production freeze attests files before acquiring ownership. A catalog,
symbol and protection fence is checked under short try/NOWAIT locks before
persistence. REPEATABLE READ serialization conflicts cannot validate an old
snapshot. Busy writes are distinguished from stale labels. Existing source
providers retain their locked behavior. Queued/running bulk, imports and grid
reinference are heavy jobs for training preparation. Admin fetches a fresh
preview after STALE and requires new consent; lost-response retry retains
idempotency. Late responses cannot modify another game's panel.

## Verification performed

- Python changed vertical: **56 PASS**, including source/crop/protection,
  unchanged manifest identity, freeze fence and reentrant ownership tests.
- PostgreSQL: **8 PASS** new concurrency/progress tests; **5 PASS** existing
  queue/reconnect/racing-start tests; **1 PASS** actual manual geometry save
  with cold-process replay and stale-fence rejection.
- Admin interactions: **12 PASS**, including fresh consent after stale,
  busy writes and a late response after switching games.
- Ruff format/check PASS. Scoped strict mypy: **7 source modules PASS**,
  using the full project configuration with only third-party torch imports
  skipped and follow-imports=silent. This is not a full project mypy gate.
- Admin scoped ESLint, full typecheck and production build PASS. The build
  reports the existing multiple-lockfile/worktree root warning.
- Backend OpenAPI check PASS: public response/request shape unchanged.
  docs:check PASS; code map generated (final currentness at closure).

Logs and bounded measurements are under worktree artifacts/task1177-*,
unit-all-local-temp.log, pg-new-local-temp.log, pg-existing-local-temp.log,
pg-correction-local-temp.log and ui-symbol-local-temp.log.

## Performance limits

The same existing three-board fixture, 45 decisions and genuine production
write paths were run once per version in an owned disposable DB: **413→376
SQL**, **1.229→1.180 seconds**. This small test demonstrates fewer queries,
not a reliable throughput estimate for a large operator batch.

Read-only EXPLAIN on operator data shows cleanup previously considered all
five game partitions; now only Mumie A2's partition remains. No DELETE or
other mutation was executed. Original observations of 56-second inventory
and waiting ownership locks are in artifacts/worker-diagnosis-20261110 in
the main checkout. The optimized inventory took 2.918 seconds in one read;
the controlled old/new comparison in the same read-only snapshot hit the old
query's **12-second deadline**, while the new query returned in **3.292s**
(891 unknown,45 unreadable,214 grid issues,0 changed crops), recorded in
task1177-source-before-after.json. Do not extrapolate these query timings to
the full worker operation or promise a fixed number of seconds.

## Audit correction round

R1 terminal Opus5.5/high: REVISE,0 P0,2 P1. P1-1: API_CONTRACT and D-600
updated for unlocked attestation, busy/not-ready errors and active job types.
P1-2: exact type/status/game predicate test added and genuine queued bulk
freeze rejection tested before attestation or artifact write. P2-3 fixed:
STALE explanation remains even when refreshed data is blocked. P2-4 fixed
with a dedicated projection-not-ready message.

P2-1 retained as an explicit coverage risk: revision-fence correctness
depends on writer invariants. Architecture now lists manifest inputs whose
writers must advance/invalidate the catalog. Actual bulk/manual geometry
are covered; exhaustive coverage of other ownership writers is not claimed.
P2-2: read-only operator check task1177-active-heavy.json found **zero**
CREATED/PROCESSING jobs of the four blocking types for Mumie A2. A future
stuck job still blocks correctly; identifying it in this panel is deferred.
No automatic cancellation or override was added. R2 closed P1-1/P1-2 and
P2-3/P2-4; it identified P1-3 (Prettier). Operator explicitly authorized
one additional formatting correction and focused audit on 2026-11-10.
Both files were formatted; **Prettier check of all three changed Admin
files PASS**. P2-5 evidence counts/headings synchronized here and in Outcome.
Additional focused review **PASS**,0 P0/0 P1, observed Opus5.5/CLI,
High requested (not independently proven by CLI). Final payload SHA:
f8ddfd9df89421444bc7e9c81c0d8c7db6c313df9acd206e35a174439476c954.
Report and receipt: TASK-1177_AUDIT_claude-opus-5-5.md/.receipt.json.
P2-6 is an existing incorrectly encoded training-start error outside this
diff; retained as a documented preexisting issue. Runner accepts round1/2 only;
the extra authorized focused review uses round2 with a distinct payload SHA,
not a replay of the preceding report. R1 and R2 receipts are preserved.

## Boundaries and remaining work

No operator writes, service restarts, migration, training, publication,
merge or push. Public API shape and historical formats unchanged; no schema
migration needed. Fresh symbol/geometry edits legitimately invalidate a
preview. Heavy queue must finish before training preparation. T2 separately
repairs grid readiness and mode guidance. Terminal Opus audit PASS.
