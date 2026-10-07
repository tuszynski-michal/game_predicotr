---
title: Astra review of the import report performance plan
status: reviewed
last_updated: 2026-10-07
---

# Astra review of the import report performance plan

## Scope and result

The user explicitly requested an independent design audit by `gpt-6-astra`
with `high` reasoning. The reviewer read the relevant code and the full plan:
[IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/delivery/IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md).

Final result on 2026-10-07: **no open P0–P2 design findings**. The reviewer
confirmed that all seven findings from the first concrete draft were resolved.
This is acceptance of the proposed design, not verification of an implementation.

## Findings and resolution

| Finding                                                                                                               | Priority | Resolution in final plan                                                                                                                                                                                                                  |
| --------------------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-09113 required descriptor/revision columns that only TASK-09115 would create.                                      | P1       | Minimal additive migration belongs to TASK-09113; TASK-09115 owns later catalog fields and pagination.                                                                                                                                      |
| An advisory-session check followed by CAS on another connection left a filesystem race after DB disconnect.           | P1       | Use a system byte lock per upload on the verified local Windows filesystem, outside rename/delete trees. Hold its handle across DB failure, abort and finally; all mutators participate. Shared-root/two-process tests are release gates. |
| The draft claimed exact/start compared all actual canonical owners, although the current checksum uses scalar counts. | P1       | Remove the stronger claim. Preserve existing exact guards and worker owner protections; no new owner-map digest/CAS is silently introduced.                                                                                               |
| Filtering by purpose would hide legacy rows whose new purpose column is NULL.                                         | P1       | A separately paginated, game-scoped legacyUnknownMetadata bucket surfaces such rows without inferring purpose or declaring readiness.                                                                                                     |
| Draft canonical first/last field names differed from the existing API.                                                | P2       | Preserve firstUnresolvedSequence/lastUnresolvedSequence; distinguish new sourceFirstSequenceNumber/sourceLastSequenceNumber.                                                                                                              |
| Legacy preparation left the job type, identity and dispatch unspecified.                                              | P2       | Reuse JobType.VALIDATE with browser_import_report_projection, explicit versioned input, canonical identity, durable checkpoints and existing validation dispatch.                                                                         |
| Reading all range metadata before SQL contradicted bounded memory for large folders.                                  | P2       | Validate the immutable root/descriptor and use a bounded, independently checksum-validated page iterator; no whole-folder collection.                                                                                                     |

The preliminary review also required separate overview/canonical/exact
contracts, source metadata before the first geometry preflight, atomic pointer
publication, preserved historical pinned profiles, SQL filters before LIMIT,
independently verified detail fragments and restart/lost-response scenarios.
These safeguards are included in the final plan.

## Final reviewer statement

The final reviewer reported: “Brak otwartych P0–P2 w projekcie.”

The reviewer confirmed the ordering of migrations, legacy handling, API
contracts, pinned preflights, indexes and validation dispatch. All eight task
model assignments match their descriptions. The local OS lock addresses the
identified DB-session-loss window only within the explicitly described local
Windows deployment; other host/filesystem topologies require a separate design.

## Evidence limits

- No product code, dependency or database change was made during this audit.
- No services were started/restarted. No database connection, test suite or
  benchmark was run by the independent reviewer.
- Existing file-only measurements establish the manifest-validation cost;
  they do not establish end-to-end HTTP latency, SQL plans or index efficacy.
- The proposed 2-second overview and 5-second canonical targets require later
  bounded measurements of the existing real folder.
- Implementation review, live SQL/HTTP checks, restart, lost-response and
  two-process race tests remain mandatory acceptance gates.
- The plan remains proposed for user acceptance and independent Claude Code review.
