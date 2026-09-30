---
title: TASK-0752 — S1 — osierocone funkcje legacy, bazy diagnostyczne i narzędzia jednorazowe
status: done
last_updated: 2026-09-30
---

# TASK-0752 — S1 — osierocone funkcje legacy, bazy diagnostyczne i narzędzia jednorazowe

## Status

`done`

## Goal

Baza bez osieroconych funkcji triggerów legacy i baz `diag_*`, repozytorium
bez jednorazowych narzędzi V1/v0.9; dokumenty D-448 i D-443 zgodne ze stanem
(migracja `0125` zastosowana).

## Context

D-467, etap S1. Inwentaryzacja 2026-09-30: 7 funkcji triggerów w `public`
bez żadnego triggera i zależności (pozostałość po tabelach usuniętych w
`0125`), 3 bazy diagnostyczne (42 MB, 0 referencji w repo), skrypty legacy
zablokowane przez D-443 albo dotyczące tylko usuniętego magazynu `public`.

## Dependencies / entry conditions

- Fakt: `alembic_version` = `0128`, 0 tabel game-owned w `public`.
- Fakt: 0 triggerów wskazuje na wymienione funkcje (sprawdzone odczytem).

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-467, D-448, D-443)

## Scope

- Migracja `0129_drop_orphaned_legacy_trigger_functions`: zamrożona lista
  7 funkcji, preflight (0 triggerów, 0 zależności — inaczej
  `LEGACY_TRIGGER_FUNCTION_STILL_REFERENCED` bez DDL), `DROP FUNCTION …
  RESTRICT`, downgrade odmawia.
- Skrypt `scripts/drop_diagnostic_databases.py`: podgląd z rozmiarami i
  liczbą sesji, suma podglądu, `--execute --confirm <fraza>`; odmowa dla
  bazy spoza zamrożonej listy, chronionej albo z otwartymi sesjami.
- Usunięcie: `scripts/preview_legacy_game_managed_asset_gc.py`,
  `audit_legacy_public_game_store.py`, `preview_legacy_game_cleanup.py`,
  `delete_legacy_game_resumable.py`, `backfill_v09_schema.py`,
  `report_v09_storage_cleanup.py`,
  `services/api/src/game_predictor_api/storage/v09_schema_backfill_repository.py`
  i ich testów (`test_legacy_*`, `test_v09_*_script/report/repository`,
  `integration/legacy_release_process_probe.py`,
  `integration/test_legacy_public_store_*`). Testy historycznych migracji
  `integration/test_v09_*_migration.py` zostają.
- Dokumenty: plan D-448 `completed` z notą o zastosowanej `0125`, runbook
  `archived`, D-443 `superseded by D-467`, `LOCAL_OPERATION_GUIDE.md` (sekcja
  0.9 jako historyczna), `RESUMABLE_LEGACY_DELETION.md` `archived`.
- `test_migration_baseline.py`: oczekiwany head `0129` i łańcuch
  `0126 → 0129` (test był czerwony od `0126`).

## Out of scope

- `build_legacy_board_search_archive.py` i modele archiwum (S5), scratch w
  root (TASK-0753), uruchomienie migracji i skryptu na bazie operatora bez
  zgody.

## Acceptance criteria

- [x] Migracja `0129` na izolowanej bazie: usuwa tylko listę, zostawia inne
  funkcje i funkcje/triggery V2, działa przy częściowo usuniętej liście,
  odmawia przy triggerze, downgrade odmawia (5 testów).
- [x] Skrypt baz `diag_*`: testy jednostkowe odmów i frazy potwierdzenia.
- [x] 0 referencji do usuniętych modułów w kodzie i `package.json`.
- [x] Ruff, mypy, testy API; audyt bez P0–P2.
- [ ] Migracja i `--execute` na bazie operatora za osobną zgodą.

## Technical notes

- Świeża baza po `0128` nadal ma te funkcje (tworzą je historyczne
  migracje; `0125` usunęła tabele i triggery, nie funkcje), więc `0129`
  jest potrzebna także dla nowych baz.
- Preflight liczy zależności z `pg_depend` (`refclassid = pg_proc`, bez
  wpisów wewnętrznych) i dopasowuje tylko sygnaturę `() RETURNS trigger`;
  `alembic upgrade --sql` jest odrzucane (wymagany preflight online), jak w
  `0125`.

## Test cases

- `services/api/tests/integration/test_drop_orphaned_legacy_trigger_functions_migration.py`
  (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`).
- `services/api/tests/test_drop_diagnostic_databases_script.py`.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q services/api/tests/integration/test_drop_orphaned_legacy_trigger_functions_migration.py services/api/tests/test_drop_diagnostic_databases_script.py
.\.venv\Scripts\python.exe scripts/drop_diagnostic_databases.py   # podgląd
```

## Risks / open questions

- Migracja `0129` zostanie zastosowana na bazie operatora dopiero po
  zgodzie (jak każde DDL w tym planie); do tego czasu `alembic` zgłasza
  pending head.

## Outcome

### Changed

- Migracja `0129` (7 osieroconych funkcji, preflight online, sygnatura
  `() RETURNS trigger`, `RESTRICT`, downgrade odmawia) i 5 testów na
  izolowanych bazach (w tym częściowo usunięta lista i ochrona funkcji V2).
- `scripts/drop_diagnostic_databases.py` z podglądem, sumą i frazą
  potwierdzenia; 5 testów jednostkowych.
- Usunięte 6 skryptów legacy/v0.9, `v09_schema_backfill_repository.py` i
  9 plików testów; `test_migration_baseline.py` sprawdza head `0129`.
- Dokumenty: plan D-448 `completed`, runbook `0125` i
  `RESUMABLE_LEGACY_DELETION.md` `archived`, D-443 `superseded`,
  `LOCAL_OPERATION_GUIDE.md` bez procedury 0.9; plan D-467 i README.

### Verification results

- `test_migration_baseline.py` 66/66, testy migracji `0129` 5/5, skrypt 5/5,
  Ruff, mypy `--strict` na migracji i skrypcie.
- Audyt `claude-opus-5-5`: FAIL (P2: czerwony baseline od `0126`,
  przewodniki wskazujące usunięte skrypty) → poprawki → PASS. Zostawione P3:
  testy `main()` skryptu, raport częściowej porażki.
- Zestaw testów API biegł równolegle z edycją S2 w tym samym worktree, więc
  jego wynik jest niemiarodajny; pełny zestaw powtórzy TASK-0754.

### Not completed

- Migracja `0129` i `--execute` dla baz `diag_*` na bazie operatora czekają
  na zgodę (podgląd skryptu: 3 bazy, 42 MB, fraza
  `DROP-DIAGNOSTIC-DATABASES bbe2f95ce5886802`).
