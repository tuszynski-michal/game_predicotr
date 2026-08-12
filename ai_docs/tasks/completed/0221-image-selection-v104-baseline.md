---
title: TASK-0221 image selection v10.4 baseline
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0221 — Baseline v10.4

## Goal

Zamrozić porównanie v9, v10.2 i v10.3 oraz znane regresje grupowania,
rozpoznawania zakresu i nazewnictwa przed aktywacją v10.4.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

Testy deterministyczne obejmują rozbicie jednego ekranu na kilka grup,
przeniesienie pierwszej klatki następnego ekranu, błąd nazwy zakresu oraz
odczyty OCR z jedną błędną albo brakującą cyfrą. Duże zbiory pozostają poza
automatycznym odbiorem tego zadania.

## Outcome

Zamrożono historyczne manifesty i fingerprinty v9–v10.3. Dodano syntetyczne
regresje dla false merge, przeniesionej klatki następnego ekranu, błędu
`7300 -> 300`, konfliktu fuzzy OCR oraz wyboru reprezentanta całej grupy. Nie
uruchamiano zbiorów właściciela.
