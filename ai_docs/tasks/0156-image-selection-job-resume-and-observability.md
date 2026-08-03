---
title: TASK-0156 image selection job resume and observability
status: todo
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0156 — Image selection job resume and observability

## Status

`todo`

## Goal

Zintegrować selekcję z trwałym lifecycle jobów, checkpointami, retry,
anulowaniem, statystykami i bezpieczną diagnostyką.

## Context

Nawet szybki skan 30 000 zdjęć jest procesem długotrwałym. Restart workera lub
błąd jednego JPEG-a nie może wymagać powtórzenia całego katalogu ani pozostawić
osieroconego procesu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/tasks/0153-fast-sequential-image-grouping-and-quality-selection.md`

## Scope

- zarejestrować handler `image_selection` w istniejącym workerze,
- użyć globalnego lease/fencing i pojedynczego `execution_slot = 1`,
- checkpointować order index, bieżącą grupę, zakresy zakończone i top-k,
- izolować uszkodzony JPEG z reason code bez zatrzymania całego runu,
- obsłużyć retry dokładnie od ostatniego potwierdzonego checkpointu,
- obsłużyć cancel bez uruchamiania kolejnej partii,
- pokazać w `Jobach` etap, pliki X/N, grupy, wybrane, manual i błędy,
- dodać bounded diagnostykę bez obrazów i ścieżek absolutnych,
- zmierzyć czas uploadu osobno od czasu obliczeń.

## Out of scope

- wiele workerów,
- Redis/Celery,
- polityka automatycznej retencji jobów,
- benchmark jakości i pełnej skali.

## Acceptance criteria

- [ ] Crash po checkpointcie wznawia następny plik bez powtarzania zakończonych
      outputów.
- [ ] Stary worker nie może zapisać wyniku po utracie lease.
- [ ] Błąd jednego JPEG-a zwiększa właściwy licznik i pozwala kontynuować.
- [ ] Cancel kończy po bounded kroku i nie usuwa źródłowego folderu.
- [ ] `waiting_for_review` zwalnia slot ciężkiego workera.
- [ ] Joby pokazują spójny procent i rzeczywiste X/N plików.
- [ ] Diagnostyka jest bounded, checksumowana i nie zawiera sekretów ani
      ścieżek absolutnych.
- [ ] Test po timeoutcie potwierdza brak osieroconego workera.

## Technical notes

Checkpoint nie powinien zawierać listy 30 000 kandydatów. Trwałe rekordy tabel
są źródłem prawdy, a JSON checkpointu zawiera wyłącznie bounded stan kursora i
bieżącej grupy.

## Expected files

- `services/worker/src/game_predictor_worker/jobs/`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/`
- `services/api/src/game_predictor_api/application/jobs.py`
- `apps/admin/src/features/jobs/`
- `apps/admin/test/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests services/api/tests -q
npm.cmd test --workspace @game-predictor/admin
```

## Risks / open questions

- Snapshot bieżącej grupy musi być mały; top-k przechowuje ścieżki i metadane,
  nigdy bajty JPEG.

## Outcome

Do uzupełnienia po realizacji.
