---
title: TASK-0046 — Layout normalization and row validation
status: done
last_updated: 2026-07-27
---

# TASK-0046 — Layout normalization and row validation

## Status

`done`

## Goal

Rozszerzyć resumowalny import o bounded walidację wymiarów i alfabetu
opublikowanej wersji reguł oraz o deterministyczną, stałoszeroką sygnaturę
każdego poprawnego wiersza, bez tworzenia datasetu ani utraty błędnych rekordów.

## Context

TASK-0045 utrwala parserowo poprawne i błędne wiersze w surowym stagingu
`layout_import_rows`. Przed raportem integralności i późniejszą publikacją
każdy parserowo poprawny rekord musi zostać sprawdzony względem jednoznacznie
wybranej, opublikowanej wersji reguł tej samej gry.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`

## Scope

- dodać resumowalny job `validate` wskazujący zakończony surowy
  `importJobId` i opublikowaną `rulesVersionId`,
- objąć oba identyfikatory kluczem idempotencji walidacji,
- pobierać dla workera niezmienne wymiary i aktywne kody symboli wybranej wersji,
- walidować liczbę komórek i przynależność każdego kodu do aktywnego alfabetu,
- obliczać stałą szerokość komórki i sygnaturę codec v1 dla poprawnych wierszy,
- utrwalać wynik walidacji oraz bezpieczny kod i opis błędu w stagingu,
- przetwarzać i checkpointować normalizację bounded partiami, idempotentnie po
  restarcie,
- zachować surowe błędy parsera i odseparować staging od `dataset_versions`,
  `layouts` oraz release pipeline,
- zaktualizować OpenAPI, generowany klient, migracje, testy i dokumentację.

## Out of scope

- luki i duplikaty `sequence_number`,
- raport grup duplikatów sygnatur,
- UI importu i raportów,
- utworzenie lub publikacja `dataset_version`,
- payouty, snapshot SQLite i APK,
- OCR oraz import zdjęć.

## Acceptance criteria

- [x] Walidacja wymaga zakończonego surowego joba i opublikowanej wersji reguł
  należących do tej samej gry.
- [x] Ten sam surowy import walidowany względem innej wersji reguł ma inny
  klucz idempotencji.
- [x] Parserowo poprawny wiersz o złej liczbie komórek pozostaje w stagingu ze
  stabilnym kodem i bezpiecznym opisem.
- [x] Parserowo poprawny wiersz z kodem spoza aktywnego alfabetu pozostaje w
  stagingu ze stabilnym kodem i bezpiecznym opisem.
- [x] Poprawny wiersz ma sygnaturę row-major zakodowaną wspólnym codec v1 i
  szerokością wyprowadzoną z całego aktywnego alfabetu wersji reguł.
- [x] Błąd jednego wiersza nie usuwa ani nie blokuje walidacji pozostałych.
- [x] Normalizacja działa bounded partiami i retry po checkpointcie nie tworzy
  duplikatów ani rozbieżnego wyniku.
- [x] Surowy i znormalizowany staging nie jest widoczny dla wydania mobilnego.
- [x] Migracja przechodzi upgrade/downgrade, a testy jednostkowe i fizyczne
  PostgreSQL chronią constraints oraz idempotencję.

## Technical notes

- Wymiary oraz alfabet są własnością wybranej, opublikowanej wersji reguł.
  Osobny job walidacji zachowuje niezmienność surowego importu, pozwala
  bezpiecznie użyć innej wersji reguł i utrzymuje jedno znaczenie liczników
  postępu przez cały lifecycle joba.
- Wynik normalizacji pozostaje w osobnym stagingu walidacji. `layouts` mają unikalny
  `sequence_number`, dlatego nie mogą przyjąć danych przed raportem duplikatów
  z TASK-0047.
- Kody błędów walidacji wiersza muszą być stabilne i niezależne od tekstu
  wyjątku bazy lub biblioteki.
- Checkpoint joba walidacji używa fizycznego `line_number` surowego stagingu,
  aby awaria po upsercie partii mogła bezpiecznie powtórzyć tę samą partię.

## Expected files

- `services/api/alembic/versions/0012_layout_import_normalization.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/application/layout_imports.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/api/src/game_predictor_api/storage/job_repository.py`
- `services/worker/src/game_predictor_worker/imports/`
- `services/api/tests/`
- `services/worker/tests/`
- `packages/api-client/`
- dokumenty wymienione w `Relevant docs`

## Verification

```powershell
npm run api:openapi:generate
npm run api:client:generate
npm run quality
npm run api:test:integration
```

## Risks / open questions

- Dotychczasowy generyczny payload `validate` dotyczył datasetu. TASK-0046
  rozszerza go o jawny wariant `validationKind = layout_import`, nie zmieniając
  istniejącego wariantu datasetowego.
- Fizyczne testy G3 na Pixelu i Samsungu pozostają odroczone na podstawie D-041
  i nie są zaliczane przez to zadanie.

## Outcome

Zadanie ukończono. G4.2 jest zaliczona, a M4 może przejść do raportu
integralności TASK-0047.

### Changed

- Dodano migrację `0012_layout_import_normalization`, model i constraints
  znormalizowanego stagingu.
- Rozszerzono `validate` o wariant `layout_import` z walidacją zakończonego
  importu, opublikowanych reguł i zgodności gry.
- Dodano czystą normalizację wymiarów, alfabetu i signature codec v1 oraz
  stabilne błędy `import_cell_count_mismatch` i
  `import_symbol_not_in_rules`.
- Dodano bounded handler `worker-v4`, idempotentny upsert, checkpoint i retry.
- Zregenerowano OpenAPI i klient TypeScript; generator formatuje także
  tymczasowe, ignorowane przez Git katalogi przed kontrolą driftu.

### Verification results

- `43 passed` w celowanych testach API/workera/migracji/OpenAPI.
- `329 passed, 11 skipped` w pełnych standardowych testach API i workera; 10
  skipów wymagało fizycznego PostgreSQL, jeden uprawnień symlinka Windows.
- `10 passed` dla całego izolowanego zestawu integracji PostgreSQL.
- Ruff: wszystkie zmienione i pełne moduły przeszły.
- mypy: `Success` dla 104 modułów źródłowych i skryptów.
- OpenAPI oraz generowany klient są aktualne; Prettier przechodzi dla generatora
  i klienta.
- TypeScript typecheck panelu i klienta przeszedł; klient ma `11 passed`.
- `git diff --check` przeszedł.

### Not completed

- Nie wykonywano UI, raportu integralności, publikacji datasetu, Android builda
  ani testów urządzeniowych — należą do kolejnych zadań.
- Formalne G3 nadal czeka na dowody Pixel/Samsung zgodnie z D-041.

### Documentation updates

- Zaktualizowano wymagania importu/admina, architekturę systemu, model danych,
  API, tech stack, strategię testów, plan M4 i `CURRENT_STATE.md`.
- Dodano zaakceptowaną decyzję D-045.

### Recommended next task

- `TASK-0047 — Import integrity and duplicate reports`.
