---
title: TASK-0235 image-selection review queues and reversible rejection
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0235 — Dwie kolejki review i odrzucenie grupy

## Goal

Rozdzielić ręczny wybór reprezentanta od ustalania nierozpoznanego zakresu,
usunąć całkowicie nieczytelne grupy z obu kolejek oraz pozwolić użytkownikowi
odrzucić i później przywrócić grupę do dokładnie tej kolejki, z której pochodziła.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`

## Outcome

Migracja `0041_image_selection_review_queues` dodaje stany `range_required`,
`range_confirmed`, `skipped_unreadable` i `rejected_by_user` oraz zapisuje
pochodzenie odrzucenia. API udostępnia idempotentne potwierdzenie zakresu dla
automatycznego reprezentanta, odrzucenie grupy i przywrócenie jej do pierwotnej
kolejki. Każda decyzja ma append-only audyt.

Admin pokazuje osobne akcje `Wybierz zdjęcie`, `Ustal grupę` i `Odrzucone`.
Ustalanie grupy nie pozwala zmieniać automatycznie wskazanego JPEG-a, a
odrzucenie i przywrócenie nie wymagają folderu wynikowego ani nie zapisują
pliku. Potwierdzony wybór zdjęcia lub zakresu nadal kończy się dopiero po
trwałym zapisie JPEG-a do katalogu użytkownika.

Weryfikacja objęła 97 skupionych testów API/workera, 36 testów klienta,
194 testy Admina, Ruff, oba typechecki, ESLint i kontrolę OpenAPI.
