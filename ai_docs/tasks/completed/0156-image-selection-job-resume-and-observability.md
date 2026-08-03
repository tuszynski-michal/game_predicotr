---
title: TASK-0156 image selection job resume and observability
status: done
release: "0.4"
last_updated: 2026-08-03
---

# TASK-0156 — Image selection job resume and observability

## Status

`done`

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
- `ai_docs/tasks/completed/0153-fast-sequential-image-grouping-and-quality-selection.md`
- `ai_docs/tasks/completed/0155-image-selection-manual-fallback-workspace.md`

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

- [x] Crash po checkpointcie wznawia następny plik bez powtarzania zakończonych
      outputów.
- [x] Stary worker nie może zapisać wyniku po utracie lease.
- [x] Błąd jednego JPEG-a zwiększa właściwy licznik i pozwala kontynuować.
- [x] Cancel kończy po bounded kroku i nie usuwa źródłowego folderu.
- [x] `waiting_for_review` zwalnia slot ciężkiego workera.
- [x] Joby pokazują spójny procent i rzeczywiste X/N plików.
- [x] Diagnostyka jest bounded, checksumowana i nie zawiera sekretów ani
      ścieżek absolutnych.
- [x] Test po timeoutcie potwierdza brak osieroconego workera.

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

Zarejestrowano produkcyjny handler `image_selection` w workerze `worker-v6`.
Selector zapisuje pełny bounded stan wznowienia co 32 pliki, utrwala grupy i
kandydatów z kontrolą aktywnego lease, a po awarii uzgadnia projekcję do
ostatniego potwierdzonego prefiksu. Opublikowanie outputu również jest
fencingowane i checkpointowane co 16 kopii.

Uszkodzony JPEG jest izolowany jako bezpieczny reason code. Cancel zatrzymuje
pracę na następnym checkpointcie bez usuwania stagingu, a manual review zwalnia
slot i może wznowić ten sam job bez regresji monotonicznych liczników. Panel
`Joby` pokazuje grupy, wybrane, manual, błędy, liczbę weryfikacji top-k oraz
oddzielny czas uploadu i aktywnych obliczeń. Kanoniczna diagnostyka nie zawiera
obrazów ani ścieżek absolutnych i jest adresowana SHA-256.

Weryfikacja objęła testy crash/resume, projection-before-checkpoint, stale lease,
cancel, corrupted JPEG, manual resume, zwolnienie execution slotu, API/OpenAPI i
kontrakt Admina. Pełna regresja zakończyła się wynikiem 481 testów workera oraz
264 testów API; 19 integracji zależnych od PostgreSQL/symlinków zostało jawnie
pominiętych przez istniejące guardy środowiska. Mypy nie zgłasza błędu w
zmienionych modułach, ale globalne przejście nadal blokują trzy wcześniejsze
błędy w `security/local_admin.py` i `main.py`. TASK-0157 pozostaje osobną bramką
jakości i skali 10k/30k.
