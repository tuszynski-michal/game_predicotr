---
title: TASK-0187 image selection scan lease heartbeat and progress
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0187 — Image selection scan lease heartbeat and progress

## Goal

Usunąć pętlę wznawiania selektora v10, gdy analiza jednej partii zdjęć trwa
dłużej niż lease workera, oraz pokazywać rzeczywisty postęp dużego runu.

## Incident

Realny run 32 079 zdjęć zatrzymał trwały postęp na `96 / 32 079`, zapisał jedną
grupę i osiągnął 48 prób joba. Analiza następnej partii przekraczała
60-sekundowy lease bez heartbeat. Fencing odrzucał checkpoint, a retry ponownie
liczył tę samą partię. Skrypt operatorski dodatkowo czytał nieistniejące pola
`progressCurrent/progressTotal` zamiast zagnieżdżonego `progress`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0178-image-selection-v10-accuracy-first-selection.md`

## Scope

- odnawiać lease podczas długiego skanowania, niezależnie od granicy checkpointu,
- zachować checkpoint i projekcję w deterministycznej kolejności źródeł,
- ograniczyć maksymalną liczbę ponownie analizowanych zdjęć po awarii,
- pokazywać właściwe `current / total`, etap i liczniki w pomiarze operatorskim,
- dodać regresję, w której batch trwa dłużej od lease, ale job nie traci tokenu,
- nie zmieniać rankingu, grupowania, jakości wyboru ani uploadu stagingu.

## Acceptance criteria

- [x] Analiza odnawia heartbeat przed wygaśnięciem lease również między
      checkpointami.
- [x] Długi batch kończy się jednym attemptem bez pętli requeue.
- [x] Checkpoint pozostaje monotoniczny i wznowienie nie pomija źródeł.
- [x] API/skrypt pokazuje rzeczywisty postęp z obiektu `progress`.
- [x] Testy selektora, job runtime i monitoringu przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/tests/`
- `scripts/run_live_image_selection.py`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_selection_job.py services/worker/tests/test_fast_image_selector.py -q
.venv\Scripts\python.exe -m pytest services/worker/tests/test_job_runtime.py -q
.venv\Scripts\python.exe -m ruff check services/worker scripts/run_live_image_selection.py
```

## Outcome

Wspólny `LocalJobWorker` uruchamia lekki keepalive dla każdego claimed joba i
odnawia ten sam fenced lease niezależnie od checkpointu handlera. Regresja z
lease 150 ms oraz handlerem 450 ms zakończyła job w pierwszym attempt i
potwierdziła wielokrotny heartbeat. Monitor operatorski czyta teraz
`progress.current`, `progress.total`, `progress.stage` oraz liczniki
`progress.imageSelection`.

Weryfikacja 2026-08-08:

- runtime i monitor: 11/11 testów,
- selektor/job/benchmark: 75/75 testów,
- Ruff zmienionych modułów: passed,
- rzeczywisty job 32 079 zdjęć po restarcie wyłącznie lane wznowił ten sam
  checkpoint i przeszedł z 96 do co najmniej 160; upload nie został powtórzony.
