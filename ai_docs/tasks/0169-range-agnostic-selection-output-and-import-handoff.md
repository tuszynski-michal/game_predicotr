---
title: TASK-0169 range agnostic selection output and import handoff
status: todo
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0169 — Range-agnostic selection output and Import handoff

## Status

`todo`

## Goal

Opublikować wybrane zdjęcia bez wymaganego zakresu sekwencji i przenieść OCR,
geometrię, numerację oraz deduplikację zakresów do `Importu layoutów`.

## Context

Po usunięciu OCR z szybkiego selektora nazwa `seq_1-9.jpg` nie jest jeszcze
znana. Selekcja nie może zgadywać numerów tylko po kolejności, ponieważ poprawny
skok może prowadzić z `19–27` do `400–408`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0168-first-usable-range-free-representative-selection.md`

## Scope

- dopuścić `recognized_range = null` dla automatycznie wybranego reprezentanta,
- publikować deterministyczne nazwy `selection_<groupOrder>.jpg` przed OCR,
- zachować `groupOrder`, oryginalną nazwę, checksum, metryki i ostrzeżenia,
- zmienić UI z liczby rozpoznanych zakresów na liczbę wybranych grup,
- przekazać range-free manifest do istniejącego `Importu layoutów`,
- w `Imporcie layoutów` uruchamiać istniejące OCR/geometrię i dopiero wtedy
  przypisywać właściwe `sequence_number` oraz wykrywać duplikat zakresu,
- zachować zgodność odczytu historycznych outputów `seq_<start>-<end>.jpg`,
- wykonać zmianę schematu wyłącznie przez migrację Alembic, jeżeli obecne
  constrainty nie dopuszczają wybranego kandydata bez zakresu.

## Out of scope

- ulepszanie dokładności OCR lub geometrii importu,
- automatyczne uruchomienie importu bez kliknięcia użytkownika,
- przepisywanie historycznych manifestów v2–v8,
- usuwanie ręcznego wyboru pliku dla wyjątków technicznych.

## Acceptance criteria

- [ ] Selekcja kończy się i publikuje output bez OCR oraz bez zakresów.
- [ ] Nazwy range-free są deterministyczne, stabilne na Windows i nie udają
      numerów layoutów.
- [ ] Import otrzymuje ten sam checksumowany JPEG i ustala numerację dopiero w
      swoim pipeline.
- [ ] Skok zakresów pozostaje poprawny; selekcja nie przewiduje numeru.
- [ ] Historyczne manifesty i publiczne nazwy `seq_*` nadal są odczytywalne.
- [ ] OpenAPI i generowany klient są zgodne z backendem.
- [ ] UI jasno rozróżnia `wybrane grupy` od `rozpoznanych layoutów`.

## Technical notes

Ta zmiana koryguje odpowiedzialności bounded contextów. `sequence_number`
pozostaje wartością domenową Importu, a `groupOrder` techniczną kolejnością
źródeł i nie może być prezentowany jako numer layoutu.

## Expected files

- `services/api/alembic/versions/*.py`
- `services/api/src/game_predictor_api/domain/image_selections.py`
- `services/api/src/game_predictor_api/application/image_selections.py`
- `services/api/src/game_predictor_api/schemas/image_selections.py`
- `services/worker/src/game_predictor_worker/images/selection/output.py`
- `services/worker/src/game_predictor_worker/images/orchestration.py`
- `apps/admin/src/features/image-selection/*`
- `packages/admin-api-client/src/generated/*`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_selections.py services/worker/tests/test_curated_image_output.py services/worker/tests/test_image_batch_orchestration.py
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Import może otrzymać kilka wizualnie podobnych reprezentantów. To bezpieczny
  koszt dodatkowy; deduplikacja po pewnym zakresie jest dokładniejsza niż
  usunięcie unikalnej strony w selektorze.

## Outcome

Do uzupełnienia po realizacji.
