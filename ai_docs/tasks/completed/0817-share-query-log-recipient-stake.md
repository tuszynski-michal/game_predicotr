# TASK-0817 — Recipient stake on the share query log charts

## Status

`done`

## Goal

The balance chart of a share-link log entry is drawn at the stake the
recipient chose, not at the base stake (D-487).

## Context

Operator report, 2026-10-02: every chart in the log showed the base stake.
The stake was chosen in the recipient's browser after the range calculation
and never reached the API (D-478).

## Decision (operator, 2026-10-02, chat)

Record the stake chosen by the recipient in the link's query log.

## Scope

- API: `GET /board-search-shares/approximate-win/stake` records a range entry
  with `stakeGrosze`; the entry validation accepts that request shape.
- Reviewer: proxy allowlist, share data source member, security gate count.
- `packages/board-search-ui`: optional data source member; the approximate
  win section reports every shown (range, stake) pair once.
- Admin log: chart at the recorded stake with its amount in the caption.
- OpenAPI and generated client.

## Out of scope

- Replaying an entry at the recipient's stake (still the base stake).
- A new query kind / schema migration.

## Outcome

### Changed

- `domain/board_search_share_queries.py`, `api/board_search_share_public.py`,
  `schemas/board_search_shares.py`.
- `apps/reviewer`: `board-search-share-proxy.ts`,
  `board-search-share-data-source.ts`, security gate test.
- `packages/board-search-ui`: `board-search-approximate-win.tsx`,
  `board-search-data-source.ts`, `index.ts` (`formatZloty` export).
- `apps/admin`: `board-search-share-query-log.tsx`, `-state.ts`.
- `API_CONTRACT.md`, `ADMIN_APP.md`, `DECISION_LOG.md` (D-487),
  `CURRENT_STATE.md`.

### Verification results

- API: share public and query log tests 34/34 (2 new); Ruff clean.
- Reviewer unit tests 200/200 (proxy, data source, security gate updated to
  9 public routes); board-search-ui approximate-win interactions 19/19
  (1 new); Admin replay-state tests 7/7, share panel interactions 6/6,
  API client tests 76/76.
- Typecheck clean for board-search-ui, reviewer and admin; ESLint clean on
  the changed files; OpenAPI artifact and generated client current.

### Not completed

- Not exercised end to end through a live share link in a browser.
- Entries recorded before this change have no stake.

### Recommended next task

- After merge: `npm run reviewer:build`, restart the API instances, then
  check one live link.
