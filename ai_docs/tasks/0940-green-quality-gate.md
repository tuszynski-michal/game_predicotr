# TASK-0940 — Zielona bramka `npm run quality` (naprawa błędów sprzed planu)

## Status

`todo`

## Goal

`npm run quality` (format:check, openapi:check, lint, typecheck, test,
snapshot/fixture validate) przechodzi w całości na gałęzi integracyjnej, bez
osłabiania asercji i bez ogólnych wyłączeń typów; lista „znanych błędów”
w audytach znika.

## Context

Audyty TASK-0929–0932 musiały za każdym razem odfiltrowywać te same błędy
istniejące przed planem. Operator zaakceptował to zadanie 2026-10-08 jako
TASK-0940 przed etapem S-B. Plan:
`ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`, etap T.

## Dependencies / entry conditions

- Gałąź `feat/mumie-super-game-plan` na v1.7.271 (równa integracyjnej).
- Fakty (z audytów i raportów wykonawców, do potwierdzenia na starcie):
  1. `services/api/tests/test_v7_independent_progress.py`: błąd kolekcji
     (`ModuleNotFoundError: test_v7_run_state`, import modułu testów workera).
  2. `services/api/tests/test_game_data_v2_schema.py::test_manifest_is_exhaustive_disjoint_and_fail_closed`:
     trzy tabele V7 nieujęte w manifeście własności tabel V2.
  3. `services/api/tests/integration/test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`:
     tabele `management_*` poza `EXPECTED_PUBLIC_TABLES` (test PG,
     `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, bazy `*_test`).
  4. Reviewer: `test/local-reviewer-workspace-contract.test.mjs:63`,
     `test/operational-review-workspace-contract.test.mjs:151` (źródła nie
     zmieniane od v1.7.183 / v1.7.143).
  5. `services/api/tests/test_board_search_share_access_api.py::test_invalid_lifetime_is_rejected_before_starting_the_ingress`:
     1441 minut jest poprawne od TASK-0925 (test opisuje stary limit).
  6. Ruff: `storage/models.py` I001; `services/worker/tests/test_page_geometry_preflight.py:345`
     E501; `ruff format --check` w `application/catalog.py` (hunk ok. linii 173–176).
  7. Mypy: błąd konfiguracji „moduł pod dwiema nazwami” dla
     `scripts/prepare_v7_reviewed_pilot.py`; `main.py:2005` `no-untyped-call`;
     błędy w `board_search_share_queries.py`, `v7_label_geometry_calibration.py`,
     `shape_geometry_v2/core.py`, `contrast_frame_grid_v12.py`,
     `qualified_manual_geometry.py`, `page_geometry_preflight.py`.
  8. TASK-0928 wspomina „cztery stare błędy fixture CLI” w `npm run python:test`.

## Recommended execution

claude-sonnet-5-5 / high. Naprawy testów, lintu i typów bez zmian zachowania
produktu; wiele małych, niezależnych poprawek. Eskalacja do claude-opus-5-5 /
high, gdy naprawa wymaga zmiany logiki produkcyjnej. Audyt: gpt-6.1-sol / high;
do czasu CLI zamiennik claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` (manifest własności tabel)
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- Uruchomić pełne `npm run quality` i `npm run python:test` (oraz PG testy
  bazowe) i zebrać kompletną listę błędów; potwierdzić albo skorygować
  listę powyżej.
- Naprawić każdy błąd u źródła: brakujące wpisy manifestu/`EXPECTED_PUBLIC_TABLES`
  (klasyfikacja tabel według `GAME_DATA_V2_OWNERSHIP.md`), import testowy
  między pakietami (fixture współdzielona albo przeniesienie modułu), testy
  opisujące nieaktualne reguły (dostosować do obowiązującej reguły, z
  odwołaniem do taska, który ją zmienił), formatowanie, długości linii,
  kolejność importów, realne poprawki typów (bez `# type: ignore` bez kodu
  i uzasadnienia; dozwolone tylko przy brakujących typach bibliotek
  zewnętrznych), konfiguracja mypy dla duplikatu nazwy modułu.
- Po naprawach: pełny `npm run quality` zielony.

## Out of scope

- Zmiany zachowania produktu, API, schematu; refaktory poza miejscem błędu.
- Benchmarki i testy obciążeniowe.

## Acceptance criteria

- [ ] `npm run quality` kończy się kodem 0.
- [ ] `npm run python:test` kończy się kodem 0 (łącznie z testami PG przy
      `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`).
- [ ] Żadna asercja nie została usunięta ani osłabiona bez odwołania do
      obowiązującej reguły; każda zmiana testu ma komentarz z numerem taska
      reguły.
- [ ] Brak nowych `# type: ignore` bez kodu błędu i uzasadnienia.

## Expected files

- Istniejące: pliki wymienione w faktach 1–8 oraz manifest własności tabel
  V2, `pyproject.toml` (konfiguracja mypy), `scripts/run_python_tests.ps1`
  tylko jeśli wymaga tego fakt 8.

## Verification

```powershell
# katalog worktree, timeout 600 s
npm run quality
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; npm run python:test
```

## Risks / open questions

- Część błędów może wymagać decyzji (np. czy tabela V7 jest „gry” czy
  „wspólna”); klasyfikować według `GAME_DATA_V2_OWNERSHIP.md`, a przy braku
  jednoznaczności opisać wybór w Outcome.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
