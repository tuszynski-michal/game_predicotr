# TASK-0924 — Stake overview, history and current results (T4)

## Status

done

## Goal

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T3 / TASK-0923 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T3 v1.7.255 / 85a8914dc2195e986f4c807c4a0cb468e9f312de; independent sol/high review PASS.

## Recommended execution

gpt-6.1-sol / high; response races, history semantics and bounded reads. Independent gpt-6.1-sol / high review
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

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear. Journal under chart/table default20 entries, immutable historical result render, current-data editor label. Queue max2 refreshes, cancellation on navigation; initial last result checking then current. Changed calculation journals before/after; unchanged read dedup; unavailable pins explicitly listed. Refresh cannot overwrite an unsaved draft or later slot revision. No eager full rows/images in point lists/card summaries.

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

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear. Journal under chart/table default20 entries, immutable historical result render, current-data editor label. Queue max2 refreshes, cancellation on navigation; initial last result checking then current. Changed calculation journals before/after; unchanged read dedup; unavailable pins explicitly listed. Refresh cannot overwrite an unsaved draft or later slot revision. No eager full rows/images in point lists/card summaries.

## Expected files

- Existing: `apps/admin/src/features/management/management-workspace.tsx`,
  `apps/admin/src/features/catalog/catalog-workspace.tsx`,
  `apps/admin/src/app/globals.css`; hierarchy and outer draft navigation guards.
- Proposed management feature modules: `management-client.ts`,
  `management-data-source.ts`, `management-slot-operation.ts`,
  `management-slot-state.ts`, `management-game-workspace.tsx`,
  `management-cards.tsx`, `management-journal.tsx`, `management-result-view.tsx`.
- Proposed focused interaction/state tests for cards, refresh queue, recovery,
  historic results, journal and guarded navigation. No API/OpenAPI extension.
- Generated response types and injected client keep the same UI extractable for
  Reviewer in T6. Compact SVG consumes bounded authoritative chart points;
  full frozen numeric rows load only on Open/history. Archived/detached history
  is read-only. Corrections refresh saved summaries/journal without draft remount.
- Lead owns shared documentation, staging and separate commit.

## Test cases

Independent slot states, changed symbols/rules and prior history, error marks stale rather than zero, six-card concurrency≤2, obsolete responses cancelled/ignored, out-of-range pins, history pagination, mobile responsive styles and archive/detach readable history.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

### Changed

Implemented six fixed-stake cards for the selected machine/game, with bounded
saved previews, exact pins, save time and independent checking/current/stale
states. Full persisted results and journal versions load only on demand. The
result chart/table/rules remain frozen while the explicitly labelled current
editor uses fresh symbols and published rules at the selected stake.

Refreshes run through a two-request abortable queue. Identity and revision
guards cover both cards and the displayed current version; a delayed refresh
cannot restore a result replaced or cleared by a later acknowledged operation.
The opened draft retains its captured CAS baseline and survives refreshes,
conflicts and capability changes. Internal navigation, outer Admin tabs,
browser history and window unload protect an unsaved draft.

Save, Clear, search and correction preserve their exact UUID and command across
uncertain responses and fresh component instances. Slot refresh recovery also
preserves the exact request across reload. A pending operation blocks composing
an unrelated replacement request. A confirmed retry acknowledges its own opened
revision without discarding a subsequently edited draft; an older refresh
receipt leaves a later remote save stale with an explicit recheck action rather
than indefinitely checking. Read-only archived/detached history remains
available. The injected generated-client boundary and actor/session storage
namespace prepare this same UI for T6.

The journal reads 20 entries per page, uses actual domain action codes and shows
readable before/after evidence for the address, archive state, game attachments,
symbol quality/approval, search pattern/scope, payout summary and saved pins.
Product labels no longer expose raw rules JSON, fingerprints or operation IDs.

### Verification results

Validation completed in fresh bounded processes (120-second command limits):

- `tsx --tsconfig tsconfig.json --test
  test-interactions/management-cards.test.mjs` in `apps/admin`: 19/19 PASS.
  Meaningful regressions cover queue bounds/cancellation, card and displayed
  result races against Save/Clear, reload retry UUID/body preservation, retry CAS
  acknowledgement, conflict baseline recovery, dirty capability changes,
  historical correction with old/new rule scaling, journal before/after and
  actual outer-tab/popstate cancellation.
- Direct `tsc --noEmit --incremental false` in `apps/admin`: PASS; no Next
  type generation or build was invoked.
- Scoped ESLint for management, Catalog host and the new interaction test with
  `--max-warnings 0`: PASS. Prettier on all 12 changed product/test files: PASS.
- Existing management interactions: 4/4 PASS. Existing Admin navigation and
  game-catalog actions/contracts/state: 33/33 PASS. Shared saved-selection,
  correction, approximate-win and replay interactions: 36/36 PASS.
- Independent T4 reviewer: PASS with no unresolved P0–P2; independently verified
  23/23 new/existing management interactions, Admin types, scoped lint and format.

### Not completed and limitations

The shared approximate-win regression fixture emitted an existing duplicate
`operational_review:10` React key warning; its assertions passed. No unrelated
fixture or product changes were added. No API/Admin lifecycle, live database,
browser/device smoke, build, push or deployment was performed. Responsive
layout uses the existing shared styles and a narrow-screen single-column card
layout; visual smoke remains for the integrated delivery check.

### Documentation updates

Executor file manifest: `artifacts/management-panel-t4/final-files.json`.
Acceptance compared with task scope and approved T4 plan: all implemented
gates pass. Lead updated architecture/CURRENT_STATE and closed the task after
independent review. Full commit receipt is appended after the commit.

### Recommended next task

T5 / TASK-0925: independent panel sessions and public API, plus48/72h links.
