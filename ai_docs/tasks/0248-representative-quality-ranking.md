---
title: Representative quality ranking cohort and shadow MLP
status: done
release: '0.6'
last_updated: 2026-08-18
---

# TASK-0248 — Kohorta i shadow ranker MLP

## Goal

Zebrać pewne etykiety z ręcznej selekcji i przygotować lekki model rankingu
reprezentantów bez zmiany segmentacji ani decyzji selektora.

## Outcome

Dodano content-addressed kohortę cech, deterministyczny pairwise split i trening
`representative-quality-mlp-v1` (`8→16→8→1`, ReLU, ONNX FP32). Worker może
przypiąć snapshot joba w trybie `shadow`; diagnostyka zapisuje rekomendacje,
zgodność z heurystyką i checksum modelu. Dodano migrację tabel kohort,
iteracji i historii aktywacji. Promocja pozostaje zablokowana do bramek jakości
i jawnej akceptacji właściciela.
