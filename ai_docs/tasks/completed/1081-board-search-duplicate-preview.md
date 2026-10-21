---
title: TASK-1081 — Remove duplicate board search previews
status: done
last_updated: 2026-10-21
---

# TASK-1081 — Remove duplicate board search previews

## Status

`done`

## Goal

Keep exactly one photo of the selected search result after opening the board
window and navigating between boards, independently of the selected game.

## Context

The operator reports duplicate photos in search results for Mumie A1 and
777 A2. A DOM interaction test reproduces two image nodes after opening
the board window and changing the selected result. React reports duplicate
sibling keys: the photo and modal share `assetMode:sequenceNumber`.

## Dependencies / entry conditions

Isolated branch `codex/board-preview-duplicate` from main at 35210b53.
Uncommitted TASK-1080 changes in the main checkout remain outside this task.
No blocking product question. Assumption: one selected result has one preview.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (board search)
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

Separate photo and modal React identities using their roles and the existing
result identity. Include game and checksum changes in remount behavior.
Add DOM interaction regressions for the regular and compact views.

## Out of scope

API, database, payout logic, restarting services, merge and push.

## Acceptance criteria

- [x] Opening/closing the board window and forward/backward navigation leaves
      exactly one photo of the selected board and at most one modal.
- [x] Regular and compact views work without duplicate-key warnings.
- [x] A new game or checksum resets an earlier image fallback state.
- [x] Existing crop interactions, shared package tests, lint, typecheck,
      formatting, code map and documentation checks pass.

## Expected files

- Existing: `packages/board-search-ui/src/board-search-results.tsx`,
  `BoardSearchResults` keys.
- Proposed: `packages/board-search-ui/test-interactions/board-search-result-identity.test.mjs`.
- `ai_docs/requirements/ADMIN_APP.md`, task and state documentation.

## Verification

Run from the isolated worktree, with a 120-second subprocess timeout per command:

```powershell
npm test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
npm run code-map:check
npm run docs:check
```

## Risks / open questions

No data writes or new product behavior. Browser layout and touch-device checks
require operator acceptance; the regression reproduces actual DOM duplication.

## Outcome

Commit: v1.7.455 (hash dopisuje kolejny commit).

### Changed

- Photo and detail modal have distinct role-prefixed keys; both include game
  and existing result identity (asset mode, sequence, checksum).
- Fallback and detail state reset when their actual board image changes.
- Four DOM interaction regressions cover repeated opening/closing, navigation
  in both directions, regular/compact rendering, game and checksum changes.

### Verification results

- Before the fix the regular-view regression produced two photo nodes and
  React's duplicate sibling key warning for `operational_review:10` / `:19`.
- Shared package unit tests: 104/104 passed.
- Shared package interaction tests: 91/91 passed, including the four new
  regressions and the existing search correction, crop, keyboard, compact
  editor and series modal workflows.
- Shared package lint and TypeScript check passed.
- Code map regenerated; no content change required. Formatting, code-map and
  documentation checks passed before closure and were repeated after closure.
- Checks ran in new processes with 120-second command timeouts.

### Not completed

- No service restart, merge, push or live browser/device acceptance.
- Independent audit is not required by an accepted plan for this bounded fix.

### Documentation updates

- Admin requirements explicitly preserve a single selected-board preview.
- Task, rolling state and archive updated with the task-close skill.

### Recommended next task

Operator acceptance and explicit merge approval; then reload the search page
to discard DOM nodes left by the old implementation.
