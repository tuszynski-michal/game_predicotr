---
title: TASK-0617 — kwalifikowane próbki profilu V1.2
status: done
---

# TASK-0617 — kwalifikowane próbki profilu V1.2

## Status

`done`

## Goal

Zwykły profil pełnej strony V1.2 korzysta wyłącznie z kompletnych, niewykluczonych korekt danej gry.

## Context

Sama obecność dziewięciu par quadów nie oznacza, że wszystkie plansze mogą uczyć zwykły profil. Kwalifikacja operatora jest nadrzędna.

## Dependencies / entry conditions

- T01 zapisuje istniejące kwalifikacje slotów.
- Snapshot profilu preflightu pozostaje niezmienny po utworzeniu joba.

## Recommended execution

`gpt-5.6-terra`, reasoning `high`. Własny audyt przed commitem, bez dodatkowego review Astra. Eskalacja jest potrzebna, jeśli trzeba zmienić politykę oddzielnego uczenia niepełnych siatek.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Sprawdzać kompletność i wykluczenie każdego slotu przed włączeniem źródła do profilu V1.2.
- Zachować istniejący profil osobnego uczenia bocznych niepełnych siatek.
- Nie zmieniać rejestracji kontrastowej, progów ani kodu V1.0/V1.1/V2.

## Out of scope

- Odblokowanie importu V1.2.

## Acceptance criteria

- [x] Źródło z niepełnym albo wykluczonym slotem nie jest zwykłą kotwicą V1.2.
- [x] Kompletna, niewykluczona korekta pozostaje źródłem profilu.
- [x] Opt-in niepełnej siatki trafia do oddzielnej puli, bez zmiany przypiętego joba.

## Technical notes

Brak kwalifikacji w starszej, poprawnej parze oznacza dotychczasowe zachowanie. Niepoprawna kwalifikacja wyklucza próbkę, zamiast usuwać oznaczenie operatora.

## Expected files

- `services/worker/src/game_predictor_worker/images/contrast_frame_grid_v12.py` — builder profilu.
- `services/worker/tests/test_contrast_frame_grid_v12.py` — regresja kwalifikacji.
- Dokumenty wymagań, architektury i stanu.

## Test cases

- Pełne, niepełne i wykluczone źródło w jednym snapshotcie → tylko pełne w zwykłym profilu; opt-in niepełnego w oddzielnej puli.
- Niewystarczający kontrast i różne kolory pozostają objęte istniejącymi testami rejestracji.

## Verification

Skoncentrowane testy workera, Ruff, format oraz kontrola diffu.

## Outcome

### Changed

- Filtrowanie profilu według kwalifikacji przed parsowaniem ręcznej pary.

### Verification results

- Skoncentrowane testy kontrastowego silnika: 6 zaliczonych.
- Ruff lint i format oraz kontrola diffu: zaliczone.

### Not completed

- Podłączenie V1.2 do importu należy do następnego zadania.

### Documentation updates

- Wymagania, architektura i `CURRENT_STATE.md`.

### Recommended next task

- T03: bezpieczna bramka i cięcie V1.2 podczas importu.
