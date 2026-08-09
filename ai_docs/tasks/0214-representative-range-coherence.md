---
title: TASK-0214 representative-range coherence
status: in_progress
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0214 — Spójność reprezentanta z zakresem

## Goal

Nie eksportować JPEG-a z zakresem rozpoznanym wyłącznie na innym ekranie tej
samej błędnie scalonej grupy.

## Verification

Regresja z klatkami `1_040014` i `1_040025`; wynik dzieli grupę albo wymaga
review, nigdy nie tworzy błędnego `seq_18406-18414.jpg`.

## Outcome

Selektor v10.2 sprawdza kandydatów w kolejności jakości i automatycznie wybiera
wyłącznie reprezentanta potwierdzającego zakres grupy. Brak zgodnego dowodu daje
`REPRESENTATIVE_RANGE_UNKNOWN` albo `REPRESENTATIVE_RANGE_MISMATCH` i
`manual_required`. Test regresyjny obejmuje błędny ekran oraz bezpieczny fallback;
odbiór na rzeczywistym wycinku pozostaje w TASK-0218.
