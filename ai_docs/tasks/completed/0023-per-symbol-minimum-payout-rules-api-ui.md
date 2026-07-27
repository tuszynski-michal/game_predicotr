---
title: TASK-0023 Per-symbol minimum and payout rules API/UI
status: done
last_updated: 2026-07-27
---

# TASK-0023 — Per-symbol minimum and payout rules API/UI

## Status

`done`

## Goal

Umożliwić administratorowi skonfigurowanie w drafcie wersji reguł minimalnej
długości wygranej każdego zwykłego symbolu oraz wypłaty dla każdej wymaganej
długości.

## Context

TASK-0021 utworzył wersje reguł, a TASK-0022 dodał paylines. Ten pion domyka
edytowalne dane algorytmu payout-v2 przed osobnym workflow publikacji.

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
- D-027 w `ai_docs/process/DECISION_LOG.md`

## Scope

- migracja Alembic tabel `rules_version_symbols` i `payout_rules`,
- wersjonowany próg `minimum_match_length` dla symbolu,
- brak progu i payout rules dla jokera,
- listowanie i aktualizacja konfiguracji symboli draftu,
- listowanie, tworzenie, edycja, archiwizacja i reaktywacja payout rules,
- unikalność `(rules_version_id, symbol_id, match_length)`,
- walidacja zakresu progu, długości i nieujemnych kredytów,
- ochrona wersji innej niż draft oraz zgodności symbolu z grą,
- ochrona zmiany liczby kolumn przed unieważnieniem konfiguracji,
- generowany klient TypeScript,
- modal konfiguracji z domyślnym minimum 3 i dynamicznymi polami wypłat,
- testy domeny, API, migracji, PostgreSQL, klienta i logiki panelu.

## Out of scope

- publikacja i archiwizacja całej wersji reguł,
- końcowa walidacja kompletności wersji,
- precomputing payoutów, dataset i APK,
- zmiana algorytmu payout-v2.

## Acceptance criteria

- [x] zwykły symbol przyjmuje próg `2..columns`, domyślnie 3,
- [x] joker ma próg `null` i nie może otrzymać payout rule,
- [x] payout rule ma długość `minimum_match_length..columns` i nieujemne kredyty,
- [x] duplikat wersja/symbol/długość jest blokowany także po archiwizacji,
- [x] panel pokazuje dokładnie pola długości od wybranego minimum do liczby kolumn,
- [x] panel waliduje komplet oraz ściśle rosnące wartości przed zapisem,
- [x] zmiana minimum archiwizuje zapisane payouty poniżej nowego progu,
- [x] mutacje wersji innej niż draft zwracają stabilny konflikt,
- [x] zmiana wymiarów nie może unieważnić zapisanej konfiguracji,
- [x] OpenAPI, generowany klient, testy i produkcyjny build panelu przechodzą.

## Technical notes

Pierwszy PATCH konfiguracji symbolu wykonuje upsert. Brak rekordu jest w UI
prezentowany z domyślnym minimum `3` dla wersji mającej co najmniej trzy
kolumny. Payout `DELETE` ustawia `is_active = false`; PATCH może reaktywować
rekord, a klucz wersja/symbol/długość pozostaje zarezerwowany.

CRUD draftu może być chwilowo niekompletny. Panel zapisuje kompletny,
ściśle rosnący zestaw jednego symbolu, natomiast transakcyjna walidacja całej
wersji i publikacja należą do TASK-0024.

## Expected files

- `services/api/alembic/versions/0005_rules_version_symbols_payout_rules.py`
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

- Sekwencja kilku wywołań HTTP z UI może pozostawić niekompletny, ale nadal
  poprawny draft po błędzie transportu; ponowny zapis uzupełnia brakujące dane,
  a publikacja nie dopuści niekompletnej macierzy.
- Brak pytań produktowych blokujących zadanie.

## Outcome

Zadanie ukończono 2026-07-27. Powstał pełny pion konfiguracji payout-v2 od
constraints PostgreSQL do dynamicznego formularza jednego symbolu.

### Changed

- dodano migrację `0005_symbol_payouts`, modele, domenę, repozytorium i siedem
  operacji Admin API dla konfiguracji symboli i payout rules,
- dodano walidację minimum, długości, kredytów, jokera, zgodności gry,
  niezmienności draftu oraz wymiarów,
- zablokowano zmianę roli zwykły/joker po użyciu symbolu w wersji reguł,
- wygenerowano klient TypeScript i dodano modal „Payouty” z dynamicznymi polami,
- dodano bezpieczne ponowienie zapisu po częściowym błędzie transportu,
- dodano testy domeny, API, migracji, fizycznego PostgreSQL, klienta i panelu.

### Verification results

- `npm run quality`: sukces; 108 testów Python (`2` jawnie pominięte w zwykłym
  przebiegu), 63 mobile, 34 admin, 23 shared i 5 klienta API,
- `npm run admin:build`: sukces; produkcyjny build Next.js,
- `npm run db:baseline:verify`: sukces; 2 fizyczne testy PostgreSQL oraz
  `upgrade → rollback → upgrade` do head `0005_symbol_payouts`.

### Not completed

- transakcyjna walidacja kompletności całej wersji i publikacja pozostają
  celowo w TASK-0024,
- precomputing, dataset i APK pozostają poza tym zadaniem.

### Documentation updates

- zaktualizowano `ADMIN_APP.md`, `API_CONTRACT.md`, `DATA_MODEL.md`,
  `TECH_STACK.md`, plan M2 oraz `CURRENT_STATE.md`,
- przyjęto D-027 opisującą cykl życia draftu konfiguracji payoutów.

### Recommended next task

- `TASK-0024 — Immutable rules publication workflow`
