---
title: TASK-0049 Transactional dataset publication from staging
status: done
last_updated: 2026-07-28
---

# TASK-0049 — Transactional dataset publication from staging

## Status

`done`

## Goal

Atomowo utworzyć niezmienny, opublikowany dataset z poprawnego
znormalizowanego stagingu importu, zachowując provenance walidacji i
idempotencję ponowienia.

## Context

TASK-0046–0048 dostarczyły znormalizowany staging, dokładny raport integralności
i panel administracyjny. Dane nie są jednak jeszcze widoczne dla istniejącego
pipeline’u payoutów, snapshotu i APK. Publikacja musi ponownie sprawdzić
integralność pod blokadą transakcyjną i skopiować rekordy setowo, bez
materializowania docelowego datasetu w pamięci API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-031 i D-042–D-047 w `ai_docs/process/DECISION_LOG.md`

## Scope

- endpoint publikacji dla zakończonej walidacji `layout_import`,
- ponowne obliczenie tego samego raportu integralności pod blokadą,
- transakcyjne utworzenie `dataset_versions` i setowe `INSERT ... SELECT` do
  `layouts`,
- serwerowa numeracja wersji per gra i niezmienny status `published`,
- provenance przez `source_job_id = validation_job_id`,
- idempotentny retry zwracający tę samą wersję datasetu,
- unikalność niepustego `source_job_id` chroniona migracją,
- akcja publikacji w panelu ręcznego importu,
- OpenAPI, generowany klient, testy i dokumentacja.

## Out of scope

- benchmark 500 000 rekordów i pełny odbiór release — TASK-0050,
- precomputing payoutów, snapshot i Android build,
- usuwanie stagingu po publikacji,
- OCR, zdjęcia i ręczna edycja SQL,
- zmiana istniejącego workflow publikacji bounded `mock-v1`.

## Acceptance criteria

- [x] publikacja jest dostępna wyłącznie dla ukończonej walidacji
  `layout_import` z raportem `readyForPublication = true`,
- [x] blokada, błąd lub pusty/odrzucony staging nie tworzy częściowego datasetu,
- [x] dataset i wszystkie layouty powstają w jednej transakcji, w ciągłej
  kolejności `1..layout_count`,
- [x] kopiowanie używa bounded pamięci procesu i setowej operacji PostgreSQL,
- [x] nowa wersja jest `published`, ma serwerowy `publishedAt`, wymiary i codec
  walidowanej wersji reguł oraz `sourceJobId` walidacji,
- [x] retry tej samej walidacji zwraca ten sam dataset bez drugiego numeru lub
  drugiego zestawu layoutów,
- [x] równoległe publikacje nie mogą przydzielić tego samego numeru wersji gry,
- [x] panel blokuje podwójny submit, pokazuje błąd/sukces i nie pozwala
  publikować raportu z blokadami,
- [x] OpenAPI i klient TypeScript są aktualne,
- [x] test PostgreSQL potwierdza sukces, idempotencję, provenance, ostrzeżenie
  duplikatu sygnatury oraz rollback przy blokadzie.

## Technical notes

- Znormalizowany staging jest warstwą `staging`; rekord `dataset_versions`
  może zostać utworzony jako `staging` i przełączony na `published` w tej samej
  niewidocznej na zewnątrz transakcji.
- `generator_version = layout-import-v1`, a wymagane historycznym schematem
  `generation_seed = 0`; źródło importu jest jednoznaczne przez
  `source_job_id`.
- Publikacja i odrzucenie stagingu blokują ten sam job importu oraz jego
  walidacje, aby wykluczyć wyścig usunięcie–publikacja.
- Staging pozostaje po publikacji jako audyt i nie może już zostać odrzucony.

## Expected files

