---
title: TASK-0896 — Collapsible single-row symbol filters
status: done
last_updated: 2026-10-07
---

# TASK-0896 — Collapsible single-row symbol filters

## Status

`done`

## Goal / context

Keep state, confidence and prediction-source options on one row each and allow
independent collapse of advanced filters and the date section to free crop space.
User explicitly requests this change. Existing fieldsets enforce three columns.

## Dependencies / entry conditions

MAIN HEAD v1.7.238, `5e44ea88954f68f2ef473ca8dcefc52e2064fc21`.
Code initially clean; prior completion receipts are not this task's changes.
Assumptions: sections initially open, collapse does not change active filters,
mobile rows scroll locally, normal/full-screen share collapse state. No blocker.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, matching the plan. Audit keyboard/hidden state
and responsive overflow. No delegation; escalate for a filter-contract conflict.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — symbol verification/fullscreen
- `ai_docs/architecture/API_CONTRACT.md` — existing filter scope
- `ai_docs/delivery/SYMBOL_REVIEW_FILTER_LAYOUT_EXECUTION_PLAN.md`
- `ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md`

## Scope / out of scope

Local collapsible UI and one-row responsive layout. Preserve all filtering,
date validation/drafts, selection, target reset, keyboard and mutation contracts.
No API/schema changes, data decisions, training, cleanup, deployment, push/merge.

## Acceptance criteria

- [x] Each radio group has one horizontal option row on desktop/fullscreen;
  narrow screens scroll it locally without wrapping or page overflow.
- [x] Radio/date sections collapse independently with accessible toggles,
  initially expanded. Hidden controls retain values and do not receive focus.
- [x] Collapse/fullscreen changes retain active filters, date draft and crop
  selection without reloading data or submitting a mutation.
- [x] Enter on an expander never invokes save; active filters remain visible
  as a count/date range in the collapsed header.
- [x] Focused tests, scoped format/lint/types, build and normal/fullscreen/
  390 px browser inspection pass. Docs, Outcome and one commit complete.

## Technical notes / expected files

Existing `symbol-review-workspace.tsx`: wrap the radio groups and date fieldset
in a proposed local `SymbolReviewFilterSection`. Keep mounted hidden content;
explicitly stop Enter bubbling from the header to the global save handler.
Use unique IDs and aria-expanded/controls. Existing `.filters fieldset` CSS
becomes full-width; proposed `.radioOptions` is nowrap with local overflow.
Keep date responsiveness and explicit hidden CSS. Existing interaction tests
cover retained state and keyboard; requirements/operator guide describe behavior.

## Test cases / verification

Open/close each section independently, change radio before collapse, retain
a typed date draft and selected crop, toggle fullscreen and reopen. Enter on
header with a chosen save target yields no decision. No page/atlas reads
introduced by collapse. Existing symbol tests remain regression coverage.
Run tsx interactions and focused Node contracts/helpers first, scoped
Prettier/ESLint/TypeScript, then Admin build, each bounded to 120 s. Read-only
browser inspection verifies actual geometry and height gain including 390 px.

## Risks / open questions

Prevent display:grid from overriding hidden and avoid document-wide overflow.
Do not clear/reset any filter while collapsing. No blocking question.

## Outcome

### Changed

- All three radio groups use full-width single rows with local horizontal
  scroll when necessary. Removed the three-column forced wrapping.
- Local `SymbolReviewFilterSection` provides independent, initially open
  radio/date sections. Mounted hidden controls retain active conditions and
  drafts. aria-expanded/controls, unique IDs and 44 px toggles provide access.
  Enter on a toggle cannot reach global save; active count/date remain visible.
- Fullscreen preserves folding. At mobile width the tall filter panel scrolls
  vertically within 45dvh to keep controls accessible without widening the page.

### Verification results

- Fresh-process interactions 14/14, focused Admin contracts/helpers 40/40
  PASS. Regression covers independent folding, preserved radio/date draft,
  selection/target, no page/atlas read or mutation on folding, fullscreen,
  Enter and active-date header. Existing mutation protections remain green.
- Scoped Prettier/ESLint/TypeScript PASS. Admin build PASS in 21.12 s. All
  commands bounded to 120 s; normal and whitespace-independent diffs audited.
- MAIN browser: desktop options share identical Y positions within each group;
  fullscreen crop viewport grows from 2 to 167 px after folding both sections
  at the observed 1280 x 720 viewport. Returning to normal mode keeps them folded.
- At 390 x 844, document width equals 390 px. Each option group remains one
  row; horizontal overflow is local (320 px containers). Mobile filter panel
  scrolls vertically (378 px client height, 866 px content). Hidden radios
  leave the accessibility tree. No console errors or submitted real decisions.
- Screenshots: `artifacts/symbol-review-filter-layout-20261007/expanded.png`,
  `collapsed.png`, `mobile.png`. Temporary browser tab closed and viewport reset.

### Documentation updates / limits

Admin requirements, Mumie operator guide, plan and CURRENT_STATE updated.
Acceptance criteria and applicable Definition of Done audited individually.
No API/schema change, real data operation, training, cleanup, service restart,
deployment, push or merge. Browser mobile check is not a physical Android test.
No task blocker. Refresh an older Admin tab if its bundle remains stale.

Completion version v1.7.239; commit
`713bf4f2b5d264bea6eaf7d749fbb369e922e312`.
