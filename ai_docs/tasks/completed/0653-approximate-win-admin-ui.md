---
title: TASK-0653 — Podsekcja UI Admina „Przybliżona wygrana”
status: done
---

# TASK-0653 — Podsekcja UI Admina „Przybliżona wygrana”

## Status

`done`

**Uwaga o numeracji:** piąty task planu sesji `2026-09-24` „Przybliżona
wygrana” w „Wyszukaj plansze”. [TASK-0649](completed/0649-board-search-result-limit-input.md)–
[TASK-0652](completed/0652-approximate-win-api-vertical.md) ukończone.
TASK-0654 (dokumentacja + odbiór) jeszcze nie istnieje jako plik.

## Goal

Rozwijana podsekcja „Przybliżona wygrana” pod wynikami „Wyszukaj plansze”:
input „Zakres wygranej”, kalkulacja dopiero po rozwinięciu, automatyczne
odświeżanie przy zmianie wybranej planszy/zakresu, ignorowanie spóźnionych
odpowiedzi, tabela wyników ze stronicowaniem klienckim.

## Context

TASK-0652 dostarczył gotowy endpoint. Ten task łączy go z istniejącym
workspace „Wyszukaj plansze” z TASK-0649 (kontrolowana karuzela wyników,
stabilna tożsamość wybranej planszy).

## Dependencies / entry conditions

TASK-0649 i TASK-0652 ukończone.

## Recommended execution

Sonnet 5, reasoning `high`, z dodatkowym review: Opus 5.5 `medium` —
wyścigi odpowiedzi (spóźnione żądania, szybkie przełączanie kandydatów) są
łatwe do subtelnie złamania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (§„Wyszukiwanie plansz z niepełnym
  wzorem”)

## Scope

- Nowy `apps/admin/src/features/board-search/board-search-approximate-win-state.ts`:
  `parseApproximateWinRange`, `approximateWinRequestKey`,
  `shouldRequestApproximateWin`, `visibleApproximateWinResult`,
  `pageApproximateWinRows`, `formatApproximateWinCredits`, stałe
  `APPROXIMATE_WIN_RANGE_DEFAULT = 1000`, `APPROXIMATE_WIN_RANGE_MAX = 10_000`
  (ta sama wartość co `APPROXIMATE_WIN_SPIN_COUNT_MAX` w API, TASK-0652),
  `APPROXIMATE_WIN_ROWS_PAGE_SIZE = 100`.
- Nowy `apps/admin/src/features/board-search/board-search-approximate-win.tsx`:
  `<details>` z inputem zakresu, stanami ładowania/błędu, podsumowaniem,
  kompletnością, tabelą wyników i stronicowaniem.
- `apps/admin/src/features/board-search/board-search-workspace.tsx`:
  renderuje nowy komponent pod `BoardSearchResults`, przekazuje
  `activeBoardSearchResult(resultsState)` jako `selectedResult`; rozszerzony
  `BoardSearchClient` Pick o `getBoardSearchApproximateWin`.
- `apps/admin/src/app/globals.css`: nowe klasy
  `.boardSearchApproximateWin*`, reużywające istniejące `.importMetrics`,
  `.importRowsTable`, `.feedbackBanner`, `.boardSearchResultNavigation`.

## Out of scope

- Zmiana endpointu/kontraktu API (TASK-0652).
- Dokumentacja `ADMIN_APP.md`/`API_CONTRACT.md`/`ALGORITHMS.md`, odbiór na
  żywych danych (TASK-0654).
- Cache serwerowy — świadomie brak (decyzja z planu sesji).

## Acceptance criteria

- [x] Podsekcja jest domyślnie zwinięta; dopóki zwinięta, zmiana wybranej
      planszy ani zakresu nie wysyła żadnego żądania.
- [x] Pierwsze rozwinięcie z wybraną planszą uruchamia dokładnie jedno
      żądanie z domyślnym zakresem 1000.
- [x] Zmiana wybranej planszy przy otwartej sekcji automatycznie odświeża
      wynik (nowe żądanie z nowym `startSequenceNumber`).
- [x] Wpisywanie cyfr w polu „Zakres wygranej” nie wysyła żądania; Enter lub
      blur zatwierdza i — jeśli wartość się zmieniła — odświeża wynik.
- [x] Spóźniona odpowiedź dla wcześniej wybranej planszy nigdy nie nadpisuje
      wyniku aktualnie wybranej (zweryfikowane: odwrotna kolejność
      rozwiązania promisów).
- [x] Zwinięcie w trakcie ładowania nie powoduje błędu; ponowne rozwinięcie
      z tym samym kluczem (ta sama plansza i zakres) pokazuje wynik z
      pamięci bez nowego żądania — zgodnie z decyzją „bez cache
      serwerowego” (TASK-0651/0652): to wyłącznie klienckie ponowne użycie
      w ramach jednej sesji, nie trwały cache.
- [x] Bez wybranego wyniku wyszukiwania: czytelny komunikat, zero żądań.
- [x] Błąd techniczny pokazuje alert i nie pokazuje żadnych metryk (nie
      udaje poprawnie obliczonego zera).
- [x] `npm run test`, `npm run test:geometry`, `npm run typecheck`,
      `npm run lint` dla `@game-predictor/admin` czyste.

## Technical notes

**`react-hooks/set-state-in-effect` (nowa reguła ESLint w tym środowisku):**
bezpośrednie synchroniczne `setState(...)` w ciele efektu jest tu
zablokowane jako błąd (nie ostrzeżenie). Rozwiązanie: `queueMicrotask(() =>
setState(...))`, dokładnie ten sam wzorzec co istniejący
`apps/admin/src/features/imports/missing-boards-section.tsx`
(`queueMicrotask(() => { if (!cancelled) void load(); })`). Zastosowane w
obu efektach tego komponentu (reset strony tabeli przy zmianie klucza;
uruchomienie kalkulacji). Bez tej zmiany `npm run lint` kończy się błędem
(2 błędy), nie tylko ostrzeżeniem — złapane i naprawione przed commitem.

