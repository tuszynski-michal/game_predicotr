---
title: TASK-1206 — Bramka v6: kandydat musi realnie poprawić grę treningową
status: done
last_updated: 2026-11-13
---

# TASK-1206 — Bramka v6: kandydat musi realnie poprawić grę treningową

## Status

`done`

## Goal

Nowa ocena kandydata siatek daje PASS tylko wtedy, gdy na grze treningowej (suma
VALIDATION i REGRESSION) przybywa co najmniej jednej planszy poprawnej albo planszy bez
cięcia symboli i żadnej z nich nie ubywa; wszystkie reguły bramki v5 zostają.

## Context

Bramka v5 przepuściła `01767a49` (52/60 zamiast 53/60 poprawnych plansz VALIDATION,
40 zamiast 41 plansz bez cięcia, 7 zamiast 8 na REGRESSION), bo straty mieściły się w
tolerancji szumu, a `improvementRequired=false` (D-604). Operator: „Wdrożenie i ocena
PASS tylko przy realnej poprawie, liczonej także po cięciu symboli”, „Etap A, potem B”.
Decyzja: D-613 (częściowo zastępuje rezygnację z wymogu poprawy z D-604).

## Dependencies / entry conditions

- TASK-1205 (v1.7.636) na tej samej gałęzi; baza operatora na `0188`.
- Zmiana dodaje migrację `0189_grid_gate_improvement` (operator: stop usług → merge →
  `db:migrate` → start, po zakończeniu importów).

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (wzorzec 1:1 z TASK-1203).

## Relevant docs

- `AGENTS.md`
- [D-604](../../process/decisions/DECISION_LOG_2026.md#d-604--bramka-oceny-siatek-odporna-na-szum)
- [D-609](../../process/decisions/DECISION_LOG_2026.md#d-609--bramka-v5-plansze-bez-cięcia-symboli)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Domena: `IMPROVEMENT_POLICY` (gate v6), `training_game_improved`, `decide_game(improvement=)`,
  wybór v6 przy budowie raportu z `cellCut`, weryfikacja v6/v5 przy odtworzeniu.
- Schematy `GridCorrectionImprovement*`, unie polityk raportu surowego i kalibrowanego,
  OpenAPI i klient.
- SQL v13 (bind v8, dyspozytor `recording_cohort_command_v10`, uprawnienia v13), migracja
  0189, repozytorium kohort, `database_roles`, `EXPECTED_ALEMBIC_HEAD`.
- Admin: „bramka v6 (wymagana poprawa)” i opis powodu.

## Out of scope

- Zmiana metryk, tolerancji v5, bramki ekranowej v3 i raportów historycznych.
- Wykonanie migracji i restart usług (operator).

## Acceptance criteria

- [x] +1 plansza poprawna albo +1 bez cięcia bez żadnej straty → PASS; remis, sama
  poprawa błędu, zysk okupiony stratą i wzajemne znoszenie się ról → REVISE z powodem
  `VALIDATION_NOT_IMPROVED:boards_correct_or_boards_within_cells`.
- [x] Przypadek `01767a49` daje REVISE.
- [x] Pozostałe wymagane gry oceniane bez wymogu poprawy (reguły v5).
- [x] Historyczny raport v5 przechodzi odtworzenie; przemianowanie v5↔v6 i podrobiona
  decyzja są odrzucane; schemat API przyjmuje raport v6.
- [x] Migracja 0189 wiąże pary v3/v5 × gate v4–v6 przez dyspozytor v10, odrzuca inne,
  utrzymuje uprawnienia i blokuje downgrade przy historii v6.

## Test cases

- `services/api/tests/test_grid_gate_improvement.py`.
- `services/api/tests/test_grid_gate_cell_cut.py` (świadoma zmiana: nowe raporty z
  `cellCut` są v6).
- `services/api/tests/integration/test_grid_gate_improvement_postgres.py`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_gate_improvement.py services/api/tests/test_grid_gate_cell_cut.py services/api/tests/test_schema_readiness.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_gate_improvement_postgres.py
```

## Risks / open questions

- Wymóg poprawy na małych zbiorach kontrolnych (19+13 zdjęć) może blokować kandydatów o
  poprawie widocznej tylko w błędzie; to świadomy wybór operatora (realna poprawa w
  planszach).

## Outcome

Commit: v1.7.637 / `27012521e666f58e48fed1fd56d858458fc1114f`.

### Changed

- Domena: `IMPROVEMENT_POLICY` (gate v6), `training_game_improved`,
  `decide_game(improvement=)`; raport z `cellCut` buduje się jako v6, odtworzenie
  rozróżnia v6 i v5.
- Schematy `GridCorrectionImprovementPolicy`, `GridCorrectionImprovementEvaluationPolicy`
  w uniach raportu v3 i kalibrowanego v5; OpenAPI i klient wygenerowane.
- `source_recording_sql_v13`, `source_recording_permissions_v13`, migracja
  `0189_grid_gate_improvement`, repozytorium kohort na `recording_cohort_command_v10`,
  `database_roles`, `EXPECTED_ALEMBIC_HEAD`.
- Admin: „bramka v6 (wymagana poprawa)”, opis powodu i kodu TASK-1205 w teście.

### Verification results

- `test_grid_gate_improvement.py` 11 passed, z `test_grid_gate_cell_cut.py`,
  `test_schema_readiness.py`, `test_grid_correction_evaluation.py`: 76 passed.
- PostgreSQL (jednorazowe bazy `*_test`): `test_grid_gate_improvement_postgres`,
  `test_grid_gate_cell_cut_postgres`, `test_grid_learning_source_limit_postgres` — 3 passed.
- Szersze testy API (ocena, uczenie, bramki, rejestr): 579 passed; 9 failed identycznie
  na `main` (`test_grid_correction_split_adapter` ×6, `test_grid_correction_cohort_contract`
  ×2, `test_game_data_v2_schema::...import_order_independent`); 6 błędów
  `test_grid_model_publication_scoped` tylko we wspólnym przebiegu — osobno 6 passed.
- ruff check/format PASS; mypy zmienionych modułów bez nowych błędów (14 zastanych);
  admin `node --test` dla etykiet 10/10.

### Not completed

- Migracja 0189 na bazie operatora i restart usług (operator, po zakończeniu importów).

### Documentation updates

- D-613 (wpis, indeks; D-582 do archiwum indeksu), `API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-1207: niższe tempo nauki przy kontynuacji z modelu korekt (z pomiarem na GPU).
