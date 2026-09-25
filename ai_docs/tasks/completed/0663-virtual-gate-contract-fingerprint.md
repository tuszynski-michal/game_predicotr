---
title: Virtual gate contract fingerprint
status: done
last_updated: 2026-09-25
---

# TASK-0663 — świeży fingerprint po naprawie geometry gate

## Status

`done`

## Goal

Zapewnić, że ręczny reprocess wykonuje poprawiony geometry gate, zamiast
bezpiecznie zwracać historyczny raport z poprzednim kontraktem.

## Context

Job v3 jest immutable i zawiera błędny wynik bramki sprzed TASK-0662. Reprocess
jest idempotentny względem fingerprintu, dlatego konieczna jest nowa wersja
kontraktu wejściowego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Bump `VIRTUAL_CELL_RENDERER_VERSION` do v4 i aktualizacja opisu kontraktu.
- Test rebindu manual continuation i utworzenie świeżego reprocessu.

## Out of scope

- Modyfikacja historycznych jobów, usuwanie zdjęć i zmiana danych gry.

## Acceptance criteria

- [x] Manual continuation tworzy osobny job z rendererem v4.
- [x] Historyczny job v3 pozostaje niezmieniony.

## Technical notes

Snapshot rolloutu zawiera wersję rendererową w pipeline fingerprint. API już
przepisuje tylko tę wersję podczas manual continuation, zachowując model,
geometrię i pozostałe przypięte dowody.

## Expected files

- `services/worker/src/game_predictor_worker/images/pipeline_contract.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `services/api/tests/test_managed_reprocess_evidence.py`

## Outcome

### Changed

- Kontrakt virtual renderer podniesiono do v4; snapshot manual continuation
  automatycznie wiąże aktualną wersję przy zachowaniu pozostałych dowodów.

### Verification results

- Testy API reprocessu: 9/9 przeszło.
- Ruff dla zmienionego kontraktu: czysty.

### Not completed

- Reprocess produkcyjny zostanie utworzony po restarcie workera z v4.

### Documentation updates

- Wymaganie renderera wskazuje wersję v4.

### Recommended next task

- Obserwacja joba v4 do zakończenia lub ręcznego review.
