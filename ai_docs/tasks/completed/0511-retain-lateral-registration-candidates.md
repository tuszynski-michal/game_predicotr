# TASK-0511 — Preserve trustworthy lateral registration candidates

## Status

`done`

## Goal

Keep a version-pinned search proposal when source support fails only at the
left or right edge, without accepting it as a symbol grid or repeating ORB/RANSAC.

## Context

Registration currently discards the transformed page before local refinement
can examine a lateral partial. This task retains evidence, not a final grid.

## Dependencies / entry conditions

TASK-0510 is committed at v0.10.226. The public v4 dispatch gate stays closed.
Existing cleanup, migration 0102, virtual repository and next-env changes stay
outside this task. No services, migrations or user data operations.

## Recommended execution

`gpt-6-astra high`, matching the accepted final model table. Independent
`gpt-6-astra high` review before commit; escalate any weakening of geometry gates.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

Opt-in, same-pass candidate retention; strict horizontal-only support exception;
original homography/matching/red-evidence/order/overlap checks; deterministic
candidate provenance and exact active slots. Historical evaluation remains unchanged.

## Out of scope

Local partial fitting (0512), preflight/run integration (0513), UI and activation.
No candidate becomes a registered page, auto-anchor, crop or manual decision.

## Acceptance criteria

- [x] Left/right evidence is retained with all filename-attested slots.
- [x] Vertical clipping, invalid homography/order/overlap and weak evidence reject.
- [x] ORB/RANSAC counts do not increase; complete v3 outputs remain identical.
- [x] Candidate payload has search quads only, never final accepted geometry.
- [x] No candidate preserves the existing full manual queue contract.
- [x] Focused tests, lint/types and independent review pass.

## Technical notes

Extend registration evaluation only with an optional pinned partial policy.
Capture the already projected quads inside the existing final-gate pass; do
not call initialize/register a second time. A candidate is considered only
when the normal source-support gate fails, after matching gates already passed.
Keep red coverage thresholds unchanged and bound horizontal extrapolation.
Prefer a normal registered result if a later existing budget succeeds.
The next integration task will transport this evidence in its versioned preflight;
historical manifests and public worker dispatch are not changed here.

## Expected files

- Existing: `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`.
- New: `services/worker/tests/test_lateral_page_registration.py`.
- Relevant requirements, architecture, CURRENT_STATE and Decision Log.

## Test cases

Deterministic left/right crops of the existing textured page fixture, vertical
cuts, missing frame evidence, singular/horizon-crossing transforms, overlap,
row-major disorder, exact terminal prefix and retained full manual slot count.
Compare full and failed legacy evaluations and instrument feature/RANSAC calls.

## Verification

Repository-root PowerShell; pytest focused registration/preflight/structured
initialization tests, Ruff check/format and scoped mypy. Bound each subprocess
to 120 seconds. Independent audit precedes commit.

## Risks / open questions

Keeping original red gates may reject substantial clipping; that is safe manual
fallback, not grounds for lowering thresholds. No real-data quality claim here.

## Outcome

### Changed

- Opt-in evaluation retains a versioned candidate separately from registered
  geometry; raw analysis quads, exact slot prefix and pinned policy checksum.
- Same-pass horizontal support exception preserves match and red-evidence
  gates, validates both raw/snapped quads and rejects singular/horizon cases.
- No candidate and failed initialization preserve every manual slot without
  inventing final geometry. The next task supplies local partial fitting.

### Verification results

- Initial focused registration suite: 41 passed; wider registration/preflight/
  structured initialization/contract suite: 84 passed in 13.65 s.
- Added two explicit full-manual-slot regressions: new module 27 passed;
  final combined suite 86 passed in 13.37 s.
- Instrumented tests preserve 6 ORB and 3 RANSAC calls for each rejected side;
  ordinary complete evaluation has identical result and diagnostic payload.
- Ruff check/format, scoped mypy and task Markdown format check passed.
- Independent gpt-6-astra high review passed with no findings; commit authorized.

### Not completed

No local fitting, preflight/run integration, public activation, data operations,
migrations, restarts or real-data quality claim. No changed HTTP contract.

### Documentation updates

Requirements, schema ownership, D-374 and CURRENT_STATE distinguish the search
candidate from an accepted lattice and preserve the closed public v4 gate.

### Recommended next task

TASK-0512 after independent review and this task's commit.
