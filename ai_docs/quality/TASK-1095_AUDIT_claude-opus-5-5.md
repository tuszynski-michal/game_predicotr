---
title: Audyt TASK-1095
status: active
last_updated: 2026-10-25
---

# Audyt TASK-1095 — Pierwszeństwo korekty i zakończone odpowiedzi fixture

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...28a86ce2259f210928dfd97b0cab888ed7ff53f5 oraz zmiany niezacommitowane, data 2026-10-25
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem poprawkę `repeatWithLimit` w hooku sekwencji, dwa nowe testy interakcji (korekta przed limitem i limit przed korektą) oraz przebudowany fixture przeglądarkowy z rejestrem zakończonych odpowiedzi i znacznikiem oceny równym limitowi. Obie uwagi TASK-1094/P2-1–2 są usunięte zgodnie z zakresem. Oczekująca korekta nie jest już degradowana do przyczyny `limit`. Fixture czeka na zakończenie konkretnej odpowiedzi i na nową wartość metryki, a dopiero potem sprawdza gotowy przycisk. Główne ryzyko: nowe zdanie w ADMIN_APP mówi szerzej, niż działa kod. Przy zmienionym wzorze zmiana limitu nie trafia do oczekującej korekty.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `ai_docs/requirements/ADMIN_APP.md:467` — Zdanie „Zmiana limitu podczas oczekiwania na to odświeżenie aktualizuje jego limit” jest sformułowane bez warunku. Tymczasem `packages/board-search-ui/src/board-search-workspace.tsx:637-638` wywołuje `repeatWithLimit` tylko przy `!sequence.draftChanged`. Weźmy sekwencję: zapisana korekta → edycja wzoru → zmiana limitu. Oczekujące odświeżenie korekty pobierze wtedy widoczny snapshot ze starym limitem (`packages/board-search-ui/src/use-board-search-sequence.ts:538`), a wynik zostanie oznaczony jako `stale`, bo `visibleSubmitted.limit !== limit`. Takie zachowanie zgadza się z regułą z `ADMIN_APP.md:459` (po edycji wzoru limit jest tylko zapamiętywany) i nie traci danych. Wymaganie jest jednak niejednoznaczne, a nowy test pokrywa tylko limit zmieniony przed edycją wzoru. Proponowana poprawka: dopisać w ADMIN_APP „przy niezmienionym wzorze” albo jawnie zaakceptować ryzyko. Zmiana kodu nie jest konieczna.
- [P2-2] `packages/board-search-ui/test-browser/board-search-sequence.mjs:196` — `waitForSearchResponse` używa indeksu `before` pobranego z `window.fixtureRequests` (`:223`, `:269`) jako indeksu do `window.fixtureResponses`. Działa to, dopóki każde wcześniejsze żądanie zakończyło się w kolejności FIFO. Asercja `deepEqual` wychwyci rozjazd głośno, bez fałszywego PASS, ale wiąże dwie tablice niejawnie. Proponowana poprawka do rozważenia przy kolejnej zmianie fixture: osobno odczytywać `fixtureResponses.length` przed akcją. Na razie akceptuję ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| AC1: korekta → limit → edycja → koniec kalkulacji; dokładnie jedno odświeżenie snapshotu korekty z najnowszym limitem, ponowny zakres, draft zmieniony | spełnione (statycznie); RED/GREEN niezweryfikowane | `packages/board-search-ui/src/use-board-search-sequence.ts:541-553`; `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs:937-1006` (asercje `calls.multi[1]` z `limit: 9`, `calls.range[1].startSequenceNumber === 1`, „Wzór zmieniony”, `calls.multi.length === 2` po drugim `finish`) |
| AC2: limit → korekta oraz zwykłe anulowanie limitu bez regresji | spełnione (statycznie) | wariant `limit-first` w `test-interactions/board-search-sequence.test.mjs:961`; ścieżka anulowania `use-board-search-sequence.ts:464-474` bez zmian; istniejący test `test-interactions/board-search-sequence.test.mjs:851` |
| AC3: fixture czeka na zakończoną odpowiedź i gotowe UI przed końcową asercją; Admin/share/panel, Enter/click, odpowiedzi natychmiastowe i opóźnione | spełnione (statycznie); przebieg Edge niezweryfikowany | `test-browser/board-search-sequence.mjs:60-68`, `:73`, `:180-202`, `:248`, `:290`, `:318-325`; metryka `src/board-search-results.tsx:157` renderuje ocenę nadpisaną limitem |
| AC4: unit/interactions, lint/format, typy, buildy, docs/map PASS; audyt rozliczony, zamknięcie skryptem i commit | niezweryfikowane | Wyniki są deklaracją wykonawcy w pliku taska. Statyczny audyt ich nie uruchamiał. Checkbox w tasku jest jeszcze odznaczony, co jest poprawne przed zamknięciem. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy.

Otwarte: P2-1, P2-2.

## Proponowane testy

- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`: scenariusz korekta → edycja wzoru → zmiana limitu → koniec kalkulacji. Test zapisze ustalone zachowanie: odświeżenie korekty ze starym limitem i flaga `stale`, albo przeciwne, jeśli wymaganie zostanie doprecyzowane inaczej. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui`.
- Opcjonalnie: wariant `limitClickRegression` z natychmiastowymi odpowiedziami także dla `share` lub `panel` w `packages/board-search-ui/test-browser/board-search-sequence.mjs:325`. Komenda: `node packages/board-search-ui/test-browser/board-search-sequence.mjs`.

## Zakres przeglądu i ograniczenia

Przeczytałem brief, plik taska, diff czterech zmienionych plików oraz bieżący `use-board-search-sequence.ts`. Sprawdziłem w nim wywołania `search`, `repeat`, `repeatWithLimit` i efekt kolejki. Przeczytałem wywołania `repeatWithLimit`/`repeat` w `board-search-workspace.tsx`, renderowanie metryk w `board-search-results.tsx`, listę testów interakcji, fragment fixture przeglądarkowego (linie 50–339) i odpowiedni fragment `ADMIN_APP.md`. Nie uruchamiałem testów, lintów, typechecku, buildów ani przeglądarki. Wyniki RED/GREEN, 108/118/293 testów i 18 kontroli Edge pochodzą wyłącznie od wykonawcy. Nie przeglądałem zmian w `CURRENT_STATE.md` i raporcie odbioru, bo leżą poza pathspec briefu.
