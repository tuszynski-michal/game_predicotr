---
title: Virtual partial fully unavailable gate
status: done
last_updated: 2026-09-25
---

# TASK-0662 — poprawna topologia częściowych komórek virtual v3

## Status

`done`

## Goal

Poprawnie odroczyć zatwierdzoną częściową planszę virtual v3 bez fałszywego
naruszenia invariantu `topology`.

## Context

Job `b70f4fce-dc1a-411b-9c3d-49ae41ec02a6` miał pięć plansz z komórkami
częściowo widocznymi. Renderer zachował ich cropy, ale gate porównał je z pełną
maską jakości i błędnie wymagał ich pominięcia.

## Dependencies / entry conditions

- TASK-0661 dostarcza zatwierdzony disposition `partial` i kwalifikację v3.
- `fullyUnavailableCellIndices` jest walidowaną podmaską
  `unavailableCellIndices`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Użycie maski całkowicie niedostępnych pól dla topology cropów virtual v3.
- Regresja dokładnie odtwarzająca częściowo widoczne pola z joba.

## Out of scope

- Usuwanie zdjęć, zmiana progu 98% i osłabianie rzeczywistych invariantów.

## Acceptance criteria

- [x] Częściowo widoczne pola virtual v3 nie powodują `topology`.
- [x] Całkowicie niedostępne pole pozostaje wyłączone z cropów i plansza jest
  odroczona do manual review.
- [x] Nieoznaczony niekompletny crop nadal jest topologiczny.

## Technical notes

`unavailableCellIndices` jest szerokim sygnałem jakości. Tylko dla poprawnej,
zatwierdzonej kwalifikacji v3 i `assetMode=virtual_source` zestaw wymaganych
tożsamości cropów wyprowadza się z `fullyUnavailableCellIndices`; w pozostałych
kontraktach obowiązuje historyczna maska.

## Expected files

- `services/worker/src/game_predictor_worker/images/grid_profile_end_to_end_gate.py`
- `services/worker/tests/test_grid_profile_end_to_end_gate.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Test cases

- Maska jakości `[0, 5, 6, 10, 11]`, maska całkowitego braku `[10]` i 14
  cropów → zero `topology`, `operator_partial`.
- Nieoznaczony zestaw 14 cropów → `topology`.

## Outcome

### Changed

- Gate weryfikuje zestaw renderów v3 względem
  `fullyUnavailableCellIndices`, nadal fail-closed walidując szeroką maskę
  jakości oraz historyczne kontrakty.
- Dodano regresję dla 14 cropów, pięciu pól częściowo widocznych i jednego
  pola całkowicie niedostępnego.

### Verification results

- Ruff dla zmienionych plików: czysty.
- 78/78 testów gate, geometry guard i production workflow: przeszło.

### Not completed

- Nie usuwano zdjęć ani nie modyfikowano istniejących jobów.

### Documentation updates

- Doprecyzowano semantykę obu masek w `IMAGE_INGESTION.md`.

### Recommended next task

- Utworzyć świeży reprocess na nowej wersji kontraktu i obserwować jego wynik.
