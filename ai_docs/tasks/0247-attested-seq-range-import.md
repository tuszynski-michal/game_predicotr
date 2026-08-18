---
title: Attested seq range image import
status: done
release: '0.6'
last_updated: 2026-08-18
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
