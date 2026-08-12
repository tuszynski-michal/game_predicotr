---
title: TASK-0214 representative-range coherence
status: done
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
`manual_required`. Test regresyjny obejmuje błędny ekran oraz bezpieczny fallback.

Rzeczywisty read-only profil indeksów `29640–29739` objął klatki
`1_040014.jpg` i `1_040025.jpg`. Mieszana grupa rozpoznała dowód
`18406–18414`, ale nie znalazła spójnego reprezentanta, dlatego zakończyła się
`manual_required`, bez wybranego checksumu i bez automatycznego pliku
`seq_18406-18414.jpg`. Tym samym reprodukowany false merge jest zamknięty
bez hardcode'u konkretnego numeru.
