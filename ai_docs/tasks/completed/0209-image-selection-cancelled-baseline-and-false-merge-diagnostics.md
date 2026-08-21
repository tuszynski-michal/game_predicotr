---
title: TASK-0209 cancelled baseline and false-merge diagnostics
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0209 — Cancelled baseline and false-merge diagnostics

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`

## Goal

Zachować odrzucony run 32 079 jako diagnostyczny baseline, udokumentować
spowolnienie końcówki oraz false merge `18406-18414 / 18415-18423` bez uznania
anulowanego wyniku za odbiór jakościowy.

## Verification

- raport i logi są zachowane,
- wskazano źródło błędnej nazwy i status joba,
- kolejny duży run pozostaje wstrzymany.

## Outcome

Run zakończył się jako `cancelled` przy 29 888 / 32 079 źródłach, 2121 grupach,
1813 zapisanych plikach i 30 590,702 s pracy. Monitor PID 18844 zakończył się,
a kolejny run pozostaje wstrzymany. Diagnostyka została zapisana w
`ai_docs/quality/image-selection-v101-cancelled-run-diagnostic.json`.

Grupa 2109 połączyła co najmniej dwa ekrany. Dowód zakresu pochodził z klatek
`1_040014` i `1_040016`, a wybrany reprezentant `1_040025` przedstawiał już
następny zakres. Wynik bramki właściciela to `rejected`.
