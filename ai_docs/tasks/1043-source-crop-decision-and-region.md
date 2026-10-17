---
title: TASK-1043 — Decision D-562, documentation and pure crop functions
status: todo
last_updated: 2026-10-17
---

# TASK-1043 — Decision D-562, documentation and pure crop functions

## Status

`todo`

## Goal

D-562 and the requirements describe the verified cropped variant of a managed
original, and pure functions for the crop region, verification rule and crop
attestation exist with tests for the plan examples.

## Context

Stage A of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md)
(R1, R2 revision 1, R6, R7). The requirement that a managed original stays the
immutable decode source changes by operator decision of 2026-10-17.

## Dependencies / entry conditions

Plan accepted; stage A ordered with audits. No DB or file changes.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (plan table). Escalate if the orientation
mapping or the verification rule cannot express the measured P1 result.
Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md`, sections 2–4
- `ai_docs/requirements/IMAGE_INGESTION.md`, sections „Discovery” (originals) and 2 „Normalizacja”
- `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` (managed original identity)

## Scope

- D-562 full entry and index row.
- Requirements and architecture text for the cropped variant (no behavior yet).
- New pure module `services/api/src/game_predictor_api/domain/source_crop.py`:
  protected bbox, margin, orientation mapping (1, 3, 6, 8), iMCU alignment,
  `not_beneficial` rule, verification mask rule, attestation canonical JSON
  build/parse/validate and deterministic crop/attestation relative paths.

## Out of scope

Database, loaders, jobs, API, UI, running `jpegtran`.

## Acceptance criteria

- [ ] P1 example `[43,0,775,478]`, 1080×589, 4:2:0 → oriented crop `[32,0,784,480]`.
- [ ] Orientation 6 and 3 with nonzero offsets round-trip; 2/4/5/7 → `SOURCE_CROP_ORIENTATION_UNSUPPORTED`.
- [ ] The crop always contains bbox + margin or reaches the image border.
- [ ] Verification rule accepts mismatches only on the 1 px ring of non-border crop edges with protected quads ≥ 8 px away.
- [ ] Attestation round-trips; a changed field or checksum is rejected.
- [ ] `ruff`, `mypy --strict`, focused pytest, `docs:check` pass.

## Technical notes

Region and verification rules: plan R6 and R7. Coordinates are
`exif-normalized-rgb-pixels-v1`; boxes are half-open `[left, top, right, bottom)`.
Attestation fields: plan R2 revision 1.

## Expected files

- New: `services/api/src/game_predictor_api/domain/source_crop.py`, `services/api/tests/test_source_crop.py`.
- Existing: `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/decisions/DECISION_LOG_2026.md`,
  `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`, code map.

## Test cases

Plan R6 examples; orientation round trips; clamp at borders; alignment for 8×8,
16×8, 16×16; verification masks (ring only, inner mismatch, quad too close);
attestation tamper cases.

## Verification

```powershell
# from the worktree root, timeout 120 s each
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop.py
D:\game_predicotr\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/source_crop.py services/api/tests/test_source_crop.py
D:\game_predicotr\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/domain/source_crop.py
```

## Risks / open questions

- Sequence-label regions per source are resolved in TASK-1044.

## Outcome

Wypełnia agent po pracy.
