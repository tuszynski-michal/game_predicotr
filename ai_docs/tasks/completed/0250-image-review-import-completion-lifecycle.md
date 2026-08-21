---
title: TASK-0250 image review import completion lifecycle
status: done
last_updated: 2026-08-21
---

# TASK-0250 — Image review import completion lifecycle

## Goal

Domknąć status importu po rozwiązaniu ostatniej planszy i przywracać stan
oczekiwania po jawnym ponownym otwarciu planszy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/completed/0249-board-cell-geometry-review-queue-and-shared-reviewer.md`

## Scope

- zsynchronizować `jobs.status` z trwałym licznikiem `pending`,
- nie kończyć importu przed rozwiązaniem ostatniej pozycji,
- ponownie otwierać ukończony import po zmianie pozycji na `pending`,
- naprawić istniejące importy całkowicie rozwiązane przed wdrożeniem,
- zachować oba gotowe statusy w selectcie i pełny audyt kolejki,
- nie zmieniać API, UI, kolejności ani decyzji plansz.

## Acceptance criteria

- [x] `pending > 0` zachowuje `waiting_for_review`.
- [x] `total > 0` i `pending = 0` ustawia `completed` oraz `finished_at`.
- [x] Ponowne otwarcie planszy ustawia `waiting_for_review` i czyści
      `finished_at`.
- [x] Migracja naprawia istniejący całkowicie rozwiązany import.
- [x] Zmiana nie dotyka importu nadal zawierającego pozycje pending.
- [x] Test migracji oraz rzeczywiste testy PostgreSQL obejmują domknięcie,
      ponowne otwarcie i backfill.

## Outcome

Migracja `0053_image_review_job_completion` dodaje trigger na autorytatywnej
projekcji `image_review_queue_states`. Trigger wykonuje przejścia wyłącznie dla
jobów typu `import` w odpowiednim stanie, a backfill obejmuje tylko niepuste
kolejki bez pozycji pending. Kontrakt HTTP i klient Admina nie zmieniły się.

Weryfikacja:

- test migracji i pełny plik integracyjny PostgreSQL: `44 passed`,
- test stanu dropdownu Admina: `3 passed`,
- Ruff, format Python, Prettier i kontrola OpenAPI/klienta: zaliczone,
- realna baza działa na `0053_image_review_job_completion (head)`,
- `50cfdcad…`: `completed`, `63 corrected`, `0 pending`,
- `b2d9b299…`: `waiting_for_review`, `19 707 pending` w chwili kontroli.
