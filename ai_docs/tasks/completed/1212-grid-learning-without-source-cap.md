---
title: Uczenie korekt bez arbitralnego limitu zdjęć
status: done
---

# TASK-1212 - Uczenie korekt bez arbitralnego limitu zdjęć

## Status

`done`

## Goal

Usunąć blokadę 20 000 zdjęć całych importów, zachowując ochronę podziału i istniejące budżety pracy.

## Context

Około 200 korekt operatora może obejmować importy przekraczające 20 000 źródeł. Operator jawnie zlecił zmianę limitu, w tym jego zniesienie. Przyjęte rozwiązanie: brak stałego limitu liczby źródeł; istniejące budżety algorytmu, czasu SQL i treningu pozostają. Nie obiecujemy obsługi miliona zdjęć w pamięci ani nie zwiększamy budżetów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-610--limit-populacji-uczenia-siatek-20-000-źródeł`

## Scope

Usunięcie limitu w odczycie populacji, obu solverach, polach validationAssignments i funkcjach SQL przez nową migrację. Regresje ochron, budżetu pracy i kontraktu HTTP; regeneracja OpenAPI/klienta i mapy kodu. Dotychczasowa migracja 0188 pozostaje odtwarzalna.

## Out of scope

Trening, migracja bazy operatora, restarty, merge/push, benchmarki i przebudowa algorytmu podziału.

## Acceptance criteria

- [x] Brak arbitralnego progu 20 000 w nowym uczeniu, obu solverach i validationAssignments.
- [x] Migracja zmienia wyłącznie predykaty liczności sześciu funkcji; downgrade odmawia przy zapisanych kohortach >20 000. Test jednostkowy i test na jednorazowym PostgreSQL PASS.
- [x] Całe importy, kolejność, kopie, role i bufory pozostają chronione; budżety pracy i czasu nie są podnoszone.
- [x] Testy odtwarzają zakres przekraczający stary próg bez dużego treningu; HTTP przyjmuje większe przypisania.
- [x] Weryfikacja i ograniczenia wdrożenia są zapisane w Outcome.

## Expected files

- `services/api/src/game_predictor_api/{domain,storage}/grid_correction_split.py`, domain/grid_correction_incremental_split.py: usunięcie progu populacji.
- `services/api/src/game_predictor_api/schemas/{grid_correction_learning,grid_training_cohorts}.py`: validationAssignments.
- Nowe: storage/source_recording_unlimited_sources.py i migracja 0189.
- Testy źródeł, migracji i HTTP; OpenAPI, dokumentacja i mapa kodu.

## Verification

Scoped pytest, ruff i mypy; generowanie i sprawdzenie OpenAPI, klienta i mapy; docs:check. Komendy skończone z timeoutem 120 s. PostgreSQL tylko na jawnie wydzielonej bazie testowej, jeśli dostępna; bez migracji danych operatora.

## Risks / open questions

Pełna populacja nadal trafia do pamięci; bardzo duży zakres może przekroczyć istniejący budżet czasu/pracy. Brak zgody na benchmark. Sandbox Codexa miał read-only `.git`; commit i zamknięcie wykonał Claude Code.

## Outcome

Commit: v1.7.639 / `c73fda9dbce1b95eb8d32037751c9b82aeb5e32b`.

Implementacja: Codex (bez zapisu `.git`). Weryfikację PostgreSQL, zamknięcie i
commit na `main` wykonał Claude Code 2026-11-15. Commit obejmuje wyłącznie pliki
i hunki tego taska; zastane zmiany `AGENTS.md`, `.claude/launch.json`, zmiany
samych końców linii w `packages/admin-api-client/src/generated/*.ts` i worktree
pozostały poza commitem.

### Changed

- Usunięto stałą i progi liczności populacji w Pythonie oraz ograniczenia map przypisań walidacji. Zapytanie zachowuje wszystkie zdjęcia, w tym bez etykiet.
- Migracja 0189 usuwa wyłącznie predykaty liczności w sześciu funkcjach; wcześniej sprawdza wszystkie definicje. Nie zmienia ról, buforów, uprawnień, budżetów ani limitu iteracji domknięcia. Downgrade odmawia kohortom >20 000.
- OpenAPI i klient zregenerowane; typy map i istniejące wrappery pozostają identyczne. Nowy test przechodzi pełną ścieżkę żądania ASGI bez socketów i przyjmuje 20 001 przypisań.

### Verification results

- Scoped pytest: 40 PASS (nowe regresje, historyczna migracja 0188, oba solvery).
- Dodatkowe regresje screen policy i learning material: 24 PASS.
- Ruff check i format --check: PASS, 10 plików. Mypy --follow-imports=silent: PASS, 7 plików backendu/migracji.
- OpenAPI export --check, check:generated i typecheck klienta: PASS. Mapa kodu zregenerowana; docs:check PASS.
- Szerszy przebieg adapter/screen/material/cohort przerwany po braku postępu; brak pełnego wyniku. Pierwszy błąd adaptera (`KeyError: nodes` w fixture Reader) odtworzono również po załadowaniu wersji modułu z HEAD, bez zmian plików; poza zakresem.
- Sandbox Codexa: test PostgreSQL odrzucony (Permission denied 10013), `git switch -c` i `git add` odmówione (lock). Oba blokery usunął przebieg Claude Code poza sandboxem.
- Zamknięcie (Claude Code, 2026-11-15): `test_grid_learning_source_limit_postgres.py` z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` na jednorazowych bazach `*_test`: 2/2 PASS (0189: tylko predykaty liczności, właściciel/ACL/ustawienia bez zmian, odmowa downgrade; historyczna 0188 upgrade/downgrade). Razem z `test_grid_learning_no_source_cap.py` i `test_grid_learning_source_limit.py`: 14/14 PASS.
- Odczyt tylko do odczytu `alembic_version` bazy deweloperskiej: `0189_grid_learning_no_source_cap`, więc migrację wdrożono poza agentem (agent nie uruchamiał `db:migrate`).
- Pierwszy test HTTP przerwano z powodu ograniczeń pętli/socketów środowiska; zastąpiono transportem ASGI w procesie z synchronicznym wykonaniem endpointu. Produkcyjny kontrakt i middleware nie zostały zmienione.

### Not completed

- Test na rzeczywistym zakresie operatora, restarty usług i trening nie zostały uruchomione przez agenta. Push i merge wymagają osobnej zgody.
- Bardzo duże zbiory nadal zajmują pamięć i mogą przekroczyć istniejący limit pracy/czasu. Nie wykonano benchmarku ani nie obiecano obsługi miliona zdjęć.
- Kolizja numeracji z niescaloną gałęzią `claude/grid-training-baseline-floor` / `claude/partial-slot-binding`: ma ona własną `0189_grid_gate_improvement` (też `down_revision=0188`), decyzje D-611–D-614 i wersje v1.7.636–v1.7.642. Ponieważ baza deweloperska ma już 0189 z tego taska, przy scaleniu tamtej gałęzi jej migrację trzeba przenumerować na 0190 (`down_revision=0189_grid_learning_no_source_cap`), a decyzje na D-612–D-615. Funkcje SQL obu migracji są rozłączne.

### Documentation updates

D-611, wymagania i architektura Vision Lab, okno stanu i mapa kodu. Historyczne 0188/testy zachowane.

### Recommended next task

Migracja 0189 jest już w bazie deweloperskiej. Operator restartuje API i workery we własnych terminalach, jeśli jeszcze działają na starym kodzie, i odświeża gotowość uczenia. Bez automatycznego treningu/aktywacji. Przed scaleniem `claude/partial-slot-binding` przenumerować jej migrację i decyzje (patrz „Not completed”).

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1212 | gpt-6.1-sol | high | Ograniczona zmiana predykatów z regresjami istniejących ochron; bez delegowania. | Nie |
