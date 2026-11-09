---
title: TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%
status: todo
last_updated: 2026-11-09
---

# TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%

## Status

`todo`

## Goal

Deterministyczna ocena zawartości i klasyfikacji bez zmiany aktywnego modelu.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

TASK-1170 zamknięty. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6-astra/high. Uzasadnienie: Deterministyczna ocena zawartości i klasyfikacji bez zmiany aktywnego modelu. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T2 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T2 planu i niezbędne testy regresji. Rzeczywisty renderer; manual potem model; te same instancje; 0.08 vs 0.0 tylko margines; lab RGB osobny kontrakt; bez labels wynik unavailable; bramka per-game bez kompensacji.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Acceptance criteria

- [ ] Każdy punkt T2 planu ma implementację lub jawny warunek zależny od danych.
- [ ] Rzeczywisty renderer; manual potem model; te same instancje; 0.08 vs 0.0 tylko margines; lab RGB osobny kontrakt; bez labels wynik unavailable; bramka per-game bez kompensacji.
- [ ] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [ ] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Analiza read-only wykonawcy potwierdziła asymetrię istniejącego renderera:
padding=0 używa cell.source_quad (dokładne wewnętrzne węzły), dodatni padding
projektuje inset przez homografię całej planszy. Zachować oba zachowania,
zmieniać wyłącznie parametr marginesu i jawnie opisać ten skutek, z regresją
nieregularnych węzłów. Nie poprawiać legacy warpu w tym tasku.
Klasyfikacja wymaga current human class/crop identity, nie samego confidence.
LocalSymbolOnnxAdapter i aktualny confidence contract są źródłem predykcji;
brak progu/modelu/ręcznej klasy daje unavailable. Lab RGB jest osobnym kontraktem.

Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

Zmiana services/worker/src/game_predictor_worker/images/production_cell_evaluation.py (opcjonalny porównawczy kontekst/raster sink z regresją defaultu). Proponowane nowe: images/production_crop_comparison.py, scripts/compare_production_symbol_crops.py, services/worker/tests/test_production_crop_comparison.py; małe moduły pinów/klasyfikacji według odpowiedzialności. Bez zmiany VirtualCellRenderer, symbol_onnx i LAB_RGB runtime.. Drobne doprecyzowania listy zapisać po prześledzeniu pionu.

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
