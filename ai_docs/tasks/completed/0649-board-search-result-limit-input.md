---
title: TASK-0649 — Input „Liczba wyników” i kontrolowany wybór wyniku wyszukiwania plansz
status: done
---

# TASK-0649 — Input „Liczba wyników” i kontrolowany wybór wyniku

## Status

`done`

**Uwaga o numeracji:** implementacja rozpoczęta z gałęzi `version-0.10` przy
najnowszym commicie `v0.10.417` (wcześniejsze taski `0650`–`0654` z planu
sesji `2026-09-24` jeszcze nie istnieją jako pliki — ten task jest pierwszym
wdrożonym z tej serii).

## Goal

Operator ustawia liczbę wyników wyszukiwania plansz (domyślnie 5, do 100) przez
jawnie zatwierdzany input, a wybrana plansza jest zachowywana między
wyszukiwaniami zamiast resetu do pierwszego wyniku.

## Context

Część 1/6 planu z sesji `2026-09-24` („Przybliżona wygrana” w „Wyszukaj
plansze”). Dziś `runSearch` w `board-search-workspace.tsx` nie przekazuje
`limit`, więc API zwraca domyślne 100 wyników. Wybór aktywnego wyniku jest
dziś wewnętrznym stanem `BoardSearchResultsCarousel`, przemontowywanym po
każdym nowym wyszukiwaniu — workspace nie wie, która plansza jest wybrana.
To blokuje TASK-0653 (podsekcja „Przybliżona wygrana” potrzebuje stabilnej
identyfikacji wybranej planszy na poziomie workspace).

## Dependencies / entry conditions

Brak zależności od innych tasków tej serii (0649 i 0650 są niezależne).

## Recommended execution

Sonnet 5, reasoning `medium`, bez dodatkowego review — lokalna zmiana UI z
jasnymi regułami i istniejącymi testami stanu jako wzorcem. Eskalacja do
Opus 5.5 `high` przy regresji nawigacji karuzeli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (§„Wyszukiwanie plansz z niepełnym wzorem”)
- `ai_docs/architecture/API_CONTRACT.md` (§„Wyszukiwanie plansz częściowym układem”)

## Scope

- `apps/admin/src/features/board-search/board-search-results-state.ts`: nowe
  `boardSearchResultIdentity`, `reconcileBoardSearchResultsState`,
  `parseBoardSearchLimit`, stałe `BOARD_SEARCH_LIMIT_DEFAULT = 5` i
  `BOARD_SEARCH_LIMIT_MAX = 100`.
- `apps/admin/src/features/board-search/board-search-results.tsx`: karuzela
  staje się kontrolowana (`state`/`onStateChange` z workspace), bez zmiany
  nawigacji klawiszowej ani prefetchu sąsiadów.
- `apps/admin/src/features/board-search/board-search-workspace.tsx`: stan
  `limit`/`limitInput`/`resultsState` na poziomie workspace, input „Liczba
  wyników” nad istniejącym `fieldset` „Zakres wyszukiwania”, `runSearch`
  przekazuje `limit` do `api.searchGameBoards`.
- `apps/admin/src/app/globals.css`: ewentualna klasa dla nowego inputu,
  zgodna ze stylem istniejących pól liczbowych.

## Out of scope

- Backend, endpoint `/board-search`, kontrakt API — bez zmian.
- Podsekcja „Przybliżona wygrana” (TASK-0653).
- Zmiana rankingu, scope'u, kolejności wpisywania wzoru.

## Acceptance criteria

- [ ] Domyślny limit w UI i w pierwszym żądaniu wynosi 5.
- [ ] Zmiana na 10 (zatwierdzona Enterem lub blurem) uruchamia nowe
      wyszukiwanie z `limit: 10`.
- [ ] Nieprawidłowa wartość (0, ujemna, > 100, tekst) pokazuje błąd inline i
      nie wysyła żądania; ostatnia poprawna wartość zostaje.
- [ ] Po zmianie limitu wybrana plansza (po `assetMode:sequenceNumber:boardChecksumSha256`)
      zostaje zachowana, jeśli nadal występuje w nowych wynikach; w przeciwnym
      razie wybierany jest wynik nr 1.
