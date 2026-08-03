---
title: TASK-0151 image selection domain contract and storage
status: done
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0151 — Image selection domain contract and storage

## Status

`done`

## Goal

Utworzyć trwały, game-scoped i idempotentny model runu, grup oraz kandydatów
selekcji zdjęć bez zapisywania obrazów w PostgreSQL.

## Context

Run obejmujący do 30 000 plików nie może istnieć wyłącznie jako duży obiekt w
pamięci lub checkpoint JSON. Potrzebuje migracji, jawnych constraintów,
wersjonowanego payloadu joba i typowanego kontraktu API przed implementacją UI
oraz algorytmu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_07_0_EXECUTION_PLAN.md`

## Scope

- dodać przez Alembic job type `image_selection`,
- dodać `image_selection_runs`, `image_selection_groups` i
  `image_selection_candidates`,
- wymusić dodatnie zakresy, kolejność grup, unikalny kandydat oraz bezpieczne
  względne ścieżki,
- zapisać selector fingerprint, input manifest SHA-256 i ordering policy,
- dodać idempotentne utworzenie i odczyt runu oraz bounded listę grup,
- dodać stabilne kody błędów i wygenerować klienta OpenAPI,
- zaktualizować DATA_MODEL i API_CONTRACT zgodnie z finalnym schematem.

## Out of scope

- upload plików,
- quality scoring, OCR i grupowanie,
- output JPEG oraz handoff,
- manualny modal,
- benchmark skali.

## Acceptance criteria

- [x] Schema powstaje wyłącznie przez migrację Alembic i przechodzi offline upgrade.
- [x] Run jest jednoznacznie związany z grą i jednym jobem `image_selection`.
- [x] Kandydaci zachowują deterministyczny `order_index`, ścieżkę, checksumę i
      metadane, ale nie zawierają BLOB.
- [x] Grupa może mieć rozpoznany dodatni zakres albo jawny stan unknown.
- [x] Ta sama gra, manifest i selector fingerprint zwracają ten sam run.
- [x] Listy są bounded i stronicowane; API nie zwraca 30 000 rekordów naraz.
- [x] Stabilne błędy nie ujawniają ścieżek absolutnych.
- [x] OpenAPI oraz wygenerowany klient nie mają driftu.

## Technical notes

Nie kopiować `recognized_boards` ani `image_review_items`. Selekcja nie jest
pełnym pipeline'em i ma własne lekkie projekcje. Exact nazwy kolumn muszą
zachować terminologię `range_start`, `range_end`, `group_order` oraz
`selector_fingerprint`.

## Expected files

- `services/api/alembic/versions/*_image_selection.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/domain/`
- `services/api/src/game_predictor_api/application/`
- `services/api/src/game_predictor_api/api/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests -q
npm.cmd run openapi:check
```

## Risks / open questions

- Migracja enum PostgreSQL musi być zgodna z istniejącą strategią downgrade i
  nie może zmieniać historycznych jobów.

## Outcome

- Dodano migrację `0025_image_selection`, enum joba oraz trzy tabele z
  constraintami zakresów, kolejności, względnych ścieżek i pojedynczego wyboru.
- Dodano czysty model domenowy, repozytorium SQLAlchemy i serwis z idempotency
  key `(game_id, input_manifest_sha256, selector_fingerprint)`.
- Dodano `POST /image-selections`, `GET /image-selections/{runId}` i bounded
  `GET /image-selections/{runId}/groups` z kursorem `afterGroupOrder`.
- Job `image_selection` jest widoczny w wspólnym monitorze, ale ogólny endpoint
  jobów nie może ominąć dedykowanego workflow źródła.
- Testy domeny/API/migracji: 37 passed. OpenAPI i wygenerowany klient są aktualne,
  a TypeScript klienta przechodzi typecheck.
- Online `alembic upgrade head` nie został wykonany, ponieważ lokalny PostgreSQL
  nie odpowiadał i po 5 sekundach zgłosił `ConnectionTimeout`. Migracja przeszła
  generowanie i asercje offline; przy następnym uruchomieniu bazy należy wykonać
  `npm.cmd run db:migrate` przed testem integracyjnym.
