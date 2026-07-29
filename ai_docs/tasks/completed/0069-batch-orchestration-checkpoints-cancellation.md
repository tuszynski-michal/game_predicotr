---
title: Batch orchestration, checkpoints and cancellation
status: done
last_updated: 2026-07-29
---

# TASK-0069 — Batch orchestration, checkpoints and cancellation

## Status

`done`

## Goal

Utrwalić i wykonać persistence-neutral kontrakt TASK-0068 jako wznawialną
orkiestrację batcha per plik, korzystając z istniejących jobs, lease, fencing i
bezpiecznego anulowania.

## Context

TASK-0068 zdefiniował `pipelineFingerprint`, `fileExecutionKey`, osiem etapów
oraz checkpoint per plik. Istniejący worker zapewnia już jeden globalny slot,
60-sekundowy lease, odzyskanie osieroconego joba, fencing token i anulowanie na
checkpointcie. Brakuje trwałego rejestru wykonania per plik oraz handlera,
który potrafi kontynuować batch bez dublowania wyniku.

Aktualne OCR i klasyfikator pozostają `manual-review-only`. Orkiestrator musi
przetworzyć diagnostycznie pozostałe pliki, a dopiero po jednym pełnym przebiegu
zatrzymać job w `waiting_for_review`.

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

- migracja Alembic trwałych `image_file_executions` i
  `image_import_job_files`,
- globalna unikalność wyniku po `fileExecutionKey` oraz idempotentne powiązanie
  wyniku z wieloma jobami,
- repozytorium seeding/query/checkpoint/statistics z blokadą i walidacją
  przejścia TASK-0068,
- handler batcha wykonujący po jednym etapie pliku i zapisujący wynik pliku
  przed checkpointem joba,
- wznowienie od trwałego checkpointu po restarcie lub utracie lease,
- cancellation wyłącznie po bezpiecznym checkpointcie bez publikacji,
- pełny przebieg plików niewymagających review przed przejściem joba do
  `waiting_for_review`,
- testy idempotencji, model drift, restartu, cancellation, review i jednego
  globalnego slotu.

## Out of scope

- rzeczywiste wykonanie discovery, normalizacji, geometrii, OCR i ONNX,
- endpoint tworzenia image importu i inspekcja katalogu wejściowego,
- zapis recognized boards, observations, review items i stagingu,
- izolacja trwałych błędów pojedynczego pliku oraz retry z UI,
- publikacja datasetu, payout, snapshot i APK,
- auto-accept, retraining i zmiana modelu.

## Acceptance criteria

- [x] ten sam SHA-256 źródła i pipeline mają jeden trwały
  `image_file_execution`,
- [x] zmiana `pipelineFingerprint` tworzy nowy wynik bez nadpisania starego,
- [x] wiele jobów może wskazać ten sam wynik bez duplikowania checkpointu,
- [x] zapis pliku poprzedza checkpoint joba, więc restart może bezpiecznie
  powtórzyć wyłącznie niedokończony etap,
- [x] checkpoint przechodzi idempotentnie albo o jeden etap i jest fenced przez
  aktywny job lease,
- [x] cancellation zatrzymuje handler na najbliższym checkpointcie i nie
  uruchamia walidacji ani publikacji po anulowaniu,
- [x] plik oczekujący na review nie blokuje diagnostycznego przebiegu
  pozostałych plików,
- [x] po pełnym przebiegu nierozwiązane review ustawia job
  `waiting_for_review`,
- [x] globalny istniejący `execution_slot = 1` nadal ogranicza worker do jednego
  ciężkiego joba,
- [x] migracja upgrade/downgrade, testy, Ruff i typecheck przechodzą.

## Technical notes

- `image_file_executions.file_execution_key` jest PK i nie zawiera job ID.
- `image_import_job_files` przechowuje deterministyczny `order_index` oraz
  względną ścieżkę diagnostyczną; wynik pozostaje content-addressed.
- Początkowy file checkpoint ma status `processing`, pusty `completedStages` i
  `nextStage = discovery`.
- Po `symbol_inference` orkiestrator zapisuje `waiting_for_review`, ale
  kontynuuje inne pliki. Retry rewaliduje każdy waiting file najwyżej raz na
  przebieg.
