---
title: TASK-0457 Selected image blue panel crop regression
status: done
last_updated: 2026-09-05
---

# TASK-0457 — Przywrócenie właściwego pasa plansz w auto-cropie

## Goal

Naprawić regresję, w której pełnoszeroki panel wypłat nad planszami rozszerzał
górną granicę automatycznego cropa, bez cofania zabezpieczeń dla innych kolorów
szaf i bez ukrytego przeliczania istniejących plików.

## Scope

- wersjonowana polityka v5 korygująca wielokolumnowy wynik profilem niebieskiego
  panelu;
- zachowanie wielokolumnowego detektora v4 jako ścieżki ogólnej;
- automatyczne kierowanie `safe_wide` do kolejki korekty;
- kompatybilny odczyt proweniencji v4;
- regresja pełnoszerokiego panelu wypłat i wąskich bocznych świateł;
- porównanie czasu istniejących jobów geometrii bez uruchamiania benchmarku.

## Out of scope

- zmiana rejestracji geometrii, liczby przebiegów auto-anchor albo aktywnych
  jobów;
- automatyczne przeliczenie katalogów użytkownika;
- OCR, API, PostgreSQL, obrót i homografia.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- niebieski panel 3×3 usuwa kolorowy panel wypłat z potwierdzonego wyniku;
- wąskie światła i częściowy sygnał nie mogą udawać pełnego panelu;
- inne kolory nadal korzystają z v4;
- brak dowodu trafia do `Do poprawy`;
- v4 pozostaje czytelne i nie jest przeliczane bez jawnej akcji;
- testy core/Admin, lint, typecheck i build zmienionego pionu są zielone.

## Outcome

- Dodano politykę `selected-image-board-band-v5-blue-priority-multicolumn`.
  Przywraca sprawdzony profil niebieskiego panelu, ale używa go wyłącznie do
  zawężenia wyniku już popartego wielokolumnowo i rozszerzonego ku panelowi
  wypłat. Nie zastępuje nim `safe_wide`.
- Zachowano walidację zapisanych propozycji v4 oraz jawne, checksum-bound
  przeliczenie wyłącznie wyników nieprzejrzanych.
- `safe_wide` jest automatycznie dodawany do trwałej kolejki korekty.

### Verification

- `npm run test --workspace @game-predictor/manual-image-selection-core` —
  49/49 passed;
- skoncentrowane testy kontraktu storage/workspace Admina — 15/15 passed;
- typecheck core i Admin — passed;
- skoncentrowany ESLint zmienionych plików Admina — passed;
- produkcyjny build Admina — passed.
