---
title: TASK-0337 Manual selection repair domain
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0337 — Domena korekty i manifest

## Goal

Zdefiniować bezpieczną, lokalną domenę korekty katalogów `seq_*`, trwały
manifest oraz operator-local persistence bez przechowywania JPEG-ów.

## Scope

- parser, sortowanie, walidacja zakresów i wyznaczanie luk;
- utrwalone granice kolekcji i dokładne zakresy usunięć;
- manifest z operacją oczekującą i reconciliacją checksummy;
- top-level skan katalogu i osobna baza IndexedDB v1 dla uchwytów i kursora.

## Out of scope

- UI oraz fizyczne uzupełnianie/usuwanie JPEG-ów;
- API, worker, PostgreSQL i OpenAPI.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Outcome

- Dodano niezależny moduł domenowy parsera `seq_*`, walidacji overlapów,
  trwałych granic i deterministycznego dzielenia luk.
- Repair manifest przechowuje aktywne pliki, checksumy, usunięcia, historię i
  operację oczekującą; recovery rozstrzyga stan na podstawie pliku i SHA-256.
- Top-level adapter ignoruje artefakty nieobrazowe, a osobna IndexedDB v1
  przechowuje tylko uchwyty, tryb, kursory i preferencje bez Blobów.
- Testy core, adaptera, lint i typecheck przeszły poprawnie.
