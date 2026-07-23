---
title: Current project state
status: active
last_updated: 2026-07-23
---

# Current State

## Phase

`M0 — Architecture clarification`

## Completed

- pierwotne wymagania zostały rozdzielone na mobile, admin, algorytmy i image ingestion,
- przygotowano proponowany stos technologiczny,
- przygotowano logiczny model danych i kontrakt API,
- przygotowano roadmap oraz definicję M1,
- zidentyfikowano pytania blokujące.

## In progress

- odpowiedzi właściciela produktu na `project/OPEN_QUESTIONS.md`,
- akceptacja lub odrzucenie decyzji D-001–D-009.

## Blocked

- finalny model wdrożenia mobile przez Q-001,
- finalny model skali przez Q-002,
- payout engine przez Q-005–Q-010,
- forecast semantics przez Q-011–Q-014,
- image prototype przez brak próbek Q-015–Q-017.

## Next recommended task

`tasks/0001-architecture-clarification.md`

## Do not start yet

- masowe przetwarzanie zdjęć,
- implementacja finalnego jokera,
- Celery/Redis,
- offline snapshot,
- produkcyjny deployment.

## Handoff notes

Dokumenty opisują rekomendację, a nie zaakceptowany stan technologii. Po uzyskaniu odpowiedzi należy:

1. zmienić status decyzji,
2. zaktualizować wymagania kolidujące z odpowiedziami,
3. stworzyć zadania M1,
4. dopiero potem inicjalizować kod.
