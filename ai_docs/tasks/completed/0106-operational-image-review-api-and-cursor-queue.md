---
title: Operational image review API and cursor queue
status: done
last_updated: 2026-07-29
completed_at: 2026-07-29
---

# TASK-0106 — Operational image review API and cursor queue

## Status

`done`

## Goal

Udostępnić osobny, job-local kontrakt Admin API dla operacyjnych
`image_review_items`, z bounded nawigacją, pełnym detailem planszy i atomowym,
idempotentnym zapisem całej decyzji do audytu oraz stagingu.

## Context

Istniejące `/review-batches` obsługuje bounded active learning M6 i nie może
zostać rozszerzone do tysięcy operacyjnych plansz. M7 utrwala już
`image_review_items`, `image_review_resolution_events`,
`cell_observations` oraz `image_layout_staging_rows`. TASK-0106 wystawia nad
nimi dedykowany kontrakt, bez nowej tabeli i bez kopiowania decyzji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wymagać `gameId` i `importJobId` dla każdego odczytu oraz zapisu,
- dodać widoki `pending` i `completed`,
- zwracać dokładne liczniki statusów bez ładowania całej kolejki,
- dodać opaque cursor poprzedni/następny i skok do `sequenceNumber`,
- zachować stabilną kolejność pending po źródle/pozycji, a completed po
  zaakceptowanym numerze,
- zwracać detail źródła, planszy, geometrii bazowej i dokładnie 15 komórek,
- zwracać maksymalnie cztery alternatywy symbolu,
- dodać item-scoped endpointy obrazów pod zarządzanym `artifact-root/data`,
- zapisywać accepted/corrected/rejected jako append-only event,
- materializować dokładnie jeden staging row dla accepted/corrected,
- pozwolić ponownie edytować completed jako kolejną rewizję,
- generować klienta TypeScript wyłącznie z OpenAPI.

## Out of scope

- implementacja ekranu — TASK-0107 i TASK-0108,
- korekta geometrii i nowe cropy — TASK-0109,
- eksport kohorty oraz retraining — TASK-0110,
- zdalny dostęp — M8.7,
- ręczne testy nowego ekranu; właściciel wykona je po ukończeniu TASK-0111.

## Acceptance criteria

- [x] każdy endpoint odrzuca grę albo job spoza kontekstu elementu,
- [x] kursory są bounded, opaque, scope-bound i deterministyczne,
- [x] pending/completed zwracają poprawne liczniki i kolejność,
- [x] detail ma dokładnie 15 komórek i maksymalnie cztery alternatywy,
- [x] accepted/corrected/rejected są atomowe oraz append-only,
- [x] exact retry nie dodaje eventu ani staging row,
- [x] stale revision oraz reuse UUID dla innej komendy zwracają `409`,
- [x] completed można zapisać ponownie jako nową rewizję,
- [x] accepted/corrected ma dokładnie jeden aktualny staging row,
- [x] OpenAPI i wygenerowany klient TypeScript są zgodne.

## Expected files

- `services/api/src/game_predictor_api/domain/image_reviews.py`
- `services/api/src/game_predictor_api/application/image_reviews.py`
- `services/api/src/game_predictor_api/application/image_review_assets.py`
- `services/api/src/game_predictor_api/storage/image_review_repository.py`
- `services/api/src/game_predictor_api/schemas/image_reviews.py`
- `services/api/src/game_predictor_api/api/image_reviews.py`
- composition root i wygenerowany klient OpenAPI,
- `services/api/tests/test_image_reviews.py`
- dokumentacja procesu

## Assumptions and decisions

- Obecna immutable geometria pipeline'u jest rewizją bazową `0`; TASK-0109
  doda append-only rewizje korekt i zmieni aktywny `cropSampleId`.
- `cropSampleId` v1 wynika deterministycznie z board, pozycji, croppera,
  względnej ścieżki i checksumy cropu.
- Ponowna edycja completed aktualizuje pojedynczą projekcję stagingu, ale
  poprzednia decyzja pozostaje w append-only events.
- Ręczne testy całego nowego ekranu są odroczone do odbioru TASK-0111.
- Każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Outcome

Wdrożono osobne `/api/v1/admin/image-review-items` z wymaganym kontekstem
gry/import joba, widokami pending/completed, licznikami, deterministycznymi
opaque cursorami, skokiem do sequence, pełnym detailem 15 komórek i
checksum-bound assetami. Decyzja całej planszy jest walidowana jako jedna
operacja, używa expected revision i UUID idempotencji, dopisuje event oraz
materializuje pojedynczy staging row; completed można poprawić kolejną rewizją.

OpenAPI i klient TypeScript zostały ponownie wygenerowane. Walidacja:

- `ruff check` — passed,
- `mypy services/api/src services/worker/src scripts` — passed,
- `pytest services/api/tests` — `187 passed, 16 skipped`,
- testy TASK-0106 i kontraktu — `12 passed`,
- generated-client check i TypeScript typecheck — passed.

Integracyjny scenariusz PostgreSQL sprawdza rejected → corrected, exact retry,
ponowną korektę, trzy append-only eventy i jeden aktualny staging row. W tym
środowisku jest kontrolowanie pominięty bez
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`. Testy ręczne ekranu nie należą do tego
zadania i zgodnie z decyzją właściciela odbędą się po TASK-0111.