- Licznik review jest kumulacyjny (`review_required`), aby nie regresował po
  późniejszym zaakceptowaniu planszy.
- Handler przyjmuje port wykonania etapu. TASK-0070 podłączy prawdziwe adaptery.

## Expected files

- `services/api/alembic/versions/0016_image_batch_orchestration.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/jobs/runtime.py`
- `services/worker/src/game_predictor_worker/images/orchestration.py`
- `services/worker/src/game_predictor_worker/images/orchestration_store.py`
- `services/worker/tests/test_image_batch_orchestration.py`
- `services/api/tests/test_image_batch_orchestration_migration.py`
- `services/api/tests/integration/test_image_batch_store.py`
- dokumentacja architektury, modelu danych, testów i bieżącego stanu

## Verification

```powershell
python -m pytest --basetemp .pytest-tmp/task-0069 services/worker/tests/test_image_batch_orchestration.py services/api/tests/test_image_batch_orchestration_migration.py
python -m ruff check services/worker/src/game_predictor_worker/images/orchestration.py services/worker/src/game_predictor_worker/images/orchestration_store.py services/worker/tests/test_image_batch_orchestration.py
python -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/images/orchestration.py services/worker/src/game_predictor_worker/images/orchestration_store.py
```

## Risks / open questions

- PostgreSQL może nie działać lokalnie; migracja i repozytorium muszą mieć test
  modelu/SQL, a fizyczny test pozostaje jawnym skipem, jeżeli baza jest
  niedostępna.
- Globalny wynik może być współdzielony przez joby tylko dla identycznego
  `fileExecutionKey`; ścieżka źródłowa pozostaje właściwością powiązania joba,
  nie tożsamości bajtów.
- Nie istnieje jeszcze produkcyjny stage executor. Brak rejestracji niepełnego
  handlera w CLI jest zamierzoną granicą do TASK-0070.

## Outcome

Wypełnia agent po pracy.

### Changed

- dodano odwracalną migrację `0016_image_orchestration` oraz mapowania
  `image_file_executions` i `image_import_job_files`,
- globalny `fileExecutionKey` deduplikuje identyczne źródło/pipeline między
  jobami, a osobna asocjacja zachowuje order i względną ścieżkę,
- `SqlAlchemyImageBatchStore` rejestruje pliki idempotentnie, wybiera pracę
  bounded, liczy statystyki i zapisuje checkpoint przy aktywnym fenced lease,
- `ImageBatchHandler` wykonuje po jednym etapie, zapisuje plik przed jobem,
  wznawia po awarii, zatrzymuje cancellation i nie blokuje pozostałych plików
  przez pojedyncze review,
- wspólny `JobExecutionContext` udostępnia handlerom wyłącznie bieżący token
  fencing i wstrzyknięty zegar potrzebny do transakcji domenowej,
- dodano test jednostkowy, offline migration test oraz opt-in izolowany test
  PostgreSQL z `connect_timeout=3`.

### Verification results

- finalny focused pytest — `48 passed, 1 skipped in 4.25s`,
- skip: fizyczny PostgreSQL wyłączony; port `127.0.0.1:5432` był niedostępny,
- próba fizyczna miała timeout 60 s; pozostałe procesy pytest zostały
  zidentyfikowane i zakończone, a test dostał `connect_timeout=3`,
- Ruff check — passed,
- Ruff format check — passed,
- bounded mypy dla orkiestracji/runtime z jawnym `MYPYPATH` — passed,
- mypy dla modeli i migracji — passed,
- `git diff --check` — passed.

### Not completed

- nie podłączono discovery, geometrii, OCR, ONNX, review storage ani stagingu;
  to TASK-0070,
- nie dodano endpointu tworzenia image importu ani rejestracji niepełnego
  handlera w CLI,
- fizyczny test PostgreSQL nie został zaliczony przy wyłączonej lokalnej bazie;
  pozostaje gotowy jako opt-in, bounded test.

### Documentation updates

- zaktualizowano DATA_MODEL, SYSTEM_ARCHITECTURE, TECH_STACK, TEST_STRATEGY,
  MILESTONE_07_EXECUTION_PLAN i CURRENT_STATE,
- zaakceptowano D-079 i oznaczono G7.1 jako passed.

### Recommended next task

- `TASK-0070 — End-to-end image processing into staging`.
