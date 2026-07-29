---
title: End-to-end image processing into staging
status: done
last_updated: 2026-07-29
---

# TASK-0070 — End-to-end image processing into staging

## Status

`done`

## Goal

Połączyć istniejące, wersjonowane adaptery discovery, normalizacji, geometrii,
OCR i klasyfikacji ONNX z orkiestratorem TASK-0069 oraz zapisać pełne
pochodzenie rozpoznanych plansz i komórek w domenowym stagingu oczekującym na
manual review.

## Context

TASK-0068 zdefiniował kanoniczny manifest i tożsamość wyniku per plik, a
TASK-0069 dodał trwałe checkpointy, lease fencing i przetwarzanie batcha.
Rzeczywiste adaptery M5–M6 nie są jeszcze podłączone do `ImageBatchHandler`,
a PostgreSQL nie przechowuje domenowych wyników konkretnego importu.

Aktualne OCR i klasyfikator pozostają `manual_review_only`. TASK-0070 nie może
automatycznie zaakceptować predykcji ani opublikować datasetu. Wyniki mają
trafić do review, a staging layoutu może powstać dopiero z kompletnej,
zaakceptowanej decyzji planszy.

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

- migracja Alembic i modele trwałych `source_images`, `recognized_boards`,
  `cell_observations` oraz image-layout stagingu,
- produkcyjny executor etapów korzystający z wymiennych portów istniejących
  adapterów M5–M6,
- deterministyczne mapowanie jednego source image na plansze row-major i
  dokładnie 15 obserwacji komórek na planszę,
- zapis raw OCR, predykcji symboli, confidence, alternatyw, geometrii,
  względnych ścieżek artefaktów, checksum i `pipelineFingerprint`,
- utworzenie elementu manual review z pełnym snapshotem planszy,
- materializacja staging row wyłącznie po kompletnej zaakceptowanej decyzji
  manual review,
- walidacja ciągłości jako diagnostyka bez poprawiania OCR i bez cichego
  przesuwania numerów,
- test pionu od wejścia adapterów do trwałego stagingu i śladu provenance.

## Out of scope

- publiczny endpoint tworzenia image-directory joba i ekran operacyjny,
- stabilne błędy per plik, kontynuacja po wyjątku i selektywny retry etapu;
  to TASK-0071,
- auto-accept, auto-reject albo zmiana progów modeli,
- ponowne trenowanie OCR lub klasyfikatora,
- publikacja datasetu, payout, SQLite albo APK,
- masowy benchmark katalogu i decyzja o kolejce.

## Acceptance criteria

- [x] każdy source image jest związany z jobem, globalnym file execution i
  pełnym `pipelineFingerprint`,
- [x] każdy recognized board zachowuje pozycję row-major, raw OCR, geometrię,
  confidence oraz wersje adapterów,
- [x] każda plansza ma dokładnie 15 unikalnych obserwacji row-major z
  checksum-bound cropem i predykcją ONNX,
- [x] nierozwiązany wynik kończy się w `waiting_for_review` i nie tworzy
  zaakceptowanego staging row,
- [x] kompletna zaakceptowana decyzja materializuje jeden idempotentny staging
  layout z zaakceptowanym numerem i komórkami,
- [x] continuity jedynie zgłasza problemy i nie zmienia wartości OCR,
- [x] ponowienie tego samego zapisu nie duplikuje source, board, cell, review
  ani staging records,
- [x] migracja upgrade/downgrade, testy, Ruff i typecheck przechodzą.

## Technical notes

- globalny `image_file_execution` pozostaje content-addressed; `source_images`
  opisuje jego użycie w konkretnym jobie,
- binaria pozostają w lokalnym storage, a PostgreSQL przechowuje tylko
  względne ścieżki, checksumy i metadane,
- staging planszy jest oddzielony od istniejącego stagingu plików CSV/JSONL,
  ale docelowo mapuje się na ten sam kontrakt `sequence_number + cells`,
