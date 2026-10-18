---
title: TASK-1051 — Crop eligibility for imports waiting for review
status: done
last_updated: 2026-10-18
---

# TASK-1051 — Crop eligibility for imports waiting for review

## Status

`done`

## Goal

Originals of settled imports — `completed` or `waiting_for_review` — can be
cropped and later deleted; active or ended imports still exclude them.

## Context

[Photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md),
revision 3 (R5). Measured 2026-10-18: every import of the library is
`waiting_for_review`, so the TASK-1044 rule (`completed` only) admits no
original. The operator chose option B (TASK-1050).

## Dependencies / entry conditions

Plan revision 3 accepted. Deletion of such originals is safe only together
with TASK-1052; the pilot deletes nothing before both are merged.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audit: Codex `gpt-6.1-sol` / `high`
(none when the quota is exhausted, recorded in Outcome).

## Relevant docs

- Plan R5, revision 3; D-562; new D-563
- `domain/source_crop_eligibility.py`, `storage/source_image_crop_repository.py`

## Scope

- `IMPORT_NOT_SETTLED` replaces `IMPORT_NOT_COMPLETED`: `completed` and
  `waiting_for_review` pass; `created`, `processing`, `failed`, `cancelled`
  exclude. All other R5 rules unchanged.
- Decision D-563 (eligibility of settled imports) in the decision log.
- Docs: `API_CONTRACT.md` (exclusion reason), `DATA_MODEL.md` if needed.

## Out of scope

Import resume (TASK-1052), runs on operator data (TASK-1050).

## Acceptance criteria

- [x] Domain and PostgreSQL tests for each import status.
- [x] The 40 P1 blobs pass or carry a reason other than the import status
      (read-only check on a test database built like the existing P1 comparison).
- [x] Lint, mypy, focused tests pass; audit closed.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests -k "source_crop_eligibility or source_image_crops"
```

## Risks / open questions

- More originals become eligible at once; the run limit and previews stay the
  operator's control.

## Outcome

Commit: v1.7.416 (hash dopisuje kolejny commit).

### Changed

- `domain/source_crop_eligibility.py`: `SETTLED_IMPORT_STATUSES` =
  {`completed`, `waiting_for_review`}; `IMPORT_NOT_SETTLED` replaces
  `IMPORT_NOT_COMPLETED`. Other R5 rules unchanged.
- Decision D-563 in `decisions/DECISION_LOG_2026.md` and the index (oldest
  row D-534 moved to the archive index).
- `API_CONTRACT.md`: the new reason, the settled statuses and the historical
  `IMPORT_NOT_COMPLETED` in older run manifests.
- Admin label for `IMPORT_NOT_SETTLED` (the old label stays for old manifests).
- Plan revision 3 marked accepted; the operator consented to the cost of
  TASK-1051 and TASK-1052 with audits (2026-10-18).

### Verification

- `services/api/tests/test_source_crop_eligibility.py`: 28 passed (every
  unsettled status excluded; `completed` and `waiting_for_review` qualify).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):
  `test_source_image_crops_postgres.py` 5 passed, including
  `test_every_import_status_is_judged_by_d563` (all six statuses; created and
  processing imports also carry `ACTIVE_IMAGE_JOB`, the test asserts
  `IMPORT_NOT_SETTLED` itself) and the cross-game test (a `waiting_for_review`
  import qualifies, a `cancelled` one does not).
- P1 comparison, read-only on the operator database (REPEATABLE READ, no
  write) with the branch code: 40 P1 blobs examined, 36 eligible; 4 excluded
  by `GEOMETRY_INCOMPLETE` and `NO_ACTIVE_BOARDS`, none by the import status
  (before the change: all 40 `IMPORT_NOT_COMPLETED`).
- ruff clean; mypy of the changed module clean apart from the two known errors.

### Audit

Codex `gpt-6.1-sol` / `high`, round 1:
[TASK-1051_AUDIT_gpt-6.1-sol.md](../quality/TASK-1051_AUDIT_gpt-6.1-sol.md),
verdict REVISE (P1-1..3, no P0). Fixed: PostgreSQL test for all six import
statuses (P1-1), `API_CONTRACT.md` (P1-2), this Outcome with the verification
and the P1 comparison (P1-3). No second round.
