---
title: TASK-0146 durable symbol model training job
status: done
last_updated: 2026-08-08
completed_at: 2026-08-08
---

# TASK-0146 — Durable symbol model training job

## Status

`done`

## Goal

Uruchamiać lokalny trening modelu symboli jako trwały, wznawialny job z
postępem, checkpointami i pełnym fingerprintem wejścia.

## Context

Trening może trwać długo i nie może blokować requestu HTTP ani zniknąć po
odświeżeniu Admina. Awaria nie może zmienić aktywnego modelu ani danych review.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0145-source-aware-cumulative-training-dataset.md`

## Scope

- dodać typ i handler trwałego joba treningowego,
- wykorzystywać istniejący wybrany model i trening od początku na całej
  kohorcie,
- zapisywać stan etapów, epoch, metryki cząstkowe, checkpoint i heartbeat,
- zapewnić retry zgodny z fingerprintem oraz kontrolowane anulowanie,
- blokować równoległy ciężki trening lub masową inferencję dla tej samej gry,
- pokazywać postęp i stabilne błędy w istniejącym workspace `Joby`,
- zapisać checkpoint i konfigurację jako niezmienne artefakty kandydata.

## Out of scope

- końcowy eksport ONNX i promocja,
- automatyczna aktywacja,
- uczenie online i fine-tuning tylko na delcie,
- zmiana danych review.

## Acceptance criteria

- [x] Request HTTP szybko tworzy job i nie wykonuje treningu w procesie API.
- [x] Job zapisuje heartbeat, etap, postęp i checkpoint wystarczający do
      kontrolowanego retry.
- [x] Ponowienie z identycznym kluczem nie tworzy konkurencyjnego treningu.
- [x] Restart workera nie zmienia fingerprintu ani danych wejściowych.
- [x] Błąd lub anulowanie pozostawia bieżący aktywny model bez zmian.
- [x] Test porównuje checksumy danych review przed i po sukcesie, błędzie i
      retry; pozostają identyczne.
- [x] Komendy treningowe i benchmarkowe mają jawne limity oraz kontrolowane
      logowanie postępu.

## Technical notes

Nie dodawać Celery/Redis. Wykorzystać istniejący automat jobs i zasadę jednego
ciężkiego procesu, dopóki pomiary nie uzasadnią innej architektury.

## Expected files

- `services/worker/src/game_predictor_worker/jobs/`
- `services/worker/src/game_predictor_worker/symbols/`
- `services/worker/tests/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `apps/admin/src/features/jobs/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests -q
.venv\Scripts\python.exe -m pytest services/api/tests -q
.tooling\node\npm.cmd test --workspace @game-predictor/admin
```

## Risks / open questions

- Pełne odtworzenie od konkretnej epoki zależy od deterministyczności PyTorch;
  raport ma jawnie odróżnić retry od rozpoczęcia nowej iteracji.

## Outcome

Dodano migrację `0035_symbol_model_training_jobs`, typ `symbol_training`,
idempotentne API iteracji, handler ogólnego workera oraz niezmienne artefakty
konfiguracji i checkpointów. Wybrany `spatial-symbol-cnn-v1` trenuje od zera na
całej kohorcie. Dataset i każda epoka odnawiają heartbeat; checkpoint zawiera
model, optimizer, najlepszy stan, historię i pełny fingerprint. Kontrolowane
anulowanie zachowuje checkpoint, a retry wznawia wyłącznie zgodne wejście.
Admin uruchamia job po zamrożeniu kohorty i pokazuje go w istniejącej zakładce
`Joby`. Mały rzeczywisty test PyTorch potwierdził sukces oraz cancel → retry;
wejściowe cropy zachowały identyczne checksumy. Eksport ONNX, bramka i aktywacja
pozostają celowo w TASK-0147/0148.
