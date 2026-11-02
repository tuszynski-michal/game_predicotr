---
title: Przyciąganie kliknięcia wykresu do korzystnego punktu
status: done
last_updated: 2026-11-01
---

# TASK-1116 — Przyciąganie kliknięcia wykresu do korzystnego punktu

## Status

`done`

## Goal

Kliknięcie wykresu wyszukiwarki przypina najwyższy bilans w zakresie ±50 spinów od klikniętego spinu.

## Context

Operator chce łatwo trafiać w opłacalne wierzchołki przy zakresie 2500 spinów. Zlecił wykonanie zmiany; scalenie całej pracy pozostaje wstrzymane do kolejnej zgody.

## Dependencies / entry conditions

- TASK-1115 ukończony; worktree czysty przy rozpoczęciu.
- Brak pytań blokujących. Założenie UI: korzystność oznacza najwyższą „kasę na czysto” na wykresie, a nie największą pojedynczą wypłatę. Remisy: najbliżej kliknięcia, następnie wcześniejszy spin.
- Mała zmiana bez osobnego planu i bez wymaganego audytu krzyżowego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

- Wspólna obsługa kliknięcia/dotyku w Adminie i online, zakres domknięty ±50 spinów.
- Przesunięcie aktywnego kursora i przypięcie wybranego spinu.
- Testy algorytmu, kliknięcia i zachowania istniejącej klawiatury.

## Out of scope

- Zmiany API, danych, migracje, usługi, merge, push i sprzątanie worktree.
- Zmiana najechania, nawigacji strzałkami i limitu przypięć.

## Acceptance criteria

- [x] Kliknięcie wybiera najwyższy końcowy bilans spinu w ±50, w granicach obliczonego zakresu.
- [x] Remisy są deterministyczne; punkty przed wypłatą nie są wybierane.
- [x] Kursor i przypięcie wskazują wybrany spin, również w kontrolowanym panelu zapisanym.
- [x] Filtr tabeli nie zmienia wyboru; klawiatura i odpinanie pozostają działające.
- [x] Testy, lint, typy, dokumentacja i mapa kodu są sprawdzone.

## Technical notes

Środek okna wynika z osi X kliknięcia, zaokrąglonej do spinu, nigdy z najbliższego wiersza wypłaty. Okno obejmuje również spiny bez wypłat i płaskie odcinki darmowych spinów. Uwzględnia rozpoznane wypłaty oraz harmonogram kosztów; wypłaty prowizoryczne nie zmieniają bilansu. Początek 0 i koniec zakresu są dopuszczalne. Przy remisie odległości wybierz wcześniejszy spin. Ponowne kliknięcie przyciągające do przypiętego spinu odpina go.

## Expected files

- `packages/board-search-ui/src/board-search-approximate-win-state.ts`: nowy helper wyboru punktu.
- `packages/board-search-ui/src/board-search-approximate-win.tsx`: `ApproximateWinBalanceChart`, obsługa kliknięcia.
- `packages/board-search-ui/test/board-search-approximate-win-state.test.mjs`.
- `packages/board-search-ui/test-interactions/board-search-approximate-win.test.mjs` i w razie potrzeby test zapisanych paneli.
- Wymagania, mapa kodu i dokumentacja zamknięcia zadania.

## Test cases

- Maksimum z lewej/prawej strony, granice ±50 i punkt poza oknem.
- Największa pojedyncza wypłata nie jest najwyższym bilansem.
- Remisy, płaski odcinek darmowych spinów, brak wypłat, początek/koniec.
- Kliknięcie obok wierzchołka przesuwa kursor, przypina spin i odpina po ponowieniu.

## Verification

Testy jednostkowe i interakcyjne `@game-predictor/board-search-ui`, lint i typecheck wspólnego UI, typecheck obu aplikacji, `npm run docs:check`, `npm run code-map:check`. Każda komenda z timeoutem 120 s. Wynik zapisany poniżej; bez uruchamiania usług.

## Risks / open questions

- Fizyczny Android i działające środowisko operatora nie są dostępne w testach automatycznych.

## Outcome

Commit: v1.7.513 / `781650dcfa28dc9af94ef3fb23700e1bd36c4b94`.

### Changed

- Czysty helper wybiera najwyższy bilans po wypłacie w domkniętym oknie ±50 spinów. Korzysta z wszystkich wierszy odpowiedzi i harmonogramu kosztów, niezależnie od filtra tabeli. Wiersze są skanowane liniowo; ocena obejmuje najwyżej 101 spinów.
- Kliknięcie ustawia aktywny kursor i przełącza przypięcie wybranego spinu w obu trybach wykresu. Tożsamość etykiet istniejących punktów zostaje zachowana, również dla wypłaty na ostatnim spinie.
- Obsłużone remisy, granice, płaskie odcinki darmowych spinów i prowizoryczne wypłaty. Brak zmiany klawiatury, API i sposobu zapisu przypięć.

### Verification results

- `npm run test --workspace @game-predictor/board-search-ui`: **113/113 PASS**, w tym 5 nowych testów algorytmu.
- `npm run test:interactions --workspace @game-predictor/board-search-ui`: **109/109 PASS**, w tym nowe testy kliknięcia, przesunięcia kursora, odpinania i strzałek dla zwykłego wykresu oraz zapisanego panelu.
- `npm run lint --workspace @game-predictor/board-search-ui`: PASS.
- `node node_modules/typescript/bin/tsc --noEmit -p <workspace>/tsconfig.json`: PASS dla `packages/board-search-ui`, `apps/admin`, `apps/reviewer`.
- Prettier czterech zmienionych plików kodu/testów: PASS; `git diff --check`: PASS.
- `npm run docs:check` i `npm run code-map:check`: PASS; mapa zregenerowana.
- Zmiana trwale zapisana w kodzie, testowana z nowych procesów Node. Nie wymaga konfiguracji sesyjnej ani migracji.

### Not completed

- Bez fizycznego testu Androida i testu na żywych usługach operatora; click jest wspólną ścieżką myszy i tapnięcia. Usług nie uruchamiano ani nie restartowano.
- Nie powtarzano produkcyjnych buildów wykonanych dla TASK-1115; ta zmiana obejmuje wyłącznie logikę interakcji, sprawdzoną testami i typami obu aplikacji.
- Audyt krzyżowy niewymagany: mała zmiana bez osobnego planu i wymaganego dodatkowego review.
- Merge, push i cleanup niewykonane zgodnie z poleceniem operatora.

### Documentation updates

- `ADMIN_APP.md`: wybór najwyższej kasy na czysto w ±50, remisy i zachowana klawiatura.
- Mapa kodu: nowy helper i stała zakresu. `CURRENT_STATE.md` i archiwum: wynik zamknięcia taska przez `close_task.py`.
- Kryteria taska i właściwe punkty Definition of Done spełnione; ograniczenia weryfikacji wyszczególniono powyżej. Kontrakt API, schemat danych i architektura pozostają zgodne.

### Recommended next task

- Odbiór ekranu przez operatora. Dopiero po jego nowej zgodzie: preflight i scalenie całej pracy, push oraz bezpieczne sprzątanie worktree.
