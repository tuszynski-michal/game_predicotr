---
title: TASK-0227 image selection v10.4 contract and telemetry
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0227 — Kontrakt i telemetria v10.4

## Goal

Dodać niezmienny manifest v10.4, jawny numer pierwszej sekwencji w panelu i
skryptach oraz telemetrię kosztu grupowania, siatki i OCR.

## Relevant docs

- `ai_docs/tasks/completed/0224-image-selection-v104-hybrid-ranges.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Verification

Historyczne fingerprinty zachowują stare zachowanie, v10.4 wymaga kotwicy,
resume jest deterministyczne, a raport pokazuje najwyżej 18 cropów OCR na grupę.

## Outcome

Domyślny manifest to `fast-image-selector-v10.4` o fingerprintcie
`8e913c923036ba7aa3f448d1049a37676d133b603103d0b641912ef17004ee7e`.
Admin, API, skrypt live, standalone CLI i worker egzekwują dodatnią kotwicę,
natomiast starsze fingerprinty pozostają rozwiązywalne. Telemetria rozdziela
próby/sukcesy `gridOcr`, liczbę cropów OCR i weryfikacje dowodu zakresu.
