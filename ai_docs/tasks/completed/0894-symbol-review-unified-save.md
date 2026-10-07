---
title: TASK-0894 — Unified save and approve in symbol verification
status: done
last_updated: 2026-10-07
---

# TASK-0894 — Unified save and approve in symbol verification

## Status

`done`

## Goal

Replace the ambiguous separate approve/reassign buttons with one explicit
symbol selection and save action that also approves an unchanged symbol.

## Context

The user requests merging `Zatwierdź` and `Zastosuj zmianę`, because the
separate actions cause incorrect submissions. A same-symbol save must move
pending crops to approved; changing the label must approve the correction.

## Dependencies / entry conditions

- Latest branch history: v1.7.236, 2959ec1b; verify full hash before commit.
- Backend `reassign_symbol_cell_review` already approves the exact current
  crop with a real active target, including a pending same-symbol assignment.
- Existing UI code is clean. Older completion receipts and unrelated folders
  are pre-existing changes and must be excluded from this task's commit.
- Scope assumption: one target must be explicitly selected for the unified
  action; reset on filter change remains. No blocking product question.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Reuse the current mutation/bulk contracts;
audit mixed visibility, keyboard and same-symbol approval. Escalate only if
an API/domain inconsistency prevents the documented behavior. No delegation.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — game-wide verification and toolbar
- `ai_docs/architecture/API_CONTRACT.md` — single and bulk cell decisions
- `ai_docs/delivery/SYMBOL_REVIEW_UNIFIED_SAVE_EXECUTION_PLAN.md`
- `ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md`
- `ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md` — MODEL-02

## Scope

- One `Zapisz i zatwierdź` button with a required `Symbol do zatwierdzenia`.
- Reuse `reassign` for the same or another active symbol and the existing
  `mark_blurry` modifier. Keep individual and bulk transaction behavior.
- Update messages, keyboard help, regression tests and documentation.

## Out of scope

API/schema changes, runtime decisions on user crops, model training/activation,
service deployment, cleanup, push/merge and unrelated performance changes.

## Acceptance criteria

- [x] Toolbar has one primary save action; the two previous buttons are absent.
- [x] Missing selection or target disables save; same active target remains
  selectable and moves pending to approved without changing the label.
- [x] A different selected target updates the label and approves it; Enter
  performs the same save. Game/filter changes reset the target.
- [x] Multiple targets retain preview/background job, exact submitted IDs and
  frozen cards; no page-wide refresh is added.
- [x] Outside logical decisions, quality flags, crop identity and conflict
  handling remain protected. No game-specific approval gate remains in UI.
- [x] Focused UI/domain tests, scoped lint/format/types and Admin build pass;
  read-only browser inspection confirms the new toolbar.
- [x] Documentation, Outcome, CURRENT_STATE and one versioned commit are done.

## Technical notes

Keep all backend guards. A same-label `reassign` on pending is a real human
approval; replay on an already approved current crop is idempotent. An outside
logical label does not create training pixels. Do not replace mutation failures
with a local successful state. Existing direct failure recovery and bulk
partial-result counts remain unchanged.

## Expected files

- Existing `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  — toolbar, messages and operation label.
- Existing `apps/admin/test-interactions/symbol-review-partial.test.mjs` and
  `fixtures/symbol-review-partial-client.mjs` — interaction fixtures/regressions.
- Existing `apps/admin/test/symbol-review-workspace-contract.test.mjs`.
- Existing `services/api/tests/test_image_symbol_reviews_domain.py` only if a
  dedicated same-symbol-pending regression is missing.
- Existing Admin requirements, API contract explanation, operator guide,
  inventory, DECISION_LOG and CURRENT_STATE.
- New plan/task files above; no API client generation is needed.

## Test cases

- Pending cherry + cherry → approved cherry and current pixel identity.
- Pending cherry + another active class → approved target class.
- Missing target → no direct/bulk mutation.
- Two pending cherries + cherry → preview then approved, frozen on current page.
- Enter, outside/null crop identity and blurry + explicit class retain behavior.
- Cold mount approved data retain state; changing game/scope clears target.

## Verification

Use the existing bounded `run_step.py` runner from the absolute MAIN root:
Node strip-types tests for symbol-review helpers/contracts; tsx interaction
test `symbol-review-partial.test.mjs`; pytest domain tests; scoped Prettier,
ESLint, TypeScript and Admin build. Each step timeout 120 s. Browser inspection
only reads the real UI and leaves MAIN decisions untouched.

## Risks / open questions

Same-symbol replay must approve pending, not be treated as an unchanged no-op.
Outside and unreadable labels must not silently become training samples.
No known blocker; substantial contract drift requires scope review.

## Outcome

- Implemented one primary `Zapisz i zatwierdź` with an explicit active
  `Symbol do zatwierdzenia`, for all games in this workspace. Missing target
  blocks both button and mutation entry. Same-label pending uses the existing
  reassign approval; another target corrects and approves. Updated success,
  preview and keyboard copy; existing reference image action remains.
- No backend implementation or API shape changed. Outside logical labels,
  blurry training exclusion, exact crop/revision guards, one-cell direct
  saves, multi-cell preview/durable operation and frozen page remain intact.
- Interaction fixtures now model pending/approved filters and actual target
  classes. Existing selector helpers use labels after the preceding folder
  filter change. The previous bulk-unreadable expectation was reconciled
  with the already required frozen-page behavior, retaining post-refresh
  quality/group assertions rather than weakening the contract.
- Verification: API domain 32/32; Admin interactions 12/12; focused Admin
  helpers/contracts 40/40 PASS. Includes unchanged and corrected labels,
  target reset, keyboard, cold mount, outside, blurry and frozen bulk targets.
  Scoped Prettier/ESLint, Ruff check/format and TypeScript PASS. Admin
  production build PASS in 28.2 s. All commands were bounded to 120 s.
- Read-only browser check on MAIN selected Mumie/Q, one crop and the same Q:
  save enabled, both old buttons absent, clearing selection disabled save,
  no console errors. Screenshot:
  `artifacts/symbol-review-unified-save-20261007/main-toolbar.png`.
  No actual decision was submitted; the temporary tab was closed.
- Requirements, contract explanation, operator guide, inventory, D-528,
  plan and CURRENT_STATE updated. Acceptance criteria and plan audited
  individually. No known task blocker. No migration, cleanup, real-data
  decision, training, activation, service restart, deployment, push or merge.
- Completion version: v1.7.237; full commit hash recorded after commit.
