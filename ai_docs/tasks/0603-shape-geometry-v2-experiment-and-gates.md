---
title: TASK-0603 Shape geometry v2 experiment and input contract
status: in_progress
last_updated: 2026-09-21
---

# TASK-0603 — Eksperyment i kontrakt wejścia geometrii shape v2

## Goal

Utworzyć rozszerzalny, read-only kontrakt eksperymentu G01 dla obecnych i
przyszłych gier z pełną ramką oraz deterministyczne raportowanie wariantów
kształtu, kontrastu, pomocniczego koloru, kotwicy lokalnej i profilu transferu.
Brak danych musi być stanem `not_evaluable` per gra/źródło, a nie blokadą
niezależnych prac G02–G07.

## Context

G00 ukończył fail-closed korpus dla pięciu początkowych gier. Właściciel
potwierdził, że podział danych dotyczy rodzin zdjęć, nie gier; geometria ma być
wspólna i ponownie używana przez Mumie, Gang i kolejne gry. Treasure bez ramki
pozostaje poza v2. Wersja kwalifikowanej wiedzy aktywuje się automatycznie po
testach jakości; liczby polityki jakości wybiera wykonawca tylko z danych
executor, nigdy z acceptance ani z pustego mianownika.

## Dependencies / entry conditions

- G00 w `c1e063d3`.
- Brak lokalnego atestowanego corpusów nie blokuje implementacji kontraktu,
  narzędzia ani testów. Ogranicza jedynie realny pomiar do `not_evaluable`.
- Acceptance nie jest wejściem do G01.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0602-shape-geometry-v2-corpus-baseline.md`
- `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

- Zachować rygory G00 dla manifestu schema v1 i dodać wersjonowaną drogę dla
  zgodnych późniejszych gier bez stałej listy nazw.
- Dostarczyć runner eksperymentu z checksumą danych, anotacji, profilu,
  wariantu algorytmu i wyników oraz z jawnymi mianownikami.
- Wymusić, aby wariant transferowy badanej gry nie zawierał jej źródeł,
  kotwic ani wkładów do profilu wspólnego.
- Utrzymać read-only charakter: bez importu, joba i zapisu do bazy.
- Zapisać reguły parametrów i statusy dowodów potrzebne G02.

## Out of scope

- Silnik v2, migracje, API, UI, import i aktywacja biblioteki.
- Użycie albo ujawnienie acceptance.
- Samodzielne przypisanie nieatestowanych JPEG-ów do gry.

## Acceptance criteria

- [ ] Stary manifest G00 zachowuje walidację i fingerprint; nowy schema nie
      przyjmuje danych acceptance ani zarezerwowanych Reels.
- [ ] Nowa zgodna gra może otrzymać status per źródło bez forka silnika.
- [ ] Runner rozdziela mianowniki i raportuje `not_evaluable` dla brakujących
      dowodów.
- [ ] Transfer wykrywa udział badanej gry jako błąd fail-closed.
- [ ] Testy pokrywają zgodność wsteczną, drift, split i transfer.

## Expected files

- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/`
- `services/worker/tests/test_shape_geometry_v2_*.py`
- `scripts/run_shape_geometry_v2_experiment.py`
- `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

W trakcie realizacji.
