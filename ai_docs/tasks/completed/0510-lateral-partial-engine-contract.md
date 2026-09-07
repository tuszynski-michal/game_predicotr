# TASK-0510 — Per-run contract for experimental lateral partial geometry

## Status

`done`

## Goal

Pin the opt-in v0.10.4 policy immutably without changing any game policy or
historical pipeline fingerprint.

## Context

The accepted TASK-0510–0515 plan adds automatic lateral partial proposals after
the manual qualification foundation. TASK-0510 is a contract foundation, not
an implemented detector or public activation.

## Dependencies / entry conditions

- TASK-0505–0509 are committed at v0.10.225.
- Existing dirty cleanup/migration 0102 and virtual repository changes remain
  excluded. No migrations, jobs, user images, or services are changed.

## Recommended execution

`gpt-6-astra high`, matching the accepted plan. Independent review by
`gpt-6-astra high` is required for replay and contract compatibility.

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

- Versioned immutable policy `structured_lattice_v4_partial_sides` and adapter
  version `structured-lattice-v4-lateral-partial-v1`.
- Additive per-run `geometryEngineVariant`, separate from per-game policy.
- Versioned rollout snapshot and explicit automatic proposal provenance,
  reusing `pending_partial`, unavailable masks, and training exclusion.
- API, OpenAPI, generated client and wrapper request regression.
- Reject unsupported/unavailable execution explicitly until integration and
  final acceptance; never silently execute v3 for a v4 request.

## Out of scope

Detection, reprocessing existing staging, UI selection and engine activation
belong to TASK-0511–0515. No database schema change.

## Acceptance criteria

- [x] Snapshot roundtrip preserves exact version, parameters and checksum.
- [x] Historical v1/v2/v3 fingerprints remain unchanged when no variant exists.
- [x] Unknown version and modified parameters fail closed.
- [x] Automatic provenance cannot be interpreted as a manual decision.
- [x] New requests are distinct from game policy and are not publicly enabled.
- [x] Focused tests, Ruff, types, OpenAPI and independent review pass.

## Technical notes

Extend the existing rollout snapshot with an optional policy and a new snapshot
schema only when present. Keep the baseline v3 config and geometry mode: full
boards still use that baseline. The new variant does not enter the game-policy
database enum. JobService pins the extension per run; public create remains
guarded until the execution path and quality gate are ready. Readers validate
the extension before any dispatch and reject unavailable execution.

## Expected files

- Existing: worker `images/pipeline_contract.py`, `production_workflow.py`;
  API `application/jobs.py`, `api/image_imports.py`, schemas; generated client.
- New: worker `images/lateral_partial_contract.py`, focused API/worker/client tests.

## Test cases

Snapshot replay, policy/config tampering, absent-extension byte identity,
per-game immutability, automatic versus manual provenance, unknown HTTP variant,
HTTP gate before staging changes, exact wrapper request body.

## Verification

PowerShell at repository root: focused pytest modules using `.venv/Scripts/python.exe`,
Ruff check/format, scoped mypy; `npm run openapi:generate`, `npm run openapi:check`,
client test/typecheck. Execute each bounded step with a 120 s limit.

## Risks / open questions

Public v4 stays gated until TASK-0515. Foundation completion must never be
reported as availability of the automatic detector.

## Outcome

### Changed

- Added strict immutable partial policy and rollout snapshot v4, preserving
  accepted full-board baseline and previous rollout identities.
- Added optional per-run HTTP choice, service pinning, typed proposal provenance,
  OpenAPI/client contract and exact wrapper request regression.
- API, JobService and worker reject unimplemented dispatch explicitly; a v4
  request cannot create or silently reuse a v3 execution.

### Verification results

- 136 API/worker tests passed (61.74 s): jobs API, image imports API, qualification,
  existing pipeline contract and new lateral partial contract modules.
- 55 generated/wrapper client tests, client typecheck and OpenAPI check passed.
- Ruff and scoped mypy (`--follow-imports=silent`, 8 changed source files) passed.
- Independent gpt-6-astra high audit: no P0–P2. P3 self-comparison coverage was
  addressed by fixed v1/v2/v3 SHA values obtained from pre-change d74fc4d7;
  25 focused contract tests passed again after adding those constants.
- New Python/subprocess verification commands used explicit 120 s limits.

### Not completed

- No automatic detector, UI activation, staging reprocess, migrations, service
  restarts or data operations. Those are intentionally outside this foundation.
- Real pipeline restart with partial inference remains TASK-0513/0515; this
  task verifies JSON replay and rejects unavailable execution.

### Documentation updates

Requirements, schema ownership, D-374 and CURRENT_STATE describe the gated
foundation and distinguish it from a working automatic v0.10.4 detector.

### Recommended next task

TASK-0511 after this accepted contract and audit.
