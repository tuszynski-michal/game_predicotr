# TASK-1057 — Allowlista proxy Reviewera i proxy panelu dla tras serii

## Status

`todo`

## Goal

Proxy udostępnienia i proxy panelu przepuszczają dokładnie cztery trasy serii
(w tym `PUT super-symbol` jako mutację) i nic więcej; test bramki potwierdza
równość allowlisty z OpenAPI.

## Context

Plan `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`.
Dziś `boardSearchShareRoute` zna tylko odczyty, `unlock` i POST korekty;
handlery `route.ts` eksportują tylko `GET` i `POST`; proxy panelu czyta body
tylko dla `POST`.

## Dependencies / entry conditions

- TASK-1056 scalony w gałęzi (OpenAPI z nowymi trasami; test bramki czyta
  `packages/admin-api-client/openapi/openapi.json`).

## Recommended execution

`claude-fable-5-1` / `high` (warunkowo). Audyt Codex przed commitem.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- plan jak wyżej
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`, „Udostępniona
  wyszukiwarka plansz”

## Scope

- `boardSearchShareRoute`: `GET …/super-game-series/state` (`noQuery`),
  `GET …/super-game-series/next-undefined` (`exactly({}, { afterTrigger:
  POSITIVE_INTEGER })`), `GET …/super-game-series/{uuid}/boards`
  (`noQuery`), `PUT …/super-game-series/{uuid}/super-symbol` →
  `{ kind: 'mutation', query: noQuery }` przed `if (method !== 'GET')`.
- `export const PUT = proxy` w `apps/reviewer/src/app/board-search-api/[...path]/route.ts`
  i `board-search-panel-api/[...path]/route.ts`.
- Proxy panelu: body dla `POST || PUT`.
- Testy bramki, proxy i proxy panelu.

## Out of scope

- UI Reviewera (TASK-1059), zmiany API.

## Acceptance criteria

- [ ] Bramka: operacje publiczne 10 → 14, `{series_id}` w `concrete()`, nowe
      schematy publiczne bez kluczy wewnętrznych.
- [ ] Lista serii, `derive` i trasy `/admin/...` → 403
      `BOARD_SEARCH_SHARE_ROUTE_FORBIDDEN`.
- [ ] `PUT` bez `Origin`/`Sec-Fetch-Site: same-origin` → 403; bez
      `application/json` → 415; > 4 KiB → 413; z query → 403.
- [ ] Panel przekazuje `PUT` z cookie potomnym i body; `set-cookie` usunięte.

## Expected files

- `apps/reviewer/src/security/board-search-share-proxy.ts`,
  `board-search-panel-proxy.ts`, oba `route.ts`.
- `apps/reviewer/test/board-search-share-security-gate.test.mjs`,
  `board-search-share-proxy.test.mjs`, `board-search-panel-proxy.test.mjs`.

## Test cases

- Każda z 4 tras: dozwolona metoda przechodzi, inna metoda → 403.
- `next-undefined` bez parametru i z `afterTrigger=12`; z `afterTrigger=0`
  albo obcym parametrem → 403.
- Odpowiedź `boards` przechodzi filtr odpowiedzi.

## Verification

```powershell
# D:\game_predicotr, timeout 120 s
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
```

## Risks / open questions

- `exactly({}, {...})` dopuszcza brak parametru: potwierdzić testem.

## Outcome

Wypełnia agent po pracy.
