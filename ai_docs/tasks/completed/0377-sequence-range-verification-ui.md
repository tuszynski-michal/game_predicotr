---
title: TASK-0377 — Weryfikacja zakresów w Ręcznej Selekcji
status: done
version: 0.10
---

# TASK-0377 — Weryfikacja zakresów w Ręcznej Selekcji

## Goal

Pozwolić operatorowi przeskanować katalog `seq_*`, zobaczyć progres i przejść
wyłącznie przez pliki nieczytelne albo niezgodne z nazwą.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0376-sequence-range-verification-backend.md`

## Scope

- Nowa sekcja `Weryfikacja zakresów` w zakładce Ręczna Selekcja.
- Jeden katalog `seq_*`, przycisk Start i trwały lokalny upload do Admin API.
- Progres `przetworzone/wszystkie` i pasek postępu.
- Po analizie viewer pokazuje wyłącznie mismatch, unreadable i invalid filename.
- `F` usuwa checksum-bound plik przez istniejący repair manifest, bez undo.
- Pliki zweryfikowane pozostają nietknięte.

## Out of scope

- Uzupełnianie luk (pozostaje w istniejącym workflow).
- Zmiana OCR i bazy danych.

## Acceptance criteria

- [x] Widać aktualny progres runu.
- [x] Manualna kolejka zawiera tylko niepewne/niezgodne pliki.
- [x] F usuwa dokładnie oglądany plik i natychmiast przechodzi dalej.
- [x] Brak automatycznego usuwania oraz brak cofania.

## Expected commit

`v0.10.79 - add sequence range verification workspace`

## Outcome

Dodano niezależną sekcję pod lokalnymi workflowami. Operator wybiera katalog
`seq_*`, uruchamia trwały pełny skan i widzi osobno postęp uploadu oraz joba.
Po analizie poprawne pliki są ukryte, a viewer pokazuje wyłącznie mismatch,
unreadable i invalid filename wraz z oczekiwanym oraz odczytanym zakresem.
Klawisz `F` usuwa wyłącznie aktualny plik przez istniejący checksum-bound
repair manifest i kieruje powstałą lukę do `Uzupełnij luki`.

Weryfikacja: 8 testów Admina, 24 testy shared core oraz typecheck Admina i
klienta API przeszły.
