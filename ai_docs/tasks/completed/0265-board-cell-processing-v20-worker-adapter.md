---
title: TASK-0265 board-cell processing v20 worker adapter
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0265 — Produkcyjny adapter v19 w workerze

## Goal

Połączyć estymator i cropper v19 z pełnym importem w jawnie przypiętym trybie,
bez zmiany domyślnego v18 i bez rozpoczęcia TASK 5.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`
- `ai_docs/tasks/completed/0264-board-cell-geometry-deferred-contract.md`

## Scope and invariants

- kontrakt `board-cell-processing-v20-verified-v19-v1`,
- trwały pre-crop stage `board_cell_geometry`,
- dokładnie 15 zweryfikowanych cropów v19 albo zero,
- source-direct, bez fallbacku v18 po błędzie v19,
- brak inferencji symboli dla odroczonej planszy,
- trwały deferred z replayem po restarcie i job-local rehydration,
- deferred uczestniczy w liczniku oczekującego review i blokuje przedwczesną
  walidację ciągłości,
- wersje geometrii/croppera w snapshotcie i fingerprintcie,
- historyczny v18 pozostaje domyślny i odtwarzalny.

## Outcome

- Start browserowego importu przyjmuje opcjonalny
  `boardCellProcessingMode=verified_v19`; wartość domyślna to
  `historical_v18`.
- Executor zapisuje geometrię v19 przed cropami jako osobny immutable stage
  result. Crash po tym zapisie nie powtarza estymacji; replayer odtwarza
  job-local deferrals idempotentnie.
- Udane pozycje jednej strony tworzą 15 source-direct cropów i przechodzą do
  modelu. Nieudane pozycje tej samej strony zapisują zamknięty reason code,
  tworzą zero cropów i nie trafiają do ONNX.
- Migracja `0055_board_cell_geometry_pipeline_stage` zmienia wyłącznie check
  constraint nazw stage results.
- Snapshot przypina niezmienny manifest benchmarku TASK 2. Ponieważ pokrycie
  wynosi `93,78%`, tryb pozostaje opt-in zgodnie z jawną decyzją właściciela.

## Verification

- Celowane Ruff: pass.
- Celowane testy workera/API/migracji, benchmarku shadow i kontraktu deferred:
  `154 passed`.
- Test API jawnego startu oraz test pełnego mieszanego łańcucha v20: pass.
- Replay z nową instancją executora nie wywołuje ponownie estymatora/croppera:
  pass.
- Pełny worker doszedł do `91%` bez błędu i został przerwany przy limicie
  120 sekund.
- Celowany mypy nie zgłasza błędów TASK 4; zatrzymuje się na dwóch istniejących
  błędach `symbol_model_iteration_repository.py`.

## Acceptance criteria

- [x] Jawnie przypięty job używa wyłącznie zweryfikowanych cropów v19.
- [x] Błędna geometria nigdy nie dociera do modelu.
- [x] Każda plansza ma 15 cropów albo zero.
- [x] Resume i rehydration zachowują wersje oraz idempotentny deferred.
- [x] Domyślny pipeline v18 i historyczne manifesty pozostają bez zmian.
- [x] TASK 5 nie został rozpoczęty.
