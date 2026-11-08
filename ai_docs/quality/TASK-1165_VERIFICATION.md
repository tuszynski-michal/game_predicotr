# TASK-1165 — Verification (R2 audit pending)

## R1 findings and single correction round

Terminal R1 returned REVISE (P0=0, P1=1, P2=4). The earlier 480.1-second
transport timeout had no verdict; the bounded retry remained R1. The coordinator
owns the retained audit/receipts and the focused R2. No executor audit or commit.

- **P1-1, corrected; R2 pending:** labels keep their original annotation UUID,
  byte SHA and content SHA. A separate `contentTargetSource` binds each target's
  UUID/bytes/EXIF/frame. Sharing requires game/pixel SHA/slot, matching normalized
  dimensions/coordinate space/adapter and sequence. The worker validates both
  identities; actual original copying verifies bytes and decoded pixels. Capture
  catches known ContentError per board, clears ambiguous labels and records the
  reason. Sampling reports source/position failures, without raw population-wide
  ContentError. New-policy pins expose `canonicalBoards`, `contentUsedBoards`,
  `contentQualifiedBoards`, `contentMissingBoards`, `contentReasonCounts`; this
  does not rewrite roles or solver counts. Missing optional TRAIN labels retain
  valid geometry; a genuine sequence/frame conflict excludes the ambiguous target.
- **P2-1, corrected:** bounds are checked before Pydantic revision construction;
  an out-of-source quad returns typed HTTP422 CONTENT_QUAD_OUTSIDE_SOURCE and
  cannot append a revision. Both ordinary and blind writes use the same guard.
- **P2-2, accepted boundary/remaining risk:** ordinary GET is outside the blind
  protocol. D590 and T5 require an isolated empty workspace without prior labels,
  proposals or retry-body hydration. This is not a technical prohibition on
  exposure through another workflow. No global application lock was introduced.
- **P2-3, corrected:** `annotationProgress` describes live labels; top-level
  state/games and `frozenPinCoverage` describe immutable worker inputs, with
  `basis=frozen_content_pins`. Legacy absent pins remain unknown. A source whose
  rejected frozen targets fall below its canonical board count remains an
  unresolved photo and cannot silently shrink the evaluable denominator.
- **P2-4, corrected under accepted D590 policy:** checkedBoards, blockedBoards
  (actual render_contract_blocked only) and notEvaluableBoards are separate.
  Renderer blocks take precedence; otherwise missing visible evidence gives
  not_evaluable. Only all-checked yields qualification ready. Repeatability can
  freeze without full content qualification; legal TRAIN negatives remain usable.

### Correction-round evidence

- Focused domain/worker checks: **17 passed in 1.66 s**. Added TRAIN-negative pin
  check: **1 passed in 2.54 s**. Subsequent counts/omitted-frozen-target tests:
  **2 passed in 2.31 s** (actual content_pin sequence failure plus explicit counts;
  repository readiness retains unresolved membership).
- Final request tests: **2 passed in 2.12 s**, including real repository write
  validation mapped to HTTP422 and live-vs-frozen readiness response. SDK build,
  wrapper request **1 passed**, OpenAPI currentness and generated-client drift PASS.
- Actual disposable PostgreSQL alias test:
  `services/api/tests/integration/test_grid_content_alias_pipeline.py` —
  **1 passed in 38.02 s**, with fresh-process cleanup **0 databases/0 roles**.
  Source one is the actual owner (9 targets accepted); source two is legitimately
  excluded by CURRENT_OWNER_UNAVAILABLE. Direct production pin projection on both
  SQL identities plus real copy_source and worker reader validates alias binding;
  it does not grant membership to the non-owner. Non-owner approval is rejected,
  revision1/provenance remain intact. Actual preview calls prepare_split, counts
  one deduplicated full photo/four missing, and creates no roles/cohorts. A third
  occurrence with sequence130 instead of110 produces counted identity rejection.
  Tampered bytes/pixels/dimensions and cross-game reads are rejected.
- Alias runs1/2 failed normally (37.67/38.72 s) because the initial test assumed
  two simultaneous current own targets. Source-specific diagnostics exposed the
  earlier ownership guard; the coordinator approved the narrower real proof.
  No guard was bypassed, no supersession or artificial revision2 was forced.
  Details: artifacts/TASK-1165_CONTENT_ALIAS_TEST.md and run3 log. This is not a
  claim that the auditor's assumed simultaneous-owner state was reproduced.
- Alias PG passed before adding per-pin count telemetry and the unresolved-photo
  readiness check. Those later independent branches have the two scoped tests
  above; the unchanged old full pipeline was not repeated. No claim that every
  verification ran against one final hash.

Final correction-round Ruff format/check: **12 changed Python files PASS**;
mypy with `--follow-imports=silent`: **8 changed source modules PASS**.
Code maps regenerated. `docs:check` PASS: 652 links/588 entries, startup
44347/45000 bytes, CURRENT_STATE16356 bytes (5 active/10 done), skill mirrors2.
Commands used explicit subprocess timeouts ≤120 s, worktree cwd/PYTHONPATH,
and unique test temporary directories. No old broad suites or full pipeline rerun.

## Verified so far

- Focused domain, sampling, HTTP and actual production renderer plus disposable
  PostgreSQL: **18 passed in 40.33 s**. PostgreSQL exercised full Alembic0182,
  own source saved by the existing guarded writer, independent CAS, exact replay,
  cold subprocess read, two-game RLS, immutable history and real `prepare_split`
  returning counted missing labels/ancestry without role writes.
