---
title: Super symbol highlights in the series board view
status: done
---

# TASK-1079 — Wyróżnienie super symbolu na planszach serii

## Status

`done`

## Goal

Wskazać wystąpienia wybranego symbolu serii w układzie 3×5 i na zdjęciu w Adminie oraz widoku udostępnionym.

## Context

Operator chce złotego tła podpowiedzi i wyraźnych fioletowych obramowań symboli na zdjęciu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Widok serii.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — Admin web i granica Reviewera.

## Scope

- Wspólny `SuperGameSeriesPanel`, używany przez Admina i modal odbiorcy.
- Podświetlenie bieżącego wyboru, także przed zapisem, po nawigacji, anulowaniu i wyczyszczeniu.
- Zachowanie obecnych oznaczeń symboli uruchamiających.

## Out of scope

- Zmiany API, wypłat, danych i sposobu zapisu serii; restart usług, wdrożenie i scalenie.

## Acceptance criteria

- [x] Wybrany symbol ma złote tło w podpowiedzi 3×5 i opis tekstowy.
- [x] Jego pola na zdjęciu mają fioletowe obramowania zgodne z geometrią API.
- [x] Zmiana wyboru i karty, anulowanie oraz wyczyszczenie aktualizują oznaczenia.
- [x] Brak geometrii nie tworzy zgadywanych współrzędnych; podpowiedź nadal działa.
- [x] Ten sam komponent zapewnia zachowanie w obu aplikacjach; oznaczenia triggerów pozostają.
- [x] Testy zmienionego panelu i modala, lint, format i typy przechodzą; kontrola dokumentacji przy zamknięciu.

## Technical notes

Założenie: „siatka CSV” oznacza nakładkę SVG na zdjęciu, bez eksportu pliku. Oznaczamy dokładne wystąpienia kodu symbolu odpowiadającego `candidateSymbolId`, bez rozwijania kolumn wypłaty. Zdjęcie i wielokąty pozostają związane z tą samą rewizją odczytu. Przy braku geometrii pokazujemy informację tekstową i nie zgadujemy położenia pól. Nie ma pytań blokujących ani zmiany architektury. Brak planu wymagającego audytu krzyżowego.

## Expected files

- `packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx` — SeriesView, SeriesBoardView.
- `packages/board-search-ui/src/super-game-series/super-game-series.css` — style oznaczeń.
- `packages/board-search-ui/test-interactions/super-game-series-panel.test.mjs` — testy wyboru i geometrii.
- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/CURRENT_STATE.md`, mapa kodu, ten task.

## Verification

Testy panelu i modala wspólnego oraz integracji Admina; ESLint i Prettier zmienionych plików; typecheck wspólnego pakietu i obu aplikacji; docs:check i code-map:check. Każdy proces ma timeout 120 s.

## Risks / open questions

- Bez wielokątów API można wyróżnić tylko podpowiedź; nakładka zdjęcia nie jest wtedy dostępna.

## Outcome

Commit: v1.7.453 (hash dopisuje kolejny commit).

### Changed

- Wspólny panel oznacza dokładne wystąpienia kodu wybranego symbolu złotym tłem i ★, a na zdjęciu fioletową ramką SVG o stałej grubości i kontrastowym cieniu.
- Wybór jest podglądem przed zapisem, reaguje na select i skróty, zmianę karty, anulowanie oraz wyczyszczenie. Oznaczenia triggerów pozostają.
- Dodano legendę z nazwą, kodem i liczbą wystąpień; brak geometrii ma jawny komunikat, bez zgadywania pól.
- Admin oraz obie trasy udostępnienia Reviewera importują ten sam panel i arkusz stylów. Bez zmiany kontraktu API, danych, architektury i zależności.

### Verification results

- Wspólne testy panelu i modala: 17/17 PASS. Dwa nowe scenariusze sprawdzają zapisany i niezapisany wybór, mapowanie ID na kod, nierówną geometrię, nawigację, anulowanie, wyczyszczenie, pola nieznane, braki plansz i geometrii oraz zachowanie triggerów.
- Testy integracji Admina dotyczące karuzeli, wyboru, skrótów i rewizji zdjęcia: 4/4 PASS.
- Pełny plik integracji Admina: 22/32 PASS, 10 wcześniejszych FAIL listy serii (brak `counts` w fixture). Odczyt panelu z HEAD i powtórzenie tego samego zestawu potwierdziło ten sam wynik 22/32 oraz te same nazwy porażek. Panel przywrócony do implementacji zadania w `finally`.
- ESLint zmienionego komponentu i testów oraz Prettier trzech plików: PASS. Pierwsza próba lintu miała złą względną ścieżkę narzędzia; poprawiona próba przeszła.
- TypeScript: wspólny pakiet, Admin i Reviewer PASS w nowych procesach.
- Mapa kodu zregenerowana; bez zmian merytorycznych (brak nowego modułu ani publicznego symbolu).
- `npm run docs:check` oraz `generate_code_map.py --check`: PASS. Zamknięcie `task-close` (dry-run i zapis) przeszło kontrolę okna i budżetów; wymagane szersze uprawnienia z powodu blokady kopiowania AGENTS.md do katalogu tymczasowego sandboxa.

### Not completed

- Nie uruchamiano usług, buildów aplikacji ani ręcznego odbioru wyglądu w przeglądarce/Androidzie. Rozmiar ramki jest stały przy skalowaniu SVG; układ responsywny pozostał bez zmian.
- Wcześniejsze błędy testów listy serii pozostają poza zakresem. Audyt krzyżowy nie jest wymagany przez plan (zadanie nie ma osobnego planu).
- Bez scalenia, push i wdrożenia; zmiana czeka na odbiór operatora.

### Documentation updates

- Wymagania widoku serii w `ADMIN_APP.md`, wskaźnik i wynik w `CURRENT_STATE.md`, task i archiwum przez `task-close`.
- Założenie o nakładce SVG zapisano przed kodowaniem. Brak blokujących pytań i decyzji domenowych.

### Recommended next task

- Odbiór oznaczeń na rzeczywistej planszy w Adminie i udostępnionym widoku; następnie decyzja operatora o scaleniu.
