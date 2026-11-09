---
title: TASK-1172 — Powiązanie renderowania i danych z uczeniem
status: todo
last_updated: 2026-11-09
---

# TASK-1172 — Powiązanie renderowania i danych z uczeniem

## Status

`todo`

## Goal

Zachowanie rozłącznych danych, przypiętych kontraktów i historycznych raportów.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

TASK-1171 zamknięty. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6-astra/high. Uzasadnienie: Zachowanie rozłącznych danych, przypiętych kontraktów i historycznych raportów. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T3 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T3 planu i niezbędne testy regresji. Aktualne liczniki i braki; R0–R3 używają tych samych pinned danych; zmiana kontraktu unieważnia zgodę starego raportu; partial nie tworzy tła; kod/dane/jakość osobno; cold restart/replay.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Acceptance criteria

- [ ] Każdy punkt T3 planu ma implementację lub jawny warunek zależny od danych.
- [ ] Aktualne liczniki i braki; R0–R3 używają tych samych pinned danych; zmiana kontraktu unieważnia zgodę starego raportu; partial nie tworzy tła; kod/dane/jakość osobno; cold restart/replay.
- [ ] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [ ] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

services/api/src/game_predictor_api/storage/production_cell_reference.py; grid_content_experiment_inputs.py; services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py; istniejąca gotowość/raport i testy. Drobne doprecyzowania listy zapisać po prześledzeniu pionu.

## Test cases

Kryteria planu: ghost quad, wspólne granice/perspektywa, J/10/obramowania/ciemne
symbole, sąsiad, brak pikseli/rzędu, blind isolation, CAS/currentness i restart/replay.
Testy specyficzne dla taska doprecyzować przed implementacją w raporcie weryfikacji.

## Verification

Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

## Risks / open questions

Brak GT i rodowodu może blokować wynik jakości, nie implementację narzędzia.
Nie deklarować poprawy wytrenowanego modelu bez rzeczywistego eksperymentu.

## Outcome

W trakcie realizacji.
