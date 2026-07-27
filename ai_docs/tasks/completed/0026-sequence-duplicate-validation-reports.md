---
title: TASK-0026 Sequence and duplicate validation reports
status: done
last_updated: 2026-07-27
---

# TASK-0026 — Sequence and duplicate validation reports

## Status

`done`

## Goal

Umożliwić administratorowi uruchomienie deterministycznego raportu integralności
stagingowego datasetu, który rozdziela blokady publikacji od dozwolonych
duplikatów sygnatur.

## Context

TASK-0025 utworzyło kanoniczny staging i kontrolowane duplikaty treści. Przed
podglądem oraz publikacją potrzebny jest jeden walidator używany zarówno przez
raport, jak i przyszłą transakcję publikacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-029–D-030 w `ai_docs/process/DECISION_LOG.md`

## Scope

- czysty i deterministyczny walidator datasetu,
- porównanie deklarowanej i rzeczywistej liczby layoutów,
- zakres numerów, luki i duplikaty `sequence_number`,
- dokładna liczba komórek `rows * columns`,
- przynależność kodów symboli do gry,
- zgodność sygnatury z komórkami i zapisaną szerokością codeca,
- grupy duplikatów sygnatur jako nieblokujące ostrzeżenie,
- ograniczone próbki diagnostyczne przy zachowaniu dokładnych liczników,
- synchroniczny endpoint raportu dla bounded mocka `mock-v1`,
- typowany klient TypeScript i panel raportu,
- testy domeny, API, repozytorium, klienta oraz panelu.

## Out of scope

- publikacja, archiwizacja i mutacja datasetu (TASK-0027),
- paginacja oraz podgląd pojedynczego layoutu jako planszy (TASK-0027),
- trwałe joby, polling workera i walidacja datasetów docelowej skali,
- payout precomputing, SQLite i APK,
- usuwanie lub automatyczna naprawa wadliwych danych.

## Acceptance criteria

- [x] raport podaje deklarowaną/rzeczywistą liczbę rekordów oraz min/max sekwencji,
- [x] luka i duplikat numeru są raportowane jako blokady,
- [x] zła liczba komórek, obcy symbol i niespójna sygnatura są blokadami,
- [x] duplikaty sygnatur zawierają posortowane numery pozycji i nie blokują,
- [x] poprawny mock ma sześć grup duplikatów i pozostaje gotowy do publikacji,
- [x] kolejność checków, grup i próbek jest deterministyczna,
- [x] dokładne liczniki nie zależą od limitu próbek diagnostycznych,
- [x] nieistniejący dataset i dataset poza bounded `mock-v1` mają stabilne błędy,
- [x] panel pokazuje loading/error/success, blokady i ostrzeżenia tekstowo,
- [x] OpenAPI, klient, testy i produkcyjny build panelu przechodzą.

## Technical notes

Raport jest wyliczany na żądanie i nie zmienia stagingu. Synchroniczna ścieżka
jest dozwolona wyłącznie dla aktualnego bounded mocka `mock-v1`; większe lub
importowane datasety będą walidowane przez worker/job. Baza nadal chroni
unikalność numeru sekwencji, a czysty walidator obsługuje duplikat jako
defense-in-depth i kontrakt przyszłego surowego stagingu.

## Expected files

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
- Synchronous validation nie może zostać rozszerzona na 500 000 rekordów bez
  przejścia do workera i raportu strumieniowego.

## Outcome

### Changed

- Dodano frameworkowo niezależny walidator oraz typowane checki
  `passed/warning/blocking`, raport i grupy duplikatów.
- Repozytorium odczytuje kanoniczny dataset, symbole gry i layouty w porządku
  sekwencji. Admin API udostępnia
  `GET /dataset-versions/{id}/validation-report`.
- OpenAPI i generowany klient TypeScript zawierają pełny kontrakt raportu.
- Panel uruchamia walidację, chroni przed podwójnym żądaniem i pokazuje metryki,
  wszystkie checki oraz tabelę duplikatów w układzie responsywnym.
- Nie była potrzebna migracja: raport jest wyliczany bez mutowania stagingu.

### Verification results

- `npm run quality`: pass — 125 Python (+ 2 jawne skipy PostgreSQL), 63 mobile,
  42 panel, 23 shared TypeScript i 7 klient API; format, OpenAPI, lint oraz
  typecheck bez błędów.
- `npm run db:baseline:verify`: pass — 2 fizyczne testy PostgreSQL; poprawny
  mock ma 6 grup ostrzeżeń, a kontrolowane uszkodzenie zwraca 5 blokad i jest
  wycofywane rollbackiem.
- `npm run admin:build`: pass — produkcyjny build Next.js.

### Not completed

- Podgląd pojedynczego layoutu, publikacja i archiwizacja należą do TASK-0027.
- Trwałe validation jobs, worker i datasety docelowej skali pozostają poza
  zakresem TASK-0026.
- Walidator nie naprawia i nie usuwa wadliwych rekordów.

### Documentation updates

- Zaktualizowano wymagania panelu, integralność modelu danych, kontrakt API,
  architekturę systemu, strategię testów, plan M2, `CURRENT_STATE.md` i D-030.

### Recommended next task

- `TASK-0027 — Dataset preview and immutable publication`
