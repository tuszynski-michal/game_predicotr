---
title: TASK-0228 image selection v10.4 acceptance
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0228 — Odbiór v10.4

## Goal

Przejść testy automatyczne przed etapową weryfikacją 200, 4032, 5000 i 42403
zdjęć wykonywaną dopiero po akceptacji implementacji.

## Relevant docs

- `ai_docs/tasks/completed/0221-image-selection-v104-baseline.md`
- `ai_docs/tasks/completed/0227-image-selection-v104-contract-and-telemetry.md`

## Verification

Automatyczne kontrakty muszą przejść bez danych właściciela. Dla późniejszych
testów danych obowiązuje manual rate do 20%, maksymalnie dwa wywołania OCR na
grupę i projekcja pełnego przebiegu nie większa niż trzy godziny.

## Outcome

Automatyczna bramka implementacji przeszła: 130 testów selektora/workera, 4
testy monitora live, 28 testów API/OpenAPI i 186 testów Admina. Ruff, zawężony
mypy, ESLint, Prettier, oba typechecki TypeScript i kontrola wygenerowanego
klienta OpenAPI również przeszły. Próby 200/4032/5000/42403, pomiar czasu i
manual rate pozostają celowo odłożone do osobnego odbioru po akceptacji
implementacji.

Realny odbiór wykazał jednak jednoznaczną regresję jakościową. Run
`edf8625d-776c-4a73-8db9-29115fe05c14` utworzył 3 840 grup, z których 3 388
(88,23%) skierował do ręcznej selekcji. Tylko 452 grupy miały rozpoznany zakres,
a 7 401 z 7 680 prób OCR zakończyło się `RANGE_LABEL_GRID_NO_HYPOTHESIS`.
V10.4 nie została zaakceptowana jako dalsza baza; zadanie zamyka wynik negatywny,
a korektę prowadzi TASK-0230 i decyzja D-170.
