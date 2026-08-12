---
title: TASK-0174 dual worker lane operational acceptance
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0174 — Dual worker lane operational acceptance

## Status

`done`

## Goal

Udowodnić jednym powtarzalnym, ograniczonym czasowo testem, że general worker i
image-selection worker nie blokują wzajemnie swoich kolejek, a nadal zachowują
pojedyncze wykonanie wewnątrz każdego lane.

## Context

TASK-0172 rozdzielił claim i execution slots, a TASK-0173 dodał bezpieczne
zarządzanie dwoma procesami. Brakuje jednej bramki regresyjnej łączącej migrację,
fizyczny PostgreSQL, konfigurację CLI oraz kontrolę operatorską. Test nie może
korzystać z danych właściciela ani dublować bramki 40 000 zdjęć TASK-0171.

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
- `ai_docs/tasks/completed/0173-local-worker-lane-process-supervisor.md`

## Scope

- rozszerzyć fizyczny test PostgreSQL do dwóch oczekujących jobów każdego lane,
- potwierdzić równoległy claim po jednym jobie general i image-selection,
- potwierdzić blokadę drugiego claimu wewnątrz każdego zajętego lane,
- po zwolnieniu obu slotów przejąć pozostałe joby właściwymi workerami,
- dodać bounded skrypt akceptacyjny uruchamiający izolowany PostgreSQL, testy
  store/runtime/CLI, składnię PowerShell i read-only status supervisora,
- zapisać maszynowo czytelny raport bez danych właściciela.

## Out of scope

- pełny profil 40 000 zdjęć i aktywacja selektora v9 z TASK-0171,
- uruchamianie prawdziwego importu lub selekcji na danych właściciela,
- pomiar wydajności algorytmu albo konkurencji CPU/RAM,
- nowy endpoint, ekran Admina, broker, kontener workera lub zmiana slotów,
- automatyczne uruchamianie workerów po starcie Windows.

## Acceptance criteria

- [x] Dwa różne lane mogą jednocześnie mieć po jednym jobie `processing`.
- [x] Drugi claim general i drugi claim image-selection zwracają brak joba,
      dopóki właściwy slot jest zajęty.
- [x] Zwolnienie jednego lane nie zmienia lease ani kolejki drugiego lane.
- [x] Po zwolnieniu obu slotów pozostałe joby są przejmowane wyłącznie przez
      odpowiedni typ workera.
- [x] Test używa osobnej, usuwanej bazy PostgreSQL i nie modyfikuje danych
      właściciela.
- [x] Jedna komenda z jawnym timeoutem zapisuje raport `passed | failed`.
- [x] Po teście nie pozostaje baza testowa ani proces workera uruchomiony przez
      test.

## Technical notes

Akceptacja sprawdza izolację kolejki, nie przepustowość dwóch ciężkich zadań.
`docker compose up` może uruchomić lokalny PostgreSQL, ale test tworzy i usuwa
wyłącznie bazę `game_predictor_worker_jobs_test`. Status supervisora jest
read-only; skrypt nie startuje workerów i nie może przejąć oczekującego joba
właściciela.

## Expected files

- `services/api/tests/integration/test_worker_job_store.py`
- `scripts/run_v04_dual_worker_lane_acceptance.ps1`
- `package.json`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run v04:worker-lanes:acceptance
```

## Risks / open questions

- Test nie ocenia spowolnienia dwóch równoległych ciężkich jobów. Takie dane są
  obserwacją operatorską, a selekcja 40 000 pozostaje osobną bramką właściciela.

## Outcome

### Changed

- Fizyczny test PostgreSQL tworzy teraz po dwa joby `general` i
  `image_selection`. Potwierdza po jednym równoległym lease, blokuje kolejny
  claim w każdym zajętym lane, zwalnia general bez naruszenia aktywnej selekcji,
  a następnie przejmuje oba pozostałe joby właściwymi workerami.
- Dodano `run_v04_dual_worker_lane_acceptance.ps1` oraz komendę
  `npm run v04:worker-lanes:acceptance`. Każdy proces potomny ma limit 180 s,
  przekierowane wyjście i cleanup po timeoutcie.
- Raport `v0.4-dual-worker-lanes` zapisuje wynik każdego kroku, deklaruje
  `isolatedPostgres = true`, `includesOwnerData = false` oraz
  `startsWorkerProcesses = false`.

### Verification results

- izolowany test PostgreSQL: `1 passed` w 3,34 s,
- regresja runtime i CLI: `11 passed` w 5,07 s,
- wszystkie 25 skryptów PowerShell ma poprawną składnię,
- read-only status supervisora zakończył się powodzeniem; oba lane były
  `stopped`,
- pełna komenda akceptacyjna zakończyła się `passed` w około 13,1 s kroków,
- Ruff, Ruff format, Prettier i `git diff --check` przeszły dla zmienionych
  części.

### Not completed

- Nie uruchamiano profilu 40 000 zdjęć ani selektora na danych właściciela;
  pozostają wyłącznie w TASK-0171.
- Nie mierzono równoległego obciążenia CPU/RAM dwóch ciężkich jobów, ponieważ
  nie jest to warunek izolacji kolejek.

### Documentation updates

- `CURRENT_STATE.md` rejestruje zakończoną bramkę,
- `TEST_STRATEGY.md` zawiera pełny kontrakt regresji dwóch lane.

### Recommended next task

- Kontynuować TASK-0171 po dostarczeniu dokładnie 40 000 naturalnych zdjęć;
  infrastruktura dwóch lane nie blokuje tej bramki.
