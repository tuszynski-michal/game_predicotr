---
title: TASK-0023 Per-symbol minimum and payout rules API/UI
status: in_progress
last_updated: 2026-07-27
---

# TASK-0023 — Per-symbol minimum and payout rules API/UI

## Status

`in_progress`

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

- [ ] zwykły symbol przyjmuje próg `2..columns`, domyślnie 3,
- [ ] joker ma próg `null` i nie może otrzymać payout rule,
- [ ] payout rule ma długość `minimum_match_length..columns` i nieujemne kredyty,
- [ ] duplikat wersja/symbol/długość jest blokowany także po archiwizacji,
- [ ] panel pokazuje dokładnie pola długości od wybranego minimum do liczby kolumn,
- [ ] panel waliduje komplet oraz ściśle rosnące wartości przed zapisem,
- [ ] zmiana minimum archiwizuje zapisane payouty poniżej nowego progu,
- [ ] mutacje wersji innej niż draft zwracają stabilny konflikt,
- [ ] zmiana wymiarów nie może unieważnić zapisanej konfiguracji,
- [ ] OpenAPI, generowany klient, testy i produkcyjny build panelu przechodzą.

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

Do uzupełnienia po implementacji.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- `TASK-0024 — Immutable rules publication workflow`
