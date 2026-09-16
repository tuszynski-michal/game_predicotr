---
title: TASK-0367 — oczekiwana liczba plansz wyłącznie z zakresu nazwy
status: done
last_updated: 2026-09-01
---

# TASK-0367 — oczekiwana liczba plansz wyłącznie z zakresu nazwy

## Cel

Zagwarantować, że produkcyjny import `seq_<start>-<end>` wyprowadza
`expectedBoardCount` jako `end - start + 1`. Wartość dziewięć pozostaje jedynie
fallbackiem dla źródła bez poświadczonego zakresu.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/tasks/completed/0366-partial-page-attested-sequence-assignment.md`

## Outcome

- poprawny zakres 1–9 zwraca dokładną liczbę plansz;
- brak zakresu zachowuje kompatybilny fallback dziewięciu;
- niepoprawny poświadczony zakres kończy się fail-closed zamiast cichego
  zastąpienia dziewięcioma;
- test regresyjny obejmuje końcowy zakres `499996–500000`.
