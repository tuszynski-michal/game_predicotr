---
title: Anulowanie starego odświeżenia limitu i testy kliknięcia
status: done
---

# TASK-1094 — Anulowanie starego odświeżenia limitu i testy kliknięcia

## Status

`done`

## Goal

Usunąć trzy nowe P2 z audytu TASK-1093, zachowując odświeżenie po korektach plansz.

## Context

Operator zlecił 2026-10-25 poprawienie TASK-1093/P2-1–3, wskazane testy, regresje i commit. Dawne TASK-1092/P2-3 (identity resultClient) pozostaje odłożone. Bez migracji bazy operatora, restartów, merge i push. Punkt startu: czysty worktree, v1.7.472 / 6d49edb9. Numer 1094 sprawdzony w lokalnych refs; brak kolizji.

## Dependencies / entry conditions

Przeczytany raport TASK-1093 i zakres B zaakceptowanego planu. Brak pytań blokujących i zmian API, domeny lub schematu. To osobna mała poprawka; nie uruchamia kolejnego płatnego audytu.

## Recommended execution

gpt-6.1-sol / high, bez delegowania. Rozdzielenie przyczyny kolejki i kontrola kolejności zdarzeń React. Eskalacja przy regresji korekt lub konieczności rozszerzenia kontraktu.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ADMIN_APP.md — D-573, limit wyników
- ai_docs/architecture/API_CONTRACT.md — ciągi plansz, bez zmian
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — zakres B
- ai_docs/quality/TASK-1093_AUDIT_claude-opus-5-5.md
- ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md

## Scope

P2-1: anulować oczekujące automatyczne odświeżenie limitu po zmianie wzoru, także podczas kalkulacji. Rozróżnić je od odświeżenia po korekcie, które musi nadal działać dla widocznych wyników przy zmienionym drafcie. P2-2: ponowić asercje liczby i treści żądań po zakończeniu wyszukiwania. P2-3: sprawdzić czysty wzór z rzeczywistym click po blur limitu, zachowując test Enter.

## Out of scope

TASK-1092/P2-3, nowe audyty Claude, API, dane operatora, migracje, restarty, merge, push, fizyczny Android.

## Acceptance criteria

- [x] Czysty commit limitu przy zajętym kalkulatorze, następnie edycja wzoru i koniec kalkulacji nie wysyłają starego zapytania; jawne Szukaj wysyła nowy wzór i limit.
- [x] Korekta planszy nadal odświeża widoczny snapshot i kalkulator pomimo edycji draftu.
- [x] Browser fixture dla Admina, linku i panelu sprawdza dokładnie jedno żądanie także po zakończeniu; czysty wzór działa przez Enter i rzeczywisty click.
- [x] Regresje, lint, format, typy, build konsumentów, docs i mapa zaliczone; osobny commit i zapis hasha.

## Technical notes / Expected files

Istniejące useBoardSearchSequence w packages/board-search-ui/src/use-board-search-sequence.ts: kolejka repeatPending dostaje przyczynę limit/correction. Efekt anuluje limit przy draftChanged przed sprawdzaniem busy; cleanup chroni opóźnioną mikrokolejkę. Publiczne opcje hooka bez zmian. Istniejące test-interactions/board-search-sequence.test.mjs i test-browser/board-search-sequence.mjs. Wymagania, raport odbioru, CURRENT_STATE i generowana mapa, jeśli zmieniona. Brak nowych modułów aplikacji.

## Test cases / Verification

Najpierw test interakcji RED na poprzednim kodzie. Potem testy board-search-ui (unit i interactions), typecheck board-search-ui/Admin/Reviewer, ESLint i Prettier zmienionych plików. Browser fixture: headless Edge z nowym izolowanym profilem, desktop i emulowany mobilny viewport; wyłącznie skończony serwer fixture. Build Admin i Reviewer. Każda komenda przez subprocess.run z timeout=120 s. Generowanie mapy, code-map:check, docs:check i diff --check.

## Risks / open questions

Nie wolno anulować kolejki korekty tylko dlatego, że draft odbiega od wyników. Fizyczny Android nie jest zastępowany deklaracją PASS z emulacji.

## Outcome

Commit: v1.7.473 (hash dopisuje kolejny commit).

### Changed

- TASK-1093/P2-1: repeatPending rozróżnia przyczynę limit/correction. Efekt usuwa kolejkę limitu przy draftChanged także podczas trwającego kalkulatora. Cleanup unieważnia mikrozadanie poprzedniego efektu. Jawne Szukaj nadal używa bieżącego draftu i zapamiętanego limitu.
- Odświeżenie po korekcie nadal dotyczy widocznego snapshotu niezależnie od edycji draftu; zachowuje wybór i ponownie liczy wygraną od tego samego końca. Osobny test chroni ten przepływ.
- TASK-1093/P2-2: po zakończeniu wyszukiwania browser test ponownie porównuje pełną listę wysłanych żądań z jednym oczekiwanym. Czekanie obejmuje włączony przycisk Szukaj, nie tylko jego widoczność, oraz nagłówek wyników.
- TASK-1093/P2-3: pozostawiono Enter i dodano rzeczywisty click dla czystego wzoru po zmianie limitu. Wszystkie trzy hosty i wariant natychmiastowy Admina mają kontrolę treści, liczby żądań i zachowania wyboru.

