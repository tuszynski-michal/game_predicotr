---
title: TASK-0057 Geometry and OCR benchmark report
status: done
last_updated: 2026-07-28
---

# TASK-0057 — Geometry and OCR benchmark report

## Status

`done`

## Goal

Zbudować jeden audytowalny raport benchmarkowy M5, który łączy jakość każdego
etapu, czas CPU, rozmiar referencjonowanych artefaktów, wyniki według warunków
zdjęcia i katalog błędów. Dla OCR niespełniającego proponowanego progu raport
ma porównać jedną lokalną alternatywę bez zmiany produkcyjnego adaptera.

## Context

TASK-0052–0056 dostarczają deterministyczne raporty discovery, normalizacji,
geometrii, cropów i OCR. Korpus obejmuje tylko 12 zdjęć jednej gry i sesji,
progi pozostają `proposed`, brakuje niezależnych golden narożników, a baseline
OCR osiąga `68/108 = 62.9630%`. Benchmark nie może ukryć tych ograniczeń ani
zaliczyć G5.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/quality/m5-quality-thresholds.json`
- raporty jakości M5.1–M5.4
- D-050, D-053–D-055 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kontrakt `m5-image-benchmark-v1`,
- weryfikacja checksum wszystkich wejściowych raportów i korpusu,
- osobne metryki detekcji, cropów, OCR i ciągłości,
- jawne `not_measurable` dla metryk bez niezależnego ground truth,
- agregaty per zdjęcie, condition tag i długość numeru,
- katalog nierozpoznanych, błędnych i błędnych z wysokim confidence wyników,
- rozmiary wyłącznie plików referencjonowanych przez raporty,
- p50/p95 czasu każdego etapu i czasu na zdjęcie na lokalnym CPU,
- porównanie baseline OCR z kontrolą tego samego modelu na surowym cropie,
- decyzja benchmarkowa `continue`, `rework` albo `blocked`, bez finalnej decyzji
  architektonicznej zarezerwowanej dla TASK-0058,
- deterministyczny validator zapisanego raportu, który nie porównuje ponownie
  niestabilnych pomiarów czasu.

## Out of scope

- strojenie modelu lub preprocessingu na tych samych 12 zdjęciach,
- akceptacja proponowanych progów,
- deklaracja G5.3, G5.4 albo pełnego G5 jako `passed`,
- trening klasyfikatora symboli,
- zmiana stagingu, API, panelu lub PostgreSQL,
- benchmark GPU albo urządzenia Android.

## Assumptions

- Obecne raporty i lokalne artefakty TASK-0052–0056 są wejściem pomiaru.
- Benchmark mierzy środowisko Windows CPU używane do lokalnego workera.
- Kontrola używa tego samego lokalnego modelu i dekodera, zmieniając wyłącznie
  wersjonowane wejście z `bright-component-tight-v1` na `raw-warp-v1`.
- Trzy próbki czasowe wystarczają do prototypowej charakterystyki, ale nie do
  formalnego budżetu produkcyjnego.

## Acceptance criteria

- [x] Raport wiąże wszystkie wejścia checksumami i nie zawiera ścieżek absolutnych.
- [x] Każda proponowana metryka ma wynik albo jawne `not_measurable` z powodem.
- [x] OCR i continuity są raportowane osobno oraz per warunek/długość numeru.
- [x] Katalog błędów nie usuwa błędnych wyników z mianownika.
- [x] Rozmiary obejmują tylko referencjonowane, istniejące artefakty.
- [x] Timing zawiera co najmniej trzy próbki, p50/p95 i czas na zdjęcie.
- [x] Alternatywa OCR ma nazwę, fingerprint, accuracy, conflict rate i timing.
- [x] Raport nie zmienia baseline adaptera i nie zalicza G5.
- [x] `--check` wykrywa drift wejść oraz manipulację raportem.
- [x] Testy, Ruff, mypy, `pip check` i pełny lokalny benchmark przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/benchmark.py`
- `services/worker/tests/test_image_benchmark.py`
- `scripts/run_m5_image_benchmark.py`
- `ai_docs/quality/m5-image-benchmark-report.json`
- `package.json`
- `ai_docs/process/CURRENT_STATE.md`

## Risks

- Wyniki czasu zależą od obciążenia laptopa i nie są przenośnym SLA.
- Porównanie dwóch preprocessingów na tym samym korpusie diagnozuje etap, ale
  nie zastępuje niezależnego zbioru walidacyjnego.
- Współwystępujące condition tags nie pozwalają przypisać błędu jednej przyczynie.
- Brak golden narożników uniemożliwia wiarygodny pomiar corner error.

## Outcome

Dodano `m5-image-benchmark-v1`, wspólny runner oraz walidator wiążący
checksumami discovery, normalizację, geometrię, cropy, golden, OCR i
proponowane progi. Raport nie zawiera ścieżek absolutnych, liczy wyłącznie
referencjonowane artefakty i osobno pokazuje wynik per zdjęcie, condition tag,
długość numeru oraz każdy błędny OCR.

Detekcja strony i kompletu dziewięciu plansz osiągnęła `12/12 = 100%`.
`boardPositionAssignmentAccuracy` i `boardCornerErrorP95` mają jawny status
`not_measurable`, ponieważ obecny golden nie zawiera niezależnych pozycji ani
narożników. Baseline `bright-component-tight-v1` osiągnął
`68/108 = 62.9630%` oraz konflikt ciągłości `51/108 = 47.2222%`.
Kontrola `raw-warp-v1` na tym samym modelu osiągnęła tylko
`46/108 = 42.5926%` i 34 konflikty; kontrola potwierdza wartość preprocessingu,
ale nie rozwiązuje problemu jakości.

P95 lokalnego CPU na 12 zdjęć: discovery `21.1432 ms`, normalizacja
`1738.6188 ms`, geometria `4016.3138 ms`, cropy
`16473.5893 ms`, baseline OCR `3874.1724 ms`, kontrola OCR
`5240.3376 ms`. Baseline ma 40 błędów: 13 brakujących cyfr, 1 dodatkową cyfrę,
19 substytucji tej samej długości i 7 nierozpoznanych wyników; 5 błędów miało
confidence co najmniej 0.8.

Raport ma SHA-256
`89c2335b64fdf957f9af8cbc65c008cb7706cb7119fd36af7ac8b7c8a8a2f408`,
kontrola OCR
`8a92143e9718da55ce8a27d8914dc1a91568fca1fe8164d56e90c8e68753f1d6`.
Retry `--check` przeszedł. Decyzja benchmarkowa to `rework`, G5 pozostaje
niezaliczone, a finalny wybór adaptera należy do TASK-0058.

Weryfikacja: 3 nowe testy benchmarku, 50 testów całego pionu obrazów, Ruff,
mypy, `pip check`, pełny przebieg z trzema iteracjami każdego etapu i
deterministyczny `--check`.
