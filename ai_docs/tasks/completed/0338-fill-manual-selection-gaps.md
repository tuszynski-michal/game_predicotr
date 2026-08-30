---
title: TASK-0338 Fill manual selection gaps
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0338 — Uzupełnianie luk

## Goal

Umożliwić lokalne przejście po zdjęciach bazowych i zapis dokładnego targetu
każdej wykrytej luki z pełną checksummą oraz odwracalnym ostatnim fill.

## Scope

- wybór read-only katalogu bazowego i naturalne listowanie rekurencyjne;
- skoki 1/2/5/10/20/50/100 oraz niezależna nawigacja luk;
- Enter/F i przycisk zapisu, A/Ctrl+A/Ctrl+Z undo;
- exact-byte zapis, repair/output manifest i repair trace z progiem 300 ms;
- wznowienie kursora i uchwytów z operator-local IndexedDB.

## Out of scope

- usuwanie dowolnego istniejącego `seq_*` i jego jednopoziomowe restore;
- integracja karty z głównym ekranem Admina.

## Outcome

- Workspace wybiera bazowy katalog tylko do odczytu, zaczyna od pierwszego
  naturalnie posortowanego JPEG-a i utrwala źródłowy oraz gap cursor.
- Skoki 1/2/5/10/20/50/100, osobna nawigacja luk, Enter/F oraz
  A/Ctrl+A/Ctrl+Z korzystają z jednej serializowanej kolejki operacji.
- Fill kopiuje oryginalne bajty, sprawdza SHA-256, aktualizuje repair/output
  manifest i zapisuje trace dopiero po co najmniej 300 ms widoczności.
- Focused testy zapisu/undo/UI, lint i typecheck Admina przeszły poprawnie.
