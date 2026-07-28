---
title: TASK-0091 M5 corpus, variable final page and OCR rework
status: in_progress
last_updated: 2026-07-28
---

# TASK-0091 — M5 corpus, variable final page and OCR rework

## Status

`in_progress`

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

- [ ] Korpus zawiera wszystkie unikalne zdjęcia i ma zaakceptowany manifest.
- [ ] Q-016/Q-017 są zamknięte w dokumentacji.
- [ ] Golden annotations opisują oczekiwaną liczbę, pozycje i geometrię.
- [ ] Pełna strona wymaga dziewięciu layoutów; tylko jawnie oznaczona końcowa
      strona może zawierać 1–8 pozycji bez luk.
- [ ] Detektor i cropper obsługują oczekiwaną liczbę 1–9 bez przesuwania
      indeksów.
- [ ] Wycinki board/cell powstają automatycznie i są wersjonowane checksumami.
- [ ] OCR osiąga zaakceptowany próg na held-out source images albo G5 pozostaje
      jawnie niezaliczone.
- [ ] Continuity nie nadpisuje raw OCR ani nie tworzy zatwierdzonej wartości.
- [ ] Benchmark, testy, lint, format i typecheck zmienionych części przechodzą.
- [ ] TASK-0059 powstaje tylko wtedy, gdy wszystkie warunki wejścia M6 są
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

Do uzupełnienia po weryfikacji.
