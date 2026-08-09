---
title: TASK-0212 image-selection tail telemetry
status: in_progress
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
mapowanie; porównanie realnej trudnej końcówki pozostaje w TASK-0218.
