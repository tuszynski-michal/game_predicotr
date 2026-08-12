---
title: TASK-0202 Admin next image batch workspace
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0202 — Admin next image batch workspace

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Dodać w Import Layoutów prosty licznik postępu i akcję Przetwórz kolejne N.

## Verification

UI przeżywa refresh/restart, nie pozwala utworzyć równoległej partii tego
źródła i prowadzi do Reviewera.

## Dependencies

TASK-0200–0201.

## Outcome

Workspace `Import Layoutów` rejestruje zweryfikowany output selekcji, pokazuje
trwały postęp i domyślnie tworzy kolejną partię 10 zdjęć. Użytkownik może podać
inną dodatnią liczbę, a historia pokazuje zakres, liczbę zdjęć, czas,
sekundy/zdjęcie i throughput. Stan pochodzi z API, więc przeżywa refresh i
restart procesu.
