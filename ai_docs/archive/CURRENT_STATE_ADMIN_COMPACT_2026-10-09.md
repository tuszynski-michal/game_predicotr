# Archived current state — compact panel closure

### TASK-0922 — Durable stake selections (done)

- Six independent slots, server-validated search contexts, compact immutable
  deduplicated results, Save/Clear/Refresh and paginated retained journal.
  Existing calculator and human writer supply current data; correction/audit
  and slot/result/receipt/audit commit atomically. Additive migration0149.
- READ COMMITTED receipt visibility; bounded read-only RR snapshot on the same
  application-role engine with NullPool. Stored history reads avoid current
  game routing; trusted same-slot/context/start can be edited by another actor.
- API/calculator/search regressions95 PASS, real app-role PostgreSQL1 PASS
  (19.57s), wrappers4 PASS, scoped mypy8/lint/format/types and contract drift PASS.
  Independent astra/high review PASS, no P0–P2. PG verifies lost-response retries,
  CAS, rollback, zero hits, coherent races, stale results and process restart.
- Completion v1.7.253 / 1a93bc521316c92eaaed8443e26e2f382a72c25a.
  No live services/data, full build or public rollout.
  Earlier V7 ownership omissions remain outside scope. Next T3 / TASK-0923.

### TASK-0921 — Management points and machines (done)

- Local Panel Administracyjny tab has editable point/machine hierarchy,
  active-game assignments and archive/restore with retained detached history.
  Additive migration0148 creates shared metadata and immutable audit/receipts.
- UUID/actor/target/body checks, point-first locks and expected revisions protect
  retries and concurrent writes. Commit precedes HTTP success; per-tab pending
  commands survive reload and ambiguous5xx without losing retry identity.
- Backend/actual PostgreSQL app-role5 PASS, rendered UI4, wrapper request1,
  Admin/client types, scoped Ruff/mypy/ESLint pass. Independent sol/high review
  has no open P0–P2. PostgreSQL verifies fresh-process reload and concurrency.
- Earlier unmapped V7 tables still fail the broad ownership gate; new shared
  tables are classified. Full transitive mypy reaches unrelated worker errors;
  scoped changed modules pass. No user service lifecycle or production migration.
- Completion v1.7.252 / c708c6e63d8ee00c8a879b0beab4ed73a62fcd62.
  TASK-0928 concurrently consumed v1.7.251. Next TASK-0922 / T2, whole plan authorized.

### TASK-0921–0927 — Management panel implementation (done)

- User explicitly started the complete accepted T1–T7 plan on2026-10-07.
  D-533; delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md and dedicated requirements/
  architecture/MANAGEMENT_PANEL.md. Point → machine → active game → six stakes.
- Explicit Save only; draft pins/browsing, confirmed slot-only Clear, immutable
  prior results and retained journal, current recalculation, UUID/revision guards.
  Whole-panel named recipient, local link administration,48/72h plus old shares.
- Executors/reviewers follow accepted model table. T1–T7 implemented, audited and delivered; operator rollout remains manual.
- Startup schema guard now requires `0150_management_sessions`; the earlier
  T2 guard required `0149_management_stake_saves`. Fix v1.7.254 / `3cb140dd874ffd6378c009aa1152a9001fed6b48`;
  schema-readiness tests 12/12 PASS. API was not started.
- T2 mutations use READ COMMITTED for UUID-lock retry visibility. A bounded
  read-only REPEATABLE READ application-role session captures coherent numeric
  snapshots; primary transaction commits result/slot/receipt/audit atomically.
  Baseline branch v1.7.250 /88d5019c7e436e5bd2895220d8fe0187f9ea177a;
  pre-existing modified CURRENT_STATE/completed task receipts remain user-owned.
- No API/Admin lifecycle, production migration/data edits, hosting, push/merge,
  model activation or destructive operation is included. Live rollout user-run.

### TASK-0920 — pełna integracja V7 na głównym branchu (done)

- v1.1-vision-lab-hybrid-geometry now contains the complete calibrated V7
  engine, independent progress, output picker, full editable draft coverage,
  quick explicit approval and saved-folder review. 131 product/test files
  integrated three-way from b087ad08b62992c54f5e26191e6408d287b64273;
  later main work and pre-existing working metadata retained.
- Immutable migration branches join at 0147_merge_v7_main; no online upgrade
  or gate activation. Merged backend/OpenAPI/generated client/wrapper agree.
- Snapshot suites: 814 PASS. Fresh main processes: API 62, writer/recovery 75,
  rendered UI 62 PASS; strict changed-source mypy (46), Admin/client types,
  scoped lint/format and contract drift PASS. Offline graph/DDL verified.
- D-532; V7_BRANCH_INTEGRATION_PLAN.md;
  completed/0920-v7-main-branch-integration.md contains Outcome and manual steps.
- No data/profile/acceptance transfer, JPEG writes, service lifecycle, SQL
  upgrade, monitoring, activation, full build or push. Main runtime needs the
  user-run migration and its own verified configuration; existing WT untouched.
- Completion v1.7.250; full commit hash recorded after committing.

### TASK-0919 — wejście do działającego półautomatu V7 (done)

- Main3000 offers "Otwórz półautomat V7" to working calibration Admin3020.
  Main API8000 remains blocked/v1; pilot8020 is active/v2. Local-only navigation
  transfers no game/run identities and preserves existing main run/crop flows.
- Focused helper/form/contract tests 19/19, rendered regressions 6/6 and
  Prettier/scoped ESLint/full Admin types PASS. Remount/browser-free SSR verified.
- Actual user's URL3000 ->3020 has enabled source/output pickers, saved folders,
  estimated draft JPEG and neighbour correction. Main reload preserves entry;
  no run start or decision. Existing file-name coverage: 3135/3135 and 3190/3190.
- D-531; V7_MAIN_PANEL_TEST_ENTRY_PLAN.md; completed/0919-v7-main-panel-test-entry.md.
  Evidence artifacts/v7-main-panel-entry-20261007/. No service lifecycle, model
  activation, data transfer, merge, monitoring, push/deployment or full build.
- Completion v1.7.249; actual hash recorded after commit.

### TASK-0904 — indexed symbol confidence reads (done)

- Shared confidence-filtered SQL now exposes the existing partial index's
  `source_available` predicate. NULL/outside semantics, filters, stable order,
  page caps and 20 s/15 s runtime guards are unchanged; no migration needed.
- Exact 777 / Wiśnia / pending / below 60% / limit 2500 GET: HTTP 503 at
  20.207 s before, HTTP 200 with 939 items at 4.574 s after (later 0.312 s).
  Read-only 500 + 439 pagination matches the complete page without duplicates.
- Actual Admin browser view shows all 939 pending items and rendered crops.
  Focused 51/51, PostgreSQL cancellation 1/1, scoped Ruff and strict mypy PASS.
  Related suites: 140 PASS, one pre-existing 5 s-test/20 s-config mismatch.
  Full transitive mypy reaches 120 s with unrelated logging/geometry errors;
  scoped checks pass. Existing timeout policy and tests were not weakened.
- Saved source verified in fresh test/client processes; no agent API/Admin
  lifecycle operation, domain data write, push or merge. Evidence and screenshot:
  artifacts/symbol-review-list-timeout-20261007/. Completion v1.7.248;
  full hash is recorded after commit.

### TASK-0903 — user-controlled API and Admin (done)

- User revoked agent-managed API/Admin lifecycle. AGENTS.md now requires a
  separate explicit current request for any agent start, stop or restart;
  generic repair/testing and historical restart approval do not grant it.
- Verified this chat's API launcher 15980 and server 29900, then stopped only
  those processes. Both are absent; port 8000 was free after cleanup.
  Admin, workers, import jobs, data and configuration were left untouched.
- Local operation guide preserves `npm run api:dev` / `npm run admin:dev`
  in user-owned terminals. No replacement server was launched for verification.
- Documentation and process/listener checks only; no product-code change,
  migration, tests requiring service startup, push or merge.
- Completion v1.7.247; full commit hash recorded after commit.

### TASK-0910 — audited import report performance plan (done)

- Proposed plan: IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md. Eight dependent
  tasks cover immutable source/geometry indexes, single-request validation,
  range-bound canonical/job queries, game-scoped staging catalog, local
  cross-process source locking, fast API/Admin views and acceptance/rollout.
- Explicit user authorization for gpt-6-astra / high audit. Seven P1/P2 design
  findings were incorporated; final independent review has no open P0–P2.
  Review: IMPORT_REPORT_PERFORMANCE_ASTRA_REVIEW_20261007.md.
- Existing file-only audit measured 19.870 s manifest validation and 3.606 s
  source hashing. The proposed 2 s overview / 5 s canonical targets are not
  measured HTTP/SQL results. Live SQL/HTTP and restart/race tests remain gates.
- Plan is proposed for independent Claude Code review and user acceptance;
  model assignments do not authorize implementation. No product code, data,
  migration, service restart, training, cleanup, activation, push or merge.
- Documentation path checks: 38 valid links; eight tasks/eight model rows.
  Initial commit v1.7.245; de62ef98ff5131102b417afdd3cd2564d7526ecc.
  Numbering/format follow-up v1.7.246; hash recorded after commit.

### TASK-0902 — read-only owner lookup during unrelated maintenance (done)

- The exact Mumie staging and completed preflight belong exclusively to Mumie.
  Its active store is writable; the failing owner probe accidentally requests
  WRITE on the independent 777v2 store, which remains `migrating`.
- Known owner SELECTs are typed reads. RLS, explicit game predicates,
  ambiguity detection and generic unknown-SQL WRITE fences remain unchanged.
  Isolated application-role PostgreSQL 25/25 and routing/import 64/64 PASS;
  scoped Ruff format/lint and strict mypy (implementation and test) PASS.
- Controlled API restart loads the committed source; health HTTP 200.
  Authorized staging `27d385b1-1580-4ece-b815-2667da19a1b7` created exactly
  one Mumie import `d82d9aba-d59c-46f7-9ee8-8a7415565e3d`. Fresh-process
  HTTP GET 200 and scoped retention read confirm its durable Mumie ownership.
- Start took about 71 s, outlasting the diagnostic client's 55 s timeout.
  Server audit confirms success; the durable job survived response loss.
  It remains `created` in the running general worker's queue; full processing
  was not awaited. Preflight takes about 32–35 s for this large neural manifest.
- Neither 777 game was provisioned, activated, reassigned or deleted; their
  statuses remain original 777 `active`, 777v2 `migrating`. No schema/API shape
  change, model activation, cleanup, push or merge.
- Evidence: artifacts/mumie-import-409-20261007/. Completion v1.7.244;
  full commit hash recorded after commit.

### TASK-0899 — fast quality overview and independent grid (done)

- User rejected the 45-second timeout. Page entry now requests SQL-only
  current-owner logical approvals; exact cohort preparation is explicit at
  training intent. Counts do not claim pixel attestation/training eligibility.
  Grid controls mount independently of symbol loading/errors/preparation.
- D-529; plan MODEL_QUALITY_OVERVIEW_FIX_PLAN_20261007.md. Fresh-process
  read-only HTTP overview: 200 in 0.922 s, 29201 logical approvals across
  6146 boards / 1384 sources. No image reads or production writes.
- Exact preview runs only at explicit training intent and retains checksum,
  source protection and freeze guards. UI has cancellation and no arbitrary
  45-second timeout. OpenAPI and generated-client contracts agree.
- Python 64/64, Admin helpers/contracts 17/17, rendered interactions 8/8 and
  client 76/76 PASS; scoped lint/format/types and API/client drift PASS.
  Isolated Admin build PASS in 31.7 s; live build directory untouched.
- Existing API reload serves overview: HTTP 200 in 0.937 s; generated-client
  metadata reads below 0.5 s each. No manual restart/deployment was performed.
  Test browser showed independent grid but network failures also affected game
  catalog/RSC; complete live UI walkthrough is unconfirmed. Rendered grid-state
  preservation, errors, cancellation and training confirmation tests PASS.
- No production mutation, migration, training, activation, cleanup, push or merge.
  Evidence: artifacts/model-quality-overview-20261007/verification.json.
- Completion v1.7.242; full commit hash recorded after commit.

### TASK-0900 — five GiB image storage reserve (done)

- Default hard reserve for managed image operations is 5 GiB after the existing
  conservative estimate, with exactly 5 GiB remaining permitted. Warning at
  80 GiB, automatic GC at 60 GiB and browser staging's physical 512 MiB reserve
  remain unchanged.
- Capacity admission and automatic/manual storage-GC manifests now use the same
  runtime threshold. Focused policies/configuration: 70 PASS; browser import
  capacity integration: 4 PASS; scoped Ruff and policy mypy PASS.
- API, Docker and PostgreSQL were unavailable during diagnosis. The shown
  `GAME_STORAGE_WRITE_UNAVAILABLE` is a separate non-active game storage
  status; no registry mutation, restart or import retry was performed. Read it
  after controlled service start before attempting recovery.
- Completion version/hash pending commit.

### TASK-0898 — bounded model-quality loading (done)

- Exact cohort reads group sources into up to seven execution-scoped RGB
  frames shared by atomic protection/descriptor checks. No per-cell JPEG
  decode or PNG round trip. Original SQL order, manifest and eligibility stay.
  UI reads have 45-second timeout/retry, cancellation and late-response guards;
  pending reinference preview no longer blocks quality or enables an empty action.
- Fresh-process read-only Mumie preview: 32.610 s; full FastAPI GET: HTTP 200,
  39.843 s. Both select 6303 samples / 3074 boards / 813 sources, same checksum
  138a43d3290d0fcc983d57cccfeb1aabcd41647edb08b6d1182bdd18cd11c7c8.
- Python regressions 104/104 plus last changed-branch 28/28; Admin helpers/
  contracts 14/14 and rendered interactions 4/4 PASS. Scoped lint/format/types
  PASS; Admin build PASS (18.17 s). Requirements, architecture/API narrative,
  plan and completed task updated. Evidence: artifacts/model-quality-loading-20261007/.
- No production mutation, migration, training, activation, cleanup, restart,
  deployment, push or merge. Exact pixel verification still takes tens of
  seconds; running API/Admin need controlled deployment to load this fix.
- Completion v1.7.241; commit pending.

### TASK-0897 — concurrent symbol review job starts (done)

- MAIN logs confirm start/worker deadlocks at board FK insertion. Start now
  flushes FK references before catalog locking, then refreshes and revalidates
  state/targets. A per-game/idempotency-key advisory lock protects retries only.
  Page selection skips pending/settled cards. API and 10,000 per-job cap stay.
- Real isolated PostgreSQL 4/4, focused backend/API 24/24, Admin interactions
  16/16 and helpers 40/40 PASS. Format/lint/types PASS in the scoped modules;
  dependency-following mypy timed out, local module/protocol mypy PASS. Admin
  build PASS (23.58 s). Wider backend/API: 51 PASS / 1 pre-existing timeout
  assertion failure (5,000 ms expected; HEAD already uses 20,000 ms).
- Requirements, API contract, guide, plan and completed task updated. No
  production mutation, migration, training, cleanup, restart, deployment, push
  or merge. Running API/Admin need a controlled restart to load this fix.
  Evidence: artifacts/symbol-review-concurrent-jobs-20261007/verification.json.
- Completion v1.7.240; full hash is recorded after commit.

### TASK-0896 — collapsible single-row symbol filters (done)

- State/confidence/source options have one full-width row each. Radio filters
  and date have independent accessible sections, initially open. Folding keeps
  filters, drafts, selection and target; Enter on a toggle never submits save.
  Headers retain active count/date. Fullscreen retains folding and gains space.
- Fresh-process interactions 14/14 and focused Admin contracts/helpers 40/40
  PASS; scoped format/lint/types and Admin build PASS (21.12 s). MAIN browser
  confirms desktop single rows, greater crop height after folding, 390 px
  local horizontal/vertical scroll, no document overflow or console errors.
- Requirements, guide, plan and completed task updated. No API/schema or real
  data change, training, cleanup, restart, deployment, push or merge. Evidence:
  artifacts/symbol-review-filter-layout-20261007/. No task blocker.
- Completion v1.7.239; full hash recorded after commit.

### TASK-0895 — clear the target on each symbol save (done)

