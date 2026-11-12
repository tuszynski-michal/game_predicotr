---
title: Szybkie wyszukiwanie członkostwa kohort w wyzwalaczu
status: done
plan: delivery/GRID_COHORT_NOTICE_PERFORMANCE_PLAN_20261112.md
---

# TASK-1195 — Szybkie wyszukiwanie członkostwa kohort w wyzwalaczu

## Status

`done`

## Goal

Zapis geometrii planszy jako rola API nie skanuje tabeli członków kohort, a
zbiór zdarzeń `currentness_notice` jest identyczny jak przed zmianą.

## Context

Pomiar 2026-11-12: zapis „Zapisz geometrię i dalej” trwa 25–33 s, bo
`grid_cohort_notice_v1` pod `FORCE ROW LEVEL SECURITY` nie może użyć indeksów
GIN (`@>` nie jest `LEAKPROOF`) i dla każdej z ~135 komórek przepinanych przez
`apply_board_repoint` skanuje wszystkich członków (163 ms na wywołanie). Plan:
`delivery/GRID_COHORT_NOTICE_PERFORMANCE_PLAN_20261112.md`, sekcje 1, 3, 5.

## Dependencies / entry conditions

- `main` v1.7.616, Alembic `0185_grid_gate_noise_tolerance`, manifest v22.
- Gałąź `claude/grid-cohort-refs`, worktree `worktrees/grid-cohort-refs`
  (operator 2026-11-12: praca poza głównym checkoutem, w którym działają usługi).

## Recommended execution

