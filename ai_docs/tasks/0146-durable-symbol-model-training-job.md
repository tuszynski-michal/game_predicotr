---
title: TASK-0146 durable symbol model training job
status: todo
last_updated: 2026-08-01
---

# TASK-0146 — Durable symbol model training job

## Status

`todo`

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
- `ai_docs/tasks/0145-source-aware-cumulative-training-dataset.md`

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

- [ ] Request HTTP szybko tworzy job i nie wykonuje treningu w procesie API.
- [ ] Job zapisuje heartbeat, etap, postęp i checkpoint wystarczający do
      kontrolowanego retry.
- [ ] Ponowienie z identycznym kluczem nie tworzy konkurencyjnego treningu.
- [ ] Restart workera nie zmienia fingerprintu ani danych wejściowych.
- [ ] Błąd lub anulowanie pozostawia bieżący aktywny model bez zmian.
- [ ] Test porównuje checksumy danych review przed i po sukcesie, błędzie i
      retry; pozostają identyczne.
- [ ] Komendy treningowe i benchmarkowe mają jawne limity oraz kontrolowane
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
python -m pytest services/worker/tests -q
python -m pytest services/api/tests -q
npm.cmd test --workspace @game-predictor/admin
```

## Risks / open questions

- Pełne odtworzenie od konkretnej epoki zależy od deterministyczności PyTorch;
  raport ma jawnie odróżnić retry od rozpoczęcia nowej iteracji.

## Outcome

Do uzupełnienia po realizacji.
