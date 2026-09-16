---
title: TASK-0575 — Ograniczenie źródła uzupełniania luk do wskazanego katalogu
status: done
last_updated: 2026-09-16
---

# TASK-0575 — Ograniczenie źródła uzupełniania luk do wskazanego katalogu

## Goal

Uzupełnianie luk ma listować tylko zdjęcia bezpośrednio we wskazanym folderze i
jasno pokazywać operatorowi, który folder został otwarty.

## Context

Dotychczasowy adapter rekurencyjnie schodził do podfolderów. Gdy picker zwrócił
katalog nadrzędny kolekcji, lista rosła do dziesiątek tysięcy zdjęć, mimo że
operator oczekiwał około 2800 obrazów jednej kolekcji. Ten sam pełny skan
powtarzał się przy odtwarzaniu sesji.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Ograniczenie listy źródeł fill oraz jej recovery do plików bezpośrednich.
- Osobna pamięć lokalizacji pickera źródła, widoczna nazwa wybranego folderu i
  błąd przy wyborze folderu bez bezpośrednich JPEG-ów.
- Zachowanie dotychczasowej rekurencji zwykłej ręcznej selekcji.

## Out of scope

- Zmiany istniejących manifestów i plików zdjęć użytkownika.
- Modyfikowanie katalogów kolekcji na dysku.

## Acceptance criteria

- [x] Folder z JPEG-ami i podfolderem innych kolekcji zwraca tylko bezpośrednie
  JPEG-i i nie otwiera podfolderu.
- [x] Odtworzenie sesji używa identycznej reguły.
- [x] Picker źródła pamięta lokalizację osobno, a UI pokazuje nazwę folderu.
- [x] Pusty na wybranym poziomie folder kończy się zrozumiałym błędem.
- [x] Zwykła selekcja zachowuje rekurencję.

## Outcome

### Changed

- Adapter źródła otrzymał opcjonalny tryb bez podfolderów. Fill i recovery
  używają go jawnie; zwykła selekcja zachowuje domyślną rekurencję.
- UI wskazuje faktyczną nazwę wybranego folderu i liczbę jego zdjęć. Picker
  źródła ma osobny identyfikator od pickera katalogu `seq_*`.

### Verification results

- 48 skoncentrowanych testów selekcji i naprawy zaliczonych. Kontrola typów i
  lint zmienionych plików bez błędów. Build panelu przeszedł po uruchomieniu
  poza ograniczeniem blokującym proces potomny Next.js.

### Not completed

- Nie odtwarzano wyboru użytkownika w przeglądarce ani nie modyfikowano danych.

### Documentation updates

- Wymagania, architektura i `CURRENT_STATE.md`.

### Recommended next task

- Brak.