claude-opus-5-5 / high: migracja z RLS, partycjami, backfillem i dokładną
równoważnością wyzwalacza; eskalacja przy niezgodności zdarzeń v1/v2.
Audyt: gpt-6.1-sol / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_COHORT_NOTICE_PERFORMANCE_PLAN_20261112.md`
- `ai_docs/architecture/DATA_MODEL.md`, sekcja „Kohorty geometrii aplikacji”
- `ai_docs/architecture/VISION_LAB.md`, sekcja „Per-game candidate evaluation
  and proof currentness”

## Scope

- Migracja `0186_grid_cohort_member_refs` (logika w
  `storage/grid_cohort_member_refs_migration.py`): tabela gry
  `grid_training_cohort_member_refs` z partycjami, RLS i grantami tabeli
  członków; wyzwalacz członków utrzymujący pary; strażnik zapisu par;
  backfill z kontrolą obu kierunków; `grid_cohort_notice_v2` w 14 wyzwalaczach
  `grid_cohort_currentness`; status `retired` (CHECK i przejście
  `frozen ↔ retired` w `grid_cohort_immutable_v1`); manifest v22 → v23.
- `storage/game_data_v2_manifest_v23.py` i podbicie importów manifestu;
  `EXPECTED_ALEMBIC_HEAD`.
- Testy PostgreSQL równoważności, RLS/planu, strażnika i cyklu migracji.

## Out of scope

Logika wycofania i API (TASK-1196), panel (TASK-1197), migracja bazy operatora,
restart usług, zapis w tle w Reviewerze.

## Acceptance criteria

- [ ] Te same zmiany na tabelach próbnych z `grid_cohort_notice_v1` i `_v2`
  dają identyczny multizbiór zdarzeń (9 klasyfikacji: INSERT, zmiana dowodu,
  przeniesienie identyfikatora, DELETE, obcy identyfikator, cisza dla zmian
  symboli), jako rola aplikacji pod RLS.
- [ ] `EXPLAIN` wyszukiwania par jako rola aplikacji z `enable_seqscan=off`
  nie ma `Seq Scan`; stare zapytanie na członkach ma (dowód przyczyny).
- [ ] Pary = tablice członków po capture i po backfillu; inna gra nie widzi par.
- [ ] Bezpośredni INSERT/UPDATE/DELETE par odrzucony
  (`GRID_COHORT_REFS_DERIVED_ONLY`); `frozen → retired → frozen` dozwolone,
  inne zmiany zamrożonej kohorty odrzucone.
- [ ] Downgrade odmawia przy kohorcie `retired`, poza tym przywraca v1 w 14
  wyzwalaczach i manifest v22; ponowny upgrade odbudowuje pary.
- [ ] Istniejące testy kohort i mostu ocen bez regresji.

## Technical notes

- Pary trzyma wyzwalacz `grid_cohort_member_refs` (AFTER INSERT/UPDATE/DELETE
  na członkach), a nie kod Pythona: każdy zapis tablic (`prepare`, `_capture`,
  przyszłe ścieżki) daje te same pary w tej samej transakcji. Odstępstwo
  techniczne od sekcji 3.3 planu, kontrakt bez zmian.
- `member_source_id` w parze zachowuje liczność v1: jedno zdarzenie na
  pasującego członka (współdzielona komórka zależna dwóch członków → dwa
  zdarzenia).
- FK par tylko do kohorty: FK do członka uruchamiałby kontrolę RI przed
  wyzwalaczem usuwającym pary.
- Wyszukiwanie: `ref_kind = … AND ref_id IN (nowy, stary)` — równość `uuid` i
  `text` jest `LEAKPROOF`, więc PK działa pod RLS.
- Backfill: 830 319 par na danych operatora (odczyt 2026-11-12, 0,6 s
  wyliczenia); `statement_timeout` 900 s tylko na backfill i kontrolę.

## Expected files

- Nowe: `services/api/alembic/versions/0186_grid_cohort_member_refs.py`,
  `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py`,
  `services/api/src/game_predictor_api/storage/game_data_v2_manifest_v23.py`,
  `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py`.
- Istniejące: `storage/catalog_repository.py`, `storage/game_partition_lifecycle.py`,
  `storage/game_storage_routing.py`, `storage/grid_cohort_asset_retention.py`
  (import manifestu), `storage/schema_readiness.py` (`EXPECTED_ALEMBIC_HEAD`),
  `tests/test_schema_readiness.py`, dokumentacja.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_cohort_member_refs_postgres.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k "cohort or grid_model_evaluation_bridge or game_storage_routing or gate_noise" -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_schema_readiness.py services/api/tests/test_grid_training_cohort_storage.py -q
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- Czas backfillu na danych operatora zmierzony tylko jako odczyt.
- Pomiar zapisu ≤ 3 s możliwy dopiero po migracji operatora (osobna zgoda).

## Outcome

Commit: v1.7.617 / `e58e22e7a15edaa70d15bbf4b3975fbdbc280724`.

### Changed

- Migracja `0186_grid_cohort_member_refs` (`storage/grid_cohort_member_refs_migration.py`):
  tabela gry `grid_training_cohort_member_refs` (PK `game_id, ref_kind, ref_id,
  cohort_id, member_source_id`, indeks członka, partycje, forced RLS, granty jak
  członkowie), wyzwalacz `grid_cohort_member_refs` na członkach, strażnik
  `grid_cohort_refs_guard_v1`, backfill z kontrolą `EXCEPT` w obu kierunkach,
  `grid_cohort_notice_v2` (cztery wyszukania po prefiksie PK, `UNION ALL`) w 14
  wyzwalaczach, CHECK `ck_grid_training_cohorts_status` z `retired`, gałąź
  `frozen ↔ retired` w `grid_cohort_immutable_v1`, manifest v22 → v23.
- `storage/game_data_v2_manifest_v23.py`; importy manifestu w `catalog_repository`,
  `game_partition_lifecycle`, `game_storage_routing`, `grid_cohort_asset_retention`;
  `EXPECTED_ALEMBIC_HEAD` i test głowy.
- Testy `tests/integration/test_grid_cohort_member_refs_postgres.py` (3 przypadki) i
  `tests/integration/test_grid_cohort_notice_real_save_postgres.py` (prawdziwy zapis).
- `game_partition_lifecycle._provision_partition`: RLS i polityka dla partycji refs
  nowej gry (audyt P0-1).
- Testy przypięte do starszych rewizji: fixture `_application_role_database`
  (manifest v22 dla 0182–0185), `test_production_cell_report_bind_postgres` i
  `test_grid_gate_noise_tolerance_postgres` (upgrade do `head` po kontroli odwracalności).
- Dokumentacja: D-605, `DATA_MODEL.md`, plan zaakceptowany, `DOC_INDEX.md`,
  `CURRENT_STATE.md`, mapa kodu.

Odstępstwo techniczne od planu (sekcja 3.3): pary wylicza wyzwalacz bazy na
członkach zamiast zapisu w `prepare()`/`_capture()`; Python bez zmian, kontrakt
ten sam. FK par tylko do kohorty (FK do członka kolidowałby z kolejnością RI).

### Verification results

- `test_grid_cohort_member_refs_postgres.py` + `test_grid_cohort_notice_real_save_postgres.py`
  po poprawkach audytu: 3 + 1 passed. Prawdziwy `save_review_item` jako rola
  aplikacji przy trzech kohortach: identyczny multizbiór zdarzeń v1 i v2, każda
  kohorta powiadomiona. Partycje refs obu gier mają RLS/FORCE i politykę;
  bezpośredni odczyt partycji w zakresie innej gry zwraca 0 wierszy. Ze stanu
  `retired` odrzucone: `failed`, `canceled`, edycja `summary`, sama rewizja,
  `preparing`. Wcześniej (przed audytem): równoważność
  v1/v2 dla 9 klasyfikacji jako rola aplikacji pod RLS; plan: 4× `Index Cond`
  `ref_kind`+`ref_id`, bez `Seq Scan` przy 20 tys. par; stare `@>` tylko jako
  `Filter`; strażnik, `retired`, backfill, downgrade (odmowa przy `retired`,
  powrót v1 w 14 wyzwalaczach), ponowny upgrade.
- `test_schema_readiness.py`, `test_grid_training_cohort_storage.py`: 28 + 19 passed.
- `ruff check` zmienionych plików: OK; `mypy --strict` zmienionych modułów: 0 błędów
  w nich (14 zastanych w innych plikach).
- `docs:check`, `code-map:check`: OK.
- Odczyt bazy operatora: backfill = 830 319 par, wyliczenie 0,6 s.
- Regresja PostgreSQL (`-k "cohort or grid_model_evaluation_bridge or
  game_storage_routing or gate_noise or effective_grid_material or content_detached
  or production_cell_report or validation_purpose or screen_correction or partition
  or game_lifecycle"`, bez dwóch plików z zaszytym manifestem v19), równolegle na
  gałęzi i na `main` 33e9197e: `main` 33 failed / 17 passed; gałąź 36 failed / 18
  passed. Wszystkie 33 porażki `main` są identyczne na gałęzi (zastane: stare
  manifesty v19 i rewizje 0179/0180 sprzed v22). Trzy porażki tylko na gałęzi
  (testy przypięte do 0183/0185 przy nowym manifeście v23) naprawione:
  fixture `_application_role_database` przypina manifest v22 dla rewizji 0182–0185,
  a `test_production_cell_report_bind_postgres` i
  `test_grid_gate_noise_tolerance_postgres` po sprawdzeniu odwracalności przechodzą
  do `head`. Ponownie: te 3 + nowe 4 testy = 8 passed (w dwóch przebiegach).

