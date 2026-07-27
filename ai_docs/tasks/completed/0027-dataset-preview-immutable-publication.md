---
title: Dataset preview and immutable publication
status: done
last_updated: 2026-07-27
---

# TASK-0027 — Dataset preview and immutable publication

## Status

`done`

## Goal

Udostępnić deterministyczny podgląd layoutów oraz atomowo opublikować poprawny
dataset bez możliwości późniejszej zmiany jego danych.

## Context

TASK-0025 utworzył stagingowy mock 1000 layoutów, a TASK-0026 dodał wspólny
raport integralności. Ostatni pion M2.4 ma pozwolić administratorowi przejrzeć
plansze, świadomie opublikować gotową wersję oraz zarchiwizować ją bez utraty
danych audytowych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- stronicowany po `sequence_number` endpoint listy layoutów,
- podgląd layoutu jako siatki zgodnej z wymiarami datasetu,
- publikacja stagingu z ponowną walidacją pod blokadą rekordu,
- dopuszczenie ostrzeżeń o duplikatach sygnatur i odrzucenie każdej blokady,
- ustawienie serwerowego `published_at` w tej samej transakcji,
- idempotentna archiwizacja opublikowanej wersji bez usuwania layoutów,
- modal publikacji z raportem, jawnym potwierdzeniem i blokadą podwójnego zapisu,
- kontrakt OpenAPI, generowany klient, testy domeny, API, panelu i PostgreSQL.

## Out of scope

- edycja layoutów stagingowych,
- fizyczne usuwanie datasetów lub layoutów,
- validation job dla importów i docelowej skali,
- budowanie snapshotu lub APK,
- zintegrowany odbiór całego M2 z TASK-0028.

## Acceptance criteria

- [x] Podgląd zwraca stabilne strony w kolejności `sequence_number`, bez
      zależności od technicznego UUID.
- [x] Panel przedstawia wybrany layout jako siatkę row-major z nazwami lub
      kodami symboli.
- [x] Publikacja blokuje rekord datasetu, ponownie uruchamia walidator z
      TASK-0026 i jest atomowa.
- [x] Poprawny dataset z ostrzeżeniami o duplikatach przechodzi
      `staging → published` i otrzymuje serwerowy timestamp.
- [x] Dataset z dowolnym blockerem pozostaje stagingiem bez `published_at`.
- [x] Ponowna publikacja wersji nie-stagingowej jest odrzucana stabilnym kodem.
- [x] Archiwizacja obsługuje `published → archived`, jest idempotentna i
      zachowuje `published_at` oraz wszystkie layouty.
- [x] Panel wymaga jawnego potwierdzenia i blokuje podwójny submit publikacji
      oraz archiwizacji.
- [x] Formatowanie, lint, typy, testy, drift OpenAPI, build panelu i fizyczna
      weryfikacja PostgreSQL przechodzą.

## Technical notes

- Kursor podglądu jest ostatnim `sequence_number`; limit jest bounded.
- Publikacja i przyszłe mutacje datasetu muszą synchronizować się przez blokadę
  rekordu `dataset_versions`.
- Wersja stagingowa nie ma publicznego endpointu edycji. Archiwizacja dotyczy
  wyłącznie opublikowanej wersji, zgodnie z lifecycle wersji reguł.
- Wiele opublikowanych datasetów jednej gry może współistnieć historycznie.
- Zmiana schematu bazy nie jest potrzebna: status i `published_at` istnieją od
  migracji `0006_dataset_staging`.

## Expected files

- `services/api/src/game_predictor_api/domain/datasets.py`
- `services/api/src/game_predictor_api/application/datasets.py`
- `services/api/src/game_predictor_api/storage/dataset_repository.py`
- `services/api/src/game_predictor_api/schemas/datasets.py`
- `services/api/src/game_predictor_api/api/datasets.py`
- `apps/admin/src/features/datasets/*`
- `apps/admin/src/app/*`
- `packages/admin-api-client/*`
- `services/api/tests/*`
- `apps/admin/tests/*`
- `ai_docs/*`

## Verification

```powershell
npm run api:openapi:generate
npm run api:client:generate
npm run quality
npm run admin:build
npm run db:baseline:verify
```

## Risks / open questions

- Brak pytań blokujących. Docelowe datasety większe niż bounded `mock-v1`
  pozostają na ścieżce workera.

## Outcome

Zadanie ukończone 2026-07-27. Bramka G2.4 została zaliczona.

### Changed

- Dodano keyset pagination layoutów po `sequence_number`, bounded limit i
  odpowiedź zawierającą wymiary planszy oraz następny kursor.
- Publikacja blokuje wersję datasetu, ponownie używa walidatora TASK-0026 i
  atomowo ustawia `published/published_at`; blokery nie zmieniają stagingu.
- Archiwizacja blokuje wyłącznie rekord wersji, jest idempotentna i zachowuje
  timestamp oraz layouty.
- OpenAPI i generowany klient obsługują podgląd, publikację i archiwizację.
- Panel ma responsywny modal planszy row-major, nawigację stron, modal raportu
  z potwierdzeniem publikacji oraz potwierdzenie archiwizacji.

### Verification results

- `npm run quality`: 129 testów Python przeszło, 2 integracyjne PostgreSQL
  zostały jawnie pominięte w standardowym przebiegu; 63 mobile, 44 panelu,
  23 wspólnej domeny i 7 klienta API przeszło. Format, lint, typy, drift
  OpenAPI, snapshot i fixture są poprawne.
- `npm run admin:build`: produkcyjny build Next.js przeszedł.
- końcowe `npm run format:check`: przeszedł po buildzie.
- `npm run db:baseline:verify`: 2 fizyczne testy PostgreSQL przeszły, w tym
  publikacja poprawnego mocka, odrzucenie uszkodzonego stagingu, stabilne strony
  oraz archiwizacja bez utraty 1000 layoutów.

### Not completed

- Nie rozpoczęto TASK-0028 ani zintegrowanego odbioru całego M2.
- Nie dodano validation job dla importów i dużej skali ani pipeline'u
  snapshot/APK.

### Documentation updates

- Dodano D-031.
- Zaktualizowano `ADMIN_APP.md`, `DATA_MODEL.md`, `API_CONTRACT.md`,
  `SYSTEM_ARCHITECTURE.md`, plan M2 i `CURRENT_STATE.md`.

### Recommended next task

- po kolejnym poleceniu właściciela:
  `TASK-0028 — Admin configuration vertical slice acceptance`
