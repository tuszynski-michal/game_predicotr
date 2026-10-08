# TASK-0923 — Shared search with explicit saved selection (T3)

## Status

done

## Goal

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T2 / TASK-0922 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T2 v1.7.253 / 1a93bc521316c92eaaed8443e26e2f382a72c25a.

## Recommended execution

gpt-6.1-sol / high; shared UI state and regression protection. Independent gpt-6.1-sol / high review
as accepted model table. Escalate unresolved safety/data/contract findings.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/architecture/SYSTEM_ARCHITECTURE.md

## Scope

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration. Controlled pin spin positions not SVG coordinates. Browsing/pinning never persists. Search again preserves old save until successful receipt. Unsaved navigation warns; failed save retains draft. Reuse payline modal and current correction writer; preserve ordinary Admin and one-game recipient defaults.

## Out of scope

Unrelated modules, accounts, hosting/synchronization, Redis, production migrations,
API/Admin lifecycle, push/merge/model activation and destructive history deletion.

## Acceptance criteria

- [x] Complete task scope and corresponding plan behavior implemented.
- [x] Test cases below verified with meaningful assertions.
- [x] Atomicity, eligibility and error semantics preserved.
- [x] Focused format/lint/types and changed-contract checks pass.
- [x] Independent review has no unresolved P0–P2.
- [x] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration. Controlled pin spin positions not SVG coordinates. Browsing/pinning never persists. Search again preserves old save until successful receipt. Unsaved navigation warns; failed save retains draft. Reuse payline modal and current correction writer; preserve ordinary Admin and one-game recipient defaults.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Rendered existing consumers unchanged; fixed stake across new searches; selected board/range/pins restore; pins and hover never autosave; stale callbacks game/slot switch ignored; response loss safe retry; disabled duplicate Save; unsaved warning.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

### Changed

- Shared workspace has optional stable `scopeKey`, `fixedStakeGrosze`, initial
  `savedSelection`, complete `BoardSearchDraft`, `onDraftChange`, `onDirtyChange`
  and explicit asynchronous `onSave`. Background slot snapshots do not overwrite
  mounted drafts. Inline host callbacks do not create notification/render loops.
- A trusted persisted start is loaded by explicit sequence and calculated without
  running a new ranked search or substituting its first hit. Existing search
  receipts are retained for same-slot edits; optional `searchContextId` accompanies
  the shared data-source result. T4 owns UUID/CAS and durable pending retries.
- Browsing, composing, ranges and controlled pins only change the draft. Failed
  Save preserves its complete contents; concurrent duplicate Save is blocked.
  `beforeunload` and exported internal-navigation confirmation protect dirty work.
  Changing a managed query limit invalidates its search receipt until a new search.
- Controlled chart pins use 0–6 integer spin positions, including zero and losing
  spins, and recompute end-of-spin values from current numeric data. Out-of-range
  pins remain explicitly unavailable and removable. Controlled no-win results
  still draw a chart; ordinary empty-chart and stake-selection defaults remain.
- Managed start, carousel and payout-row editors reuse the existing immediate
  human correction writer. Fixed stake formatting uses the modal's freshly loaded
  rules and selected unit. Corrections recalculate the unchanged saved start and
  preserve query/context/range/pins. Obsolete search/calculation/save completions
  cannot update a different game/slot.

### Verification results

All steps used `artifacts/management-t2/run_bounded.py` with a 120-second limit.
Commands run from repository root unless a package directory is stated.

- `node node_modules/tsx/dist/cli.mjs --tsconfig packages/board-search-ui/tsconfig.json
  --test packages/board-search-ui/test-interactions/board-search-saved-selection.test.mjs`:
  **10/10 PASS**. Real rendered interactions cover trusted missing ranked start,
  fixed stake, zero/losing/unavailable pins, draft-only browsing, loss/identical
  retry, duplicate Save, navigation, scope races, late symbols/background updates,
  fresh rules in both modal paths, correction invalidation and inline callbacks.
- `npm.cmd run test --workspace @game-predictor/board-search-ui`: **77/77 PASS**.
- `npm.cmd run test:interactions --workspace @game-predictor/board-search-ui`:
  **49/49 PASS**, including 39 ordinary Admin/replay/one-game-share regressions.
- `node node_modules/typescript/bin/tsc --noEmit -p` with
  `packages/board-search-ui/tsconfig.json`, `apps/admin/tsconfig.json` and
  `apps/reviewer/tsconfig.json`: **PASS**, separate fresh processes.
- Scoped ESLint for all ten source/test paths in `artifacts/management-t3/final-files.json`:
  **PASS**. Executed from `packages/board-search-ui` using
  `node ../../node_modules/eslint/bin/eslint.js` with the listed package-relative paths.
- Scoped `node node_modules/prettier/bin/prettier.cjs --check` for the same ten
  paths: **PASS**. `git diff --check -- packages/board-search-ui`: **PASS**.
- Independent gpt-6.1-sol / high review reported no unresolved P0–P2; lead owns
  final audit acceptance, versioned commit and task closure.

### Not completed

- Standard Admin/Reviewer `npm.cmd run typecheck --workspace ...` ended with
  exit 0, but their `pretypecheck` Next route generator printed sandbox SWC
  canonicalization `AccessDenied`. This is not successful route-generation
  evidence. Separate direct TypeScript checks passed; T3 changes no routes.
  T7 owns isolated route generation/build acceptance.
- No services were started/stopped, no user data or migrations were changed,
  and no deployment, push or production rollout was performed.
- Full management card hosting, persistence retry identity/revisions and public
  recipient integration belong to T4/T6. No API contract change was required.

### Documentation updates

- This Outcome and `artifacts/management-t3/final-files.json` record exact scope
  and evidence. Lead owns CURRENT_STATE, requirements/architecture notes,
  independent review receipt, staging, commit and completed-task movement.

### Recommended next task

T4 / TASK-0924 after independent audit and a separate T3 commit.
