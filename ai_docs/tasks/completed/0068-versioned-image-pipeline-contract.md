---
title: Versioned image pipeline contract
status: done
last_updated: 2026-07-29
---

# TASK-0068 — Versioned image pipeline contract

## Status

`done`

## Goal

Zdefiniować i zweryfikować jeden kanoniczny kontrakt wersji całego pipeline’u
obrazów oraz deterministyczną tożsamość wyniku per plik, zanim TASK-0069 doda
trwałą orkiestrację i checkpointy.

## Context

M5–M6 dostarczyły osobno wersjonowane discovery, normalizację, geometrię, OCR,
cropper symboli, ONNX i confidence policy. M7 nie może identyfikować pracy
wyłącznie nazwą pliku albo ogólnym `pipeline_version`, ponieważ zmiana modelu,
kalibracji lub geometrii ma tworzyć nowy wynik bez nadpisania starego.

Aktualny model symboli jest zaakceptowany wyłącznie jako bootstrap
`manual-review-only`. Kontrakt może go wskazywać wraz z tą polityką, ale nie
może na tej podstawie włączyć auto-accept ani masowego importu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kanoniczny `image-pipeline-manifest-v1` ze wszystkimi adapterami, modelami,
  checksumami, progami/politykami i jawnie uporządkowanymi etapami,
- deterministyczny `pipelineFingerprint` z kanonicznych bajtów manifestu,
- deterministyczny `fileExecutionKey` z checksumy źródła i fingerprintu,
- kontrakt stanu etapu i checkpointu, który TASK-0069 będzie utrwalać,
- walidacja wersji, SHA-256, względnych ścieżek, dojrzałości modeli oraz
  granicy `waiting_for_review`,
- schema JSON, golden manifest i testy driftu/reprodukowalności.

## Out of scope

- tabele PostgreSQL, migracje i endpointy jobów,
- lease, wykonywanie, anulowanie i wznawianie workera,
- uruchomienie discovery/geometrii/OCR/ONNX na katalogu,
- zapis recognized boards, review items albo stagingu,
- auto-accept, retraining, publikacja datasetu i masowy import.

## Acceptance criteria

- [x] manifest wskazuje wersje discovery, normalizacji, detektora, croppera,
  OCR, klasyfikatora ONNX, kalibracji i confidence policy,
- [x] wymagane artefakty modeli mają checksumy, a ścieżki są względne POSIX,
- [x] bootstrap/manual-review-only jest zapisane jawnie i wymusza
  `waiting_for_review`,
- [x] identyczny manifest daje identyczny fingerprint niezależnie od kolejności
  kluczy JSON,
- [x] zmiana modelu, checksumy, polityki albo etapu zmienia fingerprint i
  `fileExecutionKey`,
- [x] ten sam plik i pipeline mają jeden idempotency key, a inny pipeline nie
  może nadpisać wyniku,
- [x] kolejność etapów i dozwolone przejścia checkpointu są jawne oraz
  walidowane,
- [x] niepoprawna wersja, checksum, ścieżka, duplikat etapu albo brak review
  boundary kończą się stabilnym kodem,
- [x] schema, golden manifest, testy, Ruff i typecheck przechodzą.

## Technical notes

- Fingerprint nie zawiera ścieżek absolutnych, timestampów ani host-specific
  danych.
- Checkpoint z TASK-0068 jest kontraktem wartości, nie persistence. TASK-0069
  zdecyduje o mapowaniu do tabel i transakcjach.
- Stage order v1:
  `discovery → normalization → board_detection → board_crops → sequence_ocr →
  symbol_inference → manual_review → validation`.
- `manual_review` nie może zostać pominięte przy obecnej polityce modelu i OCR.
- Zmiana dowolnej wersji modelu albo adaptera wymaga nowego fingerprintu; nie
  nadpisuje historycznych artefaktów.

## Expected files

- `services/worker/src/game_predictor_worker/images/pipeline_contract.py`
- `services/worker/tests/test_image_pipeline_contract.py`
- `scripts/build_m7_image_pipeline_manifest.py`
- `ai_docs/quality/image-pipeline-manifest-v1.schema.json`
- `ai_docs/quality/m7-image-pipeline-manifest-v1.json`
- dokumentacja architektury, testów, decyzji i bieżącego stanu

## Verification

```powershell
python -m pytest --basetemp .pytest-tmp/task-0068 services/worker/tests/test_image_pipeline_contract.py
python -m ruff check services/worker/src/game_predictor_worker/images/pipeline_contract.py services/worker/tests/test_image_pipeline_contract.py
python -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/images/pipeline_contract.py
```

## Risks / open questions

- Finalny model OCR nadal nie jest wybrany; kontrakt musi przechowywać jego
  bieżący status `manual_review_only`, a nie udawać gotowość produkcyjną.
- TASK-0069 może wymagać migracji jobów, ale nie może zmienić fingerprintu ani
  semantyki idempotencji bez nowej wersji kontraktu.

## Outcome

Wypełnia agent po pracy.

### Changed

- dodano czysty kontrakt `image-pipeline-manifest-v1`, envelope,
  `pipelineFingerprint`, `image-file-execution-v1` i persistence-neutral
  `image-pipeline-file-checkpoint-v1`,
- manifest obejmuje osiem uporządkowanych etapów, wszystkie bieżące wersje
  adapterów, OCR, ONNX, preprocessing, kalibrację i confidence policy,
- wymagane artefakty mają względne ścieżki POSIX oraz zweryfikowane SHA-256;
  brak pliku lub drift checksumy kończy się fail-closed,
- checkpoint dopuszcza wyłącznie uporządkowany prefiks i przejście idempotentne
  albo o jeden etap; oba modele `manual_review_only` wymuszają
  `waiting_for_review`,
- dodano generator/checker goldenu, schema JSON i 20 testów kontraktu.

### Verification results

- `python scripts/build_m7_image_pipeline_manifest.py --check` — passed,
- focused pytest — `20 passed in 0.64s`,
- Ruff check — passed,
- Ruff format check — passed,
- bounded mypy z `--follow-imports=skip` — passed,
- `pipelineFingerprint`:
  `16f601f7fae76ccc79e23a47869a0e695a5592dbf2e0639af1b3f37a3a925d96`,
- SHA-256 golden envelope:
  `a5b5eefd8a2c05b45d4b61b8e1eb22b93131101e80eaf0211cfff7406cae57b5`.

### Not completed

- nie dodano persistence, migracji, orkiestracji, lease, cancellation ani
  rzeczywistego wykonania etapów; to zakres TASK-0069,
- nie promowano OCR ani klasyfikatora i nie włączono auto-accept,
  auto-reject ani masowego importu.

### Documentation updates

- zaktualizowano IMAGE_INGESTION, SYSTEM_ARCHITECTURE, TEST_STRATEGY,
  MILESTONE_07_EXECUTION_PLAN, CURRENT_STATE i DECISION_LOG,
- zaakceptowano D-078.

### Recommended next task

- `TASK-0069 — Batch orchestration, checkpoints and cancellation`.