- `Symbol do zatwierdzenia` clears immediately on every valid save click or
  Enter, after capturing the target for direct/bulk commands. The next save
  requires a fresh selection. Pending, error/cancel, blurry/outside and bulk
  preview retain this rule; submitted commands retain their original target.
- Fresh-process interactions 13/13 and focused Admin contracts/helpers
  40/40 PASS. Scoped format/lint/types PASS; Admin build PASS in 20.17 s.
  Existing frozen-page, filter and reference/quality behavior is preserved.
- D-528, requirements, operator guide, plan and completed task updated. No
  API/schema/layout change or real data decision, migration, training,
  activation, restart, deployment, push or merge. No task blocker.
- Completion v1.7.238; full hash recorded after commit.

### TASK-0894 — unified symbol save and approval (done)

- `Weryfikacja symboli` now has one `Zapisz i zatwierdź` with an explicit
  `Symbol do zatwierdzenia`. Same-label pending becomes approved; another
  selected active class corrects and approves. D-528 applies to all games
  in this workspace, using existing reassign/mark_blurry contracts.
- Missing target/selection blocks save. Keyboard, filter target reset,
  outside/blurry exclusions, crop/revision guards, single direct saves,
  bulk preview/durable job and frozen page retain their protections.
- API domain 32/32, Admin interactions 12/12 and focused Admin 40/40 PASS;
  scoped format/lint/types and Admin production build PASS. MAIN browser
  check confirms same-Q save is enabled and the two old buttons are absent.
- No API shape/schema changes or decisions on real user crops, migration,
  cleanup, training, activation, deployment, push or merge. Updated plan,
  requirements, contract explanation, guide, inventory and completed task.
- Completion v1.7.237; full commit hash recorded after commit.

### TASK-0893 — symbol-review import folder filter (done)

- `Weryfikacja symboli` has a game-scoped `Katalog importu` selector. It lists
  only image-directory jobs through the existing local job catalog, displays a
  safe label rather than a source path and clears on a game change.
- `importJobId` now binds page, count, direct navigation, keyset cursor and
  filter-scoped bulk selection. V2 has migration `0146` with a matching
  visible-current-cells index; no data migration, cleanup or job dispatch.
- Focused API 35/35, Admin review 40/40 and API-client 75/75 PASS; OpenAPI
  drift check, scoped lint/format/types and Admin production build PASS. The
  wider API suite retains one unrelated 5 s-vs-20 s timeout assertion.
- Completion v1.7.235; full hash recorded after commit.

### TASK-0892 — shared model family requirements (done)

- User requests published Laboratory models in the game creation catalog,
  shared by compatible games such as 777 v3 and 777 v4.
- Scope assumption: record the accepted domain direction, not implement the
  Laboratory, migrate the registry or activate models. Existing profiles and
  per-game runtime remain unchanged until a separate implementation.
- D-527 separates game records, shared families and immutable versions;
  evaluated versions can be explicitly published to the game creation catalog.
  Compatible 777 games pool qualified feedback without copying weights or
  merging boards, sequences and rules. Preserve class mapping, source origins,
  family-wide held-out protection and pinned running jobs.
- Requirements/architecture and MODEL-09/10 now distinguish current per-game
  runtime from future shared integration. Grid/symbol models remain separate.
- Fresh-process documentation review and git diff --check PASS. No code/build
  tests for documentation-only scope. No data operation or model activation.
- Completion v1.7.234; commit hash recorded after commit.

### TASK-0891 — neural preflight presentation (done)

- Actual completed job1e5c0d7d uses Mumie neural Run3/iteration03-f896da7196431be2.
  Read-only immutable manifest analysis:2575 bound photos,23175 full lattices
  eligible for neural-auto-crop-v1,zero pending slots. All2575 review flags are
  NEURAL_GRID_GATE_UNCALIBRATED, not evidence of failed geometry.
- Assumption: repair UI interpretation only; keep D-523 and source truth.
  Plan: delivery/NEURAL_PREFLIGHT_PRESENTATION_EXECUTION_PLAN.md. Record user
  request for separate shared Laboratory and main DB candidate registration.
- No DB writes, API contract changes, migration, import, training or activation.
- Fixed neural proposal/lifecycle/analysis labels and actual model export.
  Closed neural preview no longer requests all source details (actual manifest
  270.98MB); optional shared-editor labels omit classical pattern calibration.
- Unit68/interaction30 PASS, scoped format/types/lint PASS (four existing
  warnings), final Admin build PASS30.20s. Fresh actual MAIN report after
  controlled API restart shows2575/2575, correct export and enabled import;
  no closed-preview review-source request. Mobile390px has no horizontal overflow.
- API parent19632, health ok; verified old owner40856/7244 stopped. No active
  job in latest30. Explicit source inspection/report validation remain costly;
  pagination is outside this UI repair. Laboratory integration recorded in
  MODEL-09, not implemented. D-526; evidence artifacts/mumie-preflight-diagnosis-20261007/.
- Completion v1.7.233; full hash recorded after commit.

### TASK-0890 — grid diagnostics placement (done)

- User explicitly places grid problems in Korekta cięcia siatki rather than
  extending Import plansz. Assumption: UI move only, existing backend queue
  qualification and neural-auto-crop-v1 remain authoritative.
- Reuse GeometryCompletenessSection in ReviewerAccessLauncher with game-scoped
  jobs and queue refresh; retain MissingBoardsSection in import. D-525 records
  placement and separates whole-image diagnostics from V3 crop availability.
- Plan: delivery/GRID_DIAGNOSTICS_PLACEMENT_EXECUTION_PLAN.md. No DB/API change,
  migration, cleanup, import/preflight dispatch, training or activation.
- Unit47/interaction20 PASS, scoped format/lint/types PASS (existing img warning
  only), final Admin build PASS (24.39s). MAIN import has no diagnostics, folder
  stays visible; correction reload and queue refresh verified. Reused responsive
  controls; proof artifacts/grid-diagnostics-placement-20261007/.
- Historical counters retain whole-image semantics; no crop-readiness claim.
- Completion v1.7.232; full commit hash pending.

### TASK-0889 — import folder recovery and V3 registration (done)

- Diagnosis: GET browser-selections fails with GAME_NOT_FOUND for finalized
  staging owned by deleted game 2a46d3a6-bc56-4a13-8f98-dd51c88df0b2.
  Actual new Mumie folder „1 - 23175 cut” has2575 files, staging b770bcc8.
- Scope: optional retention status is null only for a deleted game; preserve
  staging files/ownership and propagate other storage failures. Panel exposes
  list errors/loading/empty states and refreshes finalized folders before
  report preparation. V3 hides classical registration; V1.1 retains it.
- Accepted repair scope: delivery/IMPORT_FOLDER_RECOVERY_EXECUTION_PLAN.md.
  No new import/preflight, DB migration, cleanup or model activation.
- Backend68 and focused4 PASS; Admin unit66/interaction13 PASS. Scoped
  lint/format/types and final Admin build PASS (35.48s), existing img warning only.
- Real API root40856/listener7244, health ok. Initial10s startup probe expired;
  process subsequently ready, no duplicate API. New folder returned as ready
  and shown with report action after page reload. V3 select absent.
- Actual read-only report:2575 sources,23175 new boards, symbol model ready.
  Fresh report labels configured V3 and hides the obsolete registration metric;
  pinned classical report labels remain. No geometry/import job was started.
- Completion v1.7.231; full commit hash recorded after commit.

### TASK-0888 — current Mumie symbol feedback analysis (done)

- Read-only MAIN analysis:126 current human-approved crops from34 photos,
  versus40 at0886;122 disagree with stored predictions. This deliberately
  edited sample is not population accuracy. All126 approved/current crop
  identities and render checks match. Fourteen preview crops visually reviewed.
- Existing preview selects81 diverse samples from30 photos/62 boards,
  no stale/missing/grid/unreadable exclusions. Q,A,Mumia absent; several
  other classes lack four source families. Freeze readiness is not training
  class/split readiness. No new cohort/job/training/activation performed.
- Active lab R2 ONNX and registry verified:3 Conv layers,RGB64,10 classes.
  Earlier283 human development/84 validation remain;443 bundle files,
  6.64MB verified. Recommend a separate qualified lab candidate combining
  current exact DB feedback with earlier human corpus, without inventing
  approvals or moving held-out sources into training. DB preview alone
  does not combine lab/DB labels; no fresh user annotation request now.
- Most corrections:A→Sarkofag42,K→Faraon22,Mumia→Sarkofag15. Visual sample
  includes blur,glare,gold frames. All disagreement confidence below0.62.
- model-quality.activeModel is hard-coded null although registry is active;
  recorded as a separate presentation gap. Whole-photo versus recording
  split limitation remains explicit. MAIN application code/runtime unchanged.
- Report: quality/MUMIE_SYMBOL_FEEDBACK_ANALYSIS_20261006.md; read-only
  evidence artifacts/mumie-feedback-analysis-20261006/. Completion v1.7.230;
  full hash recorded after commit.

### TASK-0887 — V3 import presentation and application inventory (done)

- MAIN import now shows the real Mumie neural profile as V3, omits classical
  variant arguments, and reports V3 on success. 777 keeps V1.1. V1.0/V1.2
  choices and forced V1.0 UI reprocess are hidden; history/backend retained.
- Responsive picker, existing API only; game/profile remount isolates state.
  Fresh MAIN page/reload and actual 777 picker verified without real upload.
- Import unit66 and interaction8 PASS; Admin types, scoped lint, format and
  production build PASS (34.11s). Existing Next img warning documented.
- MUMIE_MAIN_APP_OPERATOR_GUIDE expanded with exact steps and pooled symbol
  training. Draft APP_V3_FUNCTIONAL_INVENTORY.md records screen changes,
  future shared online panel, neural-grid training gap and misleading legacy
  geometry readiness/completeness descriptions for separate tasks.
- Read-only storage: main51.73GB,777 partitions48.16GB,Mumie71MB. Retained
  restore-test database46.97GB,zero connections; backup13.60GB on D retained.
  Windows C free32.16GiB; Docker VHDX106.04GB. No guaranteed host-space
  recovery without separate compaction. No data cleanup/migration/training,
  activation,push,merge or other function removal performed.
- D-524; evidence artifacts/app-v3-review-20261006/. Other pre-existing dirty
  completion hashes and unrelated folders preserved. Completion v1.7.229;
  full hash recorded after commit.

### TASK-0886 — automatic Mumie import and recoverable symbol verification (done)

- New neural-auto-crop-v1 imports render exact 24-node full bound lattices
  directly into bulk symbol verification. Missing or partial slots defer
  individually without shifting sequence numbers. Predictions remain separate
  from human approval. Legacy policy and 777 UI defaults are preserved.
- Managed reprocess validates neural schema5/v13 evidence, pins the policy
  and retries the same job. Per-sequence owner protection preserves current
  manual grids and symbol decisions; old unreviewed pending remains audited.
- MAIN Mumie recovery: 100 originals, 99 bound sources, 891 current boards,
  13,365 cells, zero failures, ready projection and exact counters. Reprocess
  af474e46-28bc-404d-af1c-07aeb05a165c completed processing 99/99 sources,
  199/199 steps and awaits bulk symbol review. Retrying returns the same job.
  Forty-four captured human geometries and two human cells preserved exactly;
  847 old pending superseded, activation histories unchanged.
- Orphan preparation starts a durable job once and offers explicit resume.
  A late previous-game response cannot overwrite or disable the current view.
  Backfill now completes unavailable historical counts in durable bounded
  batches. Final counts job 13aabb68-aa50-42b7-9176-81552ca9b651 completed;
  revision174 reports 40 approved and 13,325 pending. Current ready counts do
  not rescan. Actual Admin: page2000, 423 Mumia crop previews and working
  counters, bulk approval enabled for image-bearing selections.
- Focused API/worker108, managed21, lateral scoped15, real isolated PG2,
  manual HTTP1, count/handler12, Admin interaction9, SDK request78 passed
  (overlapping suites). Scoped Ruff/format, strict owned-source mypy,
  Admin/SDK types and lint, OpenAPI/SDK checks and final Admin build passed.
  Two unrelated failures reproduced on unchanged HEAD are documented, not
  weakened; full-suite and physical Android/OS reboot are not claimed.
- MAIN API root15292/listener10516 and worker root42784, Admin root33252 are
  controlled and healthy. Reviewer3001 and VisionLab3102 preserved. No new
  migration, cleanup, model training/activation, 777 data operation or push.
- Quality: MUMIE_AUTOMATIC_IMPORT_RECOVERY_20261006.md. Existing operator
  guide now describes bulk verification and 500→2000-photo uploads with pooled
  feedback. One ending photo still needs explicit source-range binding.
  Completion version: v1.7.228; hash recorded after the scoped commit.

### TASK-0885 — neural manual slot symbol save (done)

- Board 1405's selected cell 4 save was blocked by the source-wide projection
  gate and the rebuilding-state mutation gate. D-522 now admits only a current
  human-approved, proposal-bound manual neural lattice and its exact cells.
  Sibling slots, incomplete source, general mutation and legacy gates remain.
- Exact lattice visibility protects outside cells. Real PostgreSQL HTTP test
  covers selected-only approval, outside rollback and fresh-app retry; passed.
  Scoped 143 tests, Ruff/format and strict owned-source mypy passed. Broader
  checks: 84 passed, one pre-existing list-timeout expectation failure untouched.
- Fixed MAIN API root 46320 / listener 47872 is healthy on 8000 after guarded
  restart; initial readiness timeout recovered through checks of the same
  process. Other services preserved. No migration, cleanup, training or guessed
  production label. Operator retries Save on 1405 without changing the grid.
- Completion v1.7.227; full hash recorded after commit. Read-only proof and
  runtime/check receipts are in the main Mumie pilot and deployment artifacts.

### TASK-0884 — approved main-app pilot deployment (done)

- Actual MAIN pilot ready:100 managed originals,99 bound sources,891 pending,
  one unbound ending source. Same importf3ff4258-e561-4031-bc04-227c9dbf51b6
  waiting_for_review/attempt3,199/199,99review/0failed. No human approvals,
  approved geometry,cohorts or symbol_training. First operator review remains.
- Mumie iterationfd5b15b6-e335-410d-9720-5f2d3bd6ec43 activated by
  fa00eaa1-5f19-4675-8102-3f40e042ff7c. Qualified R2crop96/input64 and exact
  neural24-node identity preserved;777 registry/activation unchanged.
- Both histories retained: sourcev1.7.225/820083aed4b3d2dda048c938bd2f3ed410132d95
  and premerge MAINv1.7.222/48b6e0e104e19e915bde30cd89a80d508e81c0b3.
  Completionv1.7.226/full hash is recorded after commit. MAIN branch remains
  v1.1-vision-lab-hybrid-geometry. Independent RGB0878 and old dirty metadata retained.
- Live fixes: owned-listener API readiness, lab checkpoint schema_version,
  optional strict lab cropSize DTO/full generated contract, deferred crop
  producer stage contract. Real exact99-file retry preserved297 prior stages,
  checkpoint/order/digests, same job and existing pending891. No data reset.
- Final API29756/30308,Admin45912,Reviewer48888,worker38536/48684 healthy;
  MAIN ports8000/3000/3001. Vision Lab3102/RGB preserved. UI auto-preview15/15,
 24nodes, symbol-only edit and unsaved-draft reload passed without approval.
- Full13.6GB archive and retained isolated *_test restore passed. Restore filled
  C and blocked30GiB reserve; root acknowledged error and moved verified archive
  to D:\game_predictor_backups\mumie-main-app-pilot-20261006 after both fullSHA.
  Durable pointer/reconciliation passed. No DB deletion/reserve reduction.
  Earlier0143→0145 executor is unattributed; explicit migrationCLI was a no-op.
  Actual isolated migration tests and final head0145/exact777 fences passed.
- Necessary existing topology draft3×5 created through API;spinCost0 is unused
  explicit placeholder. No publication,paylines,payouts or target calculation.
- Install/builds/contracts/types/lint, scoped tests and real100 cold acceptance
  PASS. Readiness3/labworker2/query22/HTTP2/stage5/client88 tests overlap broader
  suites. Independent gpt-6.1-sol/high code/liveSQL review PASS,0 openP0–P2.
  Quality: MUMIE_MAIN_APP_PILOT_ACCEPTANCE_20261006.md; receipts in
  main artifacts/mumie-main-app-pilot-20261006. No push.
