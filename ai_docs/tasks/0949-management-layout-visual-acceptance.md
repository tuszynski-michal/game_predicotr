---
title: Visual acceptance and operator handoff
status: todo
last_updated: 2026-10-09
---

# TASK-0949 — Visual acceptance and operator handoff

## Status

todo

## Goal

Verify the new composition through actual rendering and document the distinct
mock, isolated backend and live-operator acceptance boundaries.

## Context

Prior browser fixture tested grid width/overflow but allowed disappearance of
the machine list. It mounts Reviewer with combined CSS, so it does not alone
prove the Admin wrapper/theme. Extend composition coverage, not DOM-text counts.

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

gpt-6-luna / medium. Matches the plan model table. One bounded independent
claude-opus-5-5 / medium static review. Escalate if contracts/data ownership
change or the existing acceptance tools cannot establish the required behavior.

## Scope

- Use actual shared components with separate Admin and Reviewer host fixtures.
- Verify390/1440/1920px;1/4/40 points,40 machines,6 stakes, long names, saved/empty.
- Capture before/after machine selection: list remains, highlight changes,
  details replace, selected tile remains in list viewport and page does not jump.
- Check keyboard/touch, scroll region, content insets, loading/error/empty and
  modal recovery controls. Verify collapse keeps chart/full table/journal compact.
- Run appropriate builds after implementation, preserving ordinary search/share.
- Produce screenshots, concise evidence and a separate operator-live checklist.

## Out of scope

New API/schema, payout calculations, global Admin redesign, production data,
service lifecycle, push/merge and unrelated operator changes.

## Acceptance criteria

- [ ] Both hosts retain the machine grid after selection at all tested widths.
- [ ] Exactly one selected machine and stake; labels/context match displayed data.
- [ ]40-machine list is bounded by min(288px,40dvh) and accessible; no scroll jump/hidden selection.
- [ ]16px content/action insets,44px targets, no overlap/nested buttons/overflow.
- [ ] Host builds and ordinary search/share regressions pass.
- [ ] Live saves are marked operator-unverified unless an actual run is recorded.

## Technical notes

Use existing components/helpers. Read and apply the corresponding plan section;
newly proposed UI behavior is not evidence of already working implementation.

## Expected files

- scripts/prepare_management_browser_fixture.py: separate host fixture preparation.
- scripts/management_browser_flow.mjs and verify_management_panel_browser.mjs.
- ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md: new evidence and live boundary.

## Verification

Existing browser command npm run reviewer:management:browser (fixture and
browser each120s; adapt script for both hosts with separately bounded runs).
Admin/Reviewer builds:120s each after notifying expected build duration.
Do not start API/Admin; do not label isolated mocks as live acceptance.

## Risks / open questions

Plan execution and the historical-restore exception await approval. Confirm
model availability and the complete expected cost before starting costly work.

## Outcome

Planning only. No implementation or new validation results. Replaces the
unfinished0947 draft, saved as an ignored patch after operator requested a plan.
