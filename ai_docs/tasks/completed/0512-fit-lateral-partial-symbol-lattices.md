# TASK-0512 — Fit a lateral partial lattice without changing complete v3 grids

## Status

`done`

## Goal

Produce a guarded, unconfirmed 3×5 partial proposal from trustworthy lateral
registration, with correct indices and unavailable-pixel masks.

## Context

TASK-0511 retains a search quad, not a symbol grid. Complete boards must retain
their unchanged v3 result; rejected slots alone may use one bounded local pass.

## Dependencies / entry conditions

TASK-0510/0511 are committed through v0.10.227. Public dispatch remains closed.
Dirty cleanup/0102/virtual repository/next-env changes are excluded.

## Recommended execution

`gpt-6-astra high` as assigned in the accepted plan; mandatory independent
`gpt-6-astra high` geometry/index/mask review before commit. Ambiguity is a
manual result, not permission to select a plausible column shift.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

- v3 first, preserving its complete result and pixel-independent metadata.
- One 500×300 local analysis and bounded column-offset hypotheses for a
  rejected slot with matching lateral evidence; no page matching retry.
- All three rows, at least three columns/nine inliers; residual, source
  support, projective order and existing protected-content checks.
- Full-quad footprint mask before padding, automatic pending_partial
  provenance, mandatory training and anchor exclusion; no unavailable crop.
- Vertical clipping gives source preparation error, not a lateral proposal.

## Out of scope

Run persistence/reprocessing (0513), UI (0514), real-corpus acceptance and
public activation (0515). No migrations, user import or service restart.

## Acceptance criteria

- [x] Complete v3 results and calls are unchanged.
- [x] Left/right/two-sided recoveries have exact original column indices.
- [x] Multiple valid offsets, weak evidence and vertical clipping fail closed.
- [x] Only proper cell footprints determine unavailable indices.
- [x] Missing cells cannot generate virtual renders; proposal is unconfirmed.
- [x] Tests, focused lint/types and independent geometry review pass.

## Technical notes

Reuse the v19 component locator and bounded axis-fitting helpers without
changing them. A support mask excludes interpolation outside real source
pixels from candidate evidence. Fit visible relative columns once; evaluate
at most three translated index origins analytically, without another RANSAC.
The trusted registration provides a bounded search-area consistency check,
never a fallback grid. Multiple admissible origins remain manual. Reuse the
existing SourceQuad cell transform, qualification and virtual renderer guards.
Analysis-mask placeholders are not crop pixels and are never used as evidence.

## Expected files

- New: worker `images/structured_geometry/lattice_refinement_v4.py` and focused tests.
- Existing: only explicit internal exports/contracts if required; do not edit v3 fitting.
- Requirements, geometry ownership, Decision Log and CURRENT_STATE.

## Test cases

Complete-v3 replay; rejected/no-candidate zero extra pass; each lateral edge,
both sides, tilted/perspective geometry, three/four visible columns, multiple
offsets, insufficient rows/inliers, protected bbox crossing, top/bottom source
defect; mask and available virtual render bounds with padding.

## Verification

Run focused pytest modules in bounded 120 s subprocesses, then Ruff and scoped
mypy. Audit before commit. Real acceptance belongs to 0515, not synthetic
unit fixtures; no quality percentage claimed here.

## Risks / open questions

Conservative index-origin agreement may defer uncertain cases. Safety takes
priority over increasing coverage. No lowering thresholds merely for green tests.

## Outcome

### Changed

- Added isolated internal v4 adapter, leaving v3 code unchanged. Its full
  result is returned verbatim; only explicit out-of-bounds rejection is
  translated into the same failed baseline before the optional lateral pass.
- One supported 500×300 analysis, bounded deterministic RANSAC and at most
  three algebraic index origins; nine protected inliers and full row coverage.
- Reused the 0506 source-footprint mask, qualification and virtual renderer
  guard. Proposals cannot render as automatic geometry; manual confirmation
  enables only the available original logical cell positions.
- Added stable vertical preparation errors and mandatory training/anchor
  exclusion, without changing user imports or profiles.

### Verification results

- 103 tests passed in 10.34 s across v4/v3, partial masks/rendering, source
  acceptance, registration and policy contracts; new v4 module has 21 cases.
- Left, right and two-sided perspective fixtures recover exact missing-cell
  indices. Tests cover weak evidence, bbox conflict, multiple admissible
  origins, vertical cuts, no-candidate zero extra work and metadata roundtrip.
- Different initial RNG states produce identical partial payloads; new fitting
  leaves OpenCV RNG untouched. Full v3 replay is compared under identical
  initial RNG because the existing v3 fit itself has subpixel stochastic drift.
- Ruff check/format, scoped mypy and task Markdown format passed.
- Independent gpt-6-astra high audit accepted with no P0–P3 findings.

### Not completed

No public dispatch, persistence/reprocessing, migrations, service restarts,
real-source acceptance percentage or operations on user data. These remain
0513–0515. A mock ambiguity consumer verifies fail-closed selection; final
source-disjoint ambiguity/accuracy acceptance belongs to 0515.

### Documentation updates

Requirements, geometry ownership, D-374 and CURRENT_STATE document the
proposal/confirmation boundary and deterministic bounded local fit.

### Recommended next task

TASK-0513 after this reviewed commit, binding candidate evidence to immutable
source manifests and preserving manual confirmation before partial rendering.
