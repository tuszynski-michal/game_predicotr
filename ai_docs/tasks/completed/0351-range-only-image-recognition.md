---
title: TASK-0351 Range-only image recognition
status: done
last_updated: 2026-08-31
---

# TASK-0351 — Range-only OCR

## Status

`done`

## Goal

Wydzielić wersjonowany adapter Paddle OCR, który rozpoznaje wyłącznie mocny
lokalny dowód zakresu `seq_*` i nie uruchamia geometrii, croppera, symboli ani
oceny jakości plansz.

## Context

TASK-0350 zdefiniował niezależne od frameworków kontrakty zakresów i
`RangeEvidenceGate`. Ten task mapuje istniejący proof-first OCR na te kontrakty
bez implementowania grupowania, joba albo API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- range-only port i adapter dla RGB,
- bridge do istniejącego Paddle OCR i strong local range proof,
- obsługa końcowego częściowego expected range,
- checksumowana kalibracja limitu kolejnych źródeł bez dowodu,
- testy braku wywołań geometrii, jakości i symbol inference.

## Out of scope

- migracje, SQL, staging, joby, API i UI,
- grupowanie oraz wybór środkowego zdjęcia,
- walidacja plansz, geometrii, ostrości, ekspozycji i symboli.

## Acceptance criteria

- [x] Tylko mocny lokalny proof może dać `exact_range`.
- [x] Adapter wykonuje jedną analizę OCR RGB i przekazuje pusty zestaw plansz.
- [x] Jakość obrazu nie jest wejściem ani bramką adaptera.
- [x] Końcowy częściowy expected range jest mapowany tylko z pozycyjnego proof.
- [x] Limit przerwy jest odtwarzalny z checksumowanego corpus.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/range_only_ocr.py`
- `services/worker/tests/test_semi_automatic_selection_range_only_ocr.py`
- `services/worker/tests/fixtures/semi_automatic_range_gap_calibration_v1.json`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_semi_automatic_selection_range_only_ocr.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_semi_automatic_selection_range_only_ocr.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
```

## Risks / open questions

- Produkcyjny bridge zachowuje historyczny proof-first OCR, ale celowo nie
  przekazuje mu wykrytych plansz. Jego lattice route musi pozostać jedyną
  aktywną trasą w tym workflow.

## Outcome

- Dodano czysty port RGB, adapter bramki zakresu i bridge do istniejącego
  proof-first Paddle OCR bez wejścia geometrii lub jakości.
- Końcowy częściowy zakres jest obsługiwany fail-closed na podstawie co
  najmniej trzech zgodnych dowodów pozycyjnych.
- Checksumowany korpus 283 rzeczywistych źródeł kalibruje maksymalną serię bez
  proof na 160; funkcja nie implementuje grupowania.
- Skoncentrowane testy, Ruff i mypy przechodzą.
