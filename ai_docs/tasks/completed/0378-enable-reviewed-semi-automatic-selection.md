---
title: Enable reviewed semi-automatic selection
status: done
last_updated: 2026-09-02
---

# TASK-0378 — Włączenie odebranego półautomatu v3

## Goal

Udostępnić operatorowi gotowy lokalny workflow półautomatycznej selekcji,
bez promowania odrzuconych eksperymentów OCR.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V3_PERFORMANCE.md`

## Scope

- domyślnie włączony lokalny workflow;
- aktywny adapter v3 i niezmienione fingerprinty historycznych runów;
- zachowanie jawnego override'u konfiguracji;
- test wartości domyślnej i dokumentacja decyzji.

## Out of scope

- włączanie v4.1 albo v5;
- osłabienie proof;
- zmiana schedulera, OCR, grupowania lub job lane.

## Definition of Done

- [x] Pusta konfiguracja udostępnia półautomat.
- [x] Jawne `false` nadal go wyłącza.
- [x] Nowe runy nadal przypinają v3.
- [x] Odrzucone warianty pozostają wyłączone.

## Outcome

Domyślna wartość flagi została zmieniona na `true`. Zmiana dotyczy
wyłącznie bramki lokalnego workflow i nie zmienia rozpoznawania ani
odtwarzalności istniejących runów.
