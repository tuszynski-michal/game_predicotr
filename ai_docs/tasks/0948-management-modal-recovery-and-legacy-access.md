---
title: Modal recovery and historical archived access
status: todo
last_updated: 2026-10-09
---

# TASK-0948 — Modal recovery and historical archived access

## Status

todo

## Goal

Keep errors and exact pending retries accessible in the modal; make historical
archived tiles usable without changing saved assignments or results.

## Context

Operator confirmed save now works, so the previous cause is not diagnosed.
Code still places error/retry behind the modal while its Cancel is disabled
by retryAvailable. Previous tests saw document text, not dialog accessibility.
Historical restore is a proposed exception to D-538 requiring plan acceptance.

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

- Pass error, saving, pending and exact retry callback to the structure modal.
- Cancel after a completed failed request preserves the stored pending command.
- Lock new saves/changes that could diverge from an uncertain pending body.
- Definite4xx retains editable fields under existing revision/access rules.
- Open historical archived point/machine tiles. If plan approved, offer explicit
  restore using existing archived=false updates; preserve fields and gameIds
  by omitting gameIds from machine restore. Restore point before its machine.
- Preserve delete preview/confirmation, public-session restrictions and receipts.

## Out of scope

New API/schema, payout calculations, global Admin redesign, production data,
service lifecycle, push/merge and unrelated operator changes.

## Acceptance criteria

- [ ] Error/retry/close are usable within the dialog after5xx/network failure.
- [ ] Close/remount/retry retains UUID/body and results in one saved entity.
- [ ] Rejected4xx preserves editable form fields; no hidden background-only error.
- [ ] After rejected delete409/422 closes its dialog, error remains visible on
  the point page;401/403/429 retain their distinct pending/access behavior.
- [ ] Historical cards open and retain delete; restore changes only archived.
- [ ] Archived parent blocks machine restore with a visible explanation.
- [ ] Access revocation and storage failure do not create duplicate operations.

## Technical notes

Use existing components/helpers. Read and apply the corresponding plan section;
newly proposed UI behavior is not evidence of already working implementation.
Existing restore transport is PUT via api/management.py, not PATCH; repository
point/machine writes command.archived. Recheck public/local contracts before
coding. Restore is conditional on accepted plan; if not accepted, implement
only modal recovery and archived read/delete, preserving D-538.

## Expected files

- packages/board-search-ui/src/management/management-workspace.tsx: run/save/legacy cards.
- packages/board-search-ui/src/management/management-structure-modal.tsx: ManagementStructureModal.
- apps/admin/test-interactions/management.test.mjs: recovery/remount/legacy regressions.
- packages/board-search-ui/src/management/management.css: legacy card composition if necessary.

## Verification

Focused Admin interactions as in0947 (120s); shared lint/typecheck (120s each).
Use existing bounded app-role PostgreSQL tests only if changed contracts need
confirmation. No mutation against the operator database.

## Risks / open questions

Plan execution and the historical-restore exception await approval. Confirm
model availability and the complete expected cost before starting costly work.

## Outcome

Planning only. No implementation or new validation results. Replaces the
unfinished0947 draft, saved as an ignored patch after operator requested a plan.
