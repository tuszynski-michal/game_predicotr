# Audyt TASK-1093 — Jedno kliknięcie wyszukiwania po zmianie wzoru i limitu

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: 921921fc6cb23ba39da9e6d61182cc115ad30a5a...3a30e13510ebb65fa746d6140eeff771f9d5a741 oraz zmiany niezacommitowane, data 2026-10-25
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem poprawkę P2-4: nowe pole `draftChanged` w hooku `useBoardSearchSequence` i nowy warunek w `commitLimit`. Sprawdziłem też przepływ blur→click do `sequence.search`, kolejkę `repeatPending` z blokadą busy oraz zmienione testy interakcji i przeglądarki. Poprawka jest minimalna i usuwa przyczynę błędu. Przy zmienionym drafcie blur nie ustawia już `repeatPending`, więc przycisk „Szukaj plansz” nie zostaje wyłączony między pointerdown a click. Limit w handlerze click jest aktualny, bo React synchronicznie wykonuje aktualizacje z dyskretnego zdarzenia focusout przed następnym zdarzeniem. Czysty draft nadal odświeża wyniki przez tę samą kolejkę. Zostaje jedno ryzyko P2: wcześniej zakolejkowane odświeżenie czystego snapshotu nie jest anulowane, gdy użytkownik zmieni wzór przed zakończeniem kalkulatora. Są też dwie luki w sile asercji browser testu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `packages/board-search-ui/src/use-board-search-sequence.ts:457` — Poprawka blokuje tylko kolejkowanie nowego odświeżenia przy brudnym drafcie (`board-search-workspace.tsx:637`). Nie anuluje `repeatPending` zakolejkowanego wcześniej, gdy draft był jeszcze czysty. Scenariusz: udane wyszukiwanie A, kalkulator przybliżonej wygranej jest zajęty, użytkownik zatwierdza nowy limit (czysty draft, więc `repeatPending` = snapshot A), a potem dokłada symbol B. Gdy kalkulator skończy, efekt (`:466-469`) automatycznie wysyła stary wzór A, choć draft jest już brudny. W tym czasie stan `loading` wyłącza „Szukaj plansz”, więc kliknięcie w tym oknie przepada. To ten sam rodzaj objawu co P2-4, w węższym oknie czasowym. Kryterium AC3 („przy zatwierdzeniu limitu”) jest formalnie spełnione, więc to nie P1. Proponowana poprawka: w efekcie kolejki porzucić `repeatPending`, gdy `draftChanged` jest prawdą (albo czyścić `repeatPending` w `setEditor`/`setEditors`), i dodać test interakcji „czysty commit limitu podczas kalkulacji → edycja wzoru → finish() → brak żądania”. Alternatywa: świadomie zaakceptować ryzyko i opisać je w Outcome.
- [P2-2] `packages/board-search-ui/test-browser/board-search-sequence.mjs:205` — `sent` jest odczytywane zaraz po pierwszym nowym wpisie w `fixtureRequests`. W wariancie opóźnionym drugie, spóźnione żądanie (np. stary snapshot z kolejki) pojawiłoby się po asercji. Kolejna miara `cleanBefore` (`:225`) liczy już od nowa, więc takie żądanie zostałoby niewykryte. Test case wymaga dokładnej liczby żądań i braku drugiego click. Sam test tego w pełni nie gwarantuje, choć obecny kod takiego żądania nie wysyła. Ta sama luka dotyczy asercji `clean` (`:236`). Proponowana poprawka: po `waitFor` przycisku „Szukaj plansz” i nagłówka sprawdzić jeszcze raz, że `window.fixtureRequests.length === before + 1` (analogicznie `cleanBefore + 1`).
- [P2-3] `packages/board-search-ui/test-browser/board-search-sequence.mjs:225` — Czysty wzór jest sprawdzany tylko przez Enter. Nie ma testu ścieżki „czysty wzór, wpisanie limitu, rzeczywisty click na Szukaj”. W tej ścieżce blur ustawia `repeatPending`, mikrozadanie efektu rusza z wyszukiwaniem i wyłącza przycisk, więc właściwy click przepada. Skutek jest dziś neutralny, bo żądanie z kolejki ma ten sam wzór i nowy limit. Ta równoważność nie jest jednak niczym chroniona. Proponowana poprawka: dodać wariant clean+click z asercją dokładnie jednego żądania o treści `{...expected.request, limit: N}`. Alternatywa: zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Test rzeczywistych zdarzeń odtwarza błąd na kodzie sprzed poprawki | spełnione (statycznie), wynik RED niezweryfikowany | `packages/board-search-ui/test-browser/board-search-sequence.mjs:170-206`. Playwright `locator.click` (`:144-147`) wykonuje pointerdown→blur→click przy fokusie w polu limitu. Na starym kodzie blur kolejkował stare zapytanie i wyłączał przycisk. Logi RED wskazane przez wykonawcę nie zostały przeczytane. |
| Pierwsze kliknięcie po edycji wzoru i limitu wysyła wyłącznie nowy wzór z nowym limitem (Admin, link, panel) | spełnione | `packages/board-search-ui/src/board-search-workspace.tsx:637-638`, `packages/board-search-ui/src/use-board-search-sequence.ts:117`, `:207-208`. Pętla po admin/share/panel i wariant natychmiastowy: `test-browser/board-search-sequence.mjs` (sekcja `try`, wywołania `limitClickRegression`). Siła asercji: zob. P2-2. |
| Brudny draft nie powoduje automatycznego żądania ze starego snapshotu przy zatwierdzeniu limitu; czysty nadal odświeża i czeka na kalkulator | spełnione, z resztkowym ryzykiem P2-1 | `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs:851-896` (brudny, z busy, pełne body po jawnym Szukaj); `:811-849` (czysty, kolejka i wybór #6); `use-board-search-sequence.ts:457-474` |
| Lint/format/typy, testy i browser fixture PASS; dokumentacja, mapa i commit rozliczone | niezweryfikowane (deklaracja wykonawcy) | Outcome taska. Dokumentacja wymagania: `ai_docs/requirements/ADMIN_APP.md:459-462`. Komend nie uruchamiano. |

## Listy zamknięte i otwarte

Zamknięte: brak (runda 1).

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`: czysty commit limitu przy zajętym kalkulatorze, potem edycja wzoru, potem `finish()`. Oczekiwane: `calls.single.length` się nie zmienia, a jawne Szukaj wysyła nowy wzór. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui`.
- `packages/board-search-ui/test-browser/board-search-sequence.mjs`: po ponownym włączeniu przycisku powtórna asercja dokładnej liczby żądań (`before + 1`, `cleanBefore + 1`) oraz wariant czystego wzoru z rzeczywistym click zamiast Enter. Komenda: `node packages/board-search-ui/test-browser/board-search-sequence.mjs` (headless Edge, loopback, timeout 120 s).

## Zakres przeglądu i ograniczenia

Przeczytałem brief z diffem commitów 921921fc...HEAD i niezacommitowaną zmianę pliku taska. Przeczytałem `use-board-search-sequence.ts` w liniach 60–534: stan, `search`, `restore`, kolejkę `repeatPending`, `repeat`/`repeatWithLimit`. Przeczytałem fragmenty `board-search-workspace.tsx`: mapowanie `limit`/`setLimit` na hook, `runSearch`, `commitLimit`, pole limitu z `onBlur`/Enter i przycisk „Szukaj plansz” z warunkiem `disabled`. Przeczytałem też helpery `click`/`palette`/`search`/`compose` z browser testu. Nie uruchamiałem testów, lintu, typecheck, buildów ani browser fixture. Nie czytałem logów RED w `artifacts/board-search-sequence-browser/`, AGENTS.md ani dokumentów odbioru i mapy kodu. Wyniki weryfikacji w Outcome to deklaracje wykonawcy. P2-3 z TASK-1092 (identity `resultClient`) jest świadomie poza zakresem i go nie oceniałem. Niezacommitowana zmiana pliku taska dotyczy wyłącznie dokumentacji zgody na ten audyt i nie wpływa na kod.