- Next: operator review of existing100, then500/2000. No further upload or
  training authorization needed to finish0884. Symbol TRAIN uses pooled human
  corrections; neural-grid refit remains separate. Super/manual10-spin selection
  is a later task proposal, not a pilot blocker. V5/R2pair still FAIL.

### TASK-0883 — pooled correction feedback and pilot acceptance (done)

- Whole-photo protections before existing caps, current human approvals and
  fresh preview/freeze/builder/reuse/first-epoch gates implemented. Legacy
  fingerprints and4000/class,64/source budgets preserved; no auto-training.
- Exact24-node human geometry export and visibility/outside masks retained.
  Initial approval needs no recrop. Checksum/interior/stale approval negatives
  and explicit legacy corner conversion have regression coverage.
- Frozen127 genuine human controls/136 proofs/24 whole sources,10 explicit
  catalog mappings; AI never becomes truth. New production promotion checks
  exact current crop and locks pending controls. OPEN is a real conflict;
  absent comparisons are NO_CONFLICT/0. R2 lab import and777 preserved.
- Root67/feedback53/truth51/installer15 testsPASS, with overlapping suites;
  independent55PASS. Two actual guarded *_test PG testsPASS including cold
  export resume and competing LOGIN update55P03/teardown. API/UI/contract,
  strict owned-scope types, Ruff/format and Admin buildPASS. Full Torch graph
  timed out; scoped check skips only third-party torch/torchvision.
- Prepared controls161files verified in a new process,0 writes to live store.
  Prepared100-photo folder ready; reuse bounded actual100 receipt from0882,
  not a population accuracy claim. Operator guide and concrete0144/0145
  deployment preview ready. Independent gpt-6.1-sol/high audit PASS,0 open P0–P2;
  commitv1.7.225/820083aed4b3d2dda048c938bd2f3ed410132d95.
  Post-commit merge-tree confirms only CURRENT_STATE/DECISION_LOG conflicts;
  MAIN stays clean at48b6e0e104e19e915bde30cd89a80d508e81c0b3.
- OperatorDB remains0143 with0Mumie sources/boards, no activation or restart.
  DB51.64GB/C:82.47GBfree measured read-only; full backup/restore not done.
  Main Admin3000, Reviewer3001, API8000;3102 is Vision Lab. API arguments
  currently have no --reload; stop it before merge/migration regardless.
  RGB0878 previewCLI remains active; safe checkpoint required before0884.

### TASK-0882 — neural folder import and correction (done)

- Frozen geometry_core CPU staging, immutable checkpoint replay, explicit
  source binding and exact24-node board correction implemented. Migration0145
  extends the existing override; missing slots are never compacted.
  Managed source handoff/exclusions work after staging retention.
- Actual Admin Import panel accepts99 review sources and all-unbound source
  handoff; replay recovers the existing job, active new descriptor is rejected.
  Symbols edit on opening; approved geometry and legacy777 defaults preserved.
- Root41 new/120 broader/24 managed-source tests; backend46 core/10legacy,
  client86, independent fresh backend96 PASS (overlapping counts).
  Disposable PostgreSQL1 PASS/0skip,9 invalid nested bindings rejected;
  populated0144→0145, CAS/cold receipt/RLS/guarded downgrade verified.
- UI pure41/final66 and Reviewer15/Admin21 interactions PASS. Types/lint,
  formatting, OpenAPI/SDK checks, strict Mypy root7/backend29 and both builds
  PASS. Mobile touch390/360×844 PASS; physical Android untested.
- Real100 source handler:900 expected,897 valid24-node proposals/13455fullcells,
  99 ordered drafts/1 unbound; five20-source steps below20s. Cold replay0/4
  sameSHA/0infer. Separate memory20 parent124.6MiB/child413.0MiB individualpeaks.
  These are structural counts, not population symbol accuracy.
- Quality: MUMIE_NEURAL_FOLDER_CORRECTION_20261006.md; final proof in main
  artifacts/grid-v3-deployment-20261004/0882-final-proof.json. Independent
  gpt-6.1-sol/high audit PASS,0 openP0–P2;commitv1.7.224/8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e.
  Continue0883 autonomously.
- No operator DB writes, main merge/activation/restart. Live0143 and0Mumie
  sources/boards confirmed read-only. RGB777 previewCLI still active.
  Prepared100-photo upload copies31.17MB preserve sourceSHA/originals.

### TASK-0881 — lab candidate registry and recovery (done)

- Explicit lab_import origin, nullable cohort only for lab and immutable
  candidate inventory/preview/VALIDATE import. No invented training epochs
  or human cohort; runtime keeps qualified R2 RGB96→64 and T1.05.
- Append-only deactivate and latest-state resolver prevent bootstrap/older
  activation revival. Receipt replay survives restart/response loss; cancel,
  retry and expired-lease recovery synchronize the import iteration.
  Cleanup fails closed before deleting the current disabled-state history.
- Backend/OpenAPI/generated client/wrapper/Admin request vertical completed.
  Operator commands persist exact inputs; authenticated retries retain receipts.
- 64 backend/worker, 83 client, 14 UI and 1 isolated PostgreSQL tests PASS.
  Actual 0143→0144 upgrade preserves production rows and verifies RLS,
  import/publication, cold-process replay and guarded downgrade.
- Ruff/format30, scoped Mypy23, UI/client lint/types, contract/drift and both
  builds PASS. Broad composition Mypy was bounded at120s; fresh API/CLI
  imports PASS. Independent gpt-6.1-sol/high audit:0 openP0–P2.
  Proof: main artifacts/grid-v3-deployment-20261004/0881-final-proof.json.
- No operator DB writes, main merge, activation or service restart.
  Commitv1.7.223/669cd5325140312e9da270bcd3c2ff194b875655 verified with
  show/stat and remaining status. Continue0882 next.

### TASK-0880 — qualified R2 RGB pilot adapter (done)

- Full source quad RGB96, padding0.0, float antialias96→64, opset17.
  Existing777 preprocessing/padding/fingerprints preserved.
- 77 focused +108 broader regression tests PASS; Ruff15files/scopedmypy8 PASS.
  Fresh manual/production runtime entrypoints work without Torch. Independent
  audit PASS,0 openP0–P2, original9352pins and actual405source cells verified.
- Candidate5e0489…a480 / manifest721257…a5c2; prepared managed package and
  package-render-preflight.json in main artifacts/mumie-main-app-pilot-20261006.
  Zero pixel/class differences, input7.15e-7/logit1.91e-6; no population accuracy.
- No DB/activation/main deployment. Next0881 registry;0882 folder/correction;
  0883 feedback/acceptance;0884 concrete migration/activation preview.
- Oddzielny commitv1.7.222 / e8de3b18d389207a5ceaa5d171e8a9e14d46c346.
  Potwierdzono show/stat i status; stare dirty metadata zachowane.

### TASK-0872 — większy izolowany RGB Mumii (done; candidate rejected)

- TASK-0871 zakończony i odebrany; HEAD `v1.7.219` /
  `d61d6981f1c68960d9c1ecb776303643b047421f` potwierdzony z historią.
- Manifest `58a064…d36b` opublikowany: R2 development327 + 1726 nowych high/high
  AI cropów, w tym Mumia109. Human84/diagnostic9/AI22 i human26/human8 zachowane.
  Pełny freeze 93.78 s; fresh-process verify 70.81 s, wszystkie 2000 quadów
  ponownie wyrenderowane. Cache źródeł i parent statów usuwa wcześniejsze timeouty.
- D-506: nowy jawny lokalny kontrakt wielu pakietów, jeden model RGB,
  20 epok / 7200 s / 50000 kroków. Stare generation1–4/API/limit100 bez zmian.
  Własny symbol_protocol_digest w lokalnym Request wiąże checkpoint; HYBRID
  protocol_digest pozostaje None. Manifest wymaga jednego zamrożonego run root.
- Pełny niezależny preflight kodu/danych PASS. Jedyny run `5302ac…8093` zakończył
  20 epok / 1360 kroków; best1, validation83/84. Pierwsza próba PID44912,
  631.21 s; fresh resume checkpoint20 PID7892, nadal1360 kroków, razem695.96 s.
  Real CPU ONNX parity PASS (max2.861e-6). Bez DB, Super i aktywacji.
- Ocena `efcdc9…5ee`: V5 odrzucony; 10/18 porównań według klas nie przechodzi.
  New19=16/19, held22=19/22, human8=6/8; human34 razem29/34 wobec R2 RGB34/34.
  Human84=83/84, old18=18/18, diagnostic9=9/9. Więcej AI nie poprawiło jakości;
  etapu0873 nie uruchamiać z tym kandydatem. Niezależny actual inference audit
  obu baseline RGB i V5 odtwarza wszystkie18 bramek; 11480 pinów sprawdzonych.
  To wybrane kontrole regresji, nie accuracy całego filmu.
- Próba anulowania ujawniła opóźniony stop w dawnym trainerze. Nowy lokalny
  LargeRgbRunManager honoruje go przy kolejnym batchu; 15 runner tests PASS.
  Stare kontrakty zachowane. Niezależny strict scoped mypy nowych3modułów PASS.
- 42 focused adapter/run/legacy tests PASS i 18 numerical training/resume tests
  PASS dla generation1–5. Dokładny R2 receipt, protected groups, resigned inputs,
  restart/budżety/fencing, defensive cache i Windows case/reparse guards pokryte.
- Final Ruff lint/format 5 modułów i 3 testów PASS. Real cp9/globalStep612
  odtworzony w dwóch procesach: identyczny batch32/images/logits/optimizer/model/RNG.
  Proof `1d4b43…06d9`, batch digest `3bd0b2…7ea3`, ledger i model niezmienione.
  Auditor w nowym procesie odtworzył sampler/augmentację/labels/generator.
  Preflight/model/ocena/replay PASS, bez otwartych P0–P2; V5 nadal REJECTED.
- Raport: ai_docs/quality/MUMIE_LARGE_RGB_EXPERIMENT_20261006.md.
  Hipoteza dalszej pracy: feedback draw share spadł z33.79% do6.84% mimo weight4;
  AI stanowi81.79% drawów. Kolejny osobno opisany eksperyment powinien kontrolować
  udział human/AI i ekspozycję zdjęć. Brak potrzeby nowych folderów/oznaczeń teraz.
- Pliki: trzy nowe moduły symbol_large_*, dwa opcjonalne reuse hooks, testy
  i dokumentacja protokołu. Wcześniejsze dirty metadata wyłączyć ze stagingu.
  Oddzielny commit `v1.7.220`; pełny hash dopisać po commicie. Cały zaakceptowany
  plan kończy bieżący etap na niespełnionym warunku C. Bez refitu/aktywacji/DB.

### TASK-0871 — większy zbiór Mumii (done)

- Po v1.7.218 większy trening nie został uruchomiony. Poprzednio podany czas
  był szacunkiem; aktualna kontrola procesów potwierdziła brak aktywnego CNN Mumii.
- Rozpoczęto przygotowanie większej deterministycznej serii z trzeciego filmu.
  Wyrenderowano 2000/2000 nowych kandydatów w 20 pakietach po 100; 916.50 s.
  Selection `12645e…69ff`, SHA `afcb8b…89fe`; 41 zdjęć, maksymalnie 54/zdjęcie.
  Pełny union 526 dawnych rastrów i 9351 pinów zachowany. Oba blind review
  zakończone: 2000 indywidualnych ocen każdy, własne fresh-process checks PASS.
- Fresh-process selection odtworzony bez zmian w 47.06 s; packet0 ponownie
  zweryfikowany w 36.62 s. Kontroler zakończył pracę; brak aktywnego CNN.
  Fresh aggregate odtwarza ID/pointer/bajty w 14.86 s. Qualification `8a57f6…8ac8`
  ma 11472 piny, 1726 high/high accepted i 274 rejected; Mumia 109.
  To liczności danych z AI, nie pomiar accuracy. Bez targetów Super/human approvals.
- 12 focused tests PASS; Ruff/format 4 i mypy 3 helperów PASS. Niezależny audyt
  wszystkich 2000 source/quad/pixels/montages i 40 review/20 proofs PASS;
  14 dodatkowych detached negative guards PASS. Końcowy niezależny audyt PASS,
  brak otwartych P0–P2. Oddzielny commit `v1.7.219`; hash dopisany po commicie.
- Zachować pierwszy film, human26/human8, validation/diagnostic i dawne AI audit
  poza nowym development. Bez zmian historii człowieka, modeli i aplikacji.
- Zaakceptowany zakres autonomiczny: MUMIE_LARGE_TRAINING_EXECUTION_PLAN_20261006.md.
  Najpierw przygotowanie i dwa blind review; CNN dopiero po kwalifikacji 0872.
  Bieżąca decyzja nie obejmuje DB, migracji, usuwania, merge, push ani aktywacji.
- Wcześniejsze brudne metadane wyłączyć ze stagingu. Po commicie kontynuować 0872.

### TASK-0870 — osobna diagnostyka RGB (done)

- Eligibility `5b6af3…4ac7c`: wszystkie dziewięć bramek RGB według klas i grup
  przechodzi (human84/18/19/9, held22/4, nowe control3/directed5/all8).
  Sprawdzono 9352 oryginalne piny oraz powiązania modeli, temperatur i metryk
  z niezmiennymi dowodami. Diagnostyka używa dokładnie dwóch eksportów RGB.
- 60 zdjęć / 8100 identycznych wycinków; porcje po 20 zdjęć, limit kroku 120 s.
  Czasy: 26.20 / 20.44 / 24.16 s. Osobny sidecar RGB zawiera 33 zmiany klas;
  liczba wyników poniżej progu pewności 0.9 spadła z 704 do 490 (o 214).
  To nie jest pomiar poprawności całego filmu. Nowych oznaczeń zapisano 0.
  Nowe osiem przykładów: RGB 8/8; łącznie 34/34 na dwóch wybranych zestawach.
- Powtórna inferencja obu CNN odtworzyła 60 zdjęć / 8100 wycinków bez różnic
  w logitach. Czasy porcji: 26.38 / 33.66 / 45.14 s. Replay: 9474 piny,
  digest `b3f13c…b6f1f`, siedem grup kontroli negatywnych PASS.
  Wznowienie porównania: 18.30 s, 0 nowych zdjęć. Wznowienie weryfikacji:
  35.50 s, 0 nowych zdjęć; 60 markerów, digest i bajty raportu identyczne.
  Ścisła walidacja wyników, quadów, pikseli, modeli i historii odrzuca zmiany.
- Niezależny końcowy audyt artefaktów, replay, wznowienia i dokumentacji PASS.
  Obie wcześniejsze uwagi poprawione i sprawdzone; brak otwartych P0–P2.
  17 testów inferencji PASS; cztery helpery: Ruff, formatowanie i typy PASS.
  TASK-0869 osobno: 43 testy PASS.
- Human8 revision8, human26 revision27 i oba wcześniejsze zestawy 61 wyników
  zachowane. V4 pozostaje kwalifikowaną parą; R2 combined gate=false,
  sidecar odrzuconej pary nadal nie istnieje. Bez treningu, refitu ani aktywacji.
- DoD, pięć kryteriów i kroki 1–4 zaakceptowanego planu spełnione.
  Raport: MUMIE_RGB_ONLY_DIAGNOSTIC_20261006.md. Commit `v1.7.218`.
  Wcześniejsze zmiany metadanych wyłączone ze stagingu. Etap 0869–0870 ukończony.
  Bez zmian API/UI/schematu/DB, migracji, usuwania, Super, merge, push i wdrożenia.
  Użytkownik nie musi powtarzać ośmiu oznaczeń.

### TASK-0869 — nowe osiem zatwierdzeń Mumii (done)

- Exact human8/revision8 z pełnym history/receipt/dictionary/source/quad/PNG.
  Pierwszy film poza symboldevelopment312/327,0photo/pixel overlap.
  Category nadaje własne caseIDs; join pełnym bindingiem, previous_case_id zachowane.
