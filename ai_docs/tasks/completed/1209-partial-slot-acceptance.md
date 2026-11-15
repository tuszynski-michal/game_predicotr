---
title: TASK-1209 — Akceptacja V3 dla wiązań z brakującymi slotami
status: done
last_updated: 2026-11-15
---

# TASK-1209 — Akceptacja V3 dla wiązań z brakującymi slotami

## Status

`done`

## Goal

Zdjęcie z wiązaniem z brakami (D-614) dostaje akceptację V3 dla przypisanych pozycji,
a brakujące pozycje zostają planszami do ręcznej geometrii, bez blokowania akceptacji.

## Context

Akceptacja decyduje o rozpoznaniu symboli (Mumie A2: rewizje `accepted` 170 424/170 424
plansz z komórkami, `needs_review` 94/733). Dziś wymaga kompletu pozycji, braku
`missingPositionIndexes` i braku odroczonej geometrii. Operator: „Pełny automat”.

## Dependencies / entry conditions

- TASK-1208 na tej samej gałęzi.

## Recommended execution

Claude Opus 5.5, reasoning high. Dodatkowy review: Codex (domyślny model CLI `codex`,
warunkowo), reasoning high, skill `audit-task` — zlecony przez operatora.

## Relevant docs

- `AGENTS.md`
- [D-614](../../process/decisions/DECISION_LOG_2026.md#d-614--przypisanie-plansz-po-pozycji-strony-3--3-przy-niepełnym-wykryciu)
- [plan](../../delivery/PARTIAL_SLOT_BINDING_PLAN_20261115.md)

## Decision update

Bramka kompletności bez zmian. Pierwsze pytanie o D-484 pominęło wyjątek D-523;
po audycie (P0-1) operator wybrał „8 plansz od razu”: przypisane pełne sloty
neuronowe idą od razu do symboli (D-523), brakujący slot czeka pojedynczo, zdjęcie
pozostaje `geometry_incomplete` do zapisania tej planszy.

## Scope

- `qualify_v3_engine_acceptance` i budowa `positions`/`deferred` w repozytoriach
  `v3_engine_acceptance_repository`, `virtual_grid_geometry_repository`,
  `grid_engine_acceptance_repository`: oczekiwane pozycje = zakres minus
  `missingPositionIndexes`; odroczona geometria brakującego slotu nie blokuje.

## Out of scope

- Zmiana bramki cięcia (TASK-1208) i reguły wiązania.

## Acceptance criteria

- [x] Wiązanie z brakami: przypisane pozycje akceptowane, rewizja `accepted`,
      brakująca pozycja `pending` w ręcznej kolejce geometrii.
- [x] Odroczona pozycja przypisana nadal blokuje (`V3_ACCEPTANCE_DEFERRED`).
- [x] Pełne wiązania bez zmian (dotychczasowe testy akceptacji).

## Verification

Testy jednostkowe akceptacji + integracyjne PostgreSQL z
`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'` (bazy `*_test`).

## Outcome

Commit: v1.7.641 / `1c212b529785b43e7927009e64b09df2228c6fab`.

- `qualify_v3_engine_acceptance`: oczekiwane pozycje = zakres minus
  `missingPositionIndexes`; plansze brakujących slotów pomijane; parametr
  `deferred: bool` zastąpiony `deferred_positions` (blokuje tylko odroczenie slotu
  przypisanego). Trzy repozytoria (`v3_engine_acceptance_repository`,
  `virtual_grid_geometry_repository`, `grid_engine_acceptance_repository`) czytają
  pozycje otwartych wierszy `image_board_geometry_pending`.
- Testy jednostkowe: `test_partial_slot_binding.py` (akceptacja z brakiem, odroczony
  slot przypisany, brak przypisanej planszy), `test_v3_engine_acceptance.py`;
  regresja 22 plików neural/reinferencja/akceptacja: 348 passed.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): `test_v3_engine_acceptance_postgres.py`
  i `test_neural_page_geometry_postgres.py` passed (30 z 39 w łącznym przebiegu).
  Scenariusz brakującego slotu: rewizja `accepted`, zdjęcie `geometry_incomplete`,
  otwarty `pending` tylko na slocie 1, brak planszy brakującego slotu, 15 komórek
  przypisanej planszy (v1 i v2; v2 to skutek TASK-1208, zgodny z D-523).
  `test_historical_grid_acceptance_postgres.py`: 9 failed — fixture
  `_provision_game` („provisioning did not reach done”) pada identycznie na gałęzi
  bazowej; ścieżka historyczna (`grid_engine_acceptance_repository`, zmiana tylko
  zapytania o odroczenia) nie ma więc pokrycia integracyjnego — ryzyko odnotowane.
- `ruff format/check` czyste; `mypy --strict` zmienionych modułów: jedyny błąd
  `virtual_grid_geometry_repository.py` (Row vs tuple, ~l. 2923) istnieje na bazie.
- Audyt krzyżowy Codex (CLI 0.162.0, reasoning high, diff obu tasków od 08c3a4db):
  [raport](../../quality/TASK-1209_AUDIT_codex.md), REVISE, P0-1: materializacja
  symboli przypisanej planszy niekompletnego zdjęcia sprzeczna z ówczesnym opisem D-614.
  Przyczyna: mój opis pominął wyjątek D-523. Operator wybrał „8 plansz od razu”
  (zachowanie D-523, bez zmiany bramki); P0-1 zamknięte korektą D-614, wymagań,
  planu i komentarza testu. Bez drugiej rundy (zachowanie objęte P0 nie zmieniło się).
- Nie wykonano: ponownego preflightu i importu 8 zdjęć na bazie operatora (po
  scaleniu, za zgodą); end-to-end zapisania brakującej planszy po imporcie.
