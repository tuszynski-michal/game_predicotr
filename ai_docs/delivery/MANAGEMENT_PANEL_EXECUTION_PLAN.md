---
title: Panel Administracyjny — punkty, maszyny, gry i zapisane układy
status: accepted
last_updated: 2026-10-07
---

# Panel Administracyjny — plan wykonania

User accepted and explicitly requested implementation of the complete T1–T7
plan on 2026-10-07. This document records that plan for implementation handoffs.
API/Admin lifecycle remains user-controlled. No push, deployment, production
cleanup, Redis, accounts, or hosting purchase is authorized by this plan.

## Product contract

- New local tab: **Panel Administracyjny**; point → machine → game → stake.
- Point has editable free-text name, city, street, compact responsive tiles for
  approximately 20–30 points. Named machines belong to points.
- Machine games are editable assignments from live `active` games only; draft
  and archived games cannot be newly assigned or used for new operations.
  Detaching preserves saved results/history; reattachment restores access.
- Archive points/machines instead of hard deletion; history remains readable.
- Each machine/game has stakes descending: 2000,1000,600,400,200,120 grosze.
  Each stake independently saves its start board, query, spin range and pins.
- Cards show empty state or board preview/sequence number, chart/pinned labels,
  last saved time and Open/Search again/Clear actions. Game picker sits above.
- Reuse existing search, approximate-win calculation, payline table/modal and
  immediate human symbol correction. Stake is fixed by the card.
- Browsing and pinning are drafts. Only **Zapisz układ** saves the selected
  board/range/pins (0–6); unsaved navigation warns. Search again leaves the
  preceding saved choice until Save. Clear requires confirmation and changes
  only this machine/game/stake; no deletion of boards/history.
- On opening, show last result marked checking, then recalculate current data.
  Changed symbols/rules/data update the chart and append before/after history.
  Preserve selected sequence and pinned spin positions. Out-of-range pins are
  explicitly unavailable. Failure retains last result marked stale, never zero.
- Immutable shared result versions preserve numeric chart/payline-table data,
  start-board symbols, rules and data fingerprint in compact versioned form;
  images stay outside DB. Identical results are deduplicated.
- Journal below chart/table records time, local administrator or named link,
  query/sequence, search including zero hits, save/replace/clear, saved range/
  pin changes, symbol correction before/after, recalculation and point/machine/
  assignment changes. Pages default20. No journal deletion. Historical chart is
  immutable; opening a board editor explicitly edits **current data**.
- PostgreSQL is authoritative. Mutation/audit commit atomically. Operation UUID,
  request checksum and expected revision protect response loss and concurrency.
  Recheck assignments/archive/auth expiry under the write boundary.

## Architecture and interfaces

Existing `packages/board-search-ui/src/board-search-workspace.tsx`
(`BoardSearchWorkspace`, `BoardSearchDataSource`),
`board-search-approximate-win.tsx` (`ApproximateWinBalanceChart`) and backend
`BoardSearchApproximateWinService` remain shared. Optional controlled saved
selection/stake/pins preserve default existing consumer behavior with regressions.

Proposed public control-plane entities: points, machines, game assignments, stake
saves, immutable result versions, journal events and independent panel sessions.
Stable UUIDs are independent of names. Save uniqueness: machine/game/stake_grosze.
Schema changes only through additive Alembic migrations; retain game-store routing.

Proposed endpoints: `/api/v1/admin/management/...` for local operations and link
administration; `/api/v1/management-public/...` for the authenticated panel subset;
Reviewer `/management` with separate allowlisted `/management-api` proxy/cookie.
Backend/OpenAPI/generated client/wrappers/request tests form one contract.

Named link + separate8-character code gives the one external recipient full panel
management, search and human symbol corrections across assigned active games.
Only local admin manages links. No public access to unrelated Admin endpoints,
imports/models/rules administration. Backend verifies machine/game association on
every game-bound request. Separate session purpose; old one-game shares remain
one-game. Five failed codes lock access; token hash, HttpOnly cookie, revoke,
server-side expiry and existing ingress conventions apply.