- Actual sześć ONNX:control3 wszyscy3/3;directed5 V3 RGB5/gray2/fuzja2,
  V4 5/3/5,R2 5/3/4. All8 RGB8 każda generacja,gray5/6/6,fuzja5/8/7.
  R2 RGB noweperclass/group gates PASS; wcześniejszehuman26 RGB26/26,łącznie34/34
  na dwóch wybranych zestawach. Nie jest to accuracy całego katalogu.
- Zero accepted AI/humanconflicts;7dawnychunresolved rozstrzygnięte przez człowieka,
  52pozostałe AI-only. Żadnych nadpisanych ocen, pseudo-zgód ani training/refit.
- Proof9d02a5…c5833, actual75.09s/fresh81.67s byte-identical.
  Replay11.86s:9349pins,rerender8,5negativeguards PASS,setSHAd715e61…da9d51.
  Human26 i oba61-output sets zachowane;43pytest,2helperRuff/format/types PASS.
- Independent final audit PASS,0openP0–P2;DoD/sixcriteria/plan1–4.
  Quality MUMIE_FIRST_HUMAN_CHECK_20261006.md;commit `v1.7.217`.
- Accepted MUMIE_FIRST_HUMAN_CONTINUATION_20261006.md:po audit/commicie kontynuować
 0870 conditional RGB-only diagnostic istniejących8100, bez nowej pary/aktywacji.
  QualifiedV4/rejectedR2combined bez zmian. Bez DB/Super/API/UI/merge/push/deploy.
  Wcześniejsze dirty metadata wyłączyć ze stagingu. Nie potrzeba kolejnych8/folderu.

### TASK-0868 — drugi izolowany eksperyment Mumii (done)

- Etap0867–0868 wykonany bez interakcji operatora; oba taski mają osobne commity.
- Dwa blind review100 exactPNG/20anchors:76high/high;327development=283human+44AI
  wobec312/AI29 w V4. Audit22, human84/diag9 oraz human19/5unreadable zachowane.
  Human26 całe zdjęcia/decoded aliases i pierwszy film wykluczone z development.
- Jedna para gen4,seed20261005,20ep/280steps:RGB633.28s/best8,gray606.19s/best6.
  Calibration/best tylko human84. Oba controlled workery zakończone, brak retry.
- Pairdbe76d…7e815:human84=83/84,old18=18/18,new19=19/19,diag9=9/9 dla każdej
  gałęzi/fuzji; wszystkie dotychczasowe perclass gates PASS. AI22/44 agreement100%.
- Held2eaefe…41820:RGB25/26→26/26;gray i fuzja26/26→25/26, nowy błąd Ra→J
  w directed4 (board4/field11,seq_27118-27126.jpg). Combined human gate FAIL.
  R2 RGB zachowany eksperymentalnie, V4 pozostaje qualified pair; brak aktywacji.
- Transfer pierwszego filmu:control47/47 każda gałąź;directedRGB6/gray5/fuzja5
  z6 wobec V4 6/5/6. AI agreement nie zastępuje human accuracy.
- Brak R2 sidecara8100:actual max-photos1 odrzucony stabilnym failed-gate guardem.
  Stare61 wyniki/model/raster/history bez zmian; brak refit/extra run/nowej pary.
- Independent ONNX/checkpoint196 rastrów:classes identyczne,maxabs3.8147e-6.
  Actual pair/held fresh replay byte-identical;final replay powtórzony9332pins
  i4negativeguards PASS, setSHA12bc79f…6238c. Helpers15 Ruff/format/types PASS.
- Focused50PASS/1 dawny obsolete registry assertion(gen3invalid wobecgen3/4),
  niezmieniony i opisany poza zakresem. Independent final audit PASS,0openP0–P2.
- Read-only kolejka8/revision0:directPNG0.125s/proxy0.094s;raw60/human26 zachowane.
  Nie potrzeba nowych katalogów. Bez DB/Super/migracji/usuwania/merge/push/deploy.
- DoD/sevencriteria/plan1–5 fulfilled;quality MUMIE_AI_ROUND2_20261006.md.
  Commit `v1.7.216`; wcześniejsze metadata wyłączone ze stagingu.

### TASK-0867 — autonomiczny blind AI audit pierwszej próby (done)

- Dwa niezależne review60 PNG/20human kotwic: 53 high/high readable,7 unresolved.
  Control50: V3 RGB46/gray45/fuzja45 z47; V4 wszystkie47/47.
  Directed10: V3 5/0/0 z6; V4 6/5/6 z6. AI agreement, nie human accuracy.
- Priorytet8 exact cropów; original60 i wcześniejsze26 approve zachowane.
  Gold frame3 present/51absent/6unresolved; zero Super/human pseudo-label writes.
  Pierwszy film poza symbol development; geometria wcześniej częściowo trenowana.
- Proof5fd1d19…8590a; fresh replay8748pins/20anchors i4negativeguards PASS.
  30pytest,6helpers Ruff/format/scoped strict mypy PASS; independent audit PASS.
- Saved runtime z bytebackupem; owned API2740/UI26388 gotowe po restarcie.
  Exact8 direct/proxy0.297/0.266s, revision0; galerie/editor200. API8000 nietknięte.
- DoD/sixcriteria/plan1–3 spełnione; quality MUMIE_AUTONOMOUS_AI_AUDIT_20261006.md.
  Commit `v1.7.215`; wcześniejsze metadata wyłączone ze stagingu.
- Natychmiast kontynuować TASK-0868: nowy cohort i jedna V4-R2 para. Kolejka8
  nie blokuje. Bez DB/Super/aktywacji/merge/push/wdrożenia.

### TASK-0866 — większa próba transferu z istniejących katalogów (done)

- Trzy katalogi potwierdzone: 2580/2052/2844 zdjęcia. Nie potrzeba kolejnego
  folderu ani ponownego potwierdzenia nagrań. Pierwszy film ma 0 source overlap
  z actual development312; strict exclusions: 6 duplikatów,66 wykluczonych,
  2508 eligible,60 równomiernych zdjęć z whole-photo guardami.
- Frozen V3/V4: 8100 identycznych cropów,540 plansz,0 unavailable,100 zmian
  klasy,disagreements89→54,lowconfidence461→472. Accuracy=null. Geometria była
  częściowo trenowana na tym filmie; wcześniejsze diagnostic9 użyte w regresji.
- Ready packet 4af49619…7f9d91: 50 kontroli wybranych przed inference i10
  odrębnych kierowanych przypadków,60 zdjęć,0 missing,revision0/trainable=false,
  bez pseudo-zgód. Edytor http://127.0.0.1:3102/symbols/batch; korekta symbolu
  bez zmiany dobrej siatki. Poprzednie26/revision27 i61 oryginalnych wyników zachowane.
- Saved runtime z byte backupem; API23640/UI35108 owned/ready po restarcie.
  Read-only direct/proxy60PNG:0.516/0.297s,galerie/editor200. API8000 nietknięte.
- 71 focused pytest; seven helper Ruff/format/scoped strict mypy PASS. Nowy
  proces:8539 inputSHA/372 outputfiles identyczne,rerender8100,actualONNX60,
  4 negatives PASS. Niezależny final audit PASS, bez otwartychP0–P2.
- DoD/7criteria/plan1–5 spełnione; quality MUMIE_CROSS_RECORDING_20261006.md.
  Commit `v1.7.214`; branch feat/grid-engine-v3, wcześniejsze metadata pominięte.
  Bez nowych training/calibration/activation,DB/Super/merge/push/wdrożenia.
- Wymagana następna interakcja: oznaczenie gotowych60 cropów. Potem human
  evaluation frozen pary,control50 i directed10 osobno; first film pozostaje
  poza development. Nie powtarzać wcześniejszych26 oznaczeń.

### TASK-0865 — ocena modeli na nowych oznaczeniach człowieka (done)

-26 latest approve/revision27 qualified exact pack, pełne history/receipt/source
  i dictionary guards; jedna historyczna decyzja zastąpiona. Bez wpisów agenta.
-22 withheld: V3 RGB19/gray18/fuzja18; V4 RGB21/gray22/fuzja22. Wszystkie10
  klas obecne.4 oddzielne diagnostic: V3 4/0/2, V4 4/4/4. Wynik22/22 jest
  teraz względem człowieka.0 konfliktów AI/human, RGB myli A z Faraonem.
- Wszystkie26 crop/pełne-photo SHA poza development312; bez treningu,
  recalibration/threshold/epoch selection. Same-film/kierowany dobór nadal
  ograniczają wnioski; nie accuracy całego folderu ani niezależnego filmu.
- Actual ONNX4 z frozen preprocess/settings zgodne z dawnymi propozycjami;
  qualified40.22s i nowy proces43.61s reprodukują identyczny raport7d3c0e…b38d9.
 5771 input SHA, w tym oryginalne61output SHA, bez zmian.4 negative checks PASS.
-46 pytest, helper Ruff/format/scoped strict mypy PASS; niezależny audit
  source render26/ONNX/metrics/isolation/hash PASS, bez otwartychP0–P2.
  DoD/7 acceptance criteria/plan1–5 spełnione; raport MUMIE_HUMAN_AUDIT_20261006.md.
- Commit `v1.7.213`; feat/grid-engine-v3, wcześniejsze obce metadata pominięte.
  Bez zmian aplikacji/API/UI/runtime, DB/Super/aktywacji/merge/push/wdrożenia.
- Następny etap: większa human-referenced próba z nagrania wyłączonego z V4
  po kwalifikacji lokalizacji; sprawdzić istniejące katalogi przed pytaniem
  o nowy. Obecne26 zachować jako ocenę zamrożonego modelu; nie powtarzać oznaczeń.

### TASK-0864 — autonomiczny przegląd AI i eksperyment Mumii (done)

- D-505: jawna zgoda na nocny trening/wewnętrzne AI. Dwa blind review79 exact
  crops z20 kotwicami klas; consensus high/high, pełne source/review provenance.
- Nowe24 decyzje:19 approve z oryginalną historią/priorytetem i5 unreadable
  wyłączonych z AI. Oryginalnehuman264/84/9 i18 korekt bez zmian.29 AI targets
  i22 photo-disjoint AI audit z tego samego filmu, osobny format/purpose/gen4.
-312 unikalnych development,423 draws/epoch; human feedback37 ma wagę4,
  AI29 wagę1. Audit22 nie uczestniczy w treningu/wyborze/calibration.
- Jedna para RGB/gray:20epok/280steps, attempt1, best8/6;535.908/604.668s.
  Walidacja83/84 każda/fuzja, old18=18/18, new19=19/19 po treningu, diag9=9/9.
  Wszystkie human perclass gates i ONNX parity84/gałąź PASS.
- V3 przed treningiem new19: RGB15/gray4/fuzja10. AI audit22:21/22 RGB,
  22/22 gray/fuzja względem V3 19/18/18; to AI agreement, nie human accuracy.
-8100 identycznych cropów/540 siatek:39 zmian klas, disagreements37→22,
  lowconfidence424→454. Accuracy=null; wynik mieszany, brak aktywacji.
  Porcje20/20/20, nowy proces0 powtórzeń,61 output/5673 input SHA bez zmian.
-85 pytest +14 artifact checks, Ruff/format/scoped mypy PASS. Osobne audyty
  kodu/danych i re-render wszystkich8100 pól PASS, bez otwartychP0–P2.
  DoD/9 acceptance criteria/plan1–7 spełnione; raport MUMIE_AI_OVERNIGHT_20261006.md.
- Commit `v1.7.212`. Praca na feat/grid-engine-v3; wcześniejsze obce metadata
  pominięte. Bez DB/migracji/usuwania, Super targets, grid approvals, aktywacji,
  merge/push/wdrożenia.10 AI obserwacji złotej ramki nie są targetami Super.
- Granica człowieka:26 pending crops (22 withheld +4 uncertain),
  http://127.0.0.1:3102/symbols/batch; portal
  http://127.0.0.1:8108/overnight-symbol-review/review.html. Saved runtime i lab
  API45388/UI36508 ownership/ready PASS. Nie potrzeba nowego folderu/30 na klasę.

### TASK-0863 — trzeci niezależny katalog Mumii (done)

- Follow-up `v1.7.211`: instrukcja restart/status używa zweryfikowanego
  absolutnego bundled PowerShell7. Program Files\\PowerShell7 nie istnieje
  na tym hoście; nowy proces potwierdza ownership API/UI i gotowość portów.
- Nowy24517–50112 cut:2844 źródła,0 byte duplicates/overlap,60 równomiernie
  wybranych zdjęć. Qualified V3; wykluczone2699 tożsamości/30 photo pixels.
- Wykryto540/540 plansz zgodnie z nazwami,8100/8100 pól/propozycji;
 0 count anomalies/pól poza obrazem.424 niepewnych i37 disagreements.
  Brak etykiet tego filmu: accuracy=null; zgodność liczby nie zatwierdza siatek.
-24 exact PNG z15 zdjęć,10 klas,0/24 ocenionych. D-504 zachowuje bieżące
  base approval/history i exact case gates po pełnej kwalifikacji; UI bez
  hashowania2052 niepowiązanych feedback photos. Preview API/proxy
  0.110/0.109s, HTTP/browser PASS. Skróty1–9/0, symbol bez zmiany siatki.
- Saved runtime i kontrolowany restart labu przez PowerShell7 PASS;
  API25800/UI23928. Driver25/25/10 zakończony. Nowy proces:0 powtórzeń,
  270 identycznych plików i original pins bez zmian.42+36 pytest,
  Ruff/format/scoped mypy PASS; własny odrębny review bez P0–P2, DoD spełnione.
- Commit `v1.7.210` / `92b3bd8a316fa80f4428d045d29fabf773e8c4a2`; raport MUMIE_THIRD_RECORDING_20261006.md.
  Granica człowieka: http://127.0.0.1:3102/symbols/batch — oznaczyć24 wycinki.
  Portal: http://127.0.0.1:8108/third-symbol-review-priority/review.html.
  Nie potrzeba nowego folderu/30 na klasę. Brak DB/aktywacji/Super/merge/push/wdrożenia.

### TASK-0862 — lokalizacja przeniesionych zdjęć Mumii (done)

- Operator wskazał C:\Users\tuszy\Documents\mumie. Wszystkie 2 052 SHA
  folderu481537–500000 cut są identyczne z qualified inventory.
  Nowy trzeci katalog24517–50112 cut zawiera2 844 zdjęcia z odrębnego filmu.
- D-503 zapisuje deklarację odrębnych filmów dla każdego nowego katalogu;
  nie wymaga powtarzania pytania. Przeniesione stare katalogi zachowują tożsamość.
- Create-only sidecar lokalizacji zachowuje manifest/run/split i pełną kontrolę
  SHA/re-render. Fresh-process verify i identyczny retry PASS, bez zmian zdjęć.
- 29 nowych/kwalifikacyjnych +28 regresyjnych pytest PASS; Ruff/mypy PASS.
  Osobny review bez otwartych P0–P2. Commit `v1.7.208`.
  Dalej wznowienie0861 i diagnostyczna partia60 zdjęć0863. Bez DB/aktywacji.

### TASK-0861 — ograniczona para feedback generacji3 (done)

- RGB/gray zakończone:20epok/200kroków, wybór epok
  11/11; jeden run każdej gałęzi.
  Ten sam RGB run wznowiono po0862; wcześniejszy błąd i budżet zachowane.
- Walidacja RGB/gray/fuzja: 83/83/83/84; gate wszystkich klas
  względem V1=True. Pozostaje dawny konflikt referencji K/Q.
  ONNX parity84/gałąź PASS. Unikalne264 development,318 losowań weight4.
- Feedback 18/18/18/18 to użyte targety treningu.
  Diagnostic 9/9/9/9: dwie klasy, ocena po wyborze epoki;
  nie jest ślepym testem starszych modeli ani accuracy nowego filmu.
- Dwa świeże procesy odtwarzają identyczny dowód/kalibrację; SHA/etykiety,
  wcześniejsze modele i magazyny zachowane. Worker PID-y zakończone.
  43 wcześniejsze focused pytest i Ruff/scoped mypy PASS;0862 dodał29+28 regresji.
- Odrębny review bez P0–P2; DoD/plan0861 spełnione. Commit `v1.7.209`.
  Raport MUMIE_SYMBOL_FEEDBACK_TRAINING_20261006.md. Kontynuować0863:
 60 nowych zdjęć24517–50112 z2844; brak DB/aktywacji/merge/push/wdrożenia.

