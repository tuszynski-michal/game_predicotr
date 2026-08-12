---
title: TASK-0226 image selection verification UI
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0226 — Manualna selekcja i kontrola algorytmu

## Goal

Utrwalić decyzje po ponownym otwarciu, pokazywać całą galerię grupy oraz
udostępnić pełnoekranowy, tylko do odczytu podgląd automatycznych wyborów.

## Relevant docs

- `ai_docs/tasks/completed/0217-manual-image-selection-gallery.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`

## Verification

Testy stanu po reopen, klawiatury, domyślnego środkowego/dziesiątego zdjęcia,
URL-i JPEG, scrolla, zoomu i braku mutacji w trybie weryfikacji.

## Outcome

Modal ponownie pobiera trwały stan decyzji, zaczyna od pierwszej nierozwiązanej
grupy i rozdziela wybrane, pominięte oraz pozostałe. Galeria ma scroll, pełny
ekran, jeden zoom, domyślny środkowy/dziesiąty JPEG oraz jawne zatwierdzenie
przyciskiem, Enterem lub strzałką w prawo. Osobny tryb weryfikacji automatycznych
wyborów jest tylko do odczytu.