### Verification results

Wszystkie komendy miały jawny timeout 120 s (odczyty git 15 s). Testy i buildy uruchomiono w nowych procesach; fixture Edge ma nowy izolowany profil i ponowne uruchomienie procesu.

- RED na kodzie sprzed poprawki: nowy test clean-limit → edit → finish wykazał 2 żądania zamiast 1. Log lokalny artifacts/board-search-sequence-browser/task-1094-red.log. Test ochrony korekty początkowo wymagał poprawienia otwarcia okna w fixture; nie był dowodem błędu produkcyjnego. Po dopasowaniu do istniejącej ścieżki mini planszy oba nowe testy PASS.
- npm run test --workspace @game-predictor/board-search-ui: 108/108 PASS.
- npm run test:interactions --workspace @game-predictor/board-search-ui: 116/116 PASS, w tym istniejące clean refresh, dirty commit, korekty, busy, replay, restore i management.
- node packages/board-search-ui/test-browser/board-search-sequence.mjs: 18/18 kontroli PASS, failures=[], Admin/share/panel, szybkie i opóźnione odpowiedzi, desktop/mobile viewport 390×844 i restore w nowym procesie. Log task-1094-browser.log i verification.json w ignorowanym katalogu artifacts/board-search-sequence-browser/.
- npm run test --workspace @game-predictor/reviewer: 293/293 PASS, w tym publiczne adaptery i proxy.
- ESLint trzech zmienionych plików i Prettier --check: PASS.
- npm run typecheck dla @game-predictor/board-search-ui, @game-predictor/admin i @game-predictor/reviewer: PASS.
- npm run build dla Admina i Reviewera: PASS. Znane ostrzeżenie Next.js o wielu lockfile w zagnieżdżonym worktree; poza zakresem. Pełne logi task-1094-build-admin.log i task-1094-build-reviewer.log.
- scripts/generate_code_map.py uruchomiony; wynik identyczny z wersjonowanym. code-map:check, docs:check i git diff --check: PASS. Kontrole zamknięcia i indeksu sprawdzane ponownie przy commicie.

### Not completed

- TASK-1092/P2-3 (identity resultClient) świadomie odłożone na polecenie operatora; kod tego obszaru bez zmian.
- Nie uruchamiano kolejnego audytu Claude. Historyczny raport TASK-1093 pozostaje bez zmian; niniejsze poprawki nie otrzymały nowego niezależnego werdyktu.
- Bez migracji bazy operatora, restartów, merge, push ani wdrożenia. Brak zmian API/schematu; testów PostgreSQL nie ponawiano. Fizyczny Android nieodebrany; mobilny viewport jest emulacją.

### Documentation updates / Definition of Done

- ADMIN_APP opisuje anulowanie oczekującego limitu i zachowanie odświeżenia po korekcie. Raport odbioru odróżnia nowe trzy poprawione P2 od dawnego odłożonego TASK-1092/P2-3. CURRENT_STATE i task zaktualizowane, zamknięcie przez task-close.
- AC1: odtworzenie RED i zaliczony test pełnego żądania po jawnym Szukaj. AC2: zaliczony test korekty mimo dirty draftu i busy. AC3: zaliczone asercje po zakończeniu oraz czysty Enter/click w realnym Edge. AC4: format/lint/typy/regresje/build/docs/map PASS; commit oraz hash rozliczane przez close_task.py.
- Plan nadrzędny B zachowuje wszystkie dotychczasowe zachowania: badże, restore i izolację scope, kotwicę wygranych, korekty i management, pokryte bieżącymi regresjami. Trwałość sprawdzona w nowym procesie przeglądarki; brak odbioru fizycznego Androida pozostaje jawny. API, domena i schemat bez zmian, zatem bez nowej decyzji architektonicznej.

### Recommended next task

Odbiór operatora i osobno uzgodnione wdrożenie. Migracja 0169, restarty i merge nadal wymagają odrębnych zgód. Dawne TASK-1092/P2-3 pozostaje zadaniem na później.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1094 — Trzy P2 po audycie TASK-1093 | gpt-6.1-sol | high | Mała zmiana kolejki UI z testem kolejności zdarzeń i ochroną korekt. | Bez nowego audytu w tym zleceniu; regresje wykonawcy. |