### TASK-0860 — kwalifikacja 18 korekt symboli Mumii (done)

- Operator potwierdził niezależność nowego nagrania od walidacji. D-502
  kwalifikuje wyłącznie dokładny raster symbolu; nie zatwierdza planszy ani geometrii.
- Immutable pack c1392fb1…3f8b60 zawiera 18 decyzji i PNG z 17 zdjęć.
  Pochodny manifest 0cff2a15…1e3de4: 264 development, 84 validation,
  9 diagnostic_test. Wszystkie 10 klas pozostaje w development/validation.
- Cały nowy folder (2 052 pliki) i znane aliasy pozostają w jednej części.
  Pierwsza rodzina nagrania jest wyłączona z nowego treningu; diagnostyka
  obejmuje tylko Mumię/Sfinksa i nie jest ślepym testem wcześniejszych modeli.
- 20 nowych +42 regresyjne pytest PASS; Ruff, scoped strict mypy PASS.
  Realny verify/retry w nowych procesach daje ten sam manifest i SHA oryginałów.
  Pierwsza analiza mypy bibliotek przekroczyła 120 s; procesy zakończył runner.
- Pierwotne decyzje trainable=false i adapter D-498 zachowane; API/UI bez zmian.
  Bez DB, aktywacji, merge/push/wdrożenia. Osobny review bez otwartych P0–P2.
- Commit: `v1.7.206`. Dalej TASK-0861: jedna para RGB/gray generation3,
  feedback weight4 i dokładne resume; aktualne polecenie obejmuje kontynuację.

### TASK-0859 — poprawka RGB 777 i ukończone 18 korekt Mumii (done)

- Przeczytano wskazany handoff RGB/feedback z głównego checkoutu. Mumie już
  używają pełnego RGB i SpatialSymbolCnn; 18 PNG ma exact preprocessing parity.
  Różnica to głowica RGB 777 versus dotychczasowa gray-dominant fuzja Mumii.
- Operator ukończył 18/18 decyzji approve, revision18. Zweryfikowano klasę,
  UUID, byte/pixel SHA i identyczne propozycje; bez ponownego oznaczania.
- Na trudnych18: V1 RGB/gray/fuzja11/10/10; V2 10/13/11. RGB V1 psuje
  Mumię, gray V2 psuje J względem V1. Wszystkie warianty83/84 na dawnej
  walidacji. Sama podmiana gałęzi nie rozwiązuje błędu i nie uzasadnia aktywacji.
- Zapisano bramkę dalszej oceny: mniej błędów ogółem bez regresji klasy,
  identyczne źródła/piksele/etykiety i niezależny split. Bez accuracy gry
  z celowo wybranych18. Raport MUMIE_RGB_FEEDBACK_TRANSFER_20261005.md.
- 29 pytest PASS; ponowny proces daje identyczny dowód199f2b58…ff53f84.
  Wszystkie wejścia SHA i realne decyzje zachowane. Bez DB, treningu,
  aktywacji, restartów, merge/push/wdrożenia i nowych zależności.
- Następny zakres: osobna kwalifikacja dokładnych korekt i splitu do nowej
  iteracji, potem ograniczony trening i przegląd nowych pomyłek. D-501 raw
  crop-review nadal trainable=false; nie udaje akceptacji pełnej geometrii.
  Nie potrzeba teraz kolejnych30 zwykłych przypisań ani ponownej deklaracji nagrań.
- Osobny commit: `v1.7.205`.

### TASK-0858 — korekta symboli z partii Mumii (done)

- Operator zgłosił brak edycji w galerii 18 przypadków. Źródła są poza
  obecnym katalogiem lab. Dodajemy dokładny crop-review do istniejącego API
  i edytora, z oddzielną trwałą historią i zatwierdzonym słownikiem D-498.
- Założenie D-501: wybór klasy zatwierdza wyłącznie widoczne wycięcie;
  nie pełną geometrię, sekwencję ani próbkę treningową. Bez DB/migracji,
  treningu, aktywacji, produkcyjnego wdrożenia i zmian pierwotnych etykiet.
- Plan: ai_docs/delivery/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md.
- Działający edytor http://127.0.0.1:3102/symbols/batch: wybór wycinka,
  paleta dziesięciu istniejących klas, skróty 1–9/0 i jawny zapis bez zmiany
  siatki. Desktop ma panel obok galerii; telefon — nad nią. Galeria 8108
  prowadzi do konkretnego wycinka. Miniatury pozostają zamrożone po zapisie.
- Referencja 48341730f870b38590286bffa7ff289649cd8c73f9fcc0907c81ac3c16754c54;
  18 bezstratnych PNG RGB96. Odczyt API/proxy 0,203/0,172 s. Realny zbiór
  nadal ma zero nowych decyzji; stare rev591/rev63 i SHA bez zmian.
- Osobny trwały magazyn batch_crop_review; CAS, exact retry i restart
  potwierdzone na izolowanym fixture. Saved runtime.json i launcher
  odtwarzają lab z nowego procesu. API/UI 8102/3102 gotowe po restarcie.
- Weryfikacja: backend 56, UI 62, klient 15 PASS; Ruff/mypy, OpenAPI/client
  drift, lint/typecheck i build PASS. Browser/390×844 bez overflow, guziki 44px.
  Audyt: ai_docs/quality/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md.
- Commit: `v1.7.204`.
- Następna konieczna interakcja: operator wybiera prawdziwe klasy w 18
  wycinkach. Potem osobna kwalifikacja/ocena; trening nie uruchamia się sam.

### TASK-0857 — odporność modeli symboli Mumii (done)

- Dwie ograniczone próby V2: po 20 epok/160 kroków, walidacja 83/84,
  development 255/255, czas 70,63/78,93 s. ONNX parity wszystkich 84 cropów,
  max błąd 2,861e-6. D-500; plan odporności ukończony.
- Te same 600 zdjęć/5396 plansz/80940 wycięć, identyczne piksele i geometria.
  V2: 16024 niepewnych (19,80%) i 4047 rozbieżności (5,00%); V1: 15626/3494.
  Brak wykazanej przewagi V2; obie wersje pozostają testowe, bez accuracy.
- 36 pytest, Ruff/format i scoped mypy PASS. Świeży proces: 0 powtórzeń,
  2404 pliki V2/737389437 bajtów i V1 bez zmian. Oryginalne magazyny bez zmian,
  kontrolowane procesy zakończone. Szerszy mypy: wcześniejsze błędy API/timeout.
- 18 konkretnych przypadków do rzeczywistej oceny człowieka:
  `http://127.0.0.1:8108/symbol-review-priority/review.html`. Przegląd tylko do
  odczytu; dalsza poprawa potrzebuje etykiet podświetlenia/linii/białego znacznika
  i potwierdzenia geometrii. Nie potrzeba kolejnej rutynowej zgody na testy.
- Raport `ai_docs/quality/MUMIE_SYMBOL_ROBUSTNESS_20261005.md`; osobny commit
  `v1.7.203`, pełny hash po commicie. Na `feat/grid-engine-v3`.
- Bez DB, aktywacji, Super, push/merge/wdrożenia i kolejnych losowych prób.

### TASK-0856 — większa niezależna partia Mumii (done)

-600 zdjęć z2052,5396 plansz i80940 propozycji. Manifest9068f31a…9199dac.
 15626 niepewnych modeli,3494 disagreement; bez accuracy/zgód za człowieka.
- Poprawiono końcówkę499996–500004 w folderze do500000:5 plansz, pominięty
  jeden nadmiarowy kandydat, jawny konflikt nazwy. Oryginalny plik bez zmian.
- Trwałe per-photo wyniki, kompletne SHA, root lock, porcje25/115s. Restart
  w nowym procesie:2404 pliki/737005906 bajtów identyczne, zero powtórzeń.
-28 pytest, Ruff/format/mypy i własny review PASS. Oryginały geometrii,
  symboli i run-state bez zmian. Driver/PID zakończone, bez orphanów.
- Przegląd `http://127.0.0.1:8108/symbol-batch-600/review.html`; HTTP/browser
  smoke PASS. Raport `ai_docs/quality/MUMIE_SYMBOL_BATCH_20261005.md`.
- Samodzielna dalsza praca: jasne J/K z zielonymi liniami ujawniły błędy
  modeli. Kontynuujemy TASK-0857, plan `MUMIE_SYMBOL_ROBUSTNESS_20261005.md`.
  Bez DB, aktywacji, Super, push/merge i wdrożenia.
- Osobny commit `v1.7.202`, pełny hash dopisany po commicie.

### TASK-0855 — dwa pierwsze modele symboli Mumii (done)

- RGB/gray od zera: po20 epok,255 development/84 validation z osobnych nagrań.
  Oba83/84 (98.81%), Mumia8/8; najlepsze epoki14/11. Mała walidacja, nie final_test.
- Kalibracja i fuzja wykonane; fuzja nie poprawia accuracy. ONNX obu modeli:
  parity84/84, max błąd3.8147e-6. Wagi, historia/logits i raporty zachowane.
- Jeden konfliktK/Q (crop wygląda jakQ) i niepewny Faraon do późniejszej korekty.
  Bez zmiany etykiet. Modelowa zgodność nie wykrywa każdej błędnej referencji.
- Trwały istniejący RunManager, budżety/restart/RNG/checkpoint i admission.
  RGB wznowiony po błędzie CUDA z tym samym budżetem; fixed pooling ekwiwalentny
  dla64px, test regresji PASS. Użyto55.36s/49.35s z1800s,161/160 kroków.
- 11 nowych testów +14 regresji runów, Ruff/format/Mypy i własny review PASS.
  Wszystkie SHA oryginałów niezmienione. Commit `v1.7.201`, hash po commicie.
- Raport `ai_docs/quality/MUMIE_SYMBOL_MODELS_20261005.md`; plan0854/55 ukończony.
  Modele testowe, bez aktywacji, DB, wdrożenia i Super. Kolejny zakres: większa
  niezależna partia inferencji i korekta wykrytych konfliktów.

### TASK-0854 — kwalifikowany split symboli Mumii (done)

- Potwierdzenie operatora rozstrzyga pochodzenie trzech grup; bez dalszego pytania.
- D-498: 339 aktualnych etykiet, development255/validation84, 10 klas w obu
  częściach. Pełne komponenty starego/obecnego grafu; bez duplikatów między częściami.
- Osobny niezmienny manifest `d5dc865287ca2d4583b450ccdca84f6186e16ac86922dc6f95ebea3930151589`.
  Rewalidacja cropów, grafu, źródeł i magazynów. Oryginały i D-496 bez zmian.
- 32 pytest, Ruff/format/Mypy i restart/retry PASS; własny review bez P0–P2.
  Commit `v1.7.200`; hash dopisany po commicie. Raport kwalifikacji poniżej.
- Plan `ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md` obejmuje dalszy
  TASK-0855: dwa ograniczone runy RGB/gray od zera. Bez DB/aktywacji/wdrożenia.

### TASK-0853 — aktualne etykiety Mumii (done)

- Operator zakończył przypisania i zlecił pracę bez swojej obecności.
  339 świeżych decyzji D-496: wszystkie 10 klas, 27 Mumii. 30 nie jest bramką.
- Niezmienny pakiet 339 PNG i historii, 13 zdjęć / 3 komponenty; żadnych
  identycznych pikselowo duplikatów ani sprzecznych klas. 244 dawne decyzje
  poza próbkami. Trainable=false, bez assignments i nadpisania magazynów.
- 20 testów, Ruff/format/Mypy PASS; verify i retry w nowych procesach PASS.
  SHA geometrii i symboli niezmienione. Pakiet 341 plików / 9 219 147 bajtów,
  ID `7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8`.
- Wszystkie rodziny Mumii unresolved/missing; brak splitu symboli, stary
  split geometrii stale. Pytanie o relację trzech nagrań pending; nie potrzeba
  teraz kolejnych przypisań klas. Dwa główne komponenty mają wszystkie 10 klas.
- Plan `ai_docs/delivery/MUMIE_SYMBOL_PREPARATION_20261005.md`.
  Nie osłabiamy bramek T06b; bez treningu do rozstrzygnięcia pochodzenia.
  Brak oddzielnych etykiet ramki Super; bez zgadywania, DB lub aktywacji.
- Raport `ai_docs/quality/MUMIE_SYMBOL_PREPARATION_20261005.md`.
  Osobny commit `v1.7.199`; pełny hash zostanie dopisany po commicie.
  Zastane metadane pozostają poza commitem. Bez restartu API/UI i wdrożenia.

### TASK-0852 — szybkość zapisu i poczekalnia 2000 (done)

- Operator zgłosił wielominutową blokadę po przypisaniu symboli i doprecyzował
  zamrożenie miniatur do odświeżenia. Jeden odczyt do 2000 cropów; potwierdzony
  zapis oznacza pola bez ponownego pobierania strony. Następny wybór podczas
  zapisu jest dostępny; kolejny submit wymaga receipt. D-497.
- Istniejący kontrakt rozszerzany addytywnie; domyślny podgląd 30 i zapis do
  30 pozostają. Budżet PNG 48 MiB; stare tokeny nigdy nie są odnawiane lokalnie.
- Zachowujemy bieżące etykiety człowieka. Bez zmian DB, treningu, aktywacji,
  shadow, push/merge. Weryfikacja realnych danych tylko odczytowa.
- 73 Python + 37 UI + 5 klienta PASS; format/lint/typy/OpenAPI/drift/build PASS.
  2000 realnych cropów: 5,464 s, 32,34 MiB base64. Restart API/UI 8102/3102
  z trwałej konfiguracji, PID 18980/18320, ready. Sumy etykiet i siatek identyczne.
  Browser: 2000 kafelków, 64 loaded/enabled, zero błędów. Własny audyt PASS.
- Raport `ai_docs/quality/SYMBOL_REVIEW_PERFORMANCE_20261005.md`.
  Task `ai_docs/tasks/completed/0852-symbol-review-save-and-queue-performance.md`.
  Osobny commit `v1.7.198`; pełny hash dopisywany po commicie. Zastane metadane
  innych tasków pozostają poza commitem. Pierwszy odczyt nadal trwa kilka sekund.

### TASK-0851 — wersja etykiet symboli Mumii (done)

- Operator 2026-10-05 zaakceptował kontrakt i potwierdził dwa różne nagrania.
  Deklaracja dotyczy wskazanych folderów; nie nadaje rodzinom verified.
- Wykonano: niezmienna referencja zgód i dawnych ról, opcjonalna konfiguracja
  istniejącego magazynu/API/edytora, 31 zdjęć / 279 plansz / 4185 komórek.
  Oryginalny split pozostaje stale. Bez nowego AnnotationStore i bez osłabienia
  starego workflow. Brak automatycznych etykiet i kwalifikacji treningu.
- Decyzja D-496. Main Mumie pozostaje pusty. Bez DB/migracji/materializacji/
  aktywacji/shadow/push/merge. Następna interakcja: przypisanie klas przez człowieka.
- Wersja `dab77630f3518604add168c2baeed124dc9c5010d8ea483201a5be8cb77da1fc`,
  523 chronione źródła, słownik v1, pełna oryginalna historia. Wszystkie dawne
  sumy niezmienione; zero nowych etykiet, 706 dotychczasowych zachowanych.
- 63 testy PASS; format/lint/typy/OpenAPI/build/TypeScript PASS. Restart i HTTP
  pierwszej/ostatniej strony oraz pełnej planszy PASS. Browser smoke: 15 aktywnych
  wyborów bez zmiany siatki. API/UI 8102/3102 gotowe; własny 8105 zatrzymany.
  Trwały launcher/config, PID/czas startu zapisane. Bez restartu komputera.
- Raport `ai_docs/quality/MUMIE_SYMBOL_DATASET_VERSION_20261005.md`.
  Task `ai_docs/tasks/completed/0851-mumie-symbol-label-dataset-version.md`.
  Osobny commit `v1.7.197` na `feat/grid-engine-v3`; hash dopisany po commicie.
  Zastane metadane pozostają poza commitem. Nie uruchomiono uczenia symboli.

### TASK-0850 — Mumie: iteracja 5 i dane do interakcji (done)

