---
title: Large import database and storage load tests
status: done
last_updated: 2026-07-29
---

# TASK-0074 — Large import database and storage load tests

## Status

`done`

## Goal

Zmierzyć na Windows rzeczywistą przepustowość i zużycie pamięci trwałej
rejestracji image joba, jego zapytań operacyjnych oraz zarządzanego storage dla
reprezentatywnej docelowej liczby plików, bez uruchamiania OCR/ML.

## Context

M7.3 udostępniło trwałe rekordy per plik oraz read-only inwentarz storage, ale
brakuje pomiaru ich zachowania przy skali odpowiadającej 500 000 layoutów.
TASK-0074 dostarcza dane o PostgreSQL i filesystemie. Jakość adapterów, odsetek
review, awarie i wznowienia należą do TASK-0075.

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

- deterministyczny profil `smoke` dla 1 000 plików,
- profil `full` dla 55 556 plików, reprezentujący co najmniej 500 000 layoutów
  przy maksymalnie dziewięciu planszach na zdjęcie,
- rejestracja przez produkcyjny `SqlAlchemyImageBatchStore` w bounded partiach
  po 500, bez bezpośredniego omijania repozytorium,
- pomiar czasu, throughput i peak memory procesu podczas rejestracji,
- pomiar `count_job_files`, `batch_stats` i pobrania następnego pliku,
- rozmiary tabel i indeksów PostgreSQL,
- materializacja deterministycznych małych plików w shardach zarządzanego
  `data/working`, pomiar zapisu, inwentarza, throughput i pamięci,
- raport `m7-storage-database-load-v1` bez sekretów i ścieżek absolutnych,
- tryb `--check`, twardy deadline wewnętrzny oraz wrapper PowerShell z
  zewnętrznym timeoutem i kontrolą procesu,
- testy małego profilu bez wymagania PostgreSQL oraz fizyczny benchmark na
  unikalnej tymczasowej bazie, jeśli lokalny PostgreSQL jest dostępny.

## Out of scope

- OCR, OpenCV, ONNX i pomiar jakości klasyfikacji,
- review throughput, awarie adapterów, restart i resume — TASK-0075,
- publikacja datasetu, snapshotu lub APK,
- zmiana schematu i migracja,
- Redis/Celery, dodatkowy worker albo decyzja o kolejce,
- modyfikacja lub czyszczenie deweloperskiej bazy i istniejących artefaktów.

## Acceptance criteria

- [x] pełny profil reprezentuje co najmniej 500 000 layoutów,
- [x] generator nie materializuje całego katalogu w pamięci,
- [x] benchmark używa produkcyjnego repozytorium i zachowuje semantykę
  idempotencji każdego pliku,
- [x] baza benchmarkowa ma unikalną nazwę i jest usuwana wyłącznie, jeśli
  została utworzona przez bieżący proces,
- [x] raport zawiera środowisko, cardinality, czasy, throughput, pamięć,
  rozmiary tabel/indeksów i wyniki zapytań,
- [x] storage ma dokładny file count/bytes, jest sharded i skanowany przez
  `ImageArtifactStore`,
- [x] raport i walidator nie ujawniają URL bazy ani ścieżek absolutnych,
- [x] każda ścieżka uruchomienia ma jawny timeout i kontrolę osieroconego procesu,
- [x] smoke test i testy jednostkowe przechodzą bez sieci,
- [x] fizyczny wynik full albo jawna, odtwarzalna przyczyna braku pomiaru jest
  zapisana w Outcome; bez full report TASK-0074 nie zalicza bramki pomiarowej.

## Technical notes

- `55 556 = ceil(500 000 / 9)` jest profilem pojemności danych, nie założeniem,
  że każda strona musi mieć dziewięć plansz.
- Pliki storage są małymi deterministycznymi placeholderami. Benchmark mierzy
  metadata/inode traversal i kontrakt M7.3, a nie przepustowość dekodowania JPEG.
- Wewnętrzny deadline jest sprawdzany w każdej iteracji. PostgreSQL używa
  krótkiego connect/lock/statement timeoutu.
- Raport obserwacyjny zawiera timestamp i timing, dlatego nie jest artefaktem
  byte-for-byte deterministycznym. Deterministyczne są wejście, kolejność i
  oczekiwane cardinality.
- Pierwszy smoke 1 000 plików wykazał `41.13 plików/s` przy transakcji per plik,
  czyli około 22–23 min dla profilu full. Przed pełnym pomiarem repozytorium
  dostaje bounded batch registration; retry pojedynczego pliku pozostaje
  niezależną operacją.

## Expected files

- `services/worker/src/game_predictor_worker/images/load_benchmark.py`
- `services/worker/src/game_predictor_worker/images/orchestration_store.py`
- `services/worker/src/game_predictor_worker/images/pipeline_execution.py`
- `scripts/run_m7_load_benchmark.py`
- `scripts/run_m7_load_benchmark.ps1`
- `services/worker/tests/test_image_load_benchmark.py`
- `ai_docs/quality/m7-storage-database-load-report.json`
- `package.json`
- dokumentacja procesu, architektury i testów

## Verification

```powershell
# każda komenda narzędziowa otrzymuje timeout <= 120 s
.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_load_benchmark.py
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/load_benchmark.py scripts/run_m7_load_benchmark.py services/worker/tests/test_image_load_benchmark.py
.venv\Scripts\python.exe -m mypy --follow-untyped-imports services/worker/src/game_predictor_worker/images/load_benchmark.py scripts/run_m7_load_benchmark.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_m7_load_benchmark.ps1 -Profile smoke -TimeoutSeconds 120
```

## Risks / open questions

- Pomiar obejmuje placeholdery 32 B i metadata traversal, a nie rozmiar ani
  dekodowanie rzeczywistych JPEG. Te elementy mierzy TASK-0075.
- Pełny przebieg wykonano na lokalnym PostgreSQL 18.4 i Windows 11; przed
  decyzją o zmianie architektury wynik należy zestawić z jakością, recovery i
  review throughput z TASK-0075.

## Outcome

- Dodano deterministyczne profile `smoke` (1 000 plików) i `full` (55 556
  plików, pojemność 500 004 layoutów), unikalną tymczasową bazę PostgreSQL,
  sharded storage oraz kanoniczny raport `m7-storage-database-load-v1`.
- Pierwszy smoke wykazał `41.13 plików/s` dla transakcji per plik. Produkcyjne
  repozytorium i seeder otrzymały ograniczoną rejestrację partiami po 500,
  zachowując idempotencję pojedynczego `fileExecutionKey`.
- Pełny profil zakończył się w limicie 900 s: rejestracja `301.4176 s`
  (`184.32 plików/s`), materializacja storage `128.8440 s`
  (`431.19 plików/s`), baza `132 896 447 B`.
- Przyrost peak RSS wyniósł `76 967 936 B` dla rejestracji i `25 333 760 B`
  dla storage. P95 zapytań: count `57.9233 ms`, stats `94.2885 ms`, next
  `8.4742 ms`; p95 pełnego inventory storage `441.0665 ms`.
- Raport zapisano w `ai_docs/quality/m7-storage-database-load-report.json`;
  SHA-256: `2c26008f7ef72ce165cfccee00672e854d868299f0f808060efa037f822251e7`.
- Wynik nie uzasadnia dodania Redis/Celery ani osobnego workera na podstawie
  samej warstwy storage/database. Końcowa decyzja wymaga TASK-0075.
