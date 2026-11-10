---
title: TASK-1178 — Gotowość korekt i zalecany cel uczenia
status: todo
last_updated: 2026-11-10
---

# TASK-1178 — Gotowość korekt i zalecany cel uczenia

## Status

`todo`

## Goal

Pokazać aktualne ręczne korekty, zrozumiałe blokady startu i dobierać zalecany
cel uczenia zgodnie z gotowością danych.

## Context

T2 zaakceptowanego planu REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md.
Zakres i koszt6–10h zatwierdzone dla całej pracy; zależy od zamknięcia T1.
Operator zgłasza disabled po kilkudziesięciu korektach oraz niejasny wybór.

## Recommended execution

gpt-6.1-sol/high; audyt Claude Code claude-opus-5-5/high.

## Relevant docs

- ai_docs/delivery/REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md, T2 i odbiór.
- ai_docs/requirements/IMAGE_INGESTION.md.
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md.
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md.
- ai_docs/process/CROSS_AUDIT.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/process/decisions/DECISION_LOG_2026.md#d-582--przyrostowe-wyspy-treningu-i-zwalnianie-nieużytych-rezerwacji.

## Scope / expected files

Istniejące: application/grid_correction_learning.py, storage/grid_correction_split.py,
domain/grid_correction_progress.py, schemas/grid_correction_learning.py,
Admin grid-correction-learning-panel/state i testy API/PG/interakcji.
W razie zmiany kontraktu: backend/OpenAPI/SDK/wrapper/test żądania.
Nie zmniejszać minimów, nie zmieniać ról danych dla odblokowania przycisku.
Nie uruchamiać GPU w tle ani nie stosować nowego modelu bez decyzji operatora.

## Acceptance criteria

- [ ] Bieżąca przyczyna disabled rozpoznana i przedstawiona liczbowo.
- [ ] Ręczne korekty poprawnie kwalifikowane; podgląd aktualizuje liczniki.
- [ ] Zalecany tryb wynika z danych; ręczny wybór zaawansowany zachowany.
- [ ] Każdy istotny disabled ma zrozumiały powód i dalsze działanie.
- [ ] Kontrakty, historyczne polecenia i ochrona TRAIN/A/B/REG zachowane.
- [ ] Regresje, lint/typecheck/build/docs/map i Opus zakończone.
- [ ] Outcome i task-close; finalnie pytanie o scalenie całego zakresu.

## Verification

Testy zmienionych modułów, istniejące test_grid_correction_learning_api.py,
test_grid_correction_workflow.py, test_grid_correction_split_adapter.py,
integration/test_grid_correction_learning_postgres.py oraz interakcje Admina.
Wyniki dopiero po wykonaniu; nie przedstawiać brakujących danych jako PASS.

## Outcome

Oczekuje na T1; ograniczona diagnoza czytająca dozwolona.