- Operator 2026-10-05 zlecił pracę do momentu wymagającego jego interakcji.
  Jedna iteracja 5 presetu F na nowych zatwierdzeniach, testy i przygotowanie
  cropów. Bez importu plansz do głównej gry, DB, migracji i aktywacji.
- Iteracja 5 runu 3 zakończona, preset F: 25 train / 6 holdout z 31 zdjęć,
  11 nowych. 900,75 s GPU, 1831 kroków, zużycie 4718,62/14400 s.
  Każdy kandydat przeszedł strażnik 777, ale pogorszył Mumie image-macro
  względem 0,0022076230. Poprzedni model zachowany, bez ONNX/propozycji/aktywacji.
- Oba foldery verify PASS w nowych procesach: po 200 zdjęć i 11 osobnych kontroli,
  każdy model 211 wyników na folder. Bez ponownej inferencji i deklaracji accuracy.
- 4185 cropów z 31 kompletnych zdjęć, 236 nakładek, partie 50/50/50/50/36.
  Słownik labu 10 klas zatwierdzony; zero etykiet obecnych 31 zdjęć.
  Dawne 20 ról, rewizja 591, fingerprint zgód i stan symboli niezmienione.
- 31 testów fine-tune/batches/folder CLI PASS; build/TypeScript labu PASS.
  Główna gra: 10 symboli, 0 layouts/source_images/recognized_boards/dataset_versions.
- Faktyczny edytor symboli blokuje `HOLDOUT_POLICY_UNRESOLVED`: dawny split
  pilota stale. Nie nadpisano splitu ani nie wyłączono guardów. Nowe własne
  procesy 8102/3102 zatrzymane, 8105 przywrócony (root 42788), 31/236 PASS.
- Granica interakcji: pytanie o pochodzenie obu folderów i akceptację
  `ai_docs/delivery/MUMIE_SYMBOL_DATASET_VERSION_20261005.md` (draft).
  TASK-0851 planned, niewykonany; wszystkie rodziny pozostają unresolved.
- Raport: `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`.
  Task: `ai_docs/tasks/completed/0850-mumie-train-current-approvals-and-prepare-review.md`.
  Osobny commit `v1.7.196`, hash dopisywany po commicie. Zastane metadane
  pozostają poza commitem. Bez DB/migracji/materializacji/shadow/push/merge.

### TASK-0849 — Omyłkowy duplikat Mumie usunięty (done)

- Operator jawnie zlecił archiwizację i trwałe usunięcie `mumie-1`
  (`12180d9f-6c1a-43a9-a480-4056d2da81a9`). Oryginalne `mumie` i `777`
  pozostają chronione.
- Preview bez danych użytkownika; wznowiono istniejący provisioning 9/64
  do 64/64 bez ręcznego SQL. Archiwizacja przez API 204; końcowy preview
  bez blockerów. Usunięcie istniejącym CLI, 64/64, receipt `done`.
- Nowy proces: PASS; duplikat daje 404, zero katalogu, registry i partycji.
  Snapshoty katalogów, magazynów, symboli i fingerprintów jobów oryginalnych
  gier są zgodne. Zdjęcia zachowane; bez restartów usług, treningu i shadow.
- Raport: `ai_docs/quality/MUMIE_DUPLICATE_REMOVAL_20261005.md`.
  Task: `ai_docs/tasks/completed/0849-remove-accidental-mumie-duplicate.md`.
  Osobny commit `v1.7.195`; hash dopisany po zapisie. Zastane metadane poza
  commitem; brak push/merge.
### TASK-0851 — analiza nowych korekt symboli i przekazanie metody (done)

- Operator zlecił analizę swoich nowych korekt audytu 777 i dopracowanie
  mechanizmu oraz notatkę do Claude Code.
- Ocena wyłącznie aktualnych zatwierdzonych pikseli; osobne źródła do oceny
  kandydata. Niezmienione propozycje zatwierdzone Save to słabszy dowód.
- Bez aktywacji/treningu CNN, masowego zapisu, zmian geometrii ani wznowienia
  zatrzymanych TASK-0832/0833. Zmiana metody zależy od niezależnych wyników.
- Snapshot tylko do odczytu: 5788 zatwierdzonych pól / 578 zdjęć, SHA cropów PASS.
  RGB: 100 rozbieżności; w aktualnym przeglądzie RGB 44/3780 (98,84% zgodności).
  Cytryna 0/556, Śliwka 1/584, Arbuz 1/429; główny problem Winogron/Siedem.
- Wariant nowych wzorców zmniejsza test 21 → 18 błędów, ale Cytryna 2 → 5.
  Odrzucony; kontrola regresji każdej klasy pozostawia obecną politykę D-494.
- Nowy ewaluator scripts/evaluate_grid_audit_feedback.py; 28 testów PASS,
  Ruff i scoped Mypy PASS. Nowy proces evaluate: retain_rgb_v2.
  Raport: artifacts/grid-audit-feedback-20261005/approved-v2/.
- Historia 5788 decyzji: zero masowych zatwierdzeń; exporter odrzuca je w przyszłości.
- Notatka dla Claude Code: ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md.
  Zakres globalnego pending-only adaptera pozostaje odrębny; bez publikacji.
- Task 0851 w completed; commit `v1.7.197` /
  `fbef9096a1c937ad4884e745b48dc57bffa815af` (hash dopisany po commicie).

### TASK-0850 — cofnięcie ostatniego zapisu planszy 388128 (done)

- Operator polecił cofnięcie jednej ostatnio zapisanej planszy: p00683,
  revision 2, receipt 0f3009c7-2923-4574-b130-e1cac7103f2a.
- Zakres: poprzednie narożniki i 15 zatwierdzeń tego samego zapisu.
  Przed zapisem wszystkie pola pending / requires_review. Historia pozostaje.
- Zapis kompensujący revision 3 / receipt efc87ae4-6eae-4803-9fd3-0a4980707c84:
  poprzednie narożniki przywrócone; 15 pól pending / requires_review.
- Nowy audyt silent-grid-777-20261004-undo-p00683-20261005t160416 jest kopią
  aktualnej wersji po TASK-0849; rebase wyłącznie p00683. Wcześniejszy rebase
  p00545 oraz wszystkie 975 pozycji i 917 propozycji zachowane.
- Świeży proces i UI PASS: p00683 / 388128 pierwsza w kolejce, 15/15 podpowiedzi,
  402 open / 573 corrected. Pozostałe geometrie i decyzje niezmienione.
- Ruff pomocnika PASS. Dowody: artifacts/grid-audit-undo-20261005/p00683/.
  Task 0850 w completed; commit `v1.7.196` /
  `8c16dcf16b67a8f5f61b44c9624509148a85f9e5` (hash dopisany po commicie).
- Bez zmian aplikacji, schematu, treningu ani usuwania danych.

### TASK-0849 — cofnięcie ostatniego zapisu planszy 431508 (done)

- Operator polecił cofnięcie ostatniego zapisu; odczyt wskazuje p00545,
  revision 2, receipt 9b4c8f0f-23cb-4643-9c97-79710bb977a1.
- Zakres obejmuje poprzednie narożniki i 15 zatwierdzeń tego zapisu.
  Wcześniejszy stan wszystkich pól: pending. Historia ma pozostać.
- Istniejący zapis kompensujący: revision 3 / receipt
  4c2e9a09-b1af-4b3f-99b9-9d3467ff6ae6. Poprzednie narożniki przywrócone;
  15 pól pending/requires_review, poprzednia aprobata 2 wyłącznie w historii.
- Nowy niezmienny audyt silent-grid-777-20261004-undo-p00545-20261005t130216:
  rebase tylko p00545, wszystkie 975 pozycji i 917 propozycji zachowane.
  Oryginalny audyt niezmieniony; SHA PNG zgodny dla nowych rewizji kontekstu.
- Nowy proces i UI PASS: p00545 / 431508 pierwsza, 15/15 propozycji RGB,
  kolejka 482 open / 493 corrected. Pozostałe geometrie i decyzje zachowane.
- 40 regresji API PASS, Ruff pomocników PASS. Dowody:
  artifacts/grid-audit-undo-20261005/p00545/; task 0849 w completed.
- Bez nowego UI, schematu, endpointu, treningu ani usuwania danych.
- Commit `v1.7.195` / `eb19e28aa796c259820d18c4b891f9d68068ac1b`
  (hash dopisany po commicie).

### TASK-0848 — V3-D scalony i zmigrowany na main (done)

- Wdrożono z `C:\Users\tuszy\Documents\game_predicotr` na
  `v1.1-vision-lab-hybrid-geometry`, po zgodzie operatora i koordynacji TASK-0847.
- Kandydat `v1.7.192` / `a5119244c0af32ef2cf3132550ba115f1f5c960d`;
  końcowy `v1.7.193` / `6fb6b8f2ed026d17418e4dfc3d9dcce8cf7c9b90`.
  Zachowano RGB TASK-0847 `v1.7.192` / `8a42380bc9b6d13d125c5eab2873c8c58076134f`.
- Baza na `0143_merge_share_grid_shadow` (no-op join 0141/0142), guard zgodny.
  Dwie wcześniejsze gry aktywne, manifest v5, rewizje magazynów +1.
  Parent i dwa children shadow ENABLE/FORCE RLS; rzeczywiście zero historii.
  Role compliant, brak aktywnych jobów/lifecycle w kontroli po migracji.
- 43 testy pierwszej integracji i 34 po RGB PASS; klient 82 PASS;
  regresje Reviewera 21 PASS, typy/lint/scoped Mypy PASS. Kontrakt wygenerowany.
  Zależności aktualne. Build Admin 21,25 s i Reviewer 14,11 s PASS z main.
- API 8000, Admin 3000, Reviewer 3001 gotowe; worker general z 7 wątkami.
  Odczyt HTTP i trwałego stanu PASS w nowym procesie. Pierwszy probe API
  przekroczył 10 s; gotowość potwierdzono bez drugiej kopii, bez gwarancji 10 s.
  Galerie 8105/8107 bez restartu; brak starych procesów i duplikatu workera.
- Shadow false; nie uruchomiono jego inferencji, treningu, aktywacji modelu,
  importu stagingu, downgrade, usuwania danych ani push. Zastane metadane
  odtworzone poza commitem; stashe zachowane jako odzyskiwalne kopie.
- Raport: `ai_docs/quality/GRID_V3_SHADOW_DEPLOYMENT_20261005.md`.
  Task: `ai_docs/tasks/completed/0848-grid-shadow-integration-deployment.md`.
  Główny commit `v1.7.194` / `73ae0b6fe82d397fefed24a3f1656ba805c50d6c`
  (hash dopisany po commicie).

### TASK-0805 — V3-D: shadow w aplikacji (done, domyślnie wyłączony)

- Operator jawnie uruchomił etap 2026-10-05. Kontrakt wykonawczy:
  `ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`; TASK-0805.
- Jeden pion na zmaterializowanych źródłach, domyślnie wyłączony, z jobem
  VALIDATE ograniczonym do 20 źródeł, osobnymi wynikami i ręczną korektą.
  Mumie bez kalibracji pozostają propozycją do przeglądu. 225 zdjęć w stagingu
  nadal wymaga preflightu i materializacji źródeł.
- Neutralny rdzeń, manifest v5 i RLS, API/OpenAPI/klient i Admin/Reviewer.
  Claude z pierwotnej tabeli niedostępny; jawnie przypisano gpt-6.1-sol high
  oraz audyt gpt-6-astra high. Delegacja w ramach uruchomionego etapu.
- TASK-0805 nie obejmował migracji operatora ani merge/wdrożenia. Zgoda
  na integrację i migrację udzielona później w TASK-0848; brak zgody na
  przebieg shadow, trening, push i aktywację domyślnego silnika.
  Main zawiera 0141; 0143 łączy ją z 0142 przygotowaną w tym tasku.
- Admin i Reviewer budują się poprawnie. Audyt statyczny zamknięty bez
  pozostałych P0–P2. Nowe testy workera 20 PASS, regresje labu 38 PASS,
  klient 79 PASS; testy backendu i UI, typy i OpenAPI PASS.
  Raport: `ai_docs/quality/GRID_V3_SHADOW_IMPLEMENTATION_20261005.md`.
- Po osobnej zgodzie operatora 2026-10-05 testy PostgreSQL: 4 PASS (RLS,
  migracja/downgrade, odczyt w nowym procesie i współbieżność blokad).
  Tymczasowe bazy i role usunięto, brak pozostałości potwierdzono odczytem.
  Bez zmian bazy operatora. Poprawki loading/empty i rozmiarów kontrolek
  potwierdzono 8 testami interakcji Admina, typami/lintem i końcowym buildem.
- Mobilny smoke Edge Chromium 360/390 × 844 PASS: dotyk wybiera zdjęcie,
  pole i symbol, brak poziomego overflow, zero zapisów i wyjątków.
  Fizycznego Androida nie testowano; testowe procesy przeglądarki zakończone.
- Końcowy audyt gpt-6-astra high bez P0–P2, kryteria taska/plan/DoD zamknięte.
  Task: `ai_docs/tasks/completed/0805-grid-geometry-shadow-integration.md`.
  Commit `v1.7.191`; pełny hash po commicie. Etap kodowy zakończony;
  wdrożenie z migracją zakończono później w TASK-0848. Shadow pozostaje
  wyłączony; odbiór inferencji na danych operatora jest osobny.

### TASK-0846 — Mumie: drugi folder (done)

- Operator wskazał `C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut`
  po ocenie pierwszego porównania jako niemal identycznego. Folder ma 2052 pliki.
- Wykonano 200 unikalnych zdjęć równomiernie po zakresie; istniejące modele
  iteracji 2 i 3, CPU, ten sam adapter. Zero kopii i znanych SHA.
  Inny folder nie dowodzi innej rodziny. 422 wyniki z kontrolnymi 11.
- Wyniki w `artifacts/mumie-folder-test-20261005/second-481537-500000`;
  wcześniejszy test pozostaje niezmieniony. Kontrolne 11 zdjęć oceniane osobno,
  nie jako nowe referencje drugiego folderu. Bez treningu/DB/migracji/V3-D.
- Oba modele: 199 zdjęć z 9 planszami, jedno z 6, zero błędów struktury.
  Ostatnie zdjęcie zawiera pięć rzeczywistych plansz; obie iteracje tworzą
  fałszywą szóstą na tle. `seq_485704-485712` ma uciętą górę pierwszej planszy;
  2 cropy iteracji 2 i 3 cropy iteracji 3 poza obrazem. Brak dowodu przewagi.
- Mediana różnicy 43128 węzłów 0,327794 px, P95 0,794990 px. Bez accuracy.
  20 par nakładek, największe różnice i cropy obu trudnych przypadków obejrzane.
- 7 testów PASS, nowy proces odzyskuje po 211 wyników bez inferencji;
  ponowne finish/audit/verify PASS. Galeria: filtry 200/11/2 i wycinki PASS.
  Podgląd: `http://127.0.0.1:8108/second-481537-500000/case-review.html`.
- Task i plan: `ai_docs/tasks/completed/0846-mumie-second-folder-test.md`.
  Raport: `ai_docs/quality/MUMIE_SECOND_FOLDER_TEST_20261005.md`.
  Następny zakres: referencje niepełnych ekranów i pustych miejsc, dopuszczenie
  do uczenia po zatwierdzeniach. Commit `v1.7.190`; hash po commicie.

### TASK-0845 — Mumie: test rzeczywistego folderu (done)

- Operator wskazał `C:\Users\tuszy\Documents\mumie wybrane\1 - 23175 cut`
  (2580 JPEG-ów) i upoważnił wykonawcę do doboru części. Test objął
  200 zdjęć równomiernie po zakresie 55–23175, bez SHA kompletnych zdjęć labu.
  Wykluczono 6 identycznych kopii i 5 znanych źródeł; 2569 kwalifikujących się.
- Aktualna rewizja anotacji 591: 31 kompletnych zdjęć Mumii, 11 nowych względem
  iteracji 4. Te 11 oceniono osobno, bez dalszego treningu.
