---
title: TASK-0022 Payline grid editor and duplicate validation
status: done
last_updated: 2026-07-27
---

# TASK-0022 — Payline grid editor and duplicate validation

## Status

`done`

## Goal

Umożliwić administratorowi zarządzanie paylines draftu wersji reguł przez
modalną siatkę gry, z dokładnie jednym wyborem w każdej kolumnie i trwałą
ochroną przed zduplikowanym `row_path`.

## Context

TASK-0021 utworzył wersjonowany rekord wymiarów i kosztu spinu. Paylines są
pierwszym dzieckiem wersji reguł oraz podstawą dla konfiguracji payoutów i
publikacji w następnych zadaniach.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-026 w `ai_docs/process/DECISION_LOG.md`

## Scope

- migracja Alembic tabeli `paylines` z `smallint[]`, constraints i unikalnością,
- domena, repozytorium oraz Admin API do listowania, tworzenia, pobierania,
  edycji i archiwizacji paylines,
- stabilny kod payline w obrębie wersji reguł,
- walidacja długości i zakresu `row_path` według wymiarów wersji,
- blokada duplikatu `row_path` z identyfikatorem istniejącego wzorca,
- ochrona opublikowanej lub zarchiwizowanej wersji przed mutacją,
- ochrona zmiany wymiarów przed unieważnieniem istniejących paylines,
- generowany klient TypeScript,
- modal CSS Grid z prezentacją wierszy 1-based i kontraktem API 0-based,
- tabela istniejących wzorców, edycja, archiwizacja i ponowna aktywacja,
- testy domeny, API, migracji, PostgreSQL, klienta i logiki panelu.

## Out of scope

- `rules_version_symbols` i `minimum_match_length`,
- payout rules,
- publikacja wersji reguł,
- podgląd payoutu na linii,
- generowanie datasetu lub APK.

## Acceptance criteria

- [x] `row_path` ma dokładnie `columns` elementów i każdy spełnia
  `0 <= row < rows`,
- [x] identyczny `row_path` nie może wystąpić drugi raz w tej samej wersji,
- [x] UI pozwala wybrać najwyżej jedną komórkę w kolumnie i zapisać dopiero
  pełną linię,
- [x] UI pokazuje numery wierszy 1-based, a API i baza zapisują 0-based,
- [x] tabela pokazuje po jednym wzorze w wierszu w deterministycznej kolejności,
- [x] kod payline jest stabilny, a pola draftu można edytować i archiwizować,
- [x] mutacja payline wersji innej niż draft zwraca stabilny konflikt,
- [x] zmiana wymiarów nie może pozostawić niepoprawnego istniejącego wzorca,
- [x] OpenAPI, generowany klient, testy i produkcyjny build panelu przechodzą.

## Technical notes

`DELETE` jest archiwizacją przez `is_active = false`; rekord i jego `row_path`
pozostają zarezerwowane. PATCH pozwala ponownie aktywować rekord. UI używa
natywnego `<dialog>` i CSS Grid, bez nowej zależności. Zmiana liczby kolumn jest
blokowana, jeżeli istnieje payline; zmiana liczby rzędów jest dozwolona tylko,
gdy wszystkie zapisane indeksy nadal mieszczą się w nowym zakresie.

## Expected files

- `services/api/alembic/versions/0004_paylines.py`
- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `apps/admin/src/features/rules/`
- `apps/admin/src/app/globals.css`
- `ai_docs/architecture/{API_CONTRACT,DATA_MODEL,TECH_STACK}.md`
- `ai_docs/process/{CURRENT_STATE,DECISION_LOG}.md`

## Verification

```powershell
npm run openapi:generate
npm run quality
npm run admin:build
npm run db:baseline:verify
```

## Risks / open questions

- Constraint bazy jest ostatnią linią obrony, a aplikacja wykrywa duplikat
  wcześniej, aby zwrócić `existingPaylineId`.
- Brak pytań produktowych blokujących zadanie.

## Outcome

Zadanie ukończono 2026-07-27. Powstał pełny pion payline od migracji PostgreSQL
do modalnego edytora w panelu, bez rozszerzania zakresu o payout rules.

### Changed

- dodano migrację `0004_paylines`, model SQLAlchemy, domenę, repozytorium,
  use cases i pięć operacji Admin API,
- dodano walidację `row_path`, stabilnego kodu, kolejności, unikalności i
  zgodności ze zmienianymi wymiarami,
- wygenerowano klient TypeScript i wystawiono typowane operacje payline,
- dodano tabelę wzorców, modal CSS Grid, edycję, archiwizację i reaktywację,
- dodano testy domeny, API, migracji, fizycznego PostgreSQL, klienta i logiki UI.

### Verification results

- `npm run quality`: sukces; 102 testy Python (`2` jawnie pominięte w zwykłym
  przebiegu), 63 mobile, 29 admin, 23 shared i 4 klienta API,
- `npm run admin:build`: sukces; produkcyjny build Next.js,
- `npm run db:baseline:verify`: sukces; 2 fizyczne testy PostgreSQL oraz
  `upgrade → rollback → upgrade` do head `0004`.

### Not completed

- konfiguracja minimum dopasowania symbolu i payout rules pozostaje celowo w
  TASK-0023,
- publikacja niezmiennej wersji reguł pozostaje celowo w TASK-0024.

### Documentation updates

- zaktualizowano `API_CONTRACT.md`, `DATA_MODEL.md`, `TECH_STACK.md`,
  `DECISION_LOG.md`, plan M2 oraz `CURRENT_STATE.md`,
- przyjęto D-026 opisującą stabilną tożsamość i cykl życia payline.

### Recommended next task

- `TASK-0023 — Per-symbol minimum and payout rules API/UI`
