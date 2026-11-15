---
title: TASK-1208 — Wiązanie plansz po pozycji strony 3 × 3 i bramka cięcia
status: done
last_updated: 2026-11-15
---

# TASK-1208 — Wiązanie plansz po pozycji strony 3 × 3 i bramka cięcia

## Status

`done`

## Goal

Preflight V3 wiąże wykrycia z planszami zdjęcia z niepełnym wykryciem, gdy
wykrycia wyznaczają pełne 3 rzędy i 3 kolumny strony (≤ 2 braki), a bramka cięcia
przepuszcza przypisane sloty takiego wiązania.

## Context

Import Mumie A2 pominął 8 zdjęć `slot_binding_required`; na `seq_246592-246600`
sieć przeoczyła widoczną planszę 246594 i przepadło 9 plansz. Operator: „Tak, dodaj”,
„Pełny automat”. Decyzja D-614; plan
[PARTIAL_SLOT_BINDING_PLAN_20261115](../../delivery/PARTIAL_SLOT_BINDING_PLAN_20261115.md).

## Dependencies / entry conditions

- Gałąź `claude/partial-slot-binding` na szczycie `claude/grid-training-baseline-floor`
  (v1.7.639, niescalona; migracja 0189 tamtej gałęzi). Ten task nie zmienia schematu.

## Recommended execution

Claude Opus 5.5, reasoning high; bez dodatkowego review (eskalacja do audytu, jeśli
wyniki odbiegną od tabeli D-614). Audyt krzyżowy operatora obejmie TASK-1209.

## Relevant docs

- `AGENTS.md`
- [D-614](../../process/decisions/DECISION_LOG_2026.md#d-614--przypisanie-plansz-po-pozycji-strony-3--3-przy-niepełnym-wykryciu)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja D-614)

## Scope

- `associate_expected_slots`: wiązanie dokładne bez zmian, potem nowe
  `associate_partial_slots` (wspólne `_page_frame`, `_axis_clusters`).
- `neural_auto_crop_blockers`: przypisany slot wiązania z brakami jest oceniany jak w
  wiązaniu pełnym, gdy przypisane i brakujące sloty dzielą zakres.

## Out of scope

- Akceptacja V3 (TASK-1209), model siatki, ponowny import na bazie operatora.

## Acceptance criteria

- [x] Wyniki tabeli D-614 na zapisanych węzłach 8 zdjęć (fixture).
- [x] Dotychczasowe testy wiązania, bramki i preflightu bez zmian asercji.
- [x] Brakujący slot nadal `NEURAL_GRID_SLOT_DETECTION_MISSING`; niespójny podział
      zakresu → `NEURAL_GRID_SLOT_BINDING_REQUIRED`.

## Expected files

- `services/api/src/game_predictor_api/domain/neural_grid_proposal.py`
- `services/api/src/game_predictor_api/domain/neural_crop_policy.py`
- Nowe: `services/api/tests/test_partial_slot_binding.py`,
  `services/api/tests/fixtures/neural_partial_slot_binding_mumie_a2.json`

## Verification

```powershell
$env:PYTHONPATH = "services/api/src;services/worker/src;services/api/tests"
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_partial_slot_binding.py services/api/tests/test_neural_grid_proposal.py services/api/tests/test_neural_auto_crop_v2.py services/worker/tests/test_neural_page_geometry_preflight.py services/worker/tests/test_neural_unbound_sources.py
```

## Outcome

Commit: v1.7.640 (hash dopisuje kolejny commit).

- `associate_expected_slots`: wiązanie dokładne bez zmian; po jego porażce
  `associate_partial_slots` (D-614). `associate_quad_slots` korzysta ze wspólnego
  `_page_frame` (te same osie, rzuty i tolerancja; testy ratunku bez zmian).
- `neural_auto_crop_blockers`: zamiast `missingPositionIndexes == []` wymóg, by sloty
  przypisane i brakujące dzieliły zakres bez luk i powtórzeń.
- Węzły 8 zdjęć Mumie A2 (fixture): 246592 brak slotu 2; 431191 brak 1; 439435 brak 2;
  442972 brak 0 (plansza ucięta kadrem); 499996 sloty 0–4, 3 wykrycia pustych slotów
  ignorowane; 304732, 304741 (4 rzędy) i 305785 (2 kolumny) bez wiązania.
- Testy: `test_partial_slot_binding.py` 21 passed; z `test_neural_grid_proposal.py`,
  `test_neural_auto_crop_v2.py`, preflightem i `test_neural_unbound_sources.py` 85 passed.
  Regresja 19 plików neural/reinferencja/akceptacja: 260 passed, 13 failed — te same 13
  (`test_calibrated_neural_evidence`, `test_neural_grid_operation_pin`,
  `test_pending_symbol_reinference`) padają na gałęzi bazowej bez zmian.
- `ruff format/check` i `mypy --strict` zmienionych modułów czyste; `docs:check` OK;
  mapa kodu zregenerowana (zawiera też zaległe symbole TASK-1205/1206).
- Audyt krzyżowy: na polecenie operatora po TASK-1209 (diff obu tasków).
