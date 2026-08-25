---
title: Attested seq range image import
status: done
release: '0.6'
last_updated: 2026-08-19
---

# TASK-0247 — Import zakresów `seq_*`

## Goal

Ufać poprawnie zwalidowanej nazwie `seq_<start>-<end>.jpg|jpeg` przy imporcie
layoutów i całkowicie pominąć kosztowny OCR numerów.

## Outcome

Managed manifest przechowuje źródło oraz granice zakresu, sortowanie jest
numeryczne, a duplikaty i nakładanie są odrzucane. Adapter
`sequence-number-from-attested-range-v1` przypisuje numery row-major wyłącznie
przy pełnej geometrii; częściowe wykrycie trafia do korekty bez przesuwania
numerów. Dodano regresje parsera, sortowania i częściowej geometrii.

W v0.6.39/v0.6.40 domknięto źródło manifestu dla browser stagingu oraz start
jobów: API i worker korzystają z `_browser_manifest.json`, gotowe stagingi są
odzyskiwalne po restarcie, a Admin wymaga checksumowanego preflightu przed
idempotentnym utworzeniem joba. Bieżący staging 2201 zdjęć przechodzi read-only
preflight z 19746 nowymi i 63 użytymi ponownie numerami; nie został jeszcze
uruchomiony.
