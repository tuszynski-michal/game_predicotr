---
title: TASK-1188 — Bramka oceny siatek odporna na szum
status: done
---

# TASK-1188 — Bramka oceny siatek odporna na szum

## Status

`done`

## Goal

Nowe oceny kandydatów siatki (raport v3, tylko siatka) odrzucają model wyłącznie
przy rażącym pogorszeniu, a historyczne raporty bramki v2 pozostają ważne.

## Context

Uczenie Mumie a2 z 2026-11-12 (kandydat `bf327cfa`, ocena `8723857d`) dostało
REVISE, bo na A jedna plansza (`e1fb0a96`) przekroczyła próg węzła o 0,0013
(obecny model był 0,0005 pod progiem), a REG poprawił błąd tylko o 1 %. Operator
uznał to za szum i zdecydował (2026-11-12): tolerancja w sumach na A i REG,
bez wymogu poprawy REG; zastosowanie modelu dalej ręczne.

## Dependencies / entry conditions

- `main` 7735bf9c, baza na 0184. Nowa migracja 0185 wymaga zgody operatora
  (stop usług, scalenie, `db:migrate`, start).

## Recommended execution

Claude Opus 5.5, reasoning high: zmiana kontraktu raportu podpisywanego w bazie.
Bez planu i bez audytu krzyżowego (task jednorazowy na polecenie operatora).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/VISION_LAB.md` (raport v3 i bramka v2)
- [D-604](../../process/decisions/DECISION_LOG_2026.md#d-604--bramka-oceny-siatek-odporna-na-szum)

## Scope

- Polityka `grid-model-per-game-gate-v4` dla nowych raportów v3 (i ich
  kalibrowanej wersji v5): na A i REG strata plansz dopasowanych lub poprawnych
  jest regresem dopiero powyżej `max(1, floor(2 % plansz))`, wzrost błędu
  dopiero powyżej `max(15 % bazowego, 0,001)`; brak wymogu poprawy REG.
- Fantomowe i zdublowane plansze na pełnych zdjęciach pozostają ścisłe; utrata
  całkowicie poprawnych zdjęć ma tolerancję 1 zdjęcia.
- Walidacja raportów przyjmuje v2 (historyczne, ścisłe) i v4 (nowe).
- Migracja 0185: `recording_correction_report_bind_v6` (tylko pary v4) i
  `recording_cohort_command_v8`; repozytorium woła v8.
- Schemat API, OpenAPI i klient.

## Out of scope

- Bramka ekranowa v3 (raport v4) zostaje ścisła.
- Automatyczne zastosowanie modelu; zmiana progów poprawności planszy.

## Acceptance criteria

- [x] Wyniki `bf327cfa` dają PASS pod v4 i REVISE pod v2.
- [x] Utrata 2 z 51 plansz albo wzrost błędu o > 15 % daje REVISE pod v4.
- [x] Raport v2 nadal przechodzi walidację, a przepisanie decyzji v4 jako v2 nie.
- [x] Testy API/worker zmienionych modułów, lint, mypy, OpenAPI check zielone.

## Outcome

Commit: v1.7.612 (hash dopisuje kolejny commit).

### Changed

- `domain/grid_correction_evaluation.py`: `TOLERANT_POLICY` (gate v4),
  `decide_game(tolerant=)`, `board_loss_allowance`, `error_increase_allowance`;
  `build_report` dla grid-only zapisuje v4, `require_report` przelicza v2 ściśle
  i v4 tolerancyjnie.
- `schemas/grid_model_evaluations.py`: polityka v4 w raporcie v3 i v5; OpenAPI i
  wygenerowany klient.
- Migracja `0185_grid_gate_noise_tolerance`, `source_recording_sql_v11.py`,
  `source_recording_permissions_v11.py`; repozytorium kohort woła
  `recording_cohort_command_v8`, `database_roles` używa uprawnień v11,
  `EXPECTED_ALEMBIC_HEAD` = 0185.
- Testy: `test_grid_gate_noise_tolerance.py` (18), integracyjny
  `test_grid_gate_noise_tolerance_postgres.py`; `test_schema_readiness.py` na
  0185; `test_production_cell_report_consumers.py` oczekuje surowego PASS dla
  wzrostu błędu 2,5 % (świadoma zmiana kontraktu: szum pod v4 przechodzi).

### Verification results

- `pytest` testy grid/production-cell API i worker: 32 FAIL + 12 ERROR,
  identyczna lista jak na `main` 7735bf9c (zastane, m.in.
  `test_grid_training_cohort_core.py`, `test_grid_training_run_preview.py`,
  `test_api_reader_dispatches_v6_and_rejects_forged_decision`); 908 PASS na
  gałęzi wobec 890 na `main` (+18 nowych).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, baza `*_test`): nowy test
  PASS — pary v3/v5 gate v4 i historyczne v3 gate v2 zapisane, v4/v6 z gate v4
  odrzucone, uprawnienia v11 zgodne, downgrade z historią v4 zablokowany.
- `ruff check`/`format`, `mypy --strict` zmienionych modułów bez błędów;
  `npm run openapi:check` exit 0; typecheck admina z klientem worktree exit 0;
  testy klienta admin-api 167/167.

### Not completed

- Migracja 0185 na bazie operatora, restart usług i ponowna ocena `bf327cfa`
  wymagają osobnej zgody.
- Bramka ekranowa v3 pozostaje ścisła (poza zakresem). Brak audytu krzyżowego.

### Documentation updates

- D-604, indeks decyzji (D-575 do archiwum), `requirements/VISION_LAB.md`,
  `architecture/VISION_LAB.md`, `CURRENT_STATE.md`.

### Recommended next task

- Po migracji: ponowna ocena kandydata `bf327cfa` pod gate v4 i ręczne
  zastosowanie przy PASS.
