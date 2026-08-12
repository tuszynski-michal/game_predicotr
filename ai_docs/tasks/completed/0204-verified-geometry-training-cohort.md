---
title: TASK-0204 verified geometry training cohort
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0204 — Verified geometry training cohort

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Budować niezmienną kumulacyjną kohortę geometrii z zaakceptowanych plansz.

## Verification

Manifest jest deterministyczny, source-image-disjoint i zawiera detected/final
quad oraz provenance.

## Dependencies

TASK-0199.

## Outcome

Dodano niezmienne kohorty geometrii budowane wyłącznie z decyzji `accepted` i
`corrected`. Każda próbka wiąże surowy quad detektora, finalny quad, źródło,
run Selekcji Zdjęć i pozycję na stronie. Deterministyczny podział
train/validation jest rozłączny po zdjęciu źródłowym.