**Dlaczego reużycie wyniku po zwinięciu/rozwinięciu nie jest „cache
serwerowym”:** stan `ApproximateWinState` (`idle|loading|ready|error`) żyje
wyłącznie w pamięci komponentu React tej jednej sesji przeglądarki. Klucz
żądania (`approximateWinRequestKey`) koduje grę, tożsamość wybranej planszy
i zakres — jeśli którykolwiek się zmieni, klucz się zmienia i
`shouldRequestApproximateWin` wymusza nowe żądanie. To spełnia zaakceptowaną
decyzję „bez cache serwerowego” z TASK-0651/0652 (serwer nigdy nie
przechowuje wyniku), a jednocześnie realizuje wymaganie „po ponownym
rozwinięciu pokaż aktualny wynik z poprawnego cache albo wykonaj nowe
obliczenie” — wybrano pierwszą opcję dla niezmienionego klucza.

**Test jsdom i `<details>`/`onToggle`:** jsdom 20.0.3 aktualizuje
`details.open` po kliknięciu `<summary>`, ale **nie emituje** natywnego
zdarzenia `toggle` automatycznie (zweryfikowane empirycznie). Testy
interakcji ręcznie ustawiają `details.open` i wywołują
`details.dispatchEvent(new Event('toggle'))` zamiast klikać `<summary>` —
potwierdzone (osobnym sprawdzeniem), że w tym środowisku React poprawnie
odbiera tak wygenerowane zdarzenie przez `onToggle`.

## Expected files

- Nowe: `board-search-approximate-win-state.ts`,
  `board-search-approximate-win.tsx`,
  `test/board-search-approximate-win-state.test.mjs`,
  `test-interactions/board-search-approximate-win.test.mjs`.
- Istniejące: `board-search-workspace.tsx`, `globals.css`.

## Test cases

- Stan (14 testów, `board-search-approximate-win-state.test.mjs`): walidacja
  zakresu (0/ujemna/ułamek/poza zakresem/pusty); niezależność klucza od
  „Liczby wyników”; klucz różni się dla innej gry/planszy/zakresu; brak
  żądania przy zwiniętej sekcji lub braku wyboru; żądanie przy pierwszym
  rozwinięciu; brak ponownego żądania dla trwającego/gotowego/błędnego
  dopasowanego klucza; nowe żądanie przy zmianie planszy/zakresu; widoczny
  wynik tylko dla dopasowanego klucza; stronicowanie (puste, wielostronicowe,
  przycinanie poza zakresem); formatowanie kredytów.
- Interakcja jsdom (8 testów): zwinięta sekcja + zmiana kandydata → zero
  żądań; pierwsze rozwinięcie → jedno żądanie z domyślnym zakresem 1000;
  zmiana planszy przy otwartej sekcji → nowe żądanie; wpisywanie cyfr bez
  wysyłki, Enter wysyła; spóźniona odpowiedź dla starszej planszy nie
  nadpisuje nowszej; zwinięcie w trakcie ładowania + ponowne rozwinięcie z
  tym samym kluczem → bez nowego żądania, wynik z pamięci; brak wyboru →
  komunikat, zero żądań; błąd techniczny → alert bez metryk.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Timeout: 120 s na komendę.

## Risks / open questions

- Brak testu na żywym Adminie (TASK-0654, wymaga zgody użytkownika na
  uruchomienie API/Admina).
- Tekst ostrożnego zastrzeżenia (§5 wymagań) jest jeden, wspólny baner przy
  `partialBoardCount > 0 || missingBoardCount > 0` — nie rozróżnia osobno
  obu przypadków w treści komunikatu; uznane za wystarczające wobec opisu
  wymagania.

## Outcome

### Changed

- [board-search-approximate-win-state.ts](../../apps/admin/src/features/board-search/board-search-approximate-win-state.ts)
  (nowy).
- [board-search-approximate-win.tsx](../../apps/admin/src/features/board-search/board-search-approximate-win.tsx)
  (nowy).
- [board-search-workspace.tsx](../../apps/admin/src/features/board-search/board-search-workspace.tsx):
  renderuje nową podsekcję, rozszerzony `BoardSearchClient` Pick.
- [globals.css](../../apps/admin/src/app/globals.css): nowe klasy
  `.boardSearchApproximateWin*`.
- Testy: 14 nowych w `test/board-search-approximate-win-state.test.mjs`,
  8 nowych w `test-interactions/board-search-approximate-win.test.mjs`.

### Verification results

```
npm run test --workspace @game-predictor/admin        → 584/584 (14 nowych)
npm run test:geometry --workspace @game-predictor/admin → 35/35 (8 nowych)
npm run typecheck --workspace @game-predictor/admin    → czysty
npm run lint --workspace @game-predictor/admin         → 0 błędów (po
  naprawie react-hooks/set-state-in-effect przez queueMicrotask); 4
  istniejące, niezwiązane ostrzeżenia bez zmian
```

### Not completed

- Nic w zakresie tego taska.

### Documentation updates

- Brak — zaplanowane w TASK-0654 razem z odbiorem.

### Recommended next task

- TASK-0654 — dokumentacja (`ADMIN_APP.md`, `API_CONTRACT.md`,
  `ALGORITHMS.md`, `DECISION_LOG.md` D-445) i odbiór read-only na żywych
  danych, wyłącznie za osobną zgodą użytkownika na uruchomienie API/Admina.
