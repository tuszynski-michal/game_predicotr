---
title: Audyt TASK-1094
status: active
last_updated: 2026-10-25
---

# Audyt TASK-1094 — Anulowanie starego odświeżenia limitu i testy kliknięcia

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: 6d49edb9...98c85100c60a5cb9cf27bc991b95e9dd933a4a80 oraz zmiany niezacommitowane, data 2026-10-25
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem zmianę kolejki `repeatPending` w `useBoardSearchSequence`, dwa nowe testy interakcji, przebudowaną regresję przeglądarkową `limitClickRegression` oraz wpisy w ADMIN_APP, CURRENT_STATE i raporcie odbioru. Rozróżnienie przyczyn limit i korekta poprawnie zamyka TASK-1093/P2-1 w głównym przepływie. Cleanup z flagą `cancelled` poprawnie unieważnia mikrozadania poprzedniego przebiegu efektu. Testy realizują P2-2 i P2-3 dla trzech hostów. Główne ryzyko to rzadka kolejność zdarzeń, w której zatwierdzenie limitu nadpisuje oczekującą korektę przyczyną `limit`. Późniejsza edycja wzoru gubi wtedy odświeżenie po korekcie. Nie łamie to kryteriów w testowanym przepływie, ale jest sprzeczne z ryzykiem opisanym w tasku.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `packages/board-search-ui/src/use-board-search-sequence.ts:541` — `repeatWithLimit` bezwarunkowo zastępuje kolejkę obiektem `{ reason: 'limit', ... }`, także gdy czeka już kolejka `reason: 'correction'`. Ta sama sytuacja zachodzi przy wywołaniu z `board-search-workspace.tsx:637-638`. Przebieg:
  1. Użytkownik zapisuje korektę planszy przy zajętym kalkulatorze; kolejka dostaje `correction`.
  2. Przy czystym wzorze zatwierdza nowy limit; kolejka przechodzi na `limit`.
  3. Edytuje wzór; efekt w `use-board-search-sequence.ts:464` anuluje kolejkę jako nieaktualny limit.

  Po zakończeniu kalkulacji widoczny snapshot po korekcie nie jest odświeżany: znaczniki, wypłaty i zakres wygranej pozostają sprzed korekty. Przed tą zmianą nadpisana kolejka nadal by się wykonała, więc to regresja wąskiej kolejności zdarzeń. Jest sprzeczna z sekcją Risks („Nie wolno anulować kolejki korekty tylko dlatego, że draft odbiega od wyników”). Proponowana poprawka: w `repeatWithLimit` użyć aktualizatora `setRepeatPending((pending) => ({ reason: pending?.reason === 'correction' ? 'correction' : 'limit', options: { ...visibleSubmitted, limit: nextLimit, preserveSelection: true } }))`. Do tego test interakcji opisany niżej. Można też zaakceptować ryzyko i je odnotować.
- [P2-2] `packages/board-search-ui/test-browser/board-search-sequence.mjs:263` — kontrola po zakończeniu czeka na włączony przycisk z tekstem „Szukaj plansz” i nagłówek `#end`. Oba warunki są spełnione także w stanie sprzed wyrenderowania `loading`. Nagłówek z zachowanym wyborem jest widoczny cały czas, a etykieta zmienia się na „Wyszukiwanie…” dopiero po commicie Reacta (`board-search-workspace.tsx:1079-1083`). Przy ścieżce Enter wyszukiwanie startuje z mikrozadania efektu, więc między zapisaniem żądania w fixture a renderem stanu ładowania jest krótkie okno. Gdyby `waitForFunction` trafił w to okno, asercja „no additional request after clean … settles” i dopasowanie `.boardSearchResultMetrics` sprawdzą stan przed odpowiedzią. Zabezpieczenie P2-2 stałoby się wtedy pozorne. W praktyce opóźnienia CDP czynią to mało prawdopodobnym. Proponowana poprawka: czekać na licznik zakończonych odpowiedzi w fixture, np. `window.fixtureResponses.length > cleanBefore`. Alternatywnie czekać najpierw na stan „Wyszukiwanie…”, a dopiero potem na powrót „Szukaj plansz”. Można też zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Czysty commit limitu przy zajętym kalkulatorze, potem edycja wzoru i koniec kalkulacji nie wysyłają starego zapytania; jawne Szukaj wysyła nowy wzór i limit | spełnione (statycznie) | `packages/board-search-ui/src/use-board-search-sequence.ts:464-474`, test `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs:623-663`; wyniku RED i PASS nie uruchamiałem niezależnie |
| Korekta planszy nadal odświeża widoczny snapshot i kalkulator pomimo edycji draftu | spełnione w testowanym przepływie, z wyjątkiem z P2-1 | `packages/board-search-ui/src/use-board-search-sequence.ts:475-486`, `:534-540`, test `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs:665-706` |
| Browser fixture dla Admina, linku i panelu sprawdza dokładnie jedno żądanie także po zakończeniu; czysty wzór przez Enter i rzeczywisty click | spełnione (statycznie), z uwagą z P2-2 | `packages/board-search-ui/test-browser/board-search-sequence.mjs:214-230`, `:238-288` |
| Regresje, lint, format, typy, build konsumentów, docs i mapa zaliczone; osobny commit i zapis hasha | niezweryfikowane (deklaracja wykonawcy), commit i hash potwierdzone | `git show --stat 27bb5be0` (v1.7.473, 8 plików, w tym CURRENT_STATE i raport odbioru), `98c85100` (zapis hasha); `ai_docs/process/CURRENT_STATE.md:69` |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`: zapis korekty przy zajętym kalkulatorze, potem zatwierdzenie nowego limitu przy czystym wzorze, potem edycja wzoru i koniec kalkulacji. Oczekiwane jest jedno odświeżenie widocznego snapshotu z nowym limitem i ponowne obliczenie zakresu. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui`.
- `packages/board-search-ui/test-browser/board-search-sequence.mjs`: w pętli Enter/click czekać na zakończenie odpowiedzi według licznika po stronie fixture albo przejścia „Wyszukiwanie…” → „Szukaj plansz”, a dopiero potem ponownie porównać listę żądań. Komenda: `node packages/board-search-ui/test-browser/board-search-sequence.mjs`.

## Zakres przeglądu i ograniczenia

Przeczytałem brief, task, pełny diff `6d49edb9...HEAD` dla wskazanych ścieżek oraz niezacommitowaną zmianę pliku taska (dopisana sekcja Audit; zgodna ze zgodą operatora). Przeczytałem też `use-board-search-sequence.ts` w liniach 90–555 (funkcja `search`, `replaceDraft`, `clear`, efekt kolejki), wywołania `repeat` i `repeatWithLimit` w `board-search-workspace.tsx` (`commitLimit`, `onBoardEdited`, zamknięcie serii) oraz pełną funkcję `limitClickRegression`. Odczytałem listę plików obu commitów i potwierdziłem wpisy o TASK-1094 w CURRENT_STATE i w raporcie odbioru. Nie uruchamiałem żadnych testów, lintu, typecheck, buildów ani fixture przeglądarkowej. Wszystkie wyniki w Verification results to deklaracje wykonawcy, nie niezależna weryfikacja. Nie sprawdzałem fizycznego Androida ani zachowania poza zakresem (TASK-1092/P2-3, API, schemat).