- model `manual_review_only` wymusza atomową decyzję całej planszy przed
  materializacją stagingu.

## Expected files

- `services/api/alembic/versions/0017_image_processing_staging.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/images/pipeline_execution.py`
- `services/worker/src/game_predictor_worker/images/pipeline_store.py`
- focused tests worker/API/migration
- dokumentacja architektury, modelu danych, testów i bieżącego stanu

## Verification

Komendy zostaną doprecyzowane po zamknięciu mapowania adapterów. Każda komenda
otrzyma jawny timeout; fizyczny PostgreSQL pozostanie testem opt-in.

## Risks / open questions

- istniejące adaptery M5 mają zarówno czyste porty per obraz, jak i historyczne
  runnery korpusowe; TASK-0070 ma użyć małego produkcyjnego composera zamiast
  kopiować logikę runnerów benchmarkowych,
- obecne modele wymagają manual review, więc test end-to-end użyje
  deterministycznych adapterów testowych, a osobne testy istniejących adapterów
  nadal chronią ich rzeczywistą implementację,
- izolacja trwałego błędu pojedynczego pliku należy do TASK-0071 i nie może być
  zasymulowana jako częściowy sukces w tym zadaniu.

## Outcome

### Changed

- dodano migrację `0017_image_processing` i mapowania sześciu tabel:
  niezmienne wyniki etapów, źródła, recognized boards, cell observations,
  operacyjne review M7 i zaakceptowany staging layoutów,
- dodano `ImageDirectoryBatchSeeder` korzystający z prawdziwego
  `image-discovery-v1`, manifestowy adapter discovery i wersjonowany composer
  sześciu etapów automatycznych,
- composer waliduje provenance, kolejność pozycji oraz dokładnie 15 komórek
  row-major i zapisuje wynik etapu pod aktywnym lease,
- projekcja po symbol inference tworzy pełny snapshot review; predykcja nie
  trafia do stagingu bez kompletnej decyzji planszy,
- `SqlAlchemyImagePipelineStore` obsługuje atomowe accept/correct/reject,
  aktywny katalog symboli, mapowanie na `mobile_code`, idempotentną
  materializację i diagnostykę ciągłości,
- `ImageBatchCandidate` przenosi do executorów job, fencing token i czas zapisu,
  nie zmieniając semantyki checkpointu TASK-0069.

### Verification results

- focused orchestration/composer/migration pytest:
  `31 passed in 4.18s`,
- regresja rzeczywistych adapterów discovery, normalization, geometry, crop,
  OCR i ONNX: `61 passed in 44.70s`; 9 ostrzeżeń pochodzi z przyszłej zmiany
  API PyTorch treespec i nie wpływa na wynik,
- Ruff check i Ruff format check — passed,
- bounded mypy dla czterech modułów orkiestracji/pipeline — passed,
- import SQLAlchemy metadata potwierdził wszystkie sześć nowych tabel,
- `git diff --check` — passed.

### Not completed

- `worker-v4` nie przyjmuje jeszcze publicznego image-directory joba; jego
  rejestracja wymaga izolacji wyjątków per plik i rehydratacji globalnego reuse
  w TASK-0071,
- nie uruchomiono fizycznej migracji PostgreSQL, ponieważ lokalny serwer nie
  był dostępny w poprzednim zadaniu; offline Alembic upgrade/downgrade przeszedł,
- nie dodano UI review ani operacji joba; należą do M7.3.

### Documentation updates

- zaktualizowano DATA_MODEL, SYSTEM_ARCHITECTURE, TECH_STACK, TEST_STRATEGY,
  MILESTONE_07_EXECUTION_PLAN i CURRENT_STATE,
- zaakceptowano D-080 oddzielającą operacyjne review M7 od batchy active
  learning M6.

### Recommended next task

- `TASK-0071 — Failure isolation, retry and idempotency`.