Lifetimes1/4/8/24/48/72hours, default8; extend existing board-search shares too.
Existing expiry timestamps do not change. Expiry/revoke retain all history.
Machine lists never load all charts. Six compact summaries for selected game;
full rows/images only when a stake opens. At most two concurrent card refreshes,
cancel obsolete requests; existing indexed search and image cache, no Redis.

Local computer/API/DB must remain available. Existing Reviewer/tunnel carries
public surface only; 72hours is access lifetime, not uptime guarantee. Future
server hosting requires backend/data placement and is a separate deployment;
frontend-only hosting cannot remove dependence on the computer.

## Tasks, dependencies and acceptance

| Plan task | Repo task | Scope | Acceptance |
|---|---|---|---|
| T1 | TASK-0921 | Points/machines domain, migration, API, local tab, assignments/archive; accepted requirements/architecture | Persisted CRUD, active catalog filtering, newly active games, retained detached/archive history |
| T2 | TASK-0922 | After T1: durable stake saves, result versions, clear, revisions/retry/journal, existing calculator | Fresh-process persistence, exact retry, conflict, clear retains journal |
| T3 | TASK-0923 | After T2: optional shared search/stake/pins controls and explicit Save | Browsing/pins do not persist; complete explicit save; existing consumer regression |
| T4 | TASK-0924 | After T3: six cards, quick chart, journal, search again and current recalculation | Independent stakes, current and previous result, failures/staleness |
| T5 | TASK-0925 | After T2 (executed after T4): panel sessions/public API/proxy and48/72h old/new shares | Narrow authorization, expiry/revoke including mutations, old session isolation |
| T6 | TASK-0926 | After T4/T5: complete recipient UI, named audit, CRUD/search/save/corrections | Phone flow, local visibility, concurrent tabs/response-loss recovery |
| T7 | TASK-0927 | After T6: integrated acceptance, regressions/contracts/durability/performance, operator guide | Requirement/test traceability, complete checked gates, no unresolved P0–P2 |

Each task follows TASK_TEMPLATE, gets independent review, own versioned commit,
Outcome and CURRENT_STATE update before advancing. Dirty files predating this
request belong to user. Lead stages only own hunks. T1 begins at branch
v1.7.250; verify actual log before committing, then increment patch sequentially.

## Verification and rollout

Focused backend tests first, then scoped format/lint/types; shared UI real
interactions and Admin/Reviewer regressions; OpenAPI/generated drift; broader
relevant tests/build only after focused checks. Commands use bounded120s steps.
Longer known builds require advance notification. Meaningful isolated PostgreSQL
tests cover migration/transactions/constraints/retention/new sessions and expiry.
No synthetic scale fixtures/load benchmarks. Bounded actual-data diagnostics only.

Cover reload/new process, lost response/exact retry, concurrent local/recipient,
expired/revoked in-flight operation, absent boards/rules, archived/detached games,
stale-result errors and inaccessible pins. Responsive touch UI matches current
application styles with loading/empty/error and no duplicate submission.
Live rollout is user-run migration and API/Admin startup/restart; agent does not
operate those services. Report unverified live gates honestly. No production writes
just to produce screenshots. No startup/push/deployment implied by implementation.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-0921 | gpt-6.1-sol | medium | Existing CRUD/UI/migration patterns | gpt-6.1-sol / high — relationships/history |
| T2 / TASK-0922 | gpt-6.1-sol | high | Transactions, result versions, concurrency/retry | gpt-6-astra / high — durability/consistency |
| T3 / TASK-0923 | gpt-6.1-sol | high | Shared workspace state and consumer protection | gpt-6.1-sol / high — regressions |
| T4 / TASK-0924 | gpt-6.1-sol | high | Current/history charts and bounded reads | gpt-6.1-sol / high — response races/history |
| T5 / TASK-0925 | gpt-6.1-sol | high | Multi-game online write boundary | gpt-6-astra / high — authorization/expiry/isolation |
| T6 / TASK-0926 | gpt-6.1-sol | high | Remote writes/audit/shared UI | gpt-6-astra / high — permissions/lost response |
| T7 / TASK-0927 | gpt-6.1-sol | high | Full flow and requirements verification | gpt-6-astra / high — final acceptance gates |
