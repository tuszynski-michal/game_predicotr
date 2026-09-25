---
title: Virtual crop contract fingerprint
status: in_progress
last_updated: 2026-09-25
---

# TASK-0660 — fingerprint reprocessu po zmianie kontraktu virtual cropów

## Status

`done`

## Goal

Zapewnić, że zmiana semantyki virtual cropów tworzy nowy idempotentny reprocess,
zamiast zwracać wcześniejszy job i jego immutable raport błędu.

## Context

Endpoint reprocessu zwrócił job `51b256c4-1ff5-4a94-a764-d54ee15390da`, bo
zmieniony worker nie zmienił snapshotu ani fingerprintu pipeline'u.

## Dependencies / entry conditions

- TASK-0659 jest dostarczony w `0b5a1035`.
- Żaden stary raport ani dane źródłowe nie będą nadpisywane.

## Recommended execution

`gpt-6-sol`, reasoning `high`: wersja renderera jest częścią snapshotu,
fingerprintu i tożsamości wykonania. Niezależny review tylko po błędzie
zgodności starych snapshotów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Bump wersji kontraktu renderera virtual do v2 i rebind managed manual
  continuation z historycznego snapshotu v1, zachowując jego odczyt.
- Test kontraktu i utworzenie nowego live reprocessu.

## Out of scope

- Usuwanie raportów, retry starego joba, zmiany zdjęć lub modelu geometrii.

## Acceptance criteria

- [ ] Nowy pipeline fingerprint różni się od joba `51b256c4-1ff5-4a94-a764-d54ee15390da`.
- [ ] Historyczny snapshot v1 nadal parsuje się, a manual continuation tworzy
  jego snapshot v2.

## Technical notes

Wersja renderera jest zamrożona w `imageGeometryRollout`, a checksum tego
snapshotu wchodzi do efektywnego fingerprintu pipeline'u. Bump jest wymagany
dla zmiany klasyfikacji outputu i nie modyfikuje już istniejących jobów.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/pipeline_contract.py`.
- Istniejące: `ai_docs/requirements/IMAGE_INGESTION.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_pipeline_contract.py services/api/tests/test_managed_reprocess_evidence.py
```

## Outcome

### Changed

- Wersja `virtual-cell-renderer-source-direct-v2` zamraża nową semantykę
  odraczania virtual cropów w rollout snapshot i efektywnym fingerprintie.
- Manual continuation odczytuje historyczny snapshot, lecz zawsze buduje nowy
  rollout snapshot z tym kontraktem renderera; nie modyfikuje źródłowego joba
  ani jego raportu.

### Verification results

- `test_managed_reprocess_evidence.py`: 9/9 przeszło, w tym idempotentny
  rebind snapshotu v1 do v2.
- `test_image_pipeline_contract.py`: 25/26 przeszło; jeden wcześniejszy błąd
  `IMAGE_PIPELINE_ARTIFACT_DRIFT` dla
  `ai_docs/quality/m5-image-benchmark-report.json`, pliku poza zakresem taska.

### Not completed

- Nie naprawiano niezwiązanego driftu artefaktu benchmarkowego.

### Documentation updates

- Zaktualizowano `IMAGE_INGESTION.md` i `CURRENT_STATE.md`.

### Recommended next task

- Przeładować API i worker, następnie utworzyć nowy reprocess z ręczną geometrią.
