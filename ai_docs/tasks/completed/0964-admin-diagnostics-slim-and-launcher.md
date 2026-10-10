---
title: TASK-0964 — Odchudzona Diagnostyka siatek i launcher bez wyboru importu
status: done
last_updated: 2026-10-10
---

# TASK-0964 — Odchudzona Diagnostyka siatek i launcher bez wyboru importu

## Status

`done`

## Goal

Admin → „Korekta cięcia siatki” nie ma selecta „Gotowy import plansz”, a
„Diagnostyka siatek zdjęć” pokazuje tylko liczniki i przycisk otwarcia
Reviewera — bez listy zdjęć, podglądu SVG i filtrów.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`, decyzje 1, 2, 6.
Po TASK-0963 lista zdjęć i filtry żyją w Reviewerze. Admin ma pozostać
miejscem „ile i co”, nie miejscem pracy na zdjęciach.

## Dependencies / entry conditions

- Etap A odebrany (TASK-0961–0963 `done`, Reviewer pokazuje braki zdjęć).
- Fakty z kodu: launcher woła `startLocalReviewerProcess` i otwiera okno przez
  `prepareLocalReviewerWindow`; `buildPreparedLocalReviewUrl` wymaga dziś
  `importJobId`; sekcja diagnostyki ma kontrolki zakresu „Cała gra / Wybrany
  import”, liczniki, `LowQualityBlock` i listę zdjęć z `GeometryGateControls`.

## Recommended execution

`claude-sonnet-5-5`, `medium` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`

## Scope

1. `reviewer-local-window.ts`: `importJobId` opcjonalny w
   `buildPreparedLocalReviewUrl` i `prepareLocalReviewerWindow`; gdy brak, URL
   nie zawiera parametru `importJobId`. Wołający z importem
   (`import-geometry-review-summary.tsx`) bez zmiany zachowania.
2. `ReviewerAccessLauncher`: usunięcie selecta „Gotowy import plansz”,
   identyfikatora jobu, `jobId`/`selectedJob`/`reviewReadyImports`-zależnych
   liczników i podsumowania „Stan plansz importu”; „Otwórz lokalnie” jest
   aktywny, gdy wybrano grę i nic się nie ładuje; otwiera Reviewer z samym
   `gameId`. Panel „brak importu” zostaje tylko gdy gra nie ma żadnego importu
   obrazów. Teksty nagłówka bez „odrzuconych przez algorytm” jako jedynego
   zakresu (np. „plansz odrzuconych przez algorytm, zgłoszonych jako „Zła
   siatka” oraz zdjęć z brakami”).
3. `GeometryCompletenessSection`: usunięcie listy zdjęć, `GeometryImageItem`,
   `GeometryGateControls`, filtrów stanu, paginacji i podglądu SVG;
   zostają: nagłówek, kontrolki zakresu, liczniki, podsumowania stanów i
   pozycji, `LowQualityBlock`. Nagłówek: „{N} zdjęć z realnymi brakami · {M} z
   niepotwierdzoną siatką” (N = brakuje plansz + częściowe + import nieudany +
   bez geometrii źródła; M = siatka niepotwierdzona), opis wyjaśnia, że
   „niepotwierdzona” to automatyczna siatka bez ręcznego zatwierdzenia, nie
   błąd. Przycisk „Otwórz braki w Reviewerze” woła tę samą ścieżkę
   uruchomienia co launcher (prop `onOpenReviewer`).
4. Usunięcie nieużywanego kodu: `geometry-completeness-state.ts` — funkcje i
   stałe używane wyłącznie przez usuniętą listę (kolejka, wyjątki, SVG);
   zachowaj to, co nadal używają liczniki i `LowQualityBlock`.
5. Aktualizacja testów źródłowych i interakcji Admina, które asercją
   odwołują się do usuniętych tekstów.

## Out of scope

- Reviewer (TASK-0962/0963), API (TASK-0961).
- Przywrócenie UI wyjątków bramki (osobny task, decyzja 6).
- Zmiana kontrolek zakresu „Cała gra / Wybrany import” w samej diagnostyce.

## Acceptance criteria