- Porównanie eksportów iteracji 2 i 3 na CPU, istniejące dekodowanie i D-483.
  Wyniki folderu są propozycjami. Bez accuracy na nieoznaczonych zdjęciach,
  bez treningu, DB, migracji, aktywacji i V3-D. Plan:
  `ai_docs/delivery/MUMIE_REAL_FOLDER_TEST_20261005.md`.
- 422 wyniki (211 na model), każde zdjęcie folderu ma po 9 wykrytych plansz;
  zero błędów struktury i pól poza obrazem. Przegląd 20 par nakładek oraz dwóch
  arkuszy wycinków nie pokazał oczywistych przesunięć; nie oceniono ręcznie
  wszystkich pól. Podgląd: `artifacts/mumie-folder-test-20261005/review.html`,
  lokalnie `http://127.0.0.1:8108/review.html` (serwer PID 41152, bez autostartu).
- Nowe 11: oba modele 11/11 zdjęć, 99/99 plansz według D-483. Wszystkie 99
  referencji to zatwierdzone, niezmienione propozycje iteracji 3. Jej niemal
  zerowy błąd nie jest niezależnym dowodem przewagi. Zatwierdzenia zachowano.
- 7 testów PASS, Ruff check/format PASS, Mypy strict jednego modułu PASS;
  wznowienie w nowych procesach: pending=0, recovered=211 na model; verify,
  ponowny finish i audit PASS. Galeria: nawigacja, filtry i wycinki sprawdzone.
- Raport: `ai_docs/quality/MUMIE_REAL_FOLDER_TEST_20261005.md`. Następny zakres:
  niezależna ocena reprezentatywnych cięć i dobór rzeczywistych błędów, zamiast
  automatycznego etykietowania całego folderu. Bez treningu symboli/ramki Super.
- Commit `v1.7.189` / `7ac2fb53ebb6deec3edcf65b1c34d685f70f0a65`
  (hash dopisany po commicie). Numer 0845 wybrano, ponieważ
  0844 zajęto równolegle w głównym checkoutcie. Bez scalenia do checkoutu
  z trwającym zadaniem 0844 i bez push.

### TASK-0847 — poprawne wejście RGB i propozycje sieci w audycie siatek (done)

- Operator zgłosił Śliwka → Arbuz/Pomarańcz oraz Cytryna → Pomarańcz.
- Odczyt czterech plansz odtworzył trzy śliwki w p00519; ich opis barwy
  zdominowało tło. Kod głosowania jest zgodny z Claude, lecz jakość na nowym
  cięciu i przy słabszych propozycjach wymaga osobnej kontroli.
- Próby samej barwy i dopasowania nie usunęły błędów. Głowica istniejącego
  modelu na RGB zgodnym z treningiem daje 120/120 w dwóch małych próbkach
  ocenionych wzrokowo przez agenta; biblioteka 115/120. Nie jest to truth operatora.
- Audyt używa propozycji głowicy RGB i dodatkowego potwierdzenia przez
  ścisłą bibliotekę. Brak zgodności ma `?`. Addytywna wersja algorytmu w API.
  Wagi CNN, wzorce, zatwierdzenia i zatrzymane TASK-0832/0833 bez mutacji.
- Wszystkie 496 otwartych plansz mają 7440 propozycji: 5662 potwierdzone przez
  bibliotekę, 1778 z `?`. 479 poprawionych plansz bez zapisów. Biblioteka SHA bez zmian.
- Nowy proces: `processed=0`, `coveredOpenBoards=496`; API v2 i UI p00519 odebrane
  bez Save. Osobna karta zachowuje poprzedni widok operatora.
- Python 79 + końcowe 15 worker PASS (jeden dodatkowy przypadek); klient 81 PASS,
  Ruff/format, scoped strict Mypy, OpenAPI/client oraz TS klienta i Reviewera PASS.
  Pełny Mypy trafił na niezwiązane błędy share-query/limit czasu; poza zakresem.
- Task i plan: `ai_docs/tasks/completed/0847-grid-audit-rgb-symbol-proposals.md`.
- Commit: `v1.7.192`, `8a42380bc9b6d13d125c5eab2873c8c58076134f`.
- Następny krok: przegląd propozycji przez operatora. Bez treningu/aktywacji,
  migracji, restartów usług, push/merge lub wznowienia TASK-0832/0833.

### TASK-0846 — wstępnie wybrane propozycje symboli audytu (done)

- Operator 2026-10-05 zlecił propozycje także dla niepewnych pól oraz wstępny
  wybór, aby poprawiać tylko błędne symbole przed zapisem. D-493 zmienia D-491.
- Audyt wstępnie wybiera nowe propozycje; niepewne mają `?`. Ręczny wybór,
  usunięcie i „Nie wiem” mają pierwszeństwo. Nowe cięcie usuwa stare automatyczne
  wybory. Zapis czeka na katalog/propozycje i zatwierdza widoczne symbole dopiero
  po kliknięciu operatora. Zwykłe korekty zachowują poprzednie zachowanie.
- Biblioteka/model pozostają zamrożone. Trzy rundy przeliczyły 569 otwartych
  plansz. Odbiór: wszystkie 525 nadal otwarte z 975 (450 już poprawionych),
  6073 pewne i 1802 niepewne propozycje, zero pustych pól. Nowy proces potwierdził
  pokrycie 525/525 bez ponownego rozpoznawania; sumy wszystkich plików sprawdzone.
- 397 testów PASS, format/lint, scoped strict Mypy, TypeScript, OpenAPI/klient
  i build PASS. Lokalny Reviewer zrestartowany; p00474/p00475 odebrane w UI,
  bez zapisu operatora. Nie sprawdzano fizycznego Androida ani restartu komputera.
- Plan i task: `ai_docs/tasks/completed/0846-grid-audit-preselected-symbol-proposals.md`.
- Commit: `v1.7.190`, `222be446718c4655b51fe4bb54de0a3f3baeb045`.
- Następny krok: operator przegląda wszystkie propozycje i zmienia błędne przed
  zapisem. TASK-0845 i zastane zmiany pozostają poza zakresem; bez push/merge.

### TASK-0845 — korekty symboli przez link i przegląd operatora (done)

- Operator 2026-10-05 zlecił poprawianie symboli przez udostępnioną
  wyszukiwarkę, oznaczenia przy wyszukiwaniu/stawce oraz szybki przegląd
  zmian także dalszych plansz w zakresie do 100 000 spinów.
- Operator potwierdził Q1/Q2: zastosowanie od razu i edycja również
  zatwierdzonych plansz. D-492 rozszerza D-471/D-473; bieżące plansze
  operacyjne są edytowalne lokalnie i online.
- Zapis korzysta ze wspólnego writera i atomowego audytu linku. Kontekst
  wyszukiwania/stawki jest jawny; dokładne ponowienie działa po restarcie.
  Historia pozostaje po usunięciu wyszukiwania i revoke. Przegląd sprawdza
  rewizję i SHA planszy, a nowsza zmiana ponownie otwiera kolejkę.
- Admin pokazuje liczniki przy wzorze oraz listę wszystkich zmienionych
  plansz linku. Klik otwiera edytor z historią i wyróżnieniem pól; zamknięcie
  nie zatwierdza przeglądu. Lista nie pobiera całego zakresu 100 000 plansz.
- Testy nowego pionu i regresje, lint, scoped strict Mypy, TypeScript,
  OpenAPI i oba buildy przeszły. Odbiór na danych testowych w Chromium:
  1280×900 i 390×844, bez poziomego overflow, przyciski przeglądu ≥44 px.
  PostgreSQL potwierdził nowy proces, utratę odpowiedzi, rollback audytu
  i revoke równoległe z zapisem. Szczegóły oraz wcześniejsze błędy szerszych
  kontroli (typy grupowania i podwójny React testów Admina) są w Outcome.
- Plan: `ai_docs/delivery/BOARD_SEARCH_SHARE_SYMBOL_CORRECTIONS_PLAN.md`.
  Task: `ai_docs/tasks/completed/0845-board-search-share-symbol-corrections.md`.
- Implementacja: `v1.7.190`, `c61c1e65f87e89e7669507cb902e6348fe3cc48e`.
- Operator zlecił scalenie 2026-10-05 do `v1.1-vision-lab-hybrid-geometry`
  oraz usunięcie worktree i gałęzi `codex/share-symbol-corrections` po scaleniu.
  Zachowano TASK-0846 i niezacommitowane zmiany operatora; konflikty dotyczyły
  tylko dokumentacji. Kontrakt obu funkcji połączył się zgodnie z backendem.
- Commit scalający: `v1.7.191` — `317a07c91bc1429804187d7cc7eebd1a47691770`.
- Logi w `artifacts/task0845-checks/` i `artifacts/task0845-merge/` głównego
  katalogu. Bez wdrożenia, migracji bazy operatora, restartu usług i push.
  Odbiór fizycznego Androida i publicznego tunelu pozostaje do wdrożenia.

- Po scaleniu: 63 testy API/regresji, izolowany PostgreSQL, 80 klienta,
  214 Reviewera, 39 interakcji shared i 1 kolejki operatora PASS. OpenAPI,
  klient i TypeScript czterech workspace PASS; timeout zbiorczy zastąpiono
  mniejszymi grupami. Bez ponownego builda działających aplikacji.
- Cleanup zakończony: worktree `share-symbol-corrections` zarchiwizowano
  przez aplikację i usunięto z dysku/rejestru Git. Scalona gałąź
  `codex/share-symbol-corrections` usunięta przez `git branch -d`.
  Zachowano odzyskiwalny snapshot aplikacji, logi oraz pozostałe worktree.

### TASK-0844 — nowe symbole proponowanych siatek audytu (done)

- Operator 2026-10-05 zlecił przeliczenie symboli otwartych propozycji siatek
  777 i pokazanie wyłącznie nowych podpowiedzi przed własnym przeglądem.
- Jawny zakres: korekta istniejących plansz; bez treningu i nowych importów
  V3 (D-489). Wynik biblioteki jest podpowiedzią, nie decyzją człowieka.
- Przeliczono 917/917 otwartych plansz: 10 425 nowych podpowiedzi i 3330
  pustych pól do ręcznego rozpoznania. 58 poprawionych plansz pominięto.
  Kolejka i decyzje człowieka nie zmieniły się podczas przeliczenia.
- Trwałe sidecary mają SHA-256 i dokładny kontekst podglądu. Biblioteka ma
  5653 referencje; wykluczono 192 referencje pochodzące z tego audytu.
  Restart CLI potwierdził 917 wyników, `processed=0`, bez ponownej kalkulacji.
- Reviewer 3001 przebudowano i uruchomiono. Odbiór UI: p00271 ma 10/15 nowych
  podpowiedzi, bez zaznaczonych decyzji symboli. Zmiana cięcia ukrywa wynik.
- Weryfikacja: testy API/CLI, biblioteki, Reviewera i klienta; lint, format,
  scoped strict Mypy, TypeScript, OpenAPI oraz build Reviewera. Szczegóły
  i instrukcja wznowienia w Outcome taska.
- Task i plan: `ai_docs/tasks/completed/0844-grid-audit-new-symbol-suggestions.md`.
- Commit: `v1.7.189`, `a6789285ecfbaa0ca0d94ff3016df6fab8f75d1c`.

### TASK-0842 — Mumie: wznowienie i partie danych (done)

- Operator 2026-10-04 polecił niezależnie dokończyć import i rozpocząć uczenie
  Mumii. Plan `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md` obejmuje jedną
  iterację 4 presetu F i przygotowanie danych. Bez uruchomienia TASK-0805.
- Run 3 zakończył iterację 4, próba 4, GPU worker PID 39560. Trening 901 s w istniejącym
  budżecie 14 400 s. Jawne założenie: jedna próba na tych samych 16 zdjęciach
  treningowych i 4 odłożonych (`--allow-same-data`), bez automatycznego
  powtarzania i bez etykietowania propozycji jako prawdy. Wszystkie trzy kandydaty
  przeszły strażnik 777, ale pogorszyły holdout Mumii (0,003296 →
  0,00351 / 0,00346 / 0,00358). F zachował poprzedni model. Bez nowego ONNX
  i propozycji. Zużycie runu 3602/14400 s, pozostało 10798 s.
- Sprawdzone SHA 225/225 plików folderu Mumii: wszystkie są w katalogu labu.
  Nowy eksport partii `afc4f0d7…fd816` w `artifacts/mumie-training-20261004/batches`:
  236 zdjęć, partie 50/50/50/50/36, 20 kompletnych, 216 do przeglądu,
  2700 nieoznaczonych wycinków z 180 zatwierdzonych plansz. Checksumy odczytane
  w nowym procesie. Powtórne uruchomienie odzyskało identyczny artefakt w 12,17 s.
  Bez zmian zatwierdzeń i bez zapisu do bazy.
- Istnieje zatwierdzony słownik Mumii (10 symboli) i 244 wcześniejsze decyzje
  z 2026-09-28. Wszystkie mają aktualne rewizje siatek, ale 0 dotyczy obecnie
  kompletnych zdjęć V3 i 0 pochodzi z nowego przypisywania D-489. Nie użyto ich
  do treningu symboli. 5 testów, Ruff check/format i Mypy PASS.
- Proponowana krótka nazwa: „Super”. Złota ramka wskazuje symbol wybrany do
  supergry; trzy mumie same nie ujawniają jego klasy. Stan ramki nie jest
  klasą symbolu ani Jokerem. Uczenie ramki i mechanika wypłat pozostają osobne.
- Raport: `ai_docs/quality/MUMIE_TRAINING_RESUME_20261004.md`.
  Następny zlecony zakres: TASK-0843 — wgranie do głównej aplikacji przez API.
  Commit TASK-0842: `v1.7.187` / `9f234575bb7d9090f311d5550a6264bcd7ed7ec2`
  (hash dopisany po commicie).

### TASK-0843 — Mumie w głównej aplikacji (done: upload i preflight)

- Zlecony addytywny import przez istniejące API. Gra draft z profilem Mumii,
  225 źródłowych JPEG-ów, zachowane zakresy `seq_*`. Bez wypłat, etykietowania
  za operatora, aktywacji nowego modelu, shadow i migracji.
- Nowy CLI `scripts/run_mumie_image_import.py` ma osobne kroki upload/advance/status,
  trwały raport, kontrolę SHA wejścia i ograniczone żądania. Historycznego CLI
  `verified_v19` nie uruchamiać. Rewizje bazy i modele pozostają takie jak wdrożone.
- Gra Mumie: `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`, draft,
  `grid_profile_mumie_v1`. Staging `becad72f-200d-4ba1-8d35-464b19d8f299`
  sfinalizowany: 225/225 plików, 61 768 538 bajtów. Upload 13,62 s.
  Stan trwały: `artifacts/mumie-import-20261004/state.json`.
- Geometry job `3e0151c8-b9ff-4da1-b96d-72af4cb01912` completed:
  225 źródeł, 0 failed, 225 review. Preflight wskazuje 2025 nowych pozycji,
  `IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED`. Import plansz nie został uruchomiony;
  kompletne wgranie źródeł nie oznacza materializacji plansz.
- TASK-0830 udostępnia wybór profilu, ale jawnie nie podłącza sieci do importu.
  Sieć działa w labie; główna aplikacja nadal wymaga przeglądu geometrii.
  V3-D/TASK-0805 pozostaje niewykonany bez wyraźnego polecenia operatora.
- Wznowienie w nowym procesie odzyskało ten sam gameId, uploadId i geometryJobId,
  bez nowego transferu i bez duplikatów. Kontekst `gameId` jest trwale dodany
  do wszystkich żądań stagingu/jobów; nie było potrzeby zmiany API ani migracji.
- Raport: `ai_docs/quality/MUMIE_PRODUCTION_UPLOAD_20261004.md`.
- Testy requestów 5/5 PASS, Ruff check/format PASS, Mypy strict CLI PASS
  (1 moduł, bez kontroli importowanych zależności). Commit TASK-0843: `v1.7.188`,
  `476bdc268e366720337299fb843666ec865fd9be` (hash dopisany po commicie). Bez push.
- Commity 187–188 scalone fast-forward do `v1.1-vision-lab-hybrid-geometry`
  w ramach wcześniejszej zgody operatora. Bez zmian kodu uruchamianych usług
  i bez nowego wdrożenia/migracji. Zastane zmiany pozostają poza commitami.


