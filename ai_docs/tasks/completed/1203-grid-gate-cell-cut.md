---
title: TASK-1203 — Bramka v5: plansze bez cięcia symboli
status: done
last_updated: 2026-11-13
---

# TASK-1203 — Bramka v5: plansze bez cięcia symboli

## Status

`done`

## Goal

Nowa ocena kandydata siatek odrzuca model, który w roli VALIDATION albo REGRESSION ma
wyraźnie mniej plansz bez cięcia symboli (węzły pól w 10 % pola) niż model bazowy.

## Context

Bramka v4 liczy błąd względem przekątnej planszy i toleruje przesunięcie linii o ćwierć
pola. Operator: „zaostrz ocenę modelu pole po polu”, „zrób ostrzejszą ocenę siatek z
migracją”. Decyzja: D-609.

## Dependencies / entry conditions

- Baza operatora na `0186_grid_cohort_member_refs`; zmiana dodaje `0187_grid_gate_cell_cut`.
- Etykiety referencyjne: zatwierdzone siatki z kohort (bez nowych etykiet, D-608).

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (polecenie operatora).

## Relevant docs

- `AGENTS.md`
- [D-604](../../process/decisions/DECISION_LOG_2026.md#d-604--bramka-oceny-siatek-odporna-na-szum)
- [D-609](../../process/decisions/DECISION_LOG_2026.md#d-609--bramka-v5-plansze-bez-cięcia-symboli)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Worker: `cell_cut_fraction`, liczba `boards_within_cells` na zdjęciu, blok `cellCut`
  roli tylko w ocenie korekt (`measure_role(cell_cut=True)`).
- API: polityka v5, walidacja `cellCut`, decyzja, wybór v5/v4 przy budowie raportu,
  schematy odpowiedzi, OpenAPI i klient.
- Migracja 0187: bind v7, dyspozytor v9, uprawnienia v12, głowa schematu.
- Admin: etykiety „bramka v5” i powodu `boards_within_cells`.

## Out of scope

- Zmiana metryk v1, `measure()`, wyboru checkpointu i bramki ekranowej v3.
- Wykonanie migracji i restart usług (operator).

## Acceptance criteria

- [x] Równe liczby plansz w polach przechodzą; utrata ponad `max(1, 2 %)` odrzuca rolę.
- [x] Kandydat identyczny w metrykach v4, ale tnący symbole, nie przechodzi v5.
- [x] Raport v5 przechodzi ponowną weryfikację; podrobione `cellCut` lub przemianowanie
  na v4 są odrzucane; pomiar bez `cellCut` daje v4.
- [x] Stare raporty serializują się bez nowego `null`.
- [x] Migracja wiąże pary v4/v5, odrzuca inne schematy i chroni historię v5 przed downgrade.

## Test cases

- `services/worker/tests/test_grid_cell_cut.py`: przesunięcie względne do pola, skala,
  ścinanie, liczenie tylko dopasowanych plansz.
- `services/api/tests/test_grid_gate_cell_cut.py`: decyzje, budowa i odtworzenie
  raportu, podróbki.
- `services/api/tests/integration/test_grid_gate_cell_cut_postgres.py`: pary, uprawnienia,
  historia.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_cell_cut.py services/api/tests/test_grid_gate_cell_cut.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_gate_cell_cut_postgres.py
```

## Risks / open questions

- Próg 0,10 pola to reguła produktowa bez kalibracji na danych; porównanie jest
  względne (kandydat vs baza), więc nie blokuje modelu równego bazowemu.

## Outcome

Commit: v1.7.632 / `db2f6357fd363fc0c9000c1e395c44f9e1e266af`.

### Changed

- Worker: `grid_correction_metrics.cell_cut_fraction`, `boards_within_cells`,
  `cell_cut_summary`; handler oceny włącza `cell_cut` tylko dla oceny korekt.
- API: `CELL_CUT_POLICY` (gate v5), `require_cell_cut`, `decide_game(cell_cut=)`,
  `build_report`/`require_report` dla v5; schematy `GridCorrectionCellCut*`.
- Migracja `0187_grid_gate_cell_cut`, `source_recording_sql_v12`,
  `source_recording_permissions_v12`, `recording_cohort_command_v9` w repozytorium
  kohort, `EXPECTED_ALEMBIC_HEAD`.
- Admin: etykiety bramki v5 i powodu; OpenAPI i klient wygenerowane.

### Verification results

- Nowe testy workera i bramki oraz testy v4, oceny korekt i głowy schematu: 88 passed.
- Szersze testy workera i API dotyczące ocen: wszystkie poza 7 porażkami, które
  identycznie padają na `main` (`test_grid_training_cohort_core` ×6,
  `test_production_cell_report_consumers::test_api_reader_dispatches_v6...`).
- Admin `node --test`: 864/864; `tsc` z klientem gałęzi PASS; klient i OpenAPI aktualne.
- ruff check/format PASS; mypy zmienionych modułów bez nowych błędów (14 zastanych).
- PostgreSQL (jednorazowe bazy `*_test`): `test_grid_gate_cell_cut_postgres` i `test_grid_gate_noise_tolerance_postgres` — 2 passed (upgrade do 0187, downgrade, pary, uprawnienia, ochrona historii).

### Not completed

- Migracja `0187` na bazie operatora i restart API/workerów (operator, osobna zgoda).
- Kalibracja progu 0,10 na rzeczywistych ocenach.

### Documentation updates

- D-609 (wpis i indeks), `API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- Po migracji: ponowna ocena bieżącego kandydata Mumie A2 bramką v5.