- [x] Brak elementu „Gotowy import plansz” i identyfikatora importu w launcherze.
- [x] „Otwórz lokalnie” otwiera `…:3001/?mode=local&gameId=…` bez
      `importJobId`.
- [x] Sekcja diagnostyki nie renderuje listy zdjęć, SVG ani filtrów;
      zawiera liczniki, nagłówek z N/M i przycisk „Otwórz braki w Reviewerze”.
- [x] `LowQualityBlock` działa bez zmian.
- [x] Testy, typecheck, lint i `format:check` Admina zielone.

## Technical notes

Aktualne → wymagane: launcher liczył plansze w wybranym imporcie
(`listImageGridReviews`, `listPendingBoardCellGeometry`) i od tego uzależniał
przycisk; po zmianie nie woła żadnego z nich (zakres gry byłby kosztowny —
23–45 s). Liczniki diagnostyki pochodzą z już ładowanego
`getImageGeometryCompleteness`. Launcher przekazuje do sekcji callback
`onOpenReviewer`; sekcja nie importuje już `reviewer-local-start` ani
`reviewer-local-window`. Obsługa blokady okna i błędów startu pozostaje w
jednym miejscu (launcher).

## Expected files

- Istniejące:
  `apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx`,
  `apps/admin/src/features/reviewer-access/reviewer-local-window.ts`,
  `apps/admin/src/features/reviewer-access/reviewer-access-state.ts`
  (usunięcie nieużywanych selektorów),
  `apps/admin/src/features/imports/geometry-completeness-section.tsx`,
  `apps/admin/src/features/imports/geometry-completeness-state.ts`,
  `apps/admin/test/geometry-completeness-state.test.mjs`,
  `apps/admin/test/reviewer-access-launcher-contract.test.mjs`,
  `apps/admin/test-interactions/grid-diagnostics-placement.test.mjs`,
  `apps/admin/test-interactions/neural-import-readiness.test.mjs`.
- Nowe: brak.

## Test cases

- URL: `buildPreparedLocalReviewUrl` bez `importJobId` nie dodaje parametru;
  z `importJobId` — jak dotąd.
- Launcher: brak selecta; przycisk aktywny po wyborze gry; klik uruchamia
  proces i otwiera okno z samym `gameId`.
- Sekcja: dla odpowiedzi Mumie (51 541 niepotwierdzonych, 4 braki) nagłówek
  pokazuje „4 … 51 541”; brak listy; przycisk wywołuje `onOpenReviewer`.
- Regresja: blok niskiej jakości symboli bez zmian.

## Verification

```powershell
# katalog: korzeń worktree; timeout <= 120 s na komendę
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run format:check
```

Zaliczenie: wszystkie zielone. Testy planowane nie są wynikami wykonania.

## Risks / open questions

- Utrata UI wyjątków bramki jest świadoma (decyzja 6); udokumentować w
  `Outcome` i `CURRENT_STATE`.
- Testy źródłowe sprawdzają teksty — dopasować do nowych treści, nie
  osłabiać asercji.

## Outcome

### Changed

- `reviewer-local-window.ts`: `importJobId` opcjonalny w
  `buildPreparedLocalReviewUrl` i `prepareLocalReviewerWindow`; bez niego URL
  ma tylko `mode=local&gameId=…`. Wołający z importem
  (`import-geometry-review-summary.tsx`) bez zmian.
- `ReviewerAccessLauncher`: usunięte select „Gotowy import plansz”, identyfikator
  jobu, stan `jobId`, wywołania `listImageGridReviews` i
  `listPendingBoardCellGeometry`, podsumowanie „Stan plansz importu” i komunikat
  „Wybrany import nie zawiera plansz”. „Otwórz lokalnie” jest aktywny, gdy
  wybrano grę i nic się nie ładuje; otwiera Reviewer z samym `gameId`. Panel
  „brak importu” tylko dla gry bez żadnego importu obrazów. Launcher przekazuje
  do sekcji `onOpenReviewer` i `openReviewerDisabled`.
