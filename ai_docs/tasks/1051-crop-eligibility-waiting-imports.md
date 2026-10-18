---
title: TASK-1051 — Crop eligibility for imports waiting for review
status: todo
last_updated: 2026-10-18
---

# TASK-1051 — Crop eligibility for imports waiting for review

## Status

`todo`

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

- [ ] Domain and PostgreSQL tests for each import status.
- [ ] The 40 P1 blobs pass or carry a reason other than the import status
      (read-only check on a test database built like the existing P1 comparison).
- [ ] Lint, mypy, focused tests pass; audit closed.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests -k "source_crop_eligibility or source_image_crops"
```

## Risks / open questions

- More originals become eligible at once; the run limit and previews stay the
  operator's control.

## Outcome

Wypełnia agent po pracy.
