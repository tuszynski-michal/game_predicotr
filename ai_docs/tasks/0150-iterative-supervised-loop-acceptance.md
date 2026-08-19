---
title: TASK-0150 iterative supervised loop acceptance
status: in_progress
last_updated: 2026-08-19
---

# TASK-0150 — Iterative supervised loop acceptance

## Status

`in_progress`

## Goal

Potwierdzić end to end dwie iteracje ulepszania modelu, nowy import i
przeliczenie oczekujących przy zerowej zmianie wszystkich decyzji człowieka.

## Context

Pojedyncze testy komponentów nie dowodzą, że aktywacja, retry i równoległy
Reviewer zachowują nienaruszalną granicę danych. Bramka M6.6 wymaga scenariusza
zbliżonego do planowanej pracy właściciela.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/0149-pending-only-reinference-and-import-pinning.md`

## Scope

- przygotować kontrolowaną grę z accepted, corrected, rejected i pending,
- zamrozić pierwszą reprezentatywną kohortę około 100 plansz,
- wytrenować, ocenić i jawnie aktywować kandydata,
- przeliczyć oczekujące podczas równoległego zatwierdzenia części elementów,
- rozszerzyć kohortę do około 1000 lub dostępnego reprezentatywnego odpowiednika
  i przejść drugą iterację,
- zaimportować nową partię zdjęć i potwierdzić przypięcie drugiego modelu,
- przetestować retry/restart na kontrolowanym etapie,
- porównać checksumy chronionych danych oraz raporty jakości i wydajności,
- przeprowadzić krótki odbiór panelu przez właściciela.

## Out of scope

- pełny import 500 000 layoutów,
- nowe gry produkcyjne,
- trening geometrii i OCR,
- automatyczne odblokowanie `massImportAllowed` bez osobnej bramki M7.

## Acceptance criteria

- [ ] Dwie iteracje mają odrębne kohorty, datasety, modele, metryki i checksumy.
- [ ] Każda wersja może zostać odtworzona z manifestu i wskazuje dokładne dane
      człowieka użyte do treningu.
- [ ] Aktywacja oraz rollback działają per gra i są audytowalne.
- [ ] Import rozpoczęty przed aktywacją kończy się na starej wersji, a nowy
      import używa nowej.
- [ ] Przeliczenie zmienia bieżące sugestie tylko dla nadal `pending`.
- [ ] Wszystkie `accepted`, `corrected` i `rejected` oraz ich etykiety, geometria
      i staging mają identyczne checksumy przed i po całym teście.
- [ ] Element zatwierdzony w trakcie inferencji jest raportowany jako pominięty
      i nie otrzymuje automatycznego zapisu po decyzji.
- [ ] Restart/retry nie tworzy zduplikowanej iteracji ani predykcji.
- [ ] Raport zawiera metryki per symbol, czasy etapów, miejsce na dysku i znane
      ograniczenia przed pełnym M7.
- [ ] Właściciel akceptuje workflow albo zapisuje konkretne regresje do naprawy.

## Technical notes

Jeżeli nie ma jeszcze 1000 pełnych, niezależnych plansz, druga iteracja może
użyć mniejszego dostępnego zbioru, ale raport nie może sugerować spełnienia
progu 1000. Najważniejsza jest weryfikacja mechanizmu i ochrony danych.

## Expected files

- `services/api/tests/`
- `services/worker/tests/`
- `apps/admin/test/`
- `apps/reviewer/test/`
- `ai_docs/quality/`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0150-iterative-supervised-loop-acceptance.md`

## Verification

```powershell
python -m pytest services/api/tests -q
python -m pytest services/worker/tests -q
npm.cmd test --workspace @game-predictor/admin
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd run openapi:check
```

## Risks / open questions

- Długi trening musi mieć jawny limit, progress i kontrolowany worker; nie może
  być uruchamiany jako blokująca komenda bez timeoutu.

## Outcome

Mechanizmy ochrony kanonicznych sekwencji oraz pending-only inferencji są
dostępne do testu iteracyjnego. Scenariusz dwóch iteracji z aktywacją modelu,
retry i równoległym zatwierdzeniem pozostaje bramką odbioru, a nie jest jeszcze
raportowany jako zaliczony.
Wdrożono stabilny split źródeł v2 i świeży import z aktualnymi snapshotami;
pełny odbiór dwóch iteracji pozostaje do wykonania na rzeczywistym jobie.
