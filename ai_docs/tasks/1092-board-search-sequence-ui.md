---
title: Wyszukiwanie ciągu plansz — badże i trwałość
status: todo
---

# TASK-1092 — Wyszukiwanie ciągu plansz — badże i trwałość

## Status

todo

## Goal

Udostępnić badże 1–4 wpisanych wzorów, wspólne wyniki i trwały lokalny zestaw w Adminie oraz obu linkach.

## Context

Zadanie B zaakceptowanego planu; operator zlecił cały plan i zaakceptował koszt 2026-10-24. Bez migracji operatora, restartów i scalenia do main.

## Dependencies / entry conditions

Zamknięty TASK-1091. Ponowny odczyt taska i zaakceptowanego planu przed kodowaniem B. Wspólny workspace zachowuje dotychczasowe zachowanie management.

## Recommended execution

gpt-6.1-sol / high. Stan kilku widoków, trwałość i race conditions. Audyt Claude Code claude-opus-5-5 / medium przed commitem; zakres/koszt zaakceptowany poleceniem całego planu. Niedostępność konfiguracji albo otwarte P0/P1 po poprawkach zatrzymują zadanie.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — B i reguły UX
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md

## Scope

- Opcjonalna metoda sequence w data source, badże i przyciski, oddzielny stan edytora i wspólnych wyników.
- localStorage ze scope gry/linku/panelu, restore po dostępie, replay przed restore.
- Podgląd ostatniej planszy, detale pozostałych, korekty, wygrane od końca ciągu.
- Koordynacja kalkulatora i wyszukiwania, stare odpowiedzi, błędy, 401/429, brak storage.
- Pełna historia v2 w Adminie oraz liczba układów w widoku korekt.

## Out of scope

Synchronizacja urządzeń, inne aplikacje, offline APK, zmiana wypłat i management workflow, operator DB/restarty/merge/push.

## Acceptance criteria

- [ ] Badże przełączają tylko wzór; wspólne wyniki i kotwica wygranej pozostają niezależne.
- [ ] Następny/Resetuj/Nowe szukanie i limit 4 zgodne z planem, także puste końce i środkowe luki.
- [ ] Stan odtwarzany po nowym procesie, bez pomieszania gier/linków, bez trwałych odpowiedzi/sekretów.
- [ ] Replay wygrywa z localStorage; spóźnione odpowiedzi nie wskrzeszają resetu.
- [ ] Korekty, supergry, wygrane i management mają testy regresyjne; oba rodzaje linku działają.
- [ ] Lint/typy/interakcje/docs/mapa i niezależny audyt rozliczone; ograniczenia odbioru jawne.

## Technical notes

Stany, klucze, interakcje i błędy według planu 3.1 B. Opcje wspólnych komponentów są opcjonalne. Jeden wzór nadal korzysta z GET. Badż nie zmienia stawki/pinów/wyboru wyniku. Zapis ma nie utrwalać contextId, credential ani wyników API.

## Expected files

- Istniejące: packages/board-search-ui/src/board-search-workspace.tsx, board-search-data-source.ts, board-search-approximate-win.tsx, wspólny CSS i eksporty.
- Istniejące: adapter/gates Reviewera; wrapper/workspace Admina; replay/log/korekty Admina.
- Proponowane: board-search-sequence-state.ts i dedykowane testy stanu/interakcji.

## Test cases

Mapa B planu: wszystkie przyciski i 4 badże, luki i ?, stare odpowiedzi po reset/scope, restore i zły storage, replay>restore, 401/429, wygrane od końca, korekta wcześniejszej planszy, obie powierzchnie publiczne i management. Web mobile; fizyczny Android tylko gdy dostępny bez restartowania usług.

## Verification

Testy jednostkowe/interakcyjne board-search-ui oraz zmienionych hostów; lint i typecheck pakietów; docs/OpenAPI/mapa. Każda grupa przez timeout=120 s. Trwałość z nowego procesu przeglądarki albo jawny brak tego odbioru.

## Risks / open questions

Inny origin tunelu nie odzyska localStorage. Odbiór urządzenia i ewentualne blokery środowiskowe opisać bez fikcyjnego PASS.

## Outcome

Nie rozpoczęto.
