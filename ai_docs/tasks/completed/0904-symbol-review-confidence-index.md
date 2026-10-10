---
title: TASK-0904 — restore indexed confidence-filtered symbol reads
status: done
last_updated: 2026-10-07
---

# TASK-0904 — restore indexed confidence-filtered symbol reads

## Status

`done`

## Goal

Make the exact reported 777 pending-symbol page below 60% confidence return
normally within the existing server limit, preserving all filters and ordering.

## Context

Live GET for game `bfc4f949-5c14-4850-b02a-db99610bcfa5`, symbol
`d8be5aa5-6b4a-4b91-8537-07e7280d190b`, pending, limit 2500 and
maxConfidence 0.5999999999999999 reproduced HTTP 503 in 20.207 s:
`SYMBOL_CELL_REVIEW_QUERY_TIMEOUT`, operation list, timeoutMs 20000.
Readiness itself takes approximately 0.1 s. EXPLAIN without ANALYZE shows
the broad symbol/state ordering index (cost about 1.34 million), not the
existing partial confidence index whose predicate is `source_available`.

The visibility OR includes outside cells, even though the existing source
asset CHECK requires their prediction_confidence to be NULL. An explicit
source_available predicate for confidence-filtered reads is equivalent and
lets the planner use the existing confidence index (estimated cost 46,516).
No measured latency is claimed from these cost estimates.

## Relevant docs

- `AGENTS.md` — manual user control of API and Admin
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — symbol verification
- `ai_docs/architecture/API_CONTRACT.md` — symbol-cell reads and time limits
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` — game isolation

## Scope

- Add the implied partial-index predicate to the shared confidence-filtered
  list/count/seek SQL scope, preserving logical outside cells without filters.
- Regression-test exact bounds, NULL/outside semantics and deterministic order.
- Verify the user's exact request through their already running API, plus
  neighboring pagination/filter behavior with bounded existing-data reads.
- Update relevant documentation and record the actual result before completion.

## Out of scope

Service lifecycle operations, changing 20 s/15 s runtime timeouts, page size,
new indexes/migrations, data writes, model changes, imports, push or merge.

## Assumptions / discrepancies

The user's API remains under their control; do not start, stop or restart it.
ADMIN_APP.md still says 5 s for page queries, while API_CONTRACT.md and the
existing runtime use 20 s. This predates the task. Keep runtime guards intact;
this task is an index-eligibility fix, not a timeout policy change.

## Expected files

- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
  — `_visible_cell_scope`
- `services/api/tests/test_image_symbol_review_query_storage.py`
- `ai_docs/architecture/API_CONTRACT.md` — query predicate explanation
- `ai_docs/process/CURRENT_STATE.md`
- New task file, moved to completed after verification.

## Acceptance criteria

- [x] The confidence predicate makes the existing source-available partial
  index eligible without changing query results, scope or ordering.
- [x] Outside cells and NULL confidence retain unfiltered visibility and are
  excluded only by the same confidence semantics as before.
- [x] Zero/exact/upper/lower ranges, game/symbol/state scope and pagination pass.
- [x] The exact user's live request returns HTTP 200; report actual latency,
  result count and any remaining UI verification limits honestly.
- [x] Focused tests, lint/format/type checks pass and the fix is committed
  separately on the main V1.1 branch; API/Admin remain user-controlled.

## Verification

Start with focused SQL/result regressions, then scoped Ruff/mypy and the
related API/service tests. Use an EXPLAIN-only production plan inspection and
bounded normal GET requests, never large synthetic fixtures or load benchmarks.
Every finite verification step has an explicit timeout of at most 120 seconds.

## Outcome

The shared confidence-filtered SQL scope now exposes the bare boolean
`source_available` predicate required by the existing partial confidence
index. No new index or migration is needed. Source/quality visibility,
game/symbol/state filters, NULL/outside semantics and deterministic keyset
order are unchanged. The API shape is unchanged, so no client generation or
frontend build is required. API_CONTRACT.md explains the predicate.

Verification:

- Exact live request: before HTTP 503 at 20.207417 s with
  `SYMBOL_CELL_REVIEW_QUERY_TIMEOUT`; after HTTP 200 at 4.574278 s, 939 items.
  A later fresh-client read returned the same 939 items in 0.312 s. These are
  individual existing-data reads, not a performance benchmark or SLA.
- Live pagination: 500 items in 0.313 s plus 439 in 0.187 s. Concatenation
  exactly matches the 2500-limit page; all IDs are unique, the requested
  filters match and keys are deterministically ordered.
- Admin was actually opened in the browser. Game 777, Wiśnia, pending,
  below 60%, limit 2500: range 1–939, pending 939, approved 0; preview images
  visibly render. No approval, source correction or other domain write.
- New SQL/result regressions first failed without the predicate; final
  focused suite 51/51 PASS. Scoped Ruff lint/format and strict mypy for both
  changed Python modules PASS. Mypy follows dependencies silently and skips
  the existing untyped ML-library boundary; it does not disable checks on
  either changed module. The shared SQL compiler helper now has explicit
  SQLAlchemy boundary types instead of an attribute ignore.
- Related API/domain/projection/virtual-source suites: 140 PASS, one
  pre-existing failure. The keyset API test expects a 5000 ms default but
  HEAD config already uses 20000 ms; both unchanged HEAD files confirm this
  mismatch. Neither test nor timeout was weakened or changed.
- Real PostgreSQL cancellation regression: 1/1 PASS. Full transitive mypy
  hit its 120 s limit and showed unrelated errors in board-search logging
  and worker shape geometry. No orphaned mypy process remained. Scoped
  checks above verify this fix without expanding into those unrelated modules.

Evidence: `artifacts/symbol-review-list-timeout-20261007/`, including the
EXPLAIN-only before/proposed plans, read-only HTTP verifier, verification
receipt and `ui-verification.jpg`. Tests and HTTP verification run in fresh
processes against saved source; the user's own reload process loaded it.
No agent API/Admin start, stop or restart; no schema/domain data changes,
push or merge. Browser preview may populate the existing derivative cache.

DoD: all applicable acceptance criteria are satisfied; unrelated baseline
quality failures remain explicitly outside this commit. No implementation
plan applies to this standalone bug fix. A separate follow-up may reconcile
the documented/tested default timeout with runtime policy after an explicit
policy decision. Completion v1.7.248;
68ce73a800c21c197a2cf67376792515f1c13085.
