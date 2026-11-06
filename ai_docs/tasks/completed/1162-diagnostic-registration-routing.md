---
title: TASK-1162 — Routing zapisu rejestracji diagnostyk
status: done
last_updated: 2026-11-07
---

# TASK-1162 — Routing zapisu rejestracji diagnostyk

## Status

`done`

## Goal

CLI rejestruje zatwierdzony manifest przez jawne wiązanie WRITE i zachowuje retry oraz blokady magazynu gry.

## Context

W zatwierdzonym wdrożeniu T6 rzeczywisty execute zakończył się GAME_STORAGE_SCOPE_REQUIRED i rollbackiem bez zapisów. Zwykły Session nie używa automatycznie kontekstu game_storage_scope. Root prowadzi wdrożenie; ten task naprawia wyłącznie CLI.

## Dependencies / entry conditions

WT i main 119f4716, v1.7.568; czysty WT. Zgoda użytkownika na naprawę w ramach wdrożenia i dodatkowe 1–3 h przekazana przez root. Bez blokujących pytań. Założenie: pozostają istniejące manifesty i klucze idempotencji; brak zmiany kontraktu SQL/API.

## Recommended execution

gpt-6.1-sol / high; mała naprawa istniejącego routingu. Niezależny claude-opus-5-5 / high uruchamia root. Eskalacja przy ujawnionej zmianie kontraktu lub braku ochrony zapisu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/VISION_LAB.md` — Reproducible input diagnostics.
- `ai_docs/architecture/VISION_LAB.md` — Completeness and calibration.
- `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md` — Diagnostyki przed nowym B/REG.
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope / mały plan naprawy

1. Odtworzyć błąd rzeczywistym CLI w świeżym subprocessie na disposable PG0181 i applicationRole.
2. W istniejącym Session.begin ustawić istniejące timeouty, potem GameStorageRouter.bind(..., WRITE) przed pierwszym SQL domenowym/capability. Bez raw set_config i owner bypass.
3. Ten sam test sprawdza trwały zapis, exact replay w kolejnym procesie, maintenance i exclusive game-write fence bez dodatkowych zapisów.
4. Celowany test, Ruff/format, typy CLI, mapa i docs; mały zamrożony pakiet do audytu root. Stage/commit dopiero po PASS.

## Out of scope

Baza i manifest operatora, usługi, trening/inferencja, API/UI, migracje i nowe funkcje. Nie czytać prywatnego manifestu wdrożenia. Nie powtarzać buildów ani suites T0–T6.

## Acceptance criteria

- [x] AC1: rzeczywisty CLI z get_settings/create_database_engine działa jako applicationRole na PG0181 w świeżym procesie.
- [x] AC2: exact replay zachowuje ledger/receipt bez duplikatów.
- [x] AC3: maintenance i game-write fence blokują CLI atomowo; brak bypass.
- [x] AC4: test/lint/format/types/docs/map PASS, niezależny audyt root bez otwartych P0/P1, task-close po odbiorze root.

## Expected files

- `scripts/register_grid_diagnostics.py` — main.
- Nowy `services/api/tests/integration/test_diagnostic_registration_cli_postgres.py`.
- Ten task, CURRENT_STATE, raport quality i wygenerowana mapa.

## Verification

WT `D:/game_predicotr/worktrees/full-board-detection`; każde polecenie przez subprocess z timeout120s. Test: `.venv/Scripts/python.exe -m pytest services/api/tests/integration/test_diagnostic_registration_cli_postgres.py -q`, opt-in GAME_PREDICTOR_RUN_POSTGRES_TESTS=1, własny katalog journal. Wyniki dopiero po wykonaniu.

## Risks / open questions

Blokada WRITE pochodzi z istniejącego routera; wyjątek oznacza rollback całej transakcji. Brak zmiany schematu i formatu manifestu pozwala root ponowić te same requesty. Ograniczenia testu/CLI jawnie przyjęte jako P2 poniżej.

## Outcome

Commit: v1.7.569 (hash dopisuje kolejny commit).

### Changed

- Jawny bind WRITE wewnątrz istniejącej transakcji CLI po ustawieniu timeoutów, przed SQL domenowym/capability; bez zmiany manifestu, schematu lub idempotencji.
- Nowy test rzeczywistego CLI na provisioned applicationRole, synthetic strict T1 record, nowe procesy oraz odczyty trwałego ledger.

### Verification results

- Celowany PG/CLI po kontroli kolejności timeoutów przez root: 1 PASS / 29.75s (wrapper32.39s), `artifacts/task1162/green-budget-final.txt`; bez PGOPTIONS, własny lock_timeout3s obejmuje router.
- Maintenance i exclusive write fence: brak zapisów. Następnie jeden wpis ledger i identyczne id/payload/digest/actor po replay; context v3 diagnosticExposed=true.
- Ruff i format dwóch plików PASS; scoped mypy CLI PASS (follow-imports=skip).
- Mapa/check, docs i whitespace PASS; cleanup pięciu journal potwierdzony READ ONLY: DB0/roles0/sessions0. Szczegóły: `ai_docs/quality/TASK-1162_VERIFICATION.md`.
- Początkowe próby fixture zatrzymały się na prywatnym ledger lub brakującym neural_grid_v3; nie były dowodem regresji produktu. Odtworzenie operatora GAME_STORAGE_SCOPE_REQUIRED i rollback0writes dostarczył root.
- Rzeczywisty audyt root: [Opus5.5/high R1](../../quality/TASK-1162_AUDIT_claude-opus-5-5.md) PASS, brak P0/P1. Audyt statyczny, bez uruchamiania testów i danych operatora. Root zaakceptował wszystkie P2 oraz task-close, bez nowych testów, zmian produktu i kolejnej rundy.

### Przyjęte P2

1. Replay porównuje ledger, nie zwracany receipt. AC2 ma dowód braku duplikatów; zgodności receipt nie deklarujemy. Zmiana wyjścia CLI poza naprawą routingu.
2. Jeden rekord nie odtwarza rollbacku w środku partii. Dowiedziono odmowy maintenance/fence bez zapisów, a istniejąca pojedyncza transakcja pozostała bez zmian.
3. Istniejące timeouty są per statement, nie dla całej partii do250 requestów. Root podał operatorski outer110s i wykonanie32 bindings w4s; nie dowodzi to budżetu całych250. Nowy limit transakcji wymaga osobnego zakresu.
4. Pozostaje wcześniejszy surowy traceback, bez nowego stabilnego kodu błędu CLI. Nie zmieniamy obsługi błędów przy naprawie wiązania.
5. Mypy follow-imports=skip daje wyłącznie scoped wynik skryptu. Nie deklarujemy pełnego typowania zależności; jego rozszerzenie poza minimalną naprawą.

### Not completed

- Nie wykonano operator DB/manifestu, rejestracji, usług ani modeli. Nie powtarzano buildów/T0–T6.
- Nie wykonano testów receipt, mid-batch rollback, limitu całej transakcji ani pełnego mypy zależności; zaakceptowane P2.

### Documentation updates

- Wskaźnik CURRENT_STATE, instrukcja writer w guide, mapa i raport weryfikacji.

### Recommended next task

- Root osobno prowadzi integrację i zatwierdzone wdrożenie oraz oficjalny CLI replay tych samych requestów w świeżym procesie po FF.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1162 | gpt-6.1-sol | high | Ograniczona naprawa CLI z rzeczywistym PG i ochroną transakcji. | claude-opus-5-5 / high, uruchamia root |
