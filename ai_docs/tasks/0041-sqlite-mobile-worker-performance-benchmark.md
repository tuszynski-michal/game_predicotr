---
title: SQLite, mobile and worker performance benchmark
status: blocked
last_updated: 2026-07-27
---

# TASK-0041 — SQLite, mobile and worker performance benchmark

## Status

`blocked`

## Goal

Zmierzyć na deterministycznym datasecie 500 000 layoutów czasy i pamięć
produkcyjnych ścieżek SQLite, Target oraz workera, a następnie zebrać
porównywalne wyniki z Google Pixel 10 Pro XL i Samsung Galaxy S21 Ultra.

## Context

`TASK-0040` dostarczył zwalidowany snapshot jednej gry o 500 000 layoutów,
tekstowym codec v1 i prawdziwych payoutach `payout-v2`. Przed decyzją
architektoniczną w `TASK-0042` trzeba zmierzyć istniejące rozwiązanie bez
zmiany reprezentacji sygnatury ani dodawania natywnego modułu.

`TASK-0039` pozostaje zablokowany na fizycznym buildzie przez ACL dwóch plików
snapshotu M1. TASK-0041 nie zmienia tych uprawnień. Jeżeli ten sam stan
zablokuje APK benchmarkowe, część desktopowa i workerowa zostaną wykonane, a
odbiór urządzeniowy pozostanie jawnym punktem blokującym.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/quality/m35-benchmark-dataset-report.json`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- benchmark otwarcia zweryfikowanego SQLite 500k,
- exact match dla unique, duplicate i not found,
- prefix match dla reprezentatywnych długości prefiksu,
- odczyt pełnego cyklu `499999` payoutów z zawinięciem,
- osobny oraz end-to-end pomiar obliczenia Target,
- kontrola planów zapytań i użycia indeksu,
- pomiar peak RSS/working set oraz bounded batch workera,
- przepustowość generowania layoutów, `payout-v2`, SQLite i pełnej walidacji,
- automatyczny, powtarzalny harness mobilny zapisujący wynik w logu/na ekranie,
- model urządzenia, Android, wariant builda, rozmiar bazy i liczba iteracji,
- pomiary offline na Pixel 10 Pro XL i Galaxy S21 Ultra,
- raport surowy JSON i krótkie podsumowanie względem budżetów roboczych.

## Out of scope

- decyzja TEXT kontra BLOB i zmiana adaptera (`TASK-0042`),
- optymalizacja przed uzyskaniem pomiaru bazowego,
- Redis/Celery, mikroserwis, chmura lub publiczna dystrybucja,
- OCR/ML i import zdjęć,
- uznanie G3.4 za zaliczoną bez fizycznego odbioru `TASK-0039`.

## Acceptance criteria

- [x] Skrypt desktopowy mierzy p50/p95/max dla exact, prefix i pełnego cyklu.
- [ ] Pomiar rozdziela czas SQLite od czasu czystego Target i raportuje E2E.
- [x] Plany exact/prefix potwierdzają użycie indeksu sygnatury.
- [x] Worker raportuje czas, throughput, peak memory i maksymalny batch.
- [x] Benchmarki nie materializują 500 000 sygnatur poza ścieżką, którą mierzą.
- [x] Mobilny harness używa tego samego repozytorium i engine co aplikacja.
- [ ] Raport urządzenia zawiera model, Android, build, checksumę i rozmiar bazy.
- [ ] Pomiary offline są zapisane dla Pixel 10 Pro XL i Galaxy S21 Ultra.
- [ ] Wyniki są porównane z budżetami z `TEST_STRATEGY.md`, bez ukrytej zmiany
      architektury.
- [ ] Testy, lint, format i typecheck zmienionych części przechodzą.

## Technical notes

- Warm-up nie wchodzi do percentyli.
- Exact/prefix używają produkcyjnych zapytań i indeksu
  `idx_layouts_game_signature`.
- Pełny cykl musi obejmować dokładnie `layout_count - 1` rekordów.
- Pomiar pamięci odróżnia RSS procesu od pamięci śledzonej przez runtime, jeśli
  platforma udostępnia tylko jedną z tych wartości.
- Wynik mobilny ma być możliwy do zebrania przez `adb logcat` bez sieci.
- Duży snapshot i APK benchmarkowe pozostają lokalnymi artefaktami ignorowanymi
  przez Git.

## Expected files

- benchmarki w `services/worker/src/game_predictor_worker/benchmarks/`
- `scripts/benchmark_m35_repository.py`
- `scripts/benchmark_m35_worker.py`
- mobilny harness w `apps/mobile/src/`
- testy Python i TypeScript
- raporty w `ai_docs/quality/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/benchmark_m35_repository.py
.venv\Scripts\python.exe scripts/benchmark_m35_worker.py
.venv\Scripts\python.exe -m pytest services/worker/tests -q
npm run typecheck --workspace @game-predictor/mobile
npm run test --workspace @game-predictor/mobile
npm run quality
```

## Risks / open questions

- Pełny odczyt przez Expo SQLite materializuje tablicę 499 999 obiektów;
  pomiar pokaże, czy obecny adapter mieści się w budżecie pamięci.
- Fizyczny build APK może pozostać zablokowany przez ACL z TASK-0039. Nie
  wolno obchodzić tego przez rozszerzenie uprawnień bez zgody właściciela.
- Miarodajna płynność przewijania wymaga ręcznej obserwacji na obu urządzeniach;
  liczba renderowanych wierszy pozostaje dodatkowo chroniona testem komponentu.

## Outcome

### Changed

- dodano wspólne, testowane helpery percentyli, czasu i peak memory,
- `benchmark_m35_repository.py` mierzy produkcyjne zapytania SQLite oraz ich
  plany na zwalidowanym snapshotcie TASK-0040,
- `benchmark_m35_worker.py` mierzy bounded źródło payout-v2, produkcyjny zapis
  SQLite i niezależną walidację,
- mobilny harness uruchamia się wyłącznie dla release `m35-benchmark.1`, używa
  prawdziwego `LocalLayoutRepository` i `calculateTargetForecast`, pokazuje
  wynik na ekranie oraz zapisuje JSON z prefiksem `M35_BENCHMARK_RESULT`,
- dodano kontrolowany build APK benchmarkowego i kolektor ADB zapisujący model,
  Android, stan offline, czasy oraz peak `TOTAL PSS/RSS`.

### Partial verification results

Windows/Python SQLite 3.50.4 na snapshotcie `41025536` bajtów:

- exact unique p95 `0.0024 ms`,
- exact duplicate p95 `0.0024 ms`,
- exact not found p95 `0.0030 ms`,
- prefix pięciu komórek p95 `0.0028 ms` dla czterech kandydatów,
- pełny odczyt `499999` rekordów p95 `1305.1372 ms`,
- pełny odczyt miał peak RSS `269299712` bajtów i przyrost względem baseline
  `181829632` bajty,
- exact i wszystkie prefixy użyły covering index
  `idx_layouts_game_signature`; pełny cykl użył klucza głównego oraz
  tymczasowego B-tree do końcowego porządku.

Syntetyczna, produkcyjnie ukształtowana ścieżka workera:

- payout-v2 + snapshot: `511.2962 s`, `977.91 layoutów/s`,
- maksymalny batch `1000`,
- peak RSS `180977664` bajty, przyrost `98295808` bajtów,
- pełna walidacja: `45.0271 s`, `11104.41 layoutów/s`,
- `tracemalloc` był włączony dla dowodu pamięci i istotnie zwiększył czas
  względem funkcjonalnego przebiegu TASK-0040 bez śledzenia alokacji.

Surowe raporty:

- `ai_docs/quality/m35-repository-benchmark.json`,
- `ai_docs/quality/m35-worker-benchmark.json`.

Testy pomocnicze Python: `8 passed`. Mobilny typecheck przeszedł, a test
harnessu: `2 passed`. ESLint zmienionych plików i składnia wszystkich 11
skryptów PowerShell przeszły.

### Not completed

- APK benchmarkowe nie powstało. Proces uruchomiony poza sandboxem nie może
  odczytać lokalnego artefaktu TASK-0040, ponieważ jego końcowy katalog również
  ma właściciela `CodexSandboxOffline`. ACL nie zmieniono.
- ADB nie widzi obecnie żadnego podłączonego telefonu.
- Czasy Hermes/Expo SQLite, peak PSS/RSS i ręczna płynność przewijania na Pixelu
  oraz Samsungu pozostają do wykonania. Bez nich TASK-0041 nie jest ukończony.

### Documentation updates

- `CURRENT_STATE.md` zachowuje TASK-0041 jako zablokowane,
- decyzja TEXT/BLOB i ewentualna zmiana adaptera nadal należą do TASK-0042.

Na polecenie właściciela z 2026-07-27 rozpoczęto TASK-0042, aby przygotować
automatyczną ocenę już zebranych dowodów. Nie zmienia to niezrealizowanych
kryteriów urządzeniowych tego zadania ani statusu bramki G3.

### Recommended next task

- dokończyć TASK-0041 po udostępnieniu benchmarkowego APK i podłączeniu kolejno
  obu urządzeń, a następnie ponowić ocenę TASK-0042.
