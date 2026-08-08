---
title: TASK-0177 concurrent image selection and layout import acceptance
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0177 — Concurrent image selection and layout import acceptance

## Status

`done`

## Goal

Potwierdzić na rzeczywistych procesach, że `Selekcja zdjęć` i `Import layoutów`
pracują równocześnie w osobnych lane, zachowują akceptowalne użycie zasobów oraz
mogą być niezależnie anulowane i ponowione bez zatrzymania drugiego procesu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/VERSION_0_4_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0176-worker-lane-resource-budgets-and-admin-status.md`
- `ai_docs/tasks/0171-fast-selection-real-corpus-regression-and-activation.md`

## Scope

- uruchomić oba workery przez trwały supervisor i potwierdzić ich status w API
  oraz workspace `Joby`,
- uruchomić jednocześnie kontrolowaną Selekcję zdjęć i Import layoutów,
- potwierdzić postęp obu jobów w tym samym przedziale czasu,
- zebrać bounded próbki CPU, RAM, dysku oraz throughput każdego lane,
- anulować i ponowić job jednego lane, potwierdzając nieprzerwany postęp drugiego,
- powtórzyć kierunek izolacji dla drugiego lane albo pokryć go deterministyczną
  regresją, jeżeli drugi realny run wymagałby kosztownego korpusu właściciela,
- zatrzymać procesy kontrolowanie i potwierdzić brak osieroconych workerów.

## Out of scope

- aktywacja `fast-image-selector-v9`,
- końcowy pomiar naturalnego korpusu dokładnie 40 000 zdjęć,
- zmiana algorytmu selekcji lub uploadu,
- pełny import 500 000 layoutów,
- automatyczne dostrajanie budżetów na podstawie jednego komputera.

## Acceptance criteria

- [x] Admin i API pokazują oba lane jako `running` przed rozpoczęciem jobów.
- [x] Selekcja i Import mają jednocześnie stan wykonywania oraz rosnący postęp.
- [x] Joby są claimowane wyłącznie przez właściwy lane.
- [x] CPU/RAM/dysk/throughput są zapisane w raporcie z konfiguracją komputera i
      budżetami wątków.
- [x] Cancel/retry jednego lane nie zatrzymuje ani nie resetuje drugiego.
- [x] Błąd pojedynczego joba pozostaje odizolowany od drugiej kolejki.
- [x] Po kontrolowanym stopie oba statusy przechodzą do `stopped` i nie pozostaje
      osierocony proces.
- [x] Test ma jawne timeouty, sprząta wyłącznie własne fixture i nie modyfikuje
      wartościowych danych właściciela.
- [x] Wynik ma decyzję `passed | optimize | failed` oraz opisuje, czy można
      bezpiecznie przejść do bramki 40 000 zdjęć.

## Test strategy

Pierwsza bramka techniczna używa małego, kontrolowanego fixture, aby sprawdzić
rzeczywistą konkurencję procesów bez wielogodzinnego oczekiwania. Jeżeli dostępny
jest staging właściciela, może zostać użyty wyłącznie read-only. Każdy etap ma
bounded timeout, krótki polling i jawny cleanup. Pomiary mają rozdzielać czas
uploadu od aktywnego wykonania workerów.

## Expected files

- `scripts/acceptance_concurrent_worker_lanes.ps1`
- `artifacts/worker-lanes/concurrent-acceptance-report.json`
- focused API/worker tests, jeśli próba ujawni brak kontraktu,
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

Zakończono 2026-08-05 z decyzją `passed`. Dodano bounded runner oraz wrapper
PowerShell uruchamiające migracje i dwa rzeczywiste procesy produkcyjnego entry
pointu na izolowanej bazie PostgreSQL. Bramka korzysta wyłącznie z generowanych
fixture, po zakończeniu usuwa własną bazę i katalog roboczy oraz zapisuje raport
w `artifacts/worker-lanes/concurrent-acceptance-smoke.json`.

Kontrolowana próba `100 obrazów + 10 000 rekordów` zakończyła się w `12,219 s`:

- oba lane przeszły do `running`, a oba joby były jednocześnie `processing`,
- anulowanie general nie zatrzymało selekcji; jej postęp wzrósł z `0` do
  `32/100`,
- general został wznowiony z checkpointu i ukończył próbę w drugim podejściu,
- image selection ukończył `100/100` jako `ready_for_import`,
- oba lane zostały jawnie oznaczone jako `stopped`; nie pozostał worker,
- peak drzewa procesów wyniósł około `379,2 MiB` dla general i `382,8 MiB` dla
  image selection; CPU odpowiednio `7,812 s` i `7,031 s`,
- raport ma `includesOwnerData=false`, `isolatedPostgres=true` i wynik `passed`.

Regresje store/runtime z TASK-0174–0176 pokrywają fencing, odzyskanie lease,
izolację błędu oraz przeciwny kierunek recovery. Ruff, mypy, compileall i
kontrola składni 26 skryptów PowerShell przeszły. Pierwsze dwie próby ujawniły
wyłącznie błąd wrappera w odczycie `ExitCode`; przyczynę usunięto przez użycie
`Diagnostics.Process` z bounded `WaitForExit`. Nie aktywowano v9 i nie wykonano
bramki naturalnego korpusu 40 000 zdjęć — pozostaje ona w TASK-0171.