- Final scoped mypy: **31 source modules passed**. Ruff format/check: **41 files passed**.
- Admin client TypeScript/build: PASS. New wrapper request test: **1 passed**.
  OpenAPI and SDK were generated from backend DTOs; no generated types edited.
  Final `export_admin_openapi.py --check` and generated-client drift check passed.
  Final code-map generation and `docs:check` passed (652 links/588 entries,
  startup 44332/45000 bytes).
- Existing cohort request regression: **13 passed in 1.86 s**, after fixing
  omission of the new optional null field from the legacy command body.
- Broader adapter/role/cohort/visibility regression: initial **117 passed / 10
  failed**. One T2 failure (legacy body null field) was fixed and the complete
  13-test request module then passed. Remaining **nine pre-existing fixture
  failures** reproduced identically against exact git HEAD module sources in a
  fresh process: six fixtures omit `nodes`, two mock SQL v3 although HEAD uses v5,
  one omits `policyVersion`. The bounded reproduction returned 9 failed / 5 passed
  in 0.69 s. Cwd, PYTHONPATH, HEAD, module.__file__ and executed source hashes are
  retained in `artifacts/TASK-1165_BASELINE_FAILURES.json`. No full-suite PASS is
  claimed and unrelated fixtures are unchanged.
- Full actual PostgreSQL pipeline: **1 passed in 92.49 s** in
  `test_grid_content_cohort_reference_pipeline.py`. It exercises guarded source
  writes, legacy freeze, two blind passes and renderer qualification, new-policy
  prepare/capture/materialize/freeze and actual worker A/B/REG readers. It verifies
  exact blind A nodes/quads/SHA, role-specific qualified-label SHA, canonical proof
  retained separately, unchanged legacy serialization and canonical rows including
  PostgreSQL xmin. Evaluated REG is exactly fresh5; old REG has
  contentExcluded/eligibleBoards0/used=false. Direct SQL progress mutation is
  rejected. A separate fresh process confirmed owned database/role cleanup0/0.
- Prior pipeline runs ended normally: fixture A4 after B assignment (78.31 s),
  actual JSONB report-null defect (79.35 s), fixture missing repository bind
  (67.95 s), fixture int-versus-float expected JSON hash (97.28 s). Only the JSONB
  defect required production correction. Other fixes corrected fixture setup
  without bypassing admission or weakening assertions. Full details/log paths:
  `artifacts/TASK-1165_CONTENT_PIPELINE_TEST.md` and its five bounded run logs.
- Final readiness/HTTP branches: **15 passed in 2.33 s**, including five fully
  labelled photos plus two unknown members of one component, unresolved role
  photos, and selection_ready/not_evaluated separation. These changes occurred
  around the final pipeline run: the pipeline establishes the fully labelled
  unknown0 case; scoped tests establish the later incomplete-membership branches.
  Results are not claimed as one suite run at one identical source hash.

## Runtime workflow

The T2 task now specifies exact session/reference/readiness endpoints and
the T5 caller contract. Blind sessions have durable pass1/pass2/frozen
states, source-only reads, 24 manual nodes and 15 content cells per board,
CAS/idempotent command receipts and actual second-pass renderer evidence.
The ordinary geometry writer is not called by the content workflow.
T5 must provide a separate clean canvas; the existing proposal-prefilled
geometry editor is not a blind labelling interface. No actual operator
annotations or qualification have been performed.

`targetSelection` explicitly chooses slots across the exact sourceIds; 30 boards
on 10 photos need not expand to 90 boards. Session listing enables durable resume.
The optional content policy uses blind pass2 as actual A nodes/cell quads, with
session/content/nodes SHA pins and canonical proof retained separately. Legacy
capture stays byte-identical. New qualified label hashes are calculated after A/B
assignment and materialization preserves the exact reference. Historical REG
reservations remain protected but `contentExcluded` prevents their use/counting
as new fresh evaluation controls.

Session progress contains scalar revision references, not cell documents. The
exact-key trigger comparison strengthens the storage contract; it is not a claim
that prior code allowed mutation of an existing cell document. The full pipeline
test exposed JSONB `None` versus SQL NULL for the pre-freeze report; ORM now uses
`none_as_null=True`. The final pipeline run verifies that correction.

## Manifest integration

Read-only inspection found **four current production modules** importing
manifest v21, rather than five distinct modules: `catalog_repository.py`
(`CREATE_TABLES`, `VERSION`), `game_partition_lifecycle.py` (four imports),
`game_storage_routing.py` (`GAME_TABLES`, `VERSION`) and
`grid_cohort_asset_retention.py` (`ADDED_GAME_TABLES`, `GAME_TABLES`, `VERSION`).
All now reference additive v22. The fifth integration point is ORM registration
in `storage/models.py`; it is not a separate manifest consumer. Historical
manifest v21 remains unchanged. Alembic0182 is additive after0181.

## Pending / explicitly not claimed

- T4 propagation of the already implemented low-level optional sampling policy
  through correction parent/child/experiment, and T5 isolated operator UI.
- T3 independently frozen neural-input content-cropped evidence; T2 deliberately
  does not invent `contentReferenceInputCropped` from geometry or source labels.
- Operator labels, real fresh REG selection/import, training and qualification.
- Independent audit and commit/closure. No PASS is claimed for these items.

## Odbiór koordynatora

Formalny focused R2 CLI Opus5.5, effort żądany high: PASS. Pełny raport i receipt
przeczytane; SHA pakietu/raportu oraz59 źródeł zgodne. P0/P1=0. P2-2 przyjęty
jako jawna granica D590/T5; P2-5 i P2-6 fail-closed przekazano do T5/T3 wraz
z wymaganymi testami i opisano w Outcome. Brak trzeciej rundy T2.
T2 jest odebranym kodem, nie kwalifikacją rzeczywistego operatorowego modelu.
