---
title: TASK-0208 image import scaling and observability
status: in_progress
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0208 — Image import scaling and observability

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Zmierzyć koszt etapów dla 10/100/1000 i przygotować kontrolowany pomiar 5000
zdjęć.

## Verification

Raport zawiera czas całkowity, jednostkowy, throughput, pamięć i udział etapów
bez zmiany algorytmu.

## Dependencies

TASK-0201.

## Outcome

Warstwa obserwowalności jest zaimplementowana. Historia partii w Adminie
pokazuje czas, sekundy/zdjęcie i zdjęcia/minutę, a bounded skrypt
`scripts/measure_image_import_job.ps1` zapisuje także peak RSS, postęp oraz
udział etapów. Procedurę 10/100/1000 i warunkową bramkę 5000 opisuje
`ai_docs/quality/IMAGE_IMPORT_SCALING_ACCEPTANCE.md`.

Rzeczywiste pomiary pozostają odroczonym odbiorem właściciela. Zadanie nie jest
oznaczone jako ukończone, dopóki wyniki nie zostaną zebrane i zaakceptowane.