- `GeometryCompletenessSection`: usunięte lista zdjęć, `GeometryImageItem`,
  `GeometryGateControls`, filtry stanu, paginacja i podgląd SVG; zostały
  nagłówek „{N} zdjęć z realnymi brakami · {M} z niepotwierdzoną siatką”
  (N = brakuje plansz + częściowe + import nieudany + bez geometrii źródła,
  M = siatka niepotwierdzona; liczone dla całej gry) z opisem, kontrolki zakresu,
  liczniki, podsumowania stanów i pozycji, `LowQualityBlock` oraz przycisk
  „Otwórz braki w Reviewerze”. Typ `GeometryCompletenessClient` zawężony do
  `getImageGeometryCompleteness` i `getImageGeometryLowQualityBoards`; sekcja nie
  importuje już `reviewer-local-start` ani `reviewer-local-window`.
- `geometry-completeness-state.ts`: usunięte kolejka/wyjątki bramki, etykiety
  statusów i błędów importu, `geometryPositionTone`, helpery SVG; dodane
  `geometryGapCounts`.
- `reviewer-access-state.ts`: usunięte nieużywane `reviewReadyImports`,
  `selectReviewImportId`, `hasReviewerWork`, `gridReviewTotal`,
  `reviewJobLabel`.
- Testy: `geometry-completeness-state.test.mjs`,
  `reviewer-access-state.test.mjs`, `reviewer-access-launcher-contract.test.mjs`,
  `reviewer-local-window.test.mjs`, `grid-diagnostics-placement.test.mjs`
  dostosowane; usunięto tylko asercje usuniętego kodu, dodano asercje nowego
  zachowania (URL bez `importJobId`, brak selecta i list, przycisk uruchamia
  Reviewer z samym `gameId`, launcher nie liczy plansz).
- Świadoma utrata (decyzja 6 planu): UI wyjątków bramki („Dopuść wyjątkiem…”,
  „Wycofaj wyjątek”) znika z Admina. Endpointy API i metody klienta
  (`setSourceImageGeometryException`, `withdrawSourceImageGeometryException`)
  zostają; przywrócenie UI to osobny task.

### Verification results

- `npm run test --workspace @game-predictor/admin` → 729 pass, 0 fail.
- `npm run test:geometry --workspace @game-predictor/admin` → 206 pass, 0 fail
  (w tym nowe przypadki `grid-diagnostics-placement.test.mjs`).
- `npm run typecheck --workspace @game-predictor/admin` → exit 0.
- `npm run lint --workspace @game-predictor/admin` → exit 0.
- `npm run format:check` → „All matched files use Prettier code style”.
- Odbiór na żywych danych (Mumie: 4 braki, 51 541 niepotwierdzonych) należy do
  TASK-0965; testy używają fikstur.

### Not completed

- Nieużywane reguły CSS (`geometryImageItem`, `geometryGateControls`,
  `geometryPreview`, `geometryQuad`, `reviewerImportSelect` itd.) w
  `apps/admin/src/app/globals.css` zostały; nie wpływają na działanie.
- Brak odbioru na żywo i audytu krzyżowego (zawieszony decyzją operatora
  2026-10-01).

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`: sekcja `done` TASK-0964, usunięta z
  „Aktywne taski”; najstarsza sekcja `done` (TASK-0941) przeniesiona do
  `ai_docs/archive/CURRENT_STATE_2026Q4.md`.
- Wpis D-541 i pozostała dokumentacja: TASK-0965.

### Recommended next task

- TASK-0965

### Audit

Niezależny audyt tylko do odczytu: subagent Claude `haiku` (`medium`), niższy
model niż wykonawca (Codex niedostępny z powodu wyczerpanego limitu;
zastępstwo zgodne z poleceniem operatora z 2026-10-10). Werdykt: PASS z
uwagami P2, brak P0/P1. Uwagi P2: nagłówek N/M zawsze dla całej gry (dopisane
w `ADMIN_APP.md`); brak testu renderu nagłówka na liczbach Mumii (pokryte
testem helpera `geometryGapCounts` i fixturą interakcji; odbiór na żywo w
TASK-0965); martwe reguły CSS zostały (osobne sprzątanie);
`listJobs({ jobType: 'import', limit: 200 })` bez filtra gry w trybie bez
`controlledGameId` odziedziczone z HEAD (przy > 200 importach panel „brak
importu” może się pokazać fałszywie).
