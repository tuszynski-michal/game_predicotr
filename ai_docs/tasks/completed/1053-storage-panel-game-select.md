---
title: TASK-1053 — Storage crop panel: readable game select, active games only
status: done
last_updated: 2026-10-18
---

# TASK-1053 — Storage crop panel: readable game select, active games only

## Status

`done`

## Goal

The game selector of the photo crop panel (TASK-1049) is readable and lists
only the games an operator can pick.

## Context

Operator report (2026-10-18): the options of the game selector are white on
white until hovered, and the list shows four games while only three are active
or draft. The fourth is the archived game `777v2`, whose name `777 a2` equals
that of the active `777a2`.

## Dependencies / entry conditions

TASK-1049 in `main`.

## Recommended execution

`claude-opus-5-5`, reasoning `medium`; small UI fix without API change. No
audit (TASK-1049 row of the plan table: UI, no audit).

## Scope

- `source-crop-panel.module.css`: selects use the dark, opaque Admin select
  style (`#0b1524`, `color-scheme: dark`, dark options), as the other panels.
- `source-crop-state.ts` `selectableGames`: archived games are left out, the
  list is ordered by name and code; the panel uses it. A run with the scope
  "all games" still covers every game.

## Out of scope

API changes, the other Admin panels.

## Acceptance criteria

- [x] Options are readable without hovering.
- [x] Archived games are not offered; equal names stay distinguishable by code.
- [x] Admin tests, lint and typecheck pass.

## Outcome

Commit: v1.7.419 / `c103f1ac373742e9fb4708e2f4e208e55b19b28d`.

- Changed: `apps/admin/src/features/storage/source-crop-panel.module.css`,
  `source-crop-state.ts` (`selectableGames`), `source-crop-panel.tsx`.
- Tests: `test/source-crop-state.test.mjs` (filter and order),
  `test/storage-workspace-contract.test.mjs` (select style and use of the
  filter).
- Verification: `npm run test --workspace @game-predictor/admin` 801 passed;
  lint 0 errors (5 existing warnings elsewhere); `npm run typecheck` exit 0;
  crop panel and storage regression interaction tests 12 passed. Not checked
  in a running browser (the operator's Admin).