- `services/api/alembic/versions/0013_layout_import_publication.py`
- `services/api/src/game_predictor_api/domain/layout_import_reports.py`
- `services/api/src/game_predictor_api/application/layout_import_reports.py`
- `services/api/src/game_predictor_api/storage/layout_import_report_repository.py`
- `services/api/src/game_predictor_api/api/layout_import_reports.py`
- `services/api/src/game_predictor_api/schemas/layout_import_reports.py`
- `services/api/tests/test_layout_import_reports.py`
- `services/api/tests/integration/test_layout_import_report_repository.py`
- `apps/admin/src/features/imports/`
- `packages/admin-api-client/`
- wskazane dokumenty źródłowe.

## Verification

```powershell
npm run python:format:check
npm run python:lint
npm run python:typecheck
npm run python:test
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration --basetemp .tooling/pytest-task0049
npm run api:contract:check
npm run api:client:check
npm run api:client:test
npm run admin:test
npm run admin:typecheck
npm run admin:lint
npm run admin:build
```

## Risks / open questions

- Długotrwały odbiór na reprezentatywnych 500 000 rekordach należy do
  TASK-0050; TASK-0049 dowodzi setowego, niematerializującego kopiowania i
  integralności transakcji na fixture integracyjnym.

## Outcome

### Changed

- Dodano migrację `0013_layout_import_publication` z częściowym indeksem
  unikalnym dla niepustego `dataset_versions.source_job_id`.
- `POST /api/v1/admin/layout-import-validations/{validationJobId}/publish`
  ponownie blokuje i sprawdza zakończony staging, a następnie tworzy dataset
  oraz layouty setowym `INSERT ... SELECT` w jednej transakcji.
- Dataset otrzymuje status `published`, serwerowy timestamp,
  `generator_version = layout-import-v1`, neutralny seed `0` oraz provenance
  dokładnego joba walidacji.
- Retry tej samej walidacji zwraca tę samą wersję. Publikacja i odrzucenie
  stagingu blokują ten sam job importu oraz jego walidacje.
- Panel pokazuje akcję tylko dla raportu bez blokad, wymaga potwierdzenia
  niezmienności, blokuje podwójny submit i raportuje numer oraz liczbę layoutów.
- Zregenerowano OpenAPI i klienta TypeScript.

### Verification results

- pełny standardowy zestaw Python: `340 passed, 12 skipped`; skipy to 11 testów
  wymagających jawnego PostgreSQL i jedno ograniczenie symlinka Windows,
- pełna fizyczna macierz PostgreSQL po migracji: `11 passed`,
- integracja publikacji potwierdza rollback przy blockerach, dozwolony duplikat
  sygnatury, ciąg `1..4`, provenance, idempotentny retry oraz blokadę odrzucenia
  po publikacji,
- Ruff oraz format zmienionych plików Python: bez błędów,
- mypy: bez błędów w 109 plikach źródłowych,
- OpenAPI export i kontrola driftu generowanego klienta: aktualne,
- klient API: `12 passed`; panel: `65 passed`,
- TypeScript typecheck klienta i panelu, ESLint oraz produkcyjny build Next.js:
  zaliczone,
- browser smoke lokalnego panelu: sekcja importów załadowała się bez błędów
  konsoli; aktywny lokalny katalog nie miał ukończonej walidacji importu, więc
  dialog publikacji zweryfikowano testem akcji, typecheckiem i buildem bez
  wywoływania rzeczywistej publikacji.

### Not completed

- Nie wykonano reprezentatywnego importu 500 000 rekordów, pomiarów ani pełnego
  release payout → snapshot → APK; to zakres TASK-0050.
- Nie domknięto fizycznych benchmarków Android ani G3, odroczonych na mocy
  D-041.

### Documentation updates

- Zaktualizowano wymagania importu i panelu, model danych, kontrakt API,
  architekturę, strategię testów, plan M4, Decision Log (D-048) oraz
  `CURRENT_STATE.md`.

### Recommended next task

- `TASK-0050 — Manual import scale and release acceptance`.
