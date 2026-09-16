---
title: Fix Reviewer load scheduling
status: done
last_updated: 2026-09-02
---

# TASK-0379 — Bezpieczne planowanie diagnostyki lokalnego Reviewera

## Goal

Usunąć synchroniczne aktualizacje stanu z efektu React bez zmiany sposobu
wyboru kolejki geometrii.

## Scope

- zaplanowanie resetu i obu odczytów kolejki w mikrozadaniu;
- zachowanie anulowania odpowiedzi po unmount lub zmianie zakresu;
- regresyjny lint, typecheck i testy Reviewera.

## Out of scope

- zmiana API, kolejności wyboru trybu albo interfejsu geometrii.

## Outcome

Efekt nie wywołuje już synchronicznie setterów React. Oba requesty nadal
startują razem, a nieaktualna odpowiedź nie zmienia widoku.

## Verification

- Reviewer ESLint: pass.
- Reviewer typecheck: pass.
- Reviewer tests: `168 passed`.
