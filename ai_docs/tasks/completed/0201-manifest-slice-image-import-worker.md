---
title: TASK-0201 manifest slice image import worker
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0201 — Manifest slice image import worker

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Uruchamiać image import wyłącznie dla przypiętego wycinka zweryfikowanego
manifestu i snapshotów modeli.

## Verification

Worker zachowuje groupOrder, retry wznawia ten sam zakres, a fingerprint
obejmuje model symboli i profil siatki.

## Dependencies

TASK-0200.

## Outcome

Worker odczytuje wyłącznie przypięty wycinek ukończonego manifestu, ponownie
weryfikuje checksumy i zachowuje kolejność `groupOrder`. Retry pozostaje na tym
samym niezmiennym jobie, a efektywny fingerprint obejmuje snapshot modelu
symboli i profilu siatki.
