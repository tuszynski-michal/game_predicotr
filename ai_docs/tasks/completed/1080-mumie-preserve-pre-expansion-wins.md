---
title: TASK-1080 — Preserve pre-expansion super game wins without duplicates
status: done
last_updated: 2026-10-21
---

# TASK-1080 — Preserve pre-expansion super game wins without duplicates

## Status

`done`

## Goal

Preserve the highest payout for each (payline, symbol) before and after a
super-symbol expansion, counting trigger-symbol payouts once.

## Context

The operator confirmed the rule after comparing Mumie a1 ranges #87190/824
and #428349/1335. The read-only calculation gives 1990 and 9190 PLN net at
100 credits, rather than 1290 and 8860 PLN on the recorded data. Expansion
currently discards larger or covered original wins.

## Dependencies / entry conditions

- User explicitly requested implementation of the confirmed rule.
- Initial trigger boards remain base; minimum natural-column thresholds,
  free-spin costs, retriggers, provisional status and frozen history stay unchanged.
- Existing unrelated deleted artifacts and cloudflare worktree are excluded.

## Recommended execution

`gpt-6.1-sol`, `high`: one bounded domain/API/UI change with shared golden
cases. No additional audit is required by an accepted plan for this task.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-537--wypłata-planszy-w-serii-supergry-wynik-prowizoryczny-i-koszt-per-pozycja`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

Python and TypeScript evaluators, shared golden cases, live range/detail
regressions, additive preservation trace in existing detail responses,
generated client and shared board-detail display, documentation and task closure.

## Out of scope

Expansion of initial triggers or below the existing minimum, migrations,
data edits, service restart, frozen-history recalculation, merge and push.

## Acceptance criteria

- [x] Each original line contributes only its positive difference over the
      expanded payout of the same (payline, symbol); expansion covers all
      active paylines, including nonadjacent columns, as before.
- [x] Count payouts are taken once from the original board.
- [x] New preserved-win entries retain original match evidence and show
      expanded payout plus the additional contribution; detail components sum.
- [x] Both language implementations agree on shared fixtures; unchanged wins,
      higher expanded wins, stronger originals, counts, provisional results,
      thresholds and initial-trigger behavior have regression coverage.
- [x] Recorded operator snapshots reproduce 1990 / 9190 net without data writes.
- [x] Relevant tests, lint, typecheck, generated API, code map and docs checks pass.

## Technical notes

Keep the existing expanded matches, count matches and expansion entry intact.
For every original match compute the amount already paid for its pair: the
expanded line match, or one expansion line payout for the expanded symbol.
Only positive differences become preserved wins. Total adds these differences
to existing components. This is equivalent to a pairwise maximum, without
changing the expansion's line-payout-times-payline-count contract.

Add optional `preservedWins` to board-detail responses, containing the full
original match, expanded payout and additional payout. Old consumers default
to an empty list. The shared modal includes the additional contribution in
its consistency check and shows the retained original win without mislabeling
the difference as a configured line payout. No new endpoint or schema migration.

## Expected files

- `services/worker/src/game_predictor_worker/domain/super_games/definition.py`
- `services/worker/src/game_predictor_worker/domain/super_games/wild_super_spins.py`
- `packages/shared-ts/src/super-game.ts`
- `packages/domain-fixtures/payout-golden-cases.json`
- worker, shared-ts, API and shared-modal regression tests
- API board-detail domain/application/schema and generated client
- shared board-detail data-source and modal/state
- algorithm/API/Admin documentation, decision D-568 and code map

## Test cases

Covered different-symbol win survives; original super-symbol win is stronger
than one expansion line; unchanged pair pays once; expanded pair is stronger;
three Mumias remain one count payout and retrigger; first trigger stays base;
one natural column stays unexpanded; partial/stale/undefined results stay provisional.

## Verification

From repository root, each command runs with a 120-second timeout unless a
known build is announced separately. Direct pytest is used instead of the
known single-suite wrapper issue.

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_super_game_payout.py services/api/tests/test_super_game_payout_api.py
npm test --workspace @game-predictor/shared-ts
npm run typecheck --workspace @game-predictor/board-search-ui
npm run openapi:check
npm run code-map:check
npm run docs:check
```

## Risks / open questions

Original match evidence refers to the original board, while existing matches
remain on the expanded board. Preservation is therefore a separate trace.
No unresolved product question; duplicate handling was explicitly confirmed.

## Outcome

Commit: v1.7.455 / `e424e0f4dae0c59478fb6b883f0965b923575ba5`.

Implemented D-568 in the Python and TypeScript series evaluators: add only
the unpaid positive difference for each original (payline, symbol). Count
payouts remain original-board payouts once. Initial triggers remain base;
minimum natural columns, retrigger, free spins and provisional policy remain.

Added `preservedWins` evidence to Admin/public board details, generated
OpenAPI/client/root export, and the shared modal's explanatory list and total
consistency check. Original matches retain their full configured payout;
only `additionalPayoutCredits` contributes to the total.

Verification:

- Python payout/super-game suites: 84 passed; API super-game suite: 24 passed.
- Shared TypeScript: 68 passed (including shared golden cases).
- UI state tests: 7 passed; interaction tests: 2 passed (preservation display
  and existing public correction/recovery workflow).
- Ruff lint/format passed for all eight changed Python files.
- Mypy on six changed source modules with `--follow-imports=silent`: passed.
  The first run without that flag reported pre-existing imported errors in
  `schemas/source_lattice_geometry.py:36,38` and timed out. That unrelated
  file remains unchanged; no full-repository typecheck claim is made.
- Shared UI ESLint and TypeScript typecheck passed; shared-ts build passed.
- OpenAPI generation/currentness (Admin and Vision Lab) passed. Sandboxed
  TestClient and temporary-file rename restrictions required bounded reruns
  outside the sandbox; these reruns passed without service or data changes.
- Code map regenerated/current; documentation and staged whitespace checks
  passed at closure.
- New-process implemented-engine verification of all 2159 recorded spins
  matched the independently calculated per-board totals. #87190/824:
  payout9030 minus cost7040 = 1990 PLN (+700). #428349/1335: payout21140
  minus cost11950 = 9190 PLN (+330 after operator symbol corrections).
  Initial8350 + symbol corrections510 + preservation330 = 9190.
  Evidence: `artifacts/mumia-a1-analysis-20261021/zachowane-wygrane-przed-rozwinieciem/implemented-engine-verification.json`
  (local ignored artifact; source snapshots are unchanged).

Definition of Done: scoped functionality, edge cases, deterministic engines,
additive contract/client, regression coverage, fresh-process persistence and
relevant documentation are complete. No schema/data migration is needed.
Android/device and production application builds were not run for this
shared calculation/text change; existing render/correction interaction is
covered by the package tests. No service restart, database write, frozen
history recalculation, merge or push. Existing unrelated worktree/artifact
changes are excluded. No additional audit was required by the task's model
assignment; no unresolved P0/P1 or product question.

Stored historical results remain snapshots; calculate/save a fresh result to
use this rule. Delivery is on `codex/mumie-preserve-wins`; operator acceptance
and main integration are separate steps.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1080 | gpt-6.1-sol | high | Spójna zmiana reguły w dwóch silnikach z testami kontraktu i wspólnymi fixtures. | Nie; brak wymogu w zaakceptowanym planie. |
