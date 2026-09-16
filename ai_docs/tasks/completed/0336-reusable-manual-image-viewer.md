---
title: TASK-0336 Reusable manual image viewer
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0336 — Wspólny viewer ręcznej selekcji

## Goal

Wydzielić współdzielony podgląd lokalnych zdjęć przed dodaniem korekty ręcznej
selekcji, bez zmiany zachowania obecnego selektora.

## Scope

- cache ograniczonego okna zdjęć i lifecycle URL-i obiektowych;
- zoom 100–3000%, fullscreen i pamięć pionowego scrolla;
- wspólny toolbar i nawigacja podglądu;
- regresyjne testy istniejącego lokalnego workflow.

## Out of scope

- manifest korekty, mutacje katalogu i nowa karta Admina;
- zmiany API, bazy, workera i zdalnej selekcji.

## Invariants

- przeglądarka odczytuje oryginalne bajty lokalnie;
- cache obejmuje tylko bieżące, poprzednie i następne zdjęcia;
- zmiana zdjęcia zachowuje scroll obrazu;
- dotychczasowe skróty, zoom i fullscreen działają bez zmiany semantyki.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Verification

- test lokalnej ręcznej selekcji;
- lint i typecheck Admina;
- przegląd diffu bez niezwiązanych zmian.

## Outcome

- Viewer i hook przejęły bounded cache URL-i, dekodowanie sąsiadów, zoom,
  fullscreen, obserwację viewportu i pamięć pionowego scrolla.
- Istniejący lokalny workspace korzysta ze wspólnego komponentu bez zmiany
  manifestu, skrótów i semantyki nawigacji.
- Test lokalnego selektora, lint oraz typecheck Admina przeszły poprawnie.
