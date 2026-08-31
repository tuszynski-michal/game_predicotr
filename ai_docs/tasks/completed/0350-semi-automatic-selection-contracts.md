---
title: TASK-0350 — Kontrakty półautomatycznej selekcji zdjęć
status: done
last_updated: 2026-08-31
---

# TASK-0350 — Kontrakty półautomatycznej selekcji zdjęć

## Goal

Zdefiniować czyste, niezależne od gry kontrakty półautomatycznej selekcji,
która rozpoznaje wyłącznie wiarygodny zakres `seq_*` na pojedynczym JPEG-u.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`

## Scope

- wersjonowany kontrakt `seq-inclusive-v1` i generator oczekiwanych zakresów;
- tożsamość źródła: względna ścieżka, ordinal, rozmiar i SHA-256;
- kierunek, statusy runu oraz statusy zakresu;
- deterministyczne fingerprinty źródeł i oczekiwanych zakresów;
- `RangeEvidenceGate`, który ocenia wyłącznie lokalny dowód OCR zakresu;
- testy czystej domeny;
- dokumentacja i decyzja architektoniczna.

## Out of scope

- OCR i adapter Paddle;
- grupowanie, wybór środka i checkpointy;
- migracja, ORM, API, OpenAPI, job, worker handler i UI;
- ocena plansz, geometrii, cropów, symboli, ostrości, ekspozycji albo refleksów.

## Acceptance criteria

- [ ] kontrakt jest niezależny od `gameId`, SQL, FastAPI i Reacta;
- [ ] zakresy są dodatnie, inkluzywne i deterministyczne dla obu kierunków;
- [ ] `1–19809` kończy się zakresem `19801–19809`;
- [ ] źródło wymaga bezpiecznej ścieżki, ciągłego indeksu i SHA-256;
- [ ] gate przyjmuje wyłącznie silny lokalny dowód dokładnego expected range;
- [ ] gate nie zawiera jakości plansz jako warunku;
- [ ] historia runu ma jawne stany oraz terminalne blokady.

## Technical notes

Pełna strona ma obecnie dziewięć plansz, lecz nowy kontrakt centralizuje tę
wartość i przyszłe capabilities, zamiast rozpraszać stałą. Kierunek określa
porządek źródeł, a nazwa każdego zakresu pozostaje rosnąca.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/contracts.py`
- `services/worker/tests/test_semi_automatic_selection_contracts.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_semi_automatic_selection_contracts.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_semi_automatic_selection_contracts.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
```

## Risks / open questions

- TASK-0351 musi tylko zaadaptować istniejący, wersjonowany strong local proof;
  nie może dodać drugiego OCR ani własnego progu jakości plansz.
- Żadne zachowanie runtime nie może korzystać z tych kontraktów przed TASK-0352
  i TASK-0353.

## Outcome

### Changed

- Dodano czysty pakiet `game_predictor_worker.semi_automatic_selection` z
  wersjonowanym kontraktem zakresów, źródeł, lifecycle i evidence gate.
- Gate nie ma wejść ani progów dotyczących geometrii, plansz, cropów, symboli
  lub jakości obrazu; konsumuje wyłącznie gotowy strong local proof OCR.
- Zapisano D-279 oraz wymagania i architekturę osobnego workflow.

### Verification results

- `pytest services/worker/tests/test_semi_automatic_selection_contracts.py -q`
  — 15 passed.
- `ruff check` dla nowego pakietu i testu — passed.
- `mypy` dla nowego pakietu — passed.
- `git diff --check` — bez błędów whitespace.

### Not completed

- OCR adapter, staging, migracja, job, API, UI, grupowanie i zapis outputu
  należą do TASK-0351–0356.

### Documentation updates

- Wymagania selekcji zdjęć, architektura, Current State i D-279.

### Recommended next task

- TASK-0351 — wydzielenie istniejącego OCR jako range-only adaptera.
