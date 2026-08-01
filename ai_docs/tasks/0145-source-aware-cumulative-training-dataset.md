---
title: TASK-0145 source-aware cumulative training dataset
status: todo
last_updated: 2026-08-01
---

# TASK-0145 — Source-aware cumulative training dataset

## Status

`todo`

## Goal

Zbudować odtwarzalny dataset treningowy ze skumulowanej kohorty, z
deterministycznym podziałem według źródła i bez przecieku danych.

## Context

Wiele cropów z jednego zdjęcia jest silnie skorelowanych. Losowy podział po
cropach zawyżałby wynik i mógłby promować gorszy model.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/0143-cumulative-verified-training-cohort-contract.md`

## Scope

- materializować dataset z niezmiennego manifestu kohorty,
- walidować checksumy cropów, kompletność etykiet i katalog symboli gry,
- grupować po zdjęciu źródłowym i pochodnych tego samego materiału,
- tworzyć deterministyczne train/validation/test oraz stabilny regression set,
- generować manifest, statystyki per symbol/źródło/split i listę wykluczeń,
- zapisywać artefakt content-addressed,
- zapewnić identyczny wynik dla identycznego wejścia.

## Out of scope

- trening modelu,
- zmiana geometrii lub ponowne wycinanie cropów,
- ręczne uzupełnianie etykiet,
- aktywacja modelu.

## Acceptance criteria

- [ ] Identyczna kohorta i konfiguracja dają identyczny manifest i SHA-256.
- [ ] Żadne zdjęcie źródłowe ani jego pochodne nie występują w więcej niż
      jednym split.
- [ ] Dataset zawiera wyłącznie etykiety zapisane przez człowieka dla pełnych
      `accepted` i `corrected` plansz.
- [ ] Brak pliku, niezgodna checksum lub nieznany symbol zatrzymuje build przed
      treningiem ze stabilnym kodem błędu.
- [ ] Raport pokazuje niedoreprezentowane klasy oraz rozmiary wszystkich części.
- [ ] Stały regression set nie jest dołączany do train.
- [ ] Artefakty są zapisane pod `data/training`, a baza przechowuje ścieżki i
      metadata zamiast obrazów.

## Technical notes

Trening kolejnej wersji używa całej skumulowanej kohorty, nie tylko nowych
przykładów. Seed, polityka splitu i wersja transformacji są częścią fingerprintu.

## Expected files

- `services/worker/src/game_predictor_worker/symbols/`
- `services/worker/tests/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/worker/tests -q
python -m pytest services/api/tests -q
```

## Risks / open questions

- Mała liczba niezależnych zdjęć może uniemożliwić reprezentatywny test mimo
  dużej liczby cropów; raport musi to ujawnić.

## Outcome

Do uzupełnienia po realizacji.
