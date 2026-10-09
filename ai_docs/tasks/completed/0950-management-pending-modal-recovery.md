---
title: Management pending modal recovery
status: done
last_updated: 2026-10-09
---

# TASK-0950 — Management pending modal recovery

## Status

done

## Goal

Allow recovery from a failed structural write inside the visible dialog without losing its exact operation identity.

## Context

Operator reports unavailable point/machine edit/delete in the shared panel. Read-only API checks show an active panel session and both active and archived points. The exact operator failure remains unconfirmed. Independently confirmed code defect: uncertain write disables Cancel and puts error/retry behind the modal, preventing recovery and subsequent edits/deletes.

## Dependencies / entry conditions

Standalone bounded regression fix authorized by the operator complaint. This implements only the confirmed recovery defect, not the entire proposed layout plan or historical restore. No operator-data mutation or service lifecycle change.

## Recommended execution

Current Codex executor. One scoped Claude medium static review before commit; no repeated broad audit.

## Relevant docs

- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/tasks/0948-management-modal-recovery-and-legacy-access.md

## Scope

Expose errors and exact retry inside structural edit/delete dialogs. Permit closing a completed failed write while retaining its pending receipt. Keep fields and new writes locked until the uncertain request resolves. Preserve session boundaries and delete confirmation.

## Out of scope

Restore archived entities, layout/navigation changes, schema/API changes, public deployment and live data deletion.

## Acceptance criteria

- [x] Failed edit has visible error and enabled exact retry inside its dialog.
- [x] Closing/remounting preserves operation UUID/body; successful retry unlocks edit/delete.
- [x] Failed delete has visible error and retry within its confirmation dialog.
- [x] Definite validation failure leaves editable fields and visible error.
- [x] Active requests and ended access cannot launch another write.

## Technical notes

Pending command remains in namespaced sessionStorage. Close dismisses only presentation, never uncertain mutation identity. Error outside a dialog remains accessible after closing. Do not claim this explains the reported operator failure until confirmed.

## Expected files

- packages/board-search-ui/src/management/management-workspace.tsx: run and dialog rendering.
- packages/board-search-ui/src/management/management-structure-modal.tsx: Props and controls.
- apps/admin/test-interactions/management.test.mjs: existing regression checks, unchanged.
- apps/reviewer/test-interactions/management-panel.test.mjs: shared panel recovery regression.

## Test cases

Edit/delete failures expose error/retry in dialog; retry uses identical request; closing/remounting retains receipt; validation errors remain visible without pending lock; session end blocks writes.

## Verification

Focused Admin/Reviewer interactions, scoped lint, shared typecheck and docs check, each bounded to120s. No services started.

## Risks / open questions

Operator button state/error is still requested. Archived entities follow current guards; no automatic restore. No public live write tested.

## Outcome

### Changed

Edit and deletion dialogs own their error/retry controls. Cancel after a failed request preserves pending identity. Fields are locked for active or uncertain writes. This corrects the confirmed recovery defect; the operator complaint is not yet reproduced on the public live panel.

### Verification results

- Admin management interactions:13/13 passed.
- Reviewer management interactions:23/23 passed, including nine new recovery regressions.
- Reviewer management proxy tests:11/11 passed.
- Scoped shared/Reviewer lint and shared typecheck passed.
- One Claude Code medium static audit PASS; no P0/P1. P2-1 covered by four added ended-session dialog cases; P2-2 addressed in this Outcome.
- npm run docs:check passed (39 active tasks,10 done sections). Code map regenerated; no symbol-index change.

### Audit

See [Claude report](../../quality/TASK-0950_AUDIT_claude-opus-5-5.md).

### Not completed

No public live write, operator data deletion, service restart or deployment. Exact cause of operator edit/delete complaint remains unconfirmed.

### Documentation updates

Standalone task, CURRENT_STATE rolling window/archive, requirements and0948 reuse note. Proposed0948 recovery criteria partially covered by this fix;0948 itself remains todo.

### Recommended next task

Confirm operator button state/error and implement the separately approved layout work when authorized.
