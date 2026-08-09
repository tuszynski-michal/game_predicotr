---
title: TASK-0198 v0.5 iterative image import contract
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0198 — V0.5 iterative image import contract

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md

## Goal

Utrwalić wymagania, architekturę i decyzje dla iteracyjnego importu, kalibracji
siatki oraz ochrony wcześniejszych decyzji.

## Verification

Dokumenty opisują pełny przepływ, a plan v0.5 wskazuje małe zadania i kolejność.

## Dependencies

Brak.

## Outcome

Utrwalono wymagania i architekturę iteracyjnego importu wybranego corpus,
ochronę decyzji człowieka, osobne wersjonowanie modeli symboli i profilu siatki
oraz zasady przypinania snapshotów tylko do nowych partii. Plan v0.5 został
podzielony na TASK-0198–0208, a decyzje domenowe zapisano w `DECISION_LOG.md`.