- Audyt krzyżowy: `ai_docs/quality/TASK-1195_AUDIT_gpt-6.1-sol.md`, runda 1,
  REVISE (P0: 2, P1: 2). Audyt i commit v1.7.617 powstały pod numerem roboczym
  TASK-1190; przy scaleniu przenumerowano na TASK-1195, bo równoległa sesja na `main`
  zajęła kolejno TASK-1190 (`1190-preflight-preview-lock-busy`) i TASK-1191
  (`1191-fix-two-failing-api-tests`); numery 1192–1194 zostawiono jej jako bufor. Treść raportu bez zmian. Jedna runda poprawek, bez ponownego audytu (skill
  `audit-task`, krok 5):
  - P0-1 naprawione: refs w zbiorze RLS `_provision_partition` + test flag i
    bezpośredniego odczytu partycji.
  - P0-2 naprawione: `retired` wyłączony z ogólnej gałęzi nagłówka
    (`IMMUTABLE_WITH_RETIRE_SQL`); `IMMUTABLE_ORIGINAL_SQL` dla downgrade bez zmian;
    testy negatywne wyjść z `retired`.
  - P1-1 naprawione: test prawdziwego `save_review_item` (3 kohorty, rola
    aplikacji, v2 vs v1 z ROLLBACK, wszystkie 14 tabel produkcyjnych przez
    wyzwalacze rzeczywistego zapisu).
  - P1-2 naprawione: wynik regresji poniżej.

### Not completed

- Migracja bazy operatora i pomiar zapisu ≤ 3 s (osobna zgoda, plan sekcja 7).
- Zastane (P0-1 pokrewne, poza zakresem): `_provision_partition` nie włącza RLS
  dla partycji `grid_cell_content_revisions/sessions/commands` (0182) nowych gier;
  wymaga osobnego taska.
- Zastane: `test_per_game_isolation_new_game.py` i `test_postgres_baseline.py`
  padają przy kolekcji (manifest v19 zaszyty, tak samo na `main`); `main.py` nie
  przechodzi `ruff format` (stan `main`). Nie naprawiane.

### Documentation updates

- D-605, `DATA_MODEL.md` (kohorty), plan, `DOC_INDEX.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-1196 (wycofanie i przywrócenie kohorty, backend i API).