### TASK-0841 — edycja symboli po otwarciu planszy audytu (done)

- Commit: `v1.7.186` / `65ce8f212cc5f2b3930251b6539f8787dcf8df13`
  (wpis hash po commicie).
- Kolejka audytu używa skrótów katalogu (777: `1` Wiśnia, `5` Śliwka,
  `6` Arbuz); `9` oznacza „Nie wiem”. Dalsze symbole dostają `0`, potem litery.
- Podgląd startuje bez czekania na pełne zdjęcie canvas; pierwsze pole mające
  piksele jest zaznaczone po podglądzie. Opóźniony katalog uruchamia paletę bez
  ponownego podglądu. Zaznaczenie niczego nie przypisuje ani nie zapisuje.
- Dwa testy regresji odtworzyły brak podglądu przed poprawką. Po poprawce:
  interakcje Reviewera 18/18, jednostkowe 208/208, lint, typecheck,
  formatowanie pięciu plików i build poprawne. Build w worktree ostrzega
  o dodatkowym lockfile przy wykrywaniu root; nie wpływa na wynik.
- Nowe ustawienia edytora są opcjonalne; zwykła korekta zachowuje dotychczasowe
  zachowanie. Bez zmian API, migracji i zapisu na żywej bazie.
- Poprawka scalona fast-forward do `v1.1-vision-lab-hybrid-geometry`.
  Reviewer z głównego checkoutu przebudowany (17,27 s) i zrestartowany;
  launcher PID 3432, HTTP 200. Pierwszy polling z timeoutem 1 s na request
  nie potwierdził gotowości; odczyt logów i nowy odczyt HTTP potwierdziły
  działanie tej samej kopii (bez ponownego startu).
- Odbiór w świeżo otwartej planszy 423759: podgląd 15/15, pierwsze pole
  zaznaczone, paleta `1–9` widoczna. Klawisze `1`, `5`, `6`, `9` zweryfikowane
  bez ruszania siatki i ręcznego preview. Testowy wybór usunięto bez zapisu.
  Screenshot: `artifacts/grid-v3-deployment-20261004/task0841-live.jpg`.
- Wyniki odbioru i własny hash dopisane po commicie; brak push. Zastane zmiany
  użytkownika w wygenerowanym kliencie oraz package-lock zachowane.

### TASK-0835 — konflikt rewizji przy zapisie korekty siatki (done)

- Zapis w „Korekcie cięcia siatki” kończył się `IMAGE_GRID_REVIEW_REVISION_CONFLICT`
  dla plansz z komórkami przypiętymi do starszego renderera (import 777: wszystkie
  `v1`, bieżący `v4`). Po TASK-0815 serwis wiązał kontekst z bieżącym rendererem,
  a repozytorium porównywało go z kontekstem z bazy. `_require_same_context` pomija
  teraz wersję extractora; rewizje, źródło i geometria nadal muszą się zgadzać.
- Testy `test_virtual_grid_geometry.py` 27/27. API przeładowane (`--reload`).
  Brak testu zapisu na żywej bazie.

### TASK-0834 — skróty klawiszowe symboli w korekcie siatki (done)

- Paleta symboli korekty (Reviewer 3001) używa tych samych klawiszy co Weryfikacja
  symboli (1–9, 0, litery wg kolejności katalogu gry): klawisz wybiera symbol
  zaznaczonego pola, a przycisk palety pokazuje swój klawisz. „? Nie wiem” i
  „Usuń wybór” bez skrótu.
- Interakcje 9/9, typecheck i lint czyste. Reviewer przebudowany i zrestartowany;
  brak odbioru na żywo.

### TASK-0827 — poprawianie planszy z wyników wyszukiwania (done)

- Karta „Wyniki wyszukiwania” ma przycisk „Pokaż planszę”: otwiera to samo okno z liniami
  wypłat co tabela przybliżonej wygranej, z „Popraw symbole”. Z wyników okno nie
  ma numeru spinu; wygrana i spójność linii pochodzą z odczytu planszy.
- Po zapisanej poprawce zamknięcie okna ponawia wyszukiwanie (zaznaczony wynik
  zostaje). Bez zmian API.
- Interakcje 38/38, typecheck i lint czyste. **Brak odbioru na żywo**: wymagany
  `reviewer:build` i restart.

### TASK-0825 — opcja „Nie wiem” w palecie symboli korekty siatki (done, D-488)

- Paleta ma przycisk „? Nie wiem”: pole zasłonięte lub widoczne we fragmencie można
  zapisać bez zgadywania. `cellSymbols[].symbolId = null` oznacza komórkę jako
  nieczytelną (`mark_unreadable`, oczekująca, bez etykiety); symbol dalej daje
  `reassign`. Kafelek pokazuje „?”, „Usuń wybór” przywraca podpowiedź.
- Zmiana kontraktu API (nullowalny `symbolId`), OpenAPI i klient wygenerowane.
- Testy API 42/42, interakcje Reviewera 12/12, typecheck, lint i `check:generated`
  czyste. **Brak odbioru na żywo**: wymagany restart API i `reviewer:build`.

### TASK-0826 — trwałe usunięcie zarchiwizowanej gry V2 (done)

- Na prośbę operatora (2026-10-02) usunięto z bazy deweloperskiej dwie testowe,
  zarchiwizowane gry „Mumie” (`mums`, `mums-test-1`): partycje `game_data_v2`,
  symbole, wersje zasad, zadania i rekordy gier. W bazie pozostaje jedna gra:
  777 (`draft`), nienaruszona (63 partycje, 590 zadań).
- Nowa komenda `scripts/delete_archived_v2_game.py` (podgląd tylko do odczytu,
  blokady, potwierdzenie + SHA, wznawianie) nad istniejącym lifecycle `delete`;
  opis w `LOCAL_OPERATION_GUIDE.md`. Admin nadal tylko archiwizuje.
- Na dysku pozostały niereferencjonowane pliki obu gier (ok. 8 MB w
  `imports/browser-selections` i jeden manifest geometrii); lista w Outcome
  zadania. Scalono do `v1.1-vision-lab-hybrid-geometry` jako `v1.7.168`
  (numer zadania zmieniony z TASK-0812 na TASK-0826, bo 0812 i 0824 zajęte).

### TASK-0822 — klikalne kafelki i wybór symbolu w korekcie siatki (done, D-488)

- Ekran „Korekta cięcia siatki” (Reviewer 3001): kafelek podglądu z pikselami
  jest przyciskiem, pod podglądem jest paleta aktywnych symboli gry. Kafelek
  pokazuje podpowiedź (kursywa) albo wybór operatora (pogrubienie, zielone
  tło); „Usuń wybór” cofa wybór. Zapis siatki wysyła wyłącznie wybrane pola
  (`cellSymbols`); pola bez pikseli nie są klikalne.
- Podpowiedzi są pobierane po każdym aktualnym podglądzie; ich błąd nie
  blokuje korekty ani zapisu. Dialog korekty w przeglądzie operacyjnym nie ma
  palety (poza zakresem planu).
- Testy: interakcje Reviewera 11/11 (2 nowe), jednostkowe 200/200 (1 nowy),
  typecheck i lint czyste.
- **Brak odbioru na żywo.** Po scaleniu wymagany restart API i
  `npm run reviewer:build`. Plan
  `GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md` jest wykonany w całości.

### TASK-0821 — podpowiedzi symboli dla cięcia w korekcie siatki (done, D-488)

- `GET /admin/image-reviews/{reviewItemId}/correction-symbols`
  (`getImageGridReviewCorrectionSymbols`): symbole zapisane na bieżących
  komórkach planszy zgłoszonej — przypisany, a przy jego braku predykcja.
- `POST …/board-cell-geometry-pending/{pendingId}/geometry-symbol-preview`
  (`previewPendingBoardCellGeometrySymbols`): predykcja przypiętego modelu dla
  podanego cięcia planszy odroczonej; brak modelu → pusta lista. Oba endpointy
  niczego nie zapisują. Nowy POST jest na allowliście proxy Reviewera i
  serwerowej allowliście originu 3001 (`security/local_admin.py`).
- Testy: serwis 56/56, żądania API (pending 13, grid review, security 6),
  PostgreSQL 1/1, klient 76/76, Reviewer 199/199; `openapi --check` i
  `check:generated` aktualne.

### TASK-0820 — zapis symboli operatora przy zapisie siatki (done, D-488)

- `createImageGridReviewGeometryRevision` i
  `resolvePendingBoardCellGeometryManually` przyjmują opcjonalne `cellSymbols`
  (`cellIndex`, `symbolId`). Wskazane pola są zatwierdzane istniejącą akcją
  `REASSIGN` (`approved`, `human`) dla nowego cropa, w transakcji zapisu
  geometrii; powtórzenie tym samym kluczem stosuje przypisania ponownie.
- Błąd przypisania (pole bez bieżącego cropa, nieaktywny symbol, zdublowany
  indeks) wycofuje cały zapis. Zapis bez `cellSymbols` działa jak dotąd.
- Testy: serwis 53/53, test PostgreSQL przypisań 1/1 (izolowana baza testowa),
  żądania API 13/13, klient 76/76, Reviewer 199/199, typecheck Reviewera.
  `test_grid_review_openapi_is_topology_aware_and_checksum_bound` pada także
  na niezmienionej gałęzi (oczekuje `minItems` komórek) — poza zakresem.
- Plan: `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`; dalej
  TASK-0821 (podpowiedzi) i TASK-0822 (UI).

### TASK-0819 — podgląd korekty siatki dla niepełnych plansz, jeden widok cropów (done)

- Zgłoszenie operatora: podgląd niepełnej planszy kończył się
  `IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE`. Kontrola arkusza podglądu
  wymagała braku renderu dla każdego pola z maski, a renderer od D-434/D-435
  zachowuje pola częściowo widoczne. Teraz wymagane są tylko pola spoza maski;
  pola z maski mogą mieć render. Dwa czerwone testy podglądu częściowego
  opisywały stare zachowanie i zostały zaktualizowane.
- Reviewer pokazuje jeden widok cropów (kafelki); usunięto zdublowany obraz
  zbiorczy bez odstępów.
- Testy API korekty siatki 50/50, interakcje geometrii Reviewera 9/9,
  typecheck i lint Reviewera czyste. Wymagany restart API i przebudowa
  Reviewera; brak odbioru na żywo.
- Otwarte: przypisywanie symboli w korekcie siatki (klikalne kafelki, podgląd
  predykcji) wymaga planu i zmiany D-462 — korekta dziś nie zatwierdza symboli.

### TASK-0817 — stawka odbiorcy na wykresach dziennika linku (done)

- D-487: strona linku zgłasza stawkę każdego pokazanego zakresu
  (`GET …/approximate-win/stake`), API zapisuje ją jako wpis zakresu ze
  `stakeGrosze`, a wykres w dzienniku Admina jest rysowany w tej stawce.
  Bez migracji. Starsze wpisy: „stawka nieznana (wykres w stawce bazowej)”.
- Do działania u odbiorców potrzebne są przebudowany Reviewer
  (`npm run reviewer:build`) i restart API po scaleniu.

### TASK-0816 — dziennik linku grupuje te same wzory (done)

- D-486: `listBoardSearchShareQueries` z `groupByPattern=true` zwraca jeden
  wpis na wzór z `occurrenceTimes`; `deleteBoardSearchShareQuery` z
  `wholePattern=true` usuwa wszystkie wyszukiwania wzoru. Dziennik w Adminie
  pokazuje czasy po przecinku i przycisk „Usuń wszystkie (N)”.
- Przy okazji naprawiony nieaktualny test interakcji dziennika
  (`board-search-share-panel.test.mjs` oczekiwał kontraktu sprzed D-478).

### TASK-0814 — hurtowe odświeżenie nieaktualnych odczytów wyszukiwarki (done)

- 2026-10-02 operator zgłosił, że „Pokaż planszę” dla #486288 pokazywało
  schemat z domyślnymi grafikami symboli zamiast zdjęcia do czasu ręcznego
  „Odśwież odczyt tej planszy”. Przyczyna: odczyt wyszukiwarki zapisany przed
  bieżącą siatką planszy (`documentStale`, TASK-0773). Gra 777 miała 62 142
  takich plansz (wszystkie `pending`) z 499 997.
- Nowy `scripts/refresh_stale_board_search_documents.py --game-id …` liczy
  je bez zapisu, a z `--apply` odświeża każdą tą samą synchronizacją co
  przycisk w oknie, partiami po jednej transakcji; ponowne uruchomienie
  wznawia pracę. Commit `v1.7.158` / `cd36d0a2`.
- Wynik uruchomienia na bazie deweloperskiej (2026-10-02): próba 200 plansz
  i pełny przebieg 61 942 — razem 62 142 odświeżone, 0 usuniętych z
  wyszukiwarki, 0 nadal nieaktualnych; kontrolny podgląd po przebiegu: 0.
- Przyczyna zaległości: jednorazowa ponowna weryfikacja siatek 777 z
  2026-09-25 (`system:grid-reverify-777-v1`), wykonana zanim zapis siatki
  zaczął synchronizować projekcję wyszukiwarki (`v1.7.51`, 2026-09-29;
  przepinanie sąsiednich plansz — `v1.7.145`). Żadna nieaktualna plansza nie
  miała siatki zapisanej po 2026-09-25, więc poprawka kodu nie była potrzebna.

### TASK-0818 — plansze „częściowa (potwierdzone minimum)” do korekty siatki (done)

- Decyzja operatora 2026-10-02: plansze z nieznanymi polami oznaczonymi
  `unreadable` albo `partial_visibility` trafiają do kolejki „korekta cięcia
  siatki”. `scripts/route_partial_boards_to_grid_correction.py` (podgląd,
  `--apply`) zgłasza te pola jako „zła siatka” istniejącą decyzją pola.
  Commit `v1.7.159` / `104f9d81` (numer sprzed scalenia; zadanie
  przenumerowane z 0815 z powodu kolizji z torem korekty siatki).
- 777: skierowano 219 plansz (179 + 40), 0 pominiętych; kolejka korekty ma
  331 plansz w 20 importach. 7 plansz bez rekordu pola pozostało bez zmian.
  Skierowanie jest jednorazowe; nowe przypadki wymagają ponownego uruchomienia.
### TASK-0815 — ręczna korekta siatki po bumpie kontraktu renderera (done)

- Zgłoszenie operatora: każda zmiana siatki w „Korekcie cięcia siatki” kończyła
  się `IMAGE_VIRTUAL_CELL_EXTRACTOR_MISMATCH`. Kontekst korekty brał wersję
  extractora z render speców istniejących komórek (albo ze snapshotu rolloutu
  joba), a renderer po TASK-0660/0661/0663 ma `…-source-direct-v4`, więc
  odrzucał plansze zaimportowane wcześniej.
- `VirtualGridGeometryService` wiąże teraz konfigurację renderu z bieżącym
  rendererem (pojedyncza plansza, zapis źródła/odroczonego slotu, konwersja
  legacy); pozostałe przypięte pola (preprocessing, interpolacja, rozmiar,
  padding) bez zmian. Bez zmian API, schematu i danych.
- Test regresyjny przechodzi; plik testów 48/50 — dwa przypadki
  `test_qualified_partial_preview_…` padają także bez tej zmiany (poza
  zakresem). Wymagany restart API; brak odbioru na żywym Reviewerze.

### TASK-0782 — zmiana kolejności symboli w katalogu (done)

- Gałąź `feat/symbol-display-order` (worktree `worktrees/symbol-display-order`)
  od `v1.7.56`. `PATCH` symbolu przyjmuje `displayOrder`; katalog symboli w
  Adminie ma przyciski „↑/↓”, które przenumerowują listę `0..n-1`. Skróty 1–9
  weryfikacji symboli i wyszukiwarki plansz podążają za kolejnością. Operator
  zamienia „7” i „gwiazdę” w grze 777 w panelu; snapshot mobilny dostanie nową
  kolejność przy kolejnym `snapshot:generate`.
- Commit `v1.7.57` / `5ab34453` na gałęzi `feat/symbol-display-order`
  (numer sprzed scalenia; zadanie przenumerowane z 0730 z powodu kolizji).
  Scalone do `v1.1-vision-lab-hybrid-geometry` commitem `v1.7.132`.
