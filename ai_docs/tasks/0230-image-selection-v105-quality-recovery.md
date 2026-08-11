---
title: TASK-0230 image selection v10.5 quality recovery
status: in_progress
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0230 — Selekcja zdjęć v10.5

## Goal

Odrzucić nieskuteczną ścieżkę grid-only v10.4 i połączyć poprawniejsze
rozpoznawanie zakresów v10.3 z lekkim, bounded wyborem reprezentanta oraz
bezpiecznym buforem granicy grupy.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0228-image-selection-v104-acceptance.md`

## Baseline

Realny run v10.4 `edf8625d-776c-4a73-8db9-29115fe05c14` przetworzył 42 403
JPEG-i w 5 377,373 s. Utworzył 3 840 grup: 436 automatycznych, 3 388 manualnych
i 16 pominiętych. Manual rate wyniósł 88,23%. Tylko 452 grupy miały znany
zakres. Z 7 680 prób grid OCR 7 401 zakończyło się
`RANGE_LABEL_GRID_NO_HYPOTHESIS`.

## Implementation

- osobny manifest `fast-image-selector-v10.5` i niezmienny fingerprint,
- szeroki descriptor wyglądu v10.3 z buforem granicy v10.4,
- lekki verifier bez pełnej klasycznej geometrii,
- niezależny endpoint OCR `18 -> 36 -> 72` uruchamiany dla kandydatów
  `1 -> 2 -> 4`,
- exact może zakończyć dowód po jednym JPEG-u, fuzzy wymaga dwóch zgodnych,
- reprezentant musi sam potwierdzić ten sam zakres; konflikty pozostają manualne,
- `selectorVersion` w API i historii zapisanych procesów.

## Acceptance

- regression set: zero błędnego zakresu, reprezentanta i nazwy,
- próbka około 5 000 zdjęć: co najmniej 95% znanych zakresów, najwyżej 35%
  manualnych grup i projekcja pełnego runu do pięciu godzin,
- pełne 42 403 zdjęcia dopiero po przejściu obu wcześniejszych bramek.

## Outcome

Implementacja jest gotowa, a domyślny manifest ma wersję
`fast-image-selector-v10.5` i fingerprint
`6ba81ff5a277c92a0cbf01b88aea7f8c896eee76aebb8323b2ed9cb4b3e28a32`.
Selektor wrócił do szerokiego descriptoru wyglądu, zachował bezpieczny bufor
granic v10.4 i zastąpił nieskuteczny grid-only OCR lekkim, progresywnym OCR
końców zakresu. Dokładny dowód może zakończyć się po jednym kandydacie, natomiast
fuzzy wymaga dwóch zgodnych odczytów. Reprezentant nadal musi sam potwierdzić
zakres grupy.

Backend zwraca `selectorVersion`, a lista zapisanych procesów pokazuje ją obok
daty i statusu. Kontrakt odbioru zapisano w
`ai_docs/quality/image-selection-v105-acceptance-contract.json`.

Automatyczna weryfikacja przeszła: Ruff, mypy, kontrola OpenAPI, typecheck panelu
i klienta, 137 testów workera, 19 testów API oraz 186 testów Admina. Nie
uruchomiono prób na rzeczywistych 200/5000/42403 JPEG-ach. Zadanie pozostaje
`in_progress` do czasu zaliczenia tych bramek i ręcznej oceny właściciela.
