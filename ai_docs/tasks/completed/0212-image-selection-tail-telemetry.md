---
title: TASK-0212 image-selection tail telemetry
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0212 — Telemetria trudnych partii

## Goal

Raportować bounded okno postępu, poziomy OCR, consensus i czasy etapów bez
wpływu telemetrii na decyzję selektora.

## Verification

Mapowanie checkpoint → API oraz parity wyniku z baseline'em.

## Outcome

Checkpoint oraz odpowiedź joba zawierają bounded `recentWindow`, czasy etapów,
liczniki OCR/konsensusu, cache i persistence. Testy workera oraz API potwierdzają
mapowanie. Automatyczna regresja rzeczywistego wycinka `29640–29739` z
2026-08-09 potwierdziła działanie telemetrii na sześciu trudnych grupach:
OCR zajął 219,648 s z 254,422 s całego przebiegu, geometria 26,906 s,
wykonano 15 nieudanych prób anchored OCR i 68 prób fallback OCR. Dane nie
zmieniły decyzji selektora, a 149 skupionych testów workera i API przeszło.
