---
title: Stabilne odczyty planszy podczas zmiany kontekstu korekt
status: done
---

# TASK-1096 — Stabilne odczyty planszy podczas zmiany kontekstu korekt

## Status

`done`

## Goal

Usunąć dawne TASK-1092/P2-3: zmiana blokady lub kontekstu korekt nie powtarza odczytu otwartej planszy ani preloadu tych samych wyników.

## Context / entry conditions

Operator 2026-10-25 zlecił także dotychczas odłożone P2-3 oraz migrację i potrzebne operacje wdrożeniowe. Migracja jest osobnym zakresem po naprawie blokera startowego (kod nadal oczekuje 0168, migracja ma głowę 0169). Integracja main wymaga osobnej akceptacji konkretnego wyniku zgodnie z AGENTS.md. Punkt startu czysty, v1.7.477 / 7a66325e; numer 1096 sprawdzony w historii refs i aktywnych worktree.

## Recommended execution

gpt-6.1-sol / high, bez delegowania i nowego płatnego audytu. Mała korekta zależności efektów z testem kontekstu zapisu. Eskalacja przy zmianie API, uprawnień lub zachowania korekt.

## Relevant docs

- AGENTS.md, ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md, DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ADMIN_APP.md — D-573
- ai_docs/architecture/API_CONTRACT.md — kontekst korekt bez zmian
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — zakres B
- ai_docs/quality/TASK-1092_AUDIT_claude-opus-5-5.md — dawne P2-3
- ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md

## Scope / Technical notes

Zawęzić zależności efektów odczytujących do używanych metod odczytu zamiast całego resultClient. Nie stabilizować mutujących portów kosztem aktualności kontekstu i nie czytać refów w renderze. Modal zależy od getBoardSearchBoardDetail, gry, pozycji, próby i wersji reguł. Preload zależy od boardSearchBoardViewUrl i wyników, a fallback geometrii od getOperationalImageReviewItem i tożsamości wyniku. Blokada edycji podczas loading i aktualny searchContextId w zapisie pozostają bez zmian.

## Expected files

Istniejące packages/board-search-ui/src/board-search-board-lines-modal.tsx, src/board-search-results.tsx, test-interactions/board-search-sequence.test.mjs; wymagania, raport odbioru, CURRENT_STATE i task. Mapa generowana, jeśli zmieniona. Brak nowego kontraktu i modułów aplikacji.

## Acceptance criteria / Test cases

- [x] Odtworzenie RED: przy otwartym modalu i niezmienionej planszy replay/start kolejnego wyszukiwania nie ponawia szczegółów ani preloadu starych wyników.
- [x] Po nowym wyniku o tej samej tożsamości modal zachowuje odczyt, a preload obsługuje nową listę. Korekta po odpowiedzi używa nowego kontekstu; podczas loading porty pozostają niedostępne.
- [x] Celowe odświeżenie po zapisie, zmiana planszy/checksumy, reguł i klienta odczytu nadal działają, w tym management i oba publiczne hosty.
- [x] Unit/interactions, lint/format, typy, buildy, docs/map PASS; zamknięcie skryptem, commit i hash.

## Verification

Najpierw nowy test interakcji RED, potem pełne npm test i test:interactions board-search-ui, test Reviewer, browser fixture. ESLint/Prettier zmienionych plików, typecheck board-search-ui/Admin/Reviewer i buildy Admin/Reviewer. scripts/generate_code_map.py, code-map:check, docs:check, diff --check. subprocess.run(timeout=120); git/odczyty do 30 s. Testy bez bazy operatora i bez restartów usług.

## Out of scope / Risks

API, schema, migracja i restarty w tym commicie. Migracja 0169 wymaga osobnego sprawdzenia gotowości API i przejścia ze starego kodu. Nie zmieniać ochrony korekt w celu ograniczenia odczytów. Fizyczny Android nieodebrany.

## Outcome

Commit: v1.7.478 / `e8018ef1eb34b1825d30f1f7d406e603ab50915a`.

### Changed

Efekty modalu szczegółów, preloadu sąsiadów i geometrii fallback zależą teraz od używanych metod odczytu zamiast całego opakowania klienta. resultClient nadal zmienia porty korekty i kontekst tak jak wcześniej; nie ukryto blokady loading i nie wprowadzono refów czytanych w renderze. Publiczne propsy i API bez zmian.

### Verification results

- Nowy test RED: start replay z otwartym modalem dawał 2 odczyty zamiast 1 (task-1096-red.log). Po poprawce PASS: zero ponownego odczytu przy loading i nowym contextId, zero preloadu starej listy, jeden preload sąsiada nowej listy. Mutacje niedostępne podczas loading, późniejszy zapis używa new-context. Celowe odświeżenie po zapisie i podmiana metody odczytu ponawiają szczegóły.
- board-search-ui: 108 unit i 120 interactions PASS; Reviewer 293 PASS; browser fixture 18 kontroli PASS, failures=[], w tym Admin/share/panel, oba procesy Edge i viewport mobilny. Logi task-1096-*.log w ignorowanym artifacts/board-search-sequence-browser/.
- ESLint i Prettier trzech zmienionych plików PASS. Typecheck board-search-ui/Admin/Reviewer PASS. Buildy Admin i Reviewer PASS, tylko znane ostrzeżenie Next o wielu lockfile w worktree.
- Mapa wygenerowana bez zmiany wyniku; code-map:check, docs:check i diff --check PASS. Zamknięcie oraz indeks kontrolowane ponownie przed commitem. Komendy z timeout 120 s, w nowych procesach.
- Osobny preflight migracji wykazał niezgodność schema_readiness: 1 failed, 14 passed. To potwierdzony bloker wdrożenia 0169, poza poprawką UI; zostanie naprawiony w osobnym TASK-1097 przed migracją. Baza operatora odczytana tylko do sprawdzenia: 0168_source_crop_runs. Nie zastosowano migracji.

### Not completed

Bez nowego audytu Claude (nie był wymagany dla tej małej poprawki). Bez zmian danych, restartów, scalenia i push. Fizyczny Android nieodebrany; viewport to emulacja. Rzeczywista migracja pozostaje zlecona, ale wymaga usunięcia blokera startowego i uzgodnionej integracji ze starym działającym kodem.

### Documentation updates / Definition of Done

ADMIN_APP opisuje zachowanie odczytów. Raport odbioru odróżnia zamknięte dawne P2-3 od historycznych audytów; CURRENT_STATE zaktualizowany. AC1: RED→GREEN, AC2: pełna kontrola nowego kontekstu i blokady, AC3: nowe celowe refetch plus regresje całego współdzielonego UI i obu hostów, AC4: kontrole kodu i buildy PASS, task-close i hash. Brak zmiany domeny, kontraktu, uprawnień lub schematu w tym tasku; plan B zachowany.

### Recommended next task

TASK-1097: uzgodnić wymagany Alembic head 0169 i przetestować startup, następnie przygotować zatwierdzoną migrację/uruchomienie. Osobna zgoda na main nadal wymagana.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1096 — Dawne P2-3 | gpt-6.1-sol | high | Zależności odczytu i ochrona aktualnego kontekstu korekty we wspólnym UI. | Bez nowego audytu w tym zleceniu; odtworzenie i regresje wykonawcy. |
