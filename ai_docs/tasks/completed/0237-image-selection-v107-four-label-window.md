---
title: TASK-0237 image-selection v10.7 four-label sequence window
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0237 — Zakres z czterech kolejnych etykiet

## Goal

Rozpoznawać pełny dziewięcioelementowy zakres na podstawie dowolnego czytelnego
ciągu czterech kolejnych etykiet we właściwych pozycjach siatki, bez wymagania
OCR wszystkich dziewięciu numerów i bez kosztownego rozszerzania każdej próby do
72 cropów.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/DECISION_LOG.md`

## Outcome

Domyślny `fast-image-selector-v10.7` ma fingerprint
`322d4f5319f036cd0e1dc01f2dc781e68cb0a17dbb05f25abba409f842a732d6`.
Nowy adapter `visible-sequence-label-range-v7` dopasowuje trzy wiersze i trzy
kolumny z położeń wykrytych etykiet, przypisuje OCR do pozycji row-major i
akceptuje dowolne cztery kolejne pozycje. Przykładowo odczyt `1–4` w pozycjach
0–3 oraz `5–8` w pozycjach 4–7 prowadzą do zakresu `1–9`.

Równe hipotezy, trzy etykiety, zła geometria albo zbyt niska pewność kończą się
fail-closed. Progresja OCR v10.7 wynosi `9 -> 18 -> 36`; historyczne v10.5 i
v10.6 zachowują swoje adaptery, poziomy i fingerprinty. Przeszło 187 skupionych
testów API/workera, w tym pełna regresja historycznego przypadku 55–63.
