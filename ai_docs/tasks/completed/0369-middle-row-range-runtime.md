---
title: TASK-0369 — Batch, orientacja, grouping i resume OCR v4.1
status: done
release: "0.10"
last_updated: 2026-09-01
---

# TASK-0369 — Batch, orientacja, grouping i resume OCR v4.1

## Status

`done`

## Goal

Podłączyć recognition-only Paddle do locatora środkowego rzędu v4.1 oraz
zapewnić deterministyczne batchowanie, orientację, grupowanie i recovery bez
zmiany zachowania historycznych runów v1–v3.

## Context

TASK-0368 dostarczył czysty locator, trzy source-direct cropy i exact resolver.
Ten task dodaje produkcyjny runtime, lecz nie wykonuje jeszcze odbioru na
próbach 100/1000 ani nie włącza v4.1 jako domyślnego wariantu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `.runtime/plans/plan_ocr_srodkowy_rzad_v4_1.md`

## Scope

- Recognition-only adapter Paddle i test rzeczywistego batch API.
- Bounded microbenchmark batchów 1/3/6/12 oraz przypięty `sourceBatchSize`.
- Automatyczna orientacja runu i ręczny override, utrwalane w checkpointcie.
- Odporny, bounded run-level lattice prior bez prawa dowodzenia zakresu.
- Uporządkowane mapowanie wyników batcha do źródeł.
- Grupowanie internal unknown i wybór exact proof najbliższego środkowi evidence span.
- Idempotentne observation keys, checkpoint, pause/resume i crash recovery.
- Rozwiązywanie fingerprintów v1–v4.1 z fail-closed dla nieznanych wartości.
- Diagnostyka runtime wskazana w zaakceptowanym planie.

## Out of scope

- Odbiór 100/1000 źródeł, frozen golden i challenge set.
- Włączenie v4.1 jako domyślnego recognizera nowych runów.
- Nowe API, migracja bazy, UI, worker lane, Redis, Celery lub model ML.
- Zmiana locatora/proof TASK-0368 poza integracją runtime.

## Acceptance criteria

- [x] Paddle działa wyłącznie recognition-only i zachowuje kolejność wyników.
- [x] Batch 1/3/6/12 jest zmierzony, a wybrana wartość jest częścią fingerprintu.
- [x] Orientacja, prior, grupowanie i ukończony prefiks są deterministycznie wznawialne.
- [x] Unknown nigdy nie jest kandydatem, a leading/trailing unknown nie przesuwa środka.
- [x] Każdy zapisany wybór ma własny exact proof tego samego źródła.
- [x] Retry v1–v3 zachowuje historyczny runtime, a nieznany fingerprint jest odrzucany.
- [x] Nie powstają trwałe cropy OCR ani wywołania ciężkiego pipeline'u plansz.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/middle_row_runtime.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/middle_row_grouping.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/job.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/audit.py`
- `services/worker/tests/test_middle_row_runtime.py`
- `services/worker/tests/test_middle_row_grouping.py`
- dokumentacja wskazana powyżej

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_middle_row_runtime.py services/worker/tests/test_middle_row_grouping.py services/worker/tests/test_semi_automatic_selection_job.py services/worker/tests/test_semi_automatic_selection_engine.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_middle_row_runtime.py services/worker/tests/test_middle_row_grouping.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
npm run format:check
```

## Risks / open questions

- Pełna 19-klatkowa sekwencja challenge nie jest dostępna; jej odbiór pozostaje
  jawnie w TASK-0370.
- Microbenchmark jest bounded i służy wyłącznie do wyboru batcha; nie zastępuje
  pomiarów rolloutowych TASK-0370.

## Outcome

- Dodano osobny runtime v4.1 wybierany wyłącznie przez utrwalony fingerprint.
  Recognition-only adapter korzysta z publicznego `recognize_many`, dzieli cropy
  na prawdziwe batche do dziewięciu i zachowuje mapowanie do porządku źródeł.
- Bounded pomiar na trzech rzeczywistych cropach z
  `seq_21169-21177.jpg`, po jednym warm-upie i pięciu próbach, dał medianowo:
  `4,456`, `5,249`, `6,234` i `5,962` źródła/s odpowiednio dla batchów
  `1/3/6/12`. Zgodnie z regułą 5% przypięto `sourceBatchSize=6`.
- Automatyczna orientacja bada deterministyczne próbki, utrwala wynik oraz proof
  counts i zatrzymuje się fail-closed, gdy pozostaje nierozstrzygnięta. Ręczny
  override jest częścią wewnętrznego kontraktu runtime'u. Pozycjowy prior ma
  bounded historię, okresowy pełny search i reset po trzech porażkach.
- Nowy grouping nie używa leading/trailing unknown do granic grupy. Wewnętrzny
  unknown może połączyć ten sam zakres, ale selektor wybiera wyłącznie własny
  exact proof najbliższy środkowi evidence span.
- Observation keys, stan orientacji, prior, aktywna grupa, ukończony prefiks,
  liczniki i numer batcha są checkpointowane. Test crash recovery potwierdza
  odcięcie niezatwierdzonego suffixu JSONL i brak duplikatów po wznowieniu.
- Przeszło `124` skoncentrowanych testów v1–v4.1. Ruff oraz mypy nowych modułów
  i zmienionego joba przechodzą. Pełny `format:check` pozostaje czerwony przez
  `20` wcześniej zmienionych, niezwiązanych plików frontendowych.
- Nie uruchomiono rolloutów 10/100/1000 i nie przełączono nowych runów z v3.
  Pełna 19-klatkowa challenge sequence nadal nie jest dostępna i pozostaje
  bramką TASK-0370.
