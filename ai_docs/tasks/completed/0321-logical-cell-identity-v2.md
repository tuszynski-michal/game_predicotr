---
title: TASK-0321 logical cell identity v2
status: done
last_updated: 2026-08-30
---

# TASK-0321 — Tożsamość logicznej komórki v2

## Status

`done`

## Goal

Oddzielić domenową tożsamość wystąpienia komórki od tożsamości bajtów JPEG-a,
bez przepisywania historycznych kluczy `logical-cell-v1` i bez migracji danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Wprowadzić czysty, wersjonowany kontrakt wystąpienia źródła oparty na
  `importJobId + fileExecutionKey`.
- Wprowadzić fingerprint topologii obejmujący przypiętą wersję reguł, wymiary
  oraz wersję semantyki slotów.
- Wyliczać `logical-cell-v2` z wystąpienia źródła, fingerprintu topologii,
  slotu planszy i współrzędnych komórki.
- Zachować niezmieniony klucz v1 i emitować oba klucze w wersjonowanym
  render spec oraz w wewnętrznych payloadach pipeline'u.
- Wprowadzić osobną tożsamość renderu v2; v1 pozostaje odtwarzalna.
- Przenieść wystąpienie źródła przez automatyczny pipeline oraz ręczny
  source-direct preview/save.
- Udokumentować kontrakt i decyzję kompatybilnościową.

## Out of scope

- Bez migracji Alembic, nowych kolumn i backfillu.
- Bez zmiany istniejących wartości `logical_cell_key` w bazie.
- Bez przełączania odczytów, indeksów, canonical ownership i verified labels.
- Bez edycji migracji 0082 albo niezacommitowanej 0083.
- Bez aktywacji rolloutu geometrii lub fallbacku keypoint.

## Acceptance criteria

- [x] Ten sam rekord źródłowy i ta sama pozycja zachowują v2 po recropie.
- [x] Dwa importy identycznych bajtów mają różne logical-cell-v2.
- [x] Zmiana topologii lub semantyki slotów zmienia logical-cell-v2.
- [x] Historyczne logical-cell-v1 i render-id-v1 pozostają bitowo niezmienione.
- [x] Render spec jawnie zawiera wersje oraz klucze v1 i v2.
- [x] Automatyczna i ręczna ścieżka wyliczają wystąpienie z tego samego
  `importJobId + fileExecutionKey`.
- [x] Testy domeny, API i workera przechodzą bez migracji bazy.

## Expected files

- `services/api/src/game_predictor_api/domain/image_geometry_v2.py`
- `services/api/src/game_predictor_api/application/virtual_grid_geometry.py`
- `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
- `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- testy odpowiadających modułów
- dokumentacja modelu danych, ingestion, decyzji i current state

## Risks

- Pole `logical_cell_key` pozostaje kluczem v1 do czasu osobnej addytywnej
  migracji. Klucz v2 jest w tym zadaniu utrwalany wyłącznie w checksumowanym
  render spec/payloadzie, dlatego nie wolno jeszcze przełączyć indeksowanych
  odczytów na v2.
- `fileExecutionKey` jest technicznie stabilnym identyfikatorem pliku w ramach
  importu. Powtórzenie tego samego pliku w innym jobie celowo tworzy inne
  wystąpienie domenowe.

## Planned commit

`v0.10.14 - add logical cell identity v2 contract`

## Outcome

Wprowadzono `SourceOccurrence`, fingerprint topologii oraz deterministyczne
`logical-cell-v2` i `render-id-v2`. Historyczne klucze v1 pozostały bez zmian;
ich niezmienność jest chroniona testem golden. Render spec v2 oraz payloady
predykcji przechowują równolegle klucze v1/v2, occurrence i fingerprint
topologii.

Automatyczny workflow korzysta z `job_id + file_execution_key`, a ręczny
preview/save odtwarza tę samą parę z `source_images`. Historyczne manualne
manifesty bez pola v2 nadal można odczytać. Nie dodano migracji, kolumn ani
backfillu i nie przełączono canonical ownership ani indeksowanych odczytów.

Weryfikacja:

- 14 testów domeny/API — passed;
- 5 testów source-direct renderera — passed;
- 33 testy production image workflow — passed;
- test proweniencji prediction revision — passed;
- Ruff i format check — passed;
- scoped mypy dla czterech zmienionych modułów kontraktu — passed.

Pełny import-following mypy ujawnił cztery istniejące błędy w
`virtual_cell_previews.py`, `image_imports.py` i `image_job_repository.py`;
moduły te nie zostały zmienione w TASK-0321.