- [ ] Nowe „Szukaj plansz” (zmiana wzoru/scope'u) nadal wybiera wynik nr 1.
- [ ] Nawigacja ←/→, prefetch sąsiadów i wygląd karuzeli bez regresji.
- [ ] `npm run test --workspace @game-predictor/admin`,
      `npm run test:geometry --workspace @game-predictor/admin`,
      `npm run typecheck --workspace @game-predictor/admin`,
      `npm run lint --workspace @game-predictor/admin` zielone.

## Technical notes

`BOARD_SEARCH_LIMIT_MAX` odzwierciedla istniejący limit techniczny API
(`Query(ge=1, le=100)` w `board_search.py`) — nie jest to nowa decyzja
produktowa. `boardSearchResultIdentity(result)` zwraca
`` `${result.assetMode}:${result.sequenceNumber}:${result.boardChecksumSha256}` ``
(ten sam klucz co dzisiejszy `resultKey`). `reconcileBoardSearchResultsState`
przyjmuje poprzedni stan i nową listę wyników: jeśli identity poprzednio
aktywnego wyniku istnieje w nowej liście, `activeIndex` wskazuje na nią;
w przeciwnym razie `activeIndex = 0`. Pusta lista wyników daje `activeIndex = 0`
(zgodnie z istniejącym zachowaniem pustego stanu). `runSearch` woła
`reconcileBoardSearchResultsState` tylko gdy `preserveSelection` jest `true`
(zmiana limitu); domyślne wyszukiwanie (zmiana wzoru/scope) zawsze tworzy
świeży stan przez `createBoardSearchResultsState`.

## Expected files

- Istniejące: `board-search-results-state.ts`, `board-search-results.tsx`,
  `board-search-workspace.tsx`, `globals.css`.
- Nowe: brak plików produkcyjnych; nowy test
  `apps/admin/test-interactions/board-search-limit.test.mjs`.

## Test cases

- `parseBoardSearchLimit('5')` → `{ ok: true, value: 5 }`.
- `parseBoardSearchLimit('0')`, `('-1')`, `('1.5')`, `('101')`, `('')` → `ok: false`.
- `reconcileBoardSearchResultsState` z poprzednim wyborem obecnym w nowej
  liście zachowuje `activeIndex` wskazujący tę samą planszę.
- `reconcileBoardSearchResultsState` z poprzednim wyborem nieobecnym w nowej
  liście daje `activeIndex = 0`.
- Interakcja: pierwsze wyszukiwanie wysyła `limit: 5`; zmiana inputu na `10` i
  zatwierdzenie wysyła nowe żądanie z `limit: 10` i zachowuje wybór; zmiana
  wzoru/scope resetuje wybór do indeksu 0; zmiana limitu nie zmienia
  parametrów `cells`/`scope`.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Timeout: 120 s na komendę.

## Risks / open questions

- Brak. Zakres jest wyłącznie techniczny (refaktor stanu UI), bez decyzji
  domenowych.

## Outcome

### Changed

- [board-search-results-state.ts](../../apps/admin/src/features/board-search/board-search-results-state.ts):
  nowe `BOARD_SEARCH_LIMIT_DEFAULT`/`BOARD_SEARCH_LIMIT_MAX`,
  `boardSearchResultIdentity`, `reconcileBoardSearchResultsState`,
  `parseBoardSearchLimit`.
- [board-search-results.tsx](../../apps/admin/src/features/board-search/board-search-results.tsx):
  `BoardSearchResults` jest teraz komponentem kontrolowanym (`state` +
  `onStateChange` zamiast `response` i wewnętrznego `useState`/remountu przez
  `key`). Nawigacja ←/→, prefetch sąsiadów i wygląd bez zmian.
- [board-search-workspace.tsx](../../apps/admin/src/features/board-search/board-search-workspace.tsx):
  nowy stan `resultsState`/`limit`/`limitInput`/`limitError`; input „Liczba
  wyników” nad „Zakresem wyszukiwania”, zatwierdzany Enterem lub blurem;
  `runSearch({ limit?, preserveSelection? })`; `commitLimit()` re-uruchamia
  wyszukiwanie z zachowaniem wyboru tylko gdy limit faktycznie się zmienił i
  są już wyniki; edycja wzoru/scope/undo/reset czyści `resultsState`.
- [globals.css](../../apps/admin/src/app/globals.css): nowa klasa
  `.boardSearchResultLimit`.
- Testy: rozszerzony `test/board-search-results-state.test.mjs` (8 nowych
  przypadków: parse limitu, `boardSearchResultIdentity`,
  `reconcileBoardSearchResultsState`) i nowy
  `test-interactions/board-search-limit.test.mjs` (5 scenariuszy jsdom z
  fałszywym klientem).

### Verification results

```
npm run test --workspace @game-predictor/admin        → 570/570 zielone
npm run test:geometry --workspace @game-predictor/admin → 27/27 zielone (5 nowych)
npm run typecheck --workspace @game-predictor/admin    → czysty
npm run lint --workspace @game-predictor/admin         → 0 błędów; 4 istniejące,
  niezwiązane ostrzeżenia w image-folder-import-panel.tsx i
  page-geometry-correction-panel.tsx (nie dotknięte tym taskiem)
```

### Not completed

- Brak. Wszystkie kryteria akceptacji spełnione w zakresie tego taska.

### Documentation updates

- Brak — zmiana wyłącznie techniczna UI, zgodna z opisanym już w
  `ADMIN_APP.md` zachowaniem edytora wzoru.

### Recommended next task

- TASK-0650 — wspólny kalkulator payout w workerze (plik taska jeszcze nie
  istnieje; do utworzenia przed startem, zgodnie z planem sesji
  `2026-09-24`).
