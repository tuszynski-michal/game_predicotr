---
title: TASK-0025 Mock dataset generation and staging
status: done
last_updated: 2026-07-27
---

# TASK-0025 — Mock dataset generation and staging

## Status

`done`

## Goal

Umożliwić administratorowi deterministyczne utworzenie stagingowej wersji
datasetu zawierającej dokładnie 1000 layoutów zgodnych z opublikowaną wersją
reguł.

## Context

M2.3 dostarczyło niezmienne reguły. M2.4 zaczyna kanoniczny model datasetów i
przenosi ograniczony generator mocka M1 do kontrolowanego procesu
administracyjnego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-029 w `ai_docs/process/DECISION_LOG.md`

## Scope

- migracja `dataset_versions` i `layouts`,
- wersjonowany staging z zapisanym seedem i wersją generatora,
- czysty generator 1000 layoutów row-major,
- stabilna stałoszeroka sygnatura wyliczona z `mobile_code`,
- sześć kontrolowanych duplikatów treści bez duplikowania numerów sekwencji,
- źródło wymiarów i symboli z opublikowanej wersji reguł tej samej gry,
- atomowy zapis całej wersji i layoutów,
- listowanie wersji datasetu,
- endpoint i generowany klient TypeScript,
- sekcja panelu z wyborem gry, opublikowanej wersji reguł i seedu,
- testy domeny, API, migracji, PostgreSQL, klienta i panelu.

## Out of scope

- raport luk, duplikatów numeru i duplikatów sygnatur (TASK-0026),
- podgląd pojedynczego layoutu i paginacja layoutów (TASK-0027),
- publikacja lub archiwizacja datasetu (TASK-0027),
- payout precomputing, SQLite i APK,
- generator docelowej skali 500 000 rekordów.

## Acceptance criteria

- [x] migracja ma bezpieczny upgrade/downgrade i pozostaje jedynym headem,
- [x] generator tworzy dokładnie 1000 rekordów `sequence_number = 1..1000`,
- [x] te same wejścia dają identyczne `cells` i `signature`,
- [x] każdy layout ma `rows * columns` kodów aktywnych symboli wersji reguł,
- [x] signature używa zapisanej szerokości 1–5 i kolejności row-major,
- [x] sześć końcowych rekordów powtarza kontrolowane sygnatury bez naruszania
  unikalności `sequence_number`,
- [x] nieopublikowana/obca wersja reguł i brak wystarczających symboli są
  blokowane stabilnym błędem,
- [x] wersja i wszystkie layouty zapisują się atomowo jako `staging`,
- [x] panel pokazuje loading/empty/error/success i blokuje podwójny submit,
- [x] OpenAPI, klient, testy i produkcyjny build panelu przechodzą.

## Technical notes

Endpoint jest celowo ograniczony do dokładnie 1000 layoutów. To krótki mock
administracyjny, nie precedens dla docelowego generatora 500 000 rekordów,
który pozostaje operacją workera. Aktywne konfiguracje symboli opublikowanej
wersji reguł określają alfabet generatora.

## Expected files

- `services/api/alembic/versions/0006_dataset_staging.py`
- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `apps/admin/src/features/datasets/`
- `ai_docs/`

## Verification

```powershell
npm run openapi:generate
npm run quality
npm run admin:build
npm run db:baseline:verify
```

## Risks / open questions

- Brak blokujących pytań produktowych.
- Synchroniczny request nie może zostać rozszerzony na docelową skalę bez
  przeniesienia wykonania do workera/job.

## Outcome

### Changed

- Dodano czysty, deterministyczny generator `mock-v1`, kanoniczne modele
  `dataset_versions`/`layouts`, repozytorium SQLAlchemy i migrację Alembic
  `0006_dataset_staging`.
- Admin API udostępnia generowanie, listę oraz szczegóły wersji datasetu.
  Kontrakt OpenAPI i generowany klient TypeScript zawierają te operacje.
- Panel udostępnia wybór gry, opublikowanej wersji reguł i seedu, generowanie
  dokładnie 1000 layoutów oraz historię stagingów.
- Generowanie blokuje używaną wersję reguł, a numer wersji datasetu przydziela
  pod blokadą gry; dataset i wszystkie layouty są zapisywane w jednej
  transakcji.

### Verification results

- `npm run quality`: pass — 121 Python (+ 2 jawne skipy PostgreSQL), 63 mobile,
  40 panel, 23 shared TypeScript i 7 klient API; format, OpenAPI, lint oraz
  typecheck bez błędów.
- `npm run admin:build`: pass — produkcyjny build Next.js.
- `npm run db:baseline:verify`: pass — 2 fizyczne testy PostgreSQL, w tym
  `upgrade → downgrade → upgrade`, constraints oraz dwie deterministyczne
  wersje po 1000 layoutów.
- Końcowe `npm run format:check`: pass.

### Not completed

- Raporty sekwencji i duplikatów należą do TASK-0026.
- Podgląd layoutów, publikacja i archiwizacja datasetu należą do TASK-0027.
- Generator 500 000 rekordów, payout precomputing, SQLite i APK pozostają poza
  zakresem tego zadania.

### Documentation updates

- Zaktualizowano wymagania panelu, model danych, kontrakt API, architekturę
  systemu, stos techniczny, strategię testów, `CURRENT_STATE.md` i D-029.

### Recommended next task

- `TASK-0026 — Sequence and duplicate validation reports`
