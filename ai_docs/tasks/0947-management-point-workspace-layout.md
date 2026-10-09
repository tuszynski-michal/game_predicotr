---
title: Point workspace and persistent machine selection
status: todo
last_updated: 2026-10-09
---

# TASK-0947 — Point workspace and persistent machine selection

## Status

todo

## Goal

Show the machine list and selected machine's games/stakes together on the
point page, with consistent spacing, explicit selection and saved pin summaries
visible on every saved stake without selecting it.

## Context

ManagementWorkspace hides the list under selected && !machine. Correct the
render boundary rather than just adding a color. Preserve existing navigation
state, URL restoration, dirty-draft confirmation and shared search ports.
ManagementCards currently omits pinnedPoints; the only summary renderer in
ManagementGameWorkspace is gated by selectedStake && !editor. The operator
requires summaries on all saved cards immediately after Save and on reopen.

## Dependencies / entry conditions

Plan status proposed. Do not implement until the operator authorizes execution.
Read the task and its plan again; preserve concurrent edits and check the tip.
No services, operator-data writes or migration are authorized by this task.

## Relevant docs

- ai_docs/delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Recommended execution

gpt-6.1-sol / medium. Matches the plan model table. One bounded independent
claude-opus-5-5 / medium static review. Escalate if contracts/data ownership
change or the existing acceptance tools cannot establish the required behavior.

## Scope

- Always mount the selected point's machine grid when pointId exists.
- Give the selected machine tile data-selected and aria-pressed from machineId.
- Mount only one detail workspace below the list; no machine-level screen/back.
- One Home/back action, clear headings,16px insets and12/24px spacing.
- Keep max320px tiles and4/3/2/1 columns. Cap the labelled machine-list scroll
  region at min(288px,40dvh), with role/name/tabIndex and overscroll containment.
  Only change its scrollTop on URL/reload restoration; keep document scroll
  unchanged on click. Point/Home push history; machine/game/stake replace it.
  Point title/Home source tile receive focus; machine click retains tile focus.
- Compact stake text/symbol placement per plan; preserve20px assets and fallback.
- Show all0-6 saved pins on every saved stake from its summary, independent of
  selectedStake or editor. Reuse existing pin row presentation with optional
  compact/currency ports, preserving the default credit table for other consumers.
- Use frozen requiredStakeCredits/balanceCredits/machineCashCredits with existing
  amount formatting; preserve negative/zero/unavailable/null semantics.
- After successful Save refresh that card's summary even while its editor stays
  open. Draft/reset keeps saved rows until explicit commit; scope switch/reload
  must show only current machine/game summaries, without full-result fetches.

## Out of scope

New API/schema, payout calculations, global Admin redesign, production data,
service lifecycle, push/merge and unrelated operator changes.

## Acceptance criteria

- [ ] A and B switch highlight/details while the same machine list remains.
- [ ] Home/point switch clears scope; URL/reload restores a valid selection.
- [ ] Rejected dirty navigation preserves selection, URL and draft.
- [ ] Edit/delete does not select a machine; only one detail workspace renders.
- [ ] Forty machines do not push stakes below a full-height machine list.
- [ ] Narrow layouts have no horizontal overflow or clipped content.
- [ ] Before task completion: Chromium390x844,40 machines, select35; region height
  bounded, scrollY unchanged, detail heading within1.5 viewports, selected tile
  computed border/background differs from its neighbor.
- [ ] Back does not traverse machine/game/stake choices; direct links keep
  standard browser history. Focus follows the plan without stealing tile focus.

- [ ] With no selected stake, each saved card shows all saved pin spin/value rows.
- [ ] Two saved stakes show their own different pins without opening either.
- [ ] Save updates the visible summary while editor remains open; draft/reset
  does not alter the saved summary before Save.
- [ ] Reload/reopen restores rows; machine/game switch has no leaked previous rows.
- [ ]0/1/6 pins, spin0, signed losses, unavailable/null metadata and currency
  units are readable; cards are not clipped. Frozen super-spin/provisional
  semantics are preserved without adding a calculator.

## Technical notes

Use existing components/helpers. Read and apply the corresponding plan section;
newly proposed UI behavior is not evidence of already working implementation.

## Expected files

- packages/board-search-ui/src/management/management-workspace.tsx: ManagementWorkspace.
- packages/board-search-ui/src/management/management.css: grid, tiles, section spacing.
- apps/admin/test-interactions/management.test.mjs: selection/navigation regressions.
- scripts/management_browser_flow.mjs: persistent list geometry, selection and saved summaries.
- packages/board-search-ui/src/management/management-cards.tsx: ManagementCards.
- packages/board-search-ui/src/management/management-game-workspace.tsx: summary placement.
- packages/board-search-ui/src/board-search-approximate-win.tsx: ApproximateWinPinRows optional display ports.
- apps/admin/test-interactions/management-cards.test.mjs: per-card saved pin visibility.
- Shared pin-row tests: default presentation regression if optional props are added.

## Verification

From apps/admin: node ../../node_modules/tsx/dist/cli.mjs --tsconfig tsconfig.json
--test test-interactions/management.test.mjs test-interactions/management-cards.test.mjs
(120s). Include the existing shared pin helper/interaction regression when its
presentation changes. Then shared workspace lint
and typecheck via existing npm scripts (120s each). One Chromium390x844
case is mandatory here (existing fixture/browser scripts,120s per step).
Broader two-host browser evidence follows in0949.

## Risks / open questions

Plan execution and the historical-restore exception await approval. Confirm
model availability and the complete expected cost before starting costly work.

## Outcome

Planning only. No implementation or new validation results. Replaces the
unfinished0947 draft, saved as an ignored patch after operator requested a plan.
