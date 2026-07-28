---
title: TASK-0092 M5 corpus, variable final page and OCR rework
status: done
last_updated: 2026-07-28
completed: 2026-07-28
---

# TASK-0092 — M5 corpus, variable final page and OCR rework

## Status

`done`

## Goal

Domknąć TASK-0051 i bramkę G5 na rozszerzonym korpusie, obsłużyć ostatnią
stronę zawierającą od 1 do 9 layoutów oraz przepracować OCR numerów bez
naruszania jawnej granicy manual review.

## Context

Właściciel dodał 31 nowych zdjęć w różnej jakości. Korpus ma teraz 43 zdjęcia
i ponad 300 layoutów. Q-016 potwierdza, że strona ma maksymalnie dziewięć
layoutów w siatce 3 × 3, ale końcowa strona sekwencji może mieć mniej pozycji.
Q-017 potwierdza możliwość uzyskania około 100 wycinków na symbol.

Instrukcję „popraw resztę żeby przejść do milestone 6” traktujemy jako
akceptację użycia jawnych progów z `m5-quality-thresholds.json` do reworku i
ponownej oceny. Progu nie wolno obniżyć tylko po to, aby zaliczyć istniejący
wynik.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-050, D-053–D-056 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- rozszerzenie manifestu do wszystkich dostarczonych zdjęć,
- zamknięcie Q-016/Q-017,
- golden annotations dla oczekiwanej liczby i geometrii layoutów,
- wersjonowany kontrakt stron zawierających 1–9 layoutów,
- brak cichego uznawania brakującej ramki za krótszą stronę,
- automatyczne generowanie board/cell crops,
- rework OCR i pomiar na held-out source images,
- ponowny benchmark G5 i decyzja o wejściu do M6,
- aktualizacja wymagań, architektury, planów i stanu projektu.

## Out of scope

- trening klasyfikatora symboli,
- masowy import M7,
- ręczne wycinanie 100 przykładów przez właściciela,
- ciche uzupełnianie numerów wyłącznie z ciągłości,
- obniżanie progów po obejrzeniu wyników,
- zmiana schematu PostgreSQL lub kontraktu Admin API.

## Acceptance criteria

- [x] Korpus zawiera wszystkie unikalne zdjęcia i ma zaakceptowany manifest.
- [x] Q-016/Q-017 są zamknięte w dokumentacji.
- [x] Golden annotations opisują oczekiwaną liczbę, pozycje i geometrię.
- [x] Pełna strona wymaga dziewięciu layoutów; tylko jawnie oznaczona końcowa
      strona może zawierać 1–8 pozycji bez luk.
- [x] Detektor i cropper obsługują oczekiwaną liczbę 1–9 bez przesuwania
      indeksów.
- [x] Wycinki board/cell powstają automatycznie i są wersjonowane checksumami.
- [x] OCR osiąga zaakceptowany próg na held-out source images albo pozostaje
      jawnie `manual_review_only`.
- [x] Continuity nie nadpisuje raw OCR ani nie tworzy zatwierdzonej wartości.
- [x] Benchmark, testy, lint, format i typecheck zmienionych części przechodzą.
- [x] TASK-0059 powstaje tylko wtedy, gdy wszystkie warunki wejścia M6 są
      spełnione.

## Expected files

- `ai_docs/quality/m5-corpus-manifest.json`
- `ai_docs/quality/m5-golden-annotations.json`
- `ai_docs/quality/m5-golden-annotations.schema.json`
- `ai_docs/quality/m5-quality-thresholds.json`
- `services/worker/src/game_predictor_worker/images/corpus.py`
- `services/worker/src/game_predictor_worker/images/geometry.py`
- `services/worker/src/game_predictor_worker/images/rectification.py`
- `services/worker/src/game_predictor_worker/images/sequence_ocr.py`
- `services/worker/src/game_predictor_worker/images/benchmark.py`
- `scripts/`
- `services/worker/tests/`
- dokumentacja M5/M6 i `CURRENT_STATE.md`

## Outcome

Manifest `m5-representative-corpus-v2` obejmuje 43 obrazy w dwóch grupach
źródłowych, numery 1–387 i łącznie `6 638 360` bajtów. Pełne adnotacje
geometrii mają pochodzenie `algorithm-assisted-visual-review`; wszystkie
overlaye sprawdzono wizualnie. Walidator zwraca
`readyForGeometryBenchmark = true`.

`page-board-detector-v2` oraz cropper obsługują jawnie oczekiwane 1–9 pozycji
row-major. Krótsza strona jest dozwolona wyłącznie jako ostatnia strona
sekwencji, bez luk. Recovery wymaga expected count i dowodu czerwonej ramki,
więc nie maskuje dowolnie brakującego layoutu. Pełny korpus dał 43/43
wykrytych stron, 387 board crops, 5805 cell crops i zero elementów geometrii
wymagających review.

Baseline OCR osiągnął `247/387 = 63.8243%`, a held-out
`179/279 = 64.1577%`, dlatego nie osiąga zaakceptowanego progu 98% i pozostaje
`manual_review_only`. Nie blokuje to M6: zgodnie z D-057 dataset symboli
powstaje z automatycznych cropów i przejrzanych etykiet, a nie z
automatycznie zaakceptowanego OCR.

Benchmark `m5-image-benchmark-v2` zakończył się decyzją `enter_m6` i statusem
`measured_passed_manual_review_only_ocr`. Weryfikacja korpusu, benchmark
`--check`, `40 passed` testów zmienionego pionu, Ruff oraz mypy dla 13 plików
przeszły. Raport benchmarku ma SHA-256
`0c2904331a764c5ed3bd5e122afe1380ca83665bfb9441c6d0bb1ea3d7792011`,
a raport cropów
`2a7840f140547c23c0941349a17f4146c94e5721c3a2a9923b5467f8fb1aa0ef`.
Szczegółowe checksumy i czasy znajdują się w raportach
`ai_docs/quality/m5-*.json`.
