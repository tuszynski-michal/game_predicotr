---
title: Import quality, recovery and review throughput benchmark
status: done
last_updated: 2026-07-29
---

# TASK-0075 — Import quality, recovery and review throughput benchmark

## Status

`done`

## Goal

Zamknąć G7.4 pomiarem jakości zaakceptowanego pipeline'u oraz fizycznym testem
PostgreSQL obejmującym restart po trwałym checkpointcie, izolowane awarie
każdego etapu automatycznego, dokładny retry i przepustowość operacyjnego
manual review.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- checksum-bound odczyt zaakceptowanych raportów jakości M5/M6,
- osobne raportowanie geometrii, OCR i klasyfikatora bez zmiany progów,
- fizyczny profil PostgreSQL dla 43 plików i 387 plansz/5805 komórek,
- kontrolowany crash po pierwszym trwałym file checkpointcie,
- po jednej izolowanej awarii w każdym z sześciu etapów automatycznych,
- retry dokładnego `nextStage` bez powtarzania wcześniejszych etapów,
- zapis 387 idempotentnych decyzji review i pomiar throughput,
- końcowe materializowanie stagingu i walidacja ciągłości 1–387,
- kanoniczny raport bez sekretów i ścieżek absolutnych,
- deadline wewnętrzny i zewnętrzny timeout PowerShell.

## Out of scope

- ponowny trening, zmiana modelu lub progów confidence,
- rzeczywiste tempo pracy człowieka w UI; mierzymy trwały zapis decyzji,
- publikacja datasetu, payouty, snapshot i APK — TASK-0076,
- decyzja o kolejce — TASK-0077 wykorzysta wyniki TASK-0074 i TASK-0075,
- masowy auto-accept, jeśli istniejący quality gate nadal go zabrania.

## Acceptance criteria

- [x] źródła jakości są weryfikowane przez SHA-256 i mają jawne provenance,
- [x] raport nie przedstawia synthetic operational fixture jako pomiaru jakości ML,
- [x] crash po checkpointcie nie powtarza zakończonego etapu,
- [x] awaria każdego etapu jest izolowana do jednego pliku,
- [x] retry zaczyna się od dokładnego failed `nextStage`,
- [x] pozostałe pliki kończą diagnostykę przed granicą review,
- [x] 387 decyzji review zapisuje się bez utraty i ma zmierzony throughput,
- [x] staging zawiera 387 ciągłych layoutów i 5805 komórek,
- [x] wynik jawnie blokuje albo dopuszcza auto-accept i masowy import,
- [x] raport przechodzi walidator oraz ma kontrolowane timeouty,
- [x] focused testy, lint i typecheck przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/operations_benchmark.py`
- `scripts/run_m7_operations_benchmark.py`
- `scripts/run_m7_operations_benchmark.ps1`
- `services/worker/tests/test_image_operations_benchmark.py`
- `ai_docs/quality/m7-import-operations-benchmark-report.json`
- `package.json`
- dokumentacja procesu, architektury i testów

## Risks / open questions

- Aktualny raport M6 ma `massImportAllowed = false` i
  `manualReviewShare = 1.0`. Benchmark nie może zmienić tej decyzji samym
  dobrym wynikiem persistence/recovery.
- Synthetic operational fixture mierzy orkiestrację i bazę, nie czas dekodowania
  ani accuracy nowych, nieoznaczonych zdjęć.

## Outcome

- Raport `m7-import-operations-benchmark-v1` wiąże checksumami zaakceptowane
  raporty M5/M6 i nie przelicza ani nie osłabia ich progów.
- Fizyczny PostgreSQL przetworzył fixture 43 plików, 387 plansz i 5805 komórek.
  Kontrolowany crash nastąpił po trwałym checkpointcie i po restarcie nie
  powtórzył ukończonego `discovery`.
- Po jednej awarii w `discovery`, `normalization`, `board_detection`,
  `board_crops`, `sequence_ocr` i `symbol_inference` zostało odizolowane do
  właściwego pliku. Wszystkie retry zaczęły się od dokładnego failed stage.
- Zapis 387 decyzji review trwał `14.7937 s` (`26.16 decyzji/s`), przyrost peak
  RSS wyniósł `1 617 920 B`. Końcowy staging ma ciągłe numery 1–387 i dokładnie
  5805 komórek.
- Pełny przebieg operacyjny trwał poniżej zewnętrznego limitu 300 s. Raport ma
  SHA-256 `a372b46d02aed3b26f37a96e7dafd103602e066350415461cb5d8d61b9ef08f5`.
- G7.4 przechodzi wyłącznie jako `passed_manual_review_only`: geometria jest
  zaakceptowana, ale classifier accuracy pozostaje `0.68509615`,
  `manualReviewShare = 1.0`, OCR auto-accept i classifier auto-accept są
  wyłączone, a `massImportAllowed = false`.
- Wyniki TASK-0074/0075 nie uzasadniają natychmiastowego dodania kolejki, ale
  finalna decyzja architektoniczna nadal należy do TASK-0077. TASK-0076 nie
  może publikować dużego datasetu przed zebraniem feedbacku i retrainingiem.
