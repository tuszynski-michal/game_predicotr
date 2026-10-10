---
title: TASK-0871 — kontrakt zapisu symbol-rgb-v2 w writerze
status: done
last_updated: 2026-10-06
---

# TASK-0871 — kontrakt zapisu symbol-rgb-v2 w writerze

## Status

`done`

## Goal

Writer zapisuje rewizję `symbol-rgb-v2` (pewna 0,99, do przeglądu 0,50, wpis `rgbV2` z pochodzeniem); zapis, weryfikacja i cofnięcie działają dla nowej wersji; side-effect na komórce spoza celów kończy planszę jako stale zamiast zatrzymywać przebieg.

## Context

Etap A planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
(zaakceptowany przez operatora 2026-10-05). Metoda i ograniczenia:
`ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`.

## Dependencies / entry conditions

- Plan zaakceptowany; poprzednie taski etapu A wykonane w kolejności planu.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (zgodnie z tabelą planu; audyt wstrzymany
przez operatora 2026-10-01).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- `reference_library_writer.py`: polityka zapisu jako parametr (wersja, aktor, pewność, wpis), dotychczasowe zachowanie biblioteki bez zmian.
- Zapis/weryfikacja/cofnięcie manifestów RGB v2.
- Wpis D-520 w `DECISION_LOG.md`.

## Out of scope

- Zapis w bazie operatora (etap B), trening i zmiana checkpointu CNN,
  zatwierdzanie komórek, geometria.

## Acceptance criteria

- [x] Testy writera: pewna, do przeglądu, cel na komórce starej biblioteki, side-effect jako stale.
- [x] Test PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`) zapisu i cofnięcia jednej planszy.
- [x] Stare testy biblioteki bez zmian zielone.

## Test cases

- `services/worker/tests/test_symbol_reference_library_writer.py` + test integracyjny PG.

## Outcome

- `reference_library_writer.py`: `WritePolicy` (wersja, aktor, pochodzenie
  przebiegu), `LIBRARY_POLICY` (domyślna, zachowanie biblioteki bez zmian),
  `rgb_v2_policy`, `RgbTarget` w `TargetCell`. Cel RGB v2 dostaje pewność
  0,99/0,50, wpis `rgbV2` (status, CNN, biblioteka, głosy, poprzedni symbol,
  pewność i źródło, pierwotna pewność modelu, sumy checkpointu, biblioteki i
  przebiegu); `referenceLibrary` tej komórki znika. Zapis odrzuca planszę jako
  `stale:cell_changed`, gdy pewność komórki różni się od podglądu.
  `apply_board`/`revert_board` przyjmują politykę; aktor w zdarzeniach
  `system:symbol-rgb-v2`.
- `scripts/symbol_rgb_v2.py`: `apply`, `verify`, `revert` dla manifestu
  `symbol-rgb-v2-apply-manifest-v1`; `SYMBOL_REFERENCE_WRITE_SIDE_EFFECT` i
  `SYMBOL_REFERENCE_TARGET_QUALITY_CHANGED` kończą planszę jako `stale` i
  przebieg idzie dalej (cofnięcie zawsze się zatrzymuje).
- D-520 w `DECISION_LOG.md`.
- Testy: writer 12 PASS (3 nowe dla RGB v2), `test_symbol_rgb_v2.py` 32 PASS
  (plan planszy, manifest, stany odczytu, równość wersji z filtrem API),
  integracyjny PostgreSQL `test_symbol_rgb_v2_writer_postgres.py` PASS: zapis
  pewnej i niepewnej komórki, `already_applied`, ochrona pewności
  (`stale:cell_changed`), filtry `rgb_v2`/`rgb_v2_tentative`/`model`/
  `reference_library`, cofnięcie. Ruff, format i mypy `--strict` bez uwag.
