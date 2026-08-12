---
title: TASK-0175 dual worker lane recovery and fencing
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0175 — Dual worker lane recovery and fencing

## Status

`done`

## Goal

Potwierdzić na fizycznym PostgreSQL, że wygaśnięcie lease, retry i anulowanie
joba w jednym worker lane nie zmienia aktywnego joba ani tokenu fencing drugiego
lane.

## Context

TASK-0174 potwierdził równoległy claim i kolejność obu kolejek w ścieżce bez
awarii. Wielogodzinny proces selekcji może jednak działać podczas restartu albo
anulowania importu. Każdy lane musi odzyskiwać wyłącznie swój wygasły slot, a
stary proces nie może zapisać checkpointu po wydaniu nowego lease.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/completed/0172-dedicated-image-selection-worker-lane.md`
- `ai_docs/tasks/completed/0174-dual-worker-lane-operational-acceptance.md`

## Scope

- utworzyć po dwa oczekujące joby w general i image-selection lane,
- nadać pierwszym jobom różne czasy lease i zapisać checkpointy,
- odzyskać wygasły general lease bez zmiany aktywnego selection lease,
- potwierdzić odrzucenie zapisu ze starego general fencing tokenu,
- anulować wznowiony general job w safe poincie i przejąć kolejny general job,
- później odzyskać selection lease bez wpływu na general lane,
- potwierdzić odrzucenie starego selection tokenu i prawidłową kolejność
  pozostałego joba,
- włączyć scenariusz do bounded bramki `v04:worker-lanes:acceptance`.

## Out of scope

- zabijanie prawdziwego procesu workera albo modyfikowanie jobów właściciela,
- test 40 000 zdjęć, wydajność selektora i aktywacja v9,
- zmiana timeoutów lease, heartbeatów lub polityki retry,
- automatyczny restart workera, nowy endpoint albo UI,
- recovery częściowych artefaktów konkretnego handlera.

## Acceptance criteria

- [x] General worker odzyskuje wyłącznie wygasły slot general.
- [x] Selection lease pozostaje ważny, gdy general job jest odzyskiwany lub
      anulowany.
- [x] Stary general token po retry nie może wykonać heartbeat/checkpoint.
- [x] Anulowanie general w checkpointcie zwalnia wyłącznie general slot.
- [x] Image-selection worker odzyskuje później wyłącznie własny wygasły job.
- [x] Stary selection token jest odrzucany po retry.
- [x] Pozostałe joby obu typów zachowują deterministyczną kolejność.
- [x] Izolowana bramka kończy się `passed` i usuwa testową bazę.

## Technical notes

Test używa różnych lease durations zamiast rzeczywistego oczekiwania. Wszystkie
timestampy są stałe, więc scenariusz pozostaje szybki i deterministyczny.
Weryfikowany jest istniejący fenced lease; zadanie nie zmienia produkcyjnej
polityki timeoutów.

## Expected files

- `services/api/tests/integration/test_worker_job_store.py`
- `scripts/run_v04_dual_worker_lane_acceptance.ps1`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run v04:worker-lanes:acceptance
```

## Risks / open questions

- Scenariusz pokrywa trwały lifecycle joba, ale nie handler-specific cleanup.
  Każdy handler nadal odpowiada za własny idempotentny checkpoint i artefakty.

## Outcome

### Changed

- Dodano fizyczny test PostgreSQL z dwoma jobami każdego lane i różnymi lease
  durations. General job wygasa jako pierwszy, wraca z zachowanym checkpointem
  i nowym tokenem, podczas gdy selection job nadal ma pierwszy ważny lease.
- Stary general token jest odrzucany przez fencing. Anulowanie wznowionego joba
  w checkpointcie ustawia `cancelled`, czyści slot 1 i pozwala przejąć drugi
  general job bez zmiany selection lease.
- Po późniejszym wygaśnięciu selection lease ten sam selection job wraca z
  zachowanym checkpointem i nowym tokenem. Stary token jest odrzucany, a po
  zakończeniu retry kolejny selection job zachowuje kolejność.
- Bounded bramka v0.4 uruchamia oba testy izolacji i recovery w tej samej
  automatycznie usuwanej bazie testowej.

### Verification results

- izolowane kontrakty PostgreSQL: `2 passed` w 3,96 s,
- regresja runtime i CLI: `11 passed` w 5,05 s,
- składnia wszystkich 25 skryptów PowerShell: poprawna,
- Ruff, Ruff format i `git diff --check`: zaliczone,
- raport `v0.4-dual-worker-lanes`: `passed`; wszystkie pięć bounded kroków
  zaliczone, dane właściciela i procesy workera nie zostały użyte.

### Not completed

- Nie wykonywano handler-specific recovery artefaktów ani profilu 40 000 zdjęć;
  pozostają w istniejących zadaniach handlerów i TASK-0171.

### Documentation updates

- `CURRENT_STATE.md` rejestruje zakończenie recovery/fencing,
- `TEST_STRATEGY.md` obejmuje niezależne wygasanie i anulowanie lane.

### Recommended next task

- Kontynuować TASK-0171 po przygotowaniu pełnego naturalnego korpusu 40 000;
  kolejki, supervisor, podstawowa izolacja i recovery są zamknięte.
