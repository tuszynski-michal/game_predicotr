---
title: TASK-0793 — S7 — usunięcie kolumny `render_spec` z komórek weryfikacji (migracja `0136`) i odzyskanie miejsca
status: done
last_updated: 2026-10-01
---

# TASK-0793 — S7 — usunięcie kolumny `render_spec` z komórek weryfikacji (migracja `0136`) i odzyskanie miejsca

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.121; cutover `0136` i `VACUUM FULL` partycji 777 po commicie)

## Goal

`image_symbol_review_cells` nie ma kolumny `render_spec` (ani jej gałęzi w
CHECK-ach), ORM, pisarze i testy nie znają tej kolumny, a partycja 777 po
przepisaniu zajmuje ok. 1/3 dotychczasowego rozmiaru.

## Context

D-467, etap S7, po TASK-0792 (żaden czytelnik runtime nie czyta kolumny;
ORM `deferred_raiseload`). Partycja komórek 777: 34 GB (6,7 GB wiersze,
reszta TOAST `render_spec` + indeksy). Baza 61 GB, `alembic` = `0135`.
Pisarze kolumny: `image_symbol_review_repository` (`_asset_provenance_values`,
`_apply_cell_projection`, zapis `NULL` dla `outside`),
`virtual_grid_geometry_repository` (`_replace_current_cells`,
`_convert_current_cells`), `flag_modified(cell, "render_spec")`. CHECK-i:
`ck_image_symbol_review_cells_asset_provenance` (`jsonb_typeof(render_spec) = 'object'`
dla `virtual_source`) i `ck_image_symbol_review_cells_source_asset`
(`render_spec IS NULL` dla `none`). Test PG `test_cell_render_specs_postgres`
używa kolumny jako punktu odniesienia; eksport `scripts/vision_lab_export.py`
niesie pole `render_spec`.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.120` (TASK-0792) scalony i uruchomiony na bazie operatora.
- Fakt: 7,5 mln komórek ma wpis manifestu bieżącej rewizji (pomiar
  TASK-0792, 0 różnic sum).
- Decyzja operatora 2026-10-01: audyty zawieszone; przepisanie partycji
  (`VACUUM FULL`) wykonuje orkiestrator w oknie bez zapisów.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S7)
- `ai_docs/process/DECISION_LOG.md` (D-467)
- `ai_docs/tasks/completed/0792-render-spec-readers-on-manifests.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (VACUUM FULL, miejsce, VHDX)
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (cutover)

## Scope

- Migracja `0136_drop_cell_render_spec`: `SET LOCAL lock_timeout '5s'`,
  `statement_timeout '120s'`, `LOCK` rodzica komórek ACCESS EXCLUSIVE,
  preflight (0 komórek `virtual_source` bez wpisu manifestu bieżącej
  rewizji planszy — zapytanie po manifestach, nie po JSONB komórek; odmowa
  z kodem), podmiana obu CHECK-ów na wersje bez `render_spec`
  (`asset_provenance` jako `NOT VALID` + walidacja w runbooku, jak w `0135`;
  `source_asset` jest `NOT VALID` już dziś — zachować), `ALTER TABLE …
  DROP COLUMN render_spec` na rodzicu (natychmiastowe, bez przepisania);
  downgrade odmawia (`CELL_RENDER_SPEC_DROP_IRREVERSIBLE` — dane są w
  manifestach, ale odtworzenie kolumny to backfill, nie downgrade).
  `EXPECTED_ALEMBIC_HEAD` = `0136` + test.
- ORM `storage/models.py`: kolumna i gałęzie CHECK usunięte; pisarze bez
  `render_spec` i `flag_modified`; `vision_lab_export` bez pola (zmiana
  kontraktu eksportu opisana); test PG `test_cell_render_specs_postgres`
  przepięty na porównanie z sumą/manifestem; testy jednostkowe tworzące
  komórki bez `render_spec`.
- Runbook `LOCAL_OPERATION_GUIDE.md`: cutover `0136` (stop → merge →
  `db:migrate` → start) + walidacja CHECK; `DATABASE_MAINTENANCE.md`:
  przepisanie partycji komórek po `0136` (`VACUUM (FULL, ANALYZE)
  game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d` w oknie bez zapisów,
  `lock_timeout`, wymagane wolne miejsce ≈ rozmiar wierszy + indeksów po
  usunięciu kolumny, pomiar przed/po).
- Dokumentacja: `DATA_MODEL.md` (kolumna usunięta), `DECISION_LOG.md`
  nota D-467 S7, plan, Outcome.

## Out of scope

- Wykonanie migracji i `VACUUM FULL` na bazie operatora (orkiestrator).
- S8 (TASK-0794), TASK-0796, TASK-0795.

## Acceptance criteria

- [ ] `git grep "render_spec\b"` w `services/*/src` (bez `*_checksum`,
      `virtual_render_spec`, `approved_render_spec`, `renderSpec` manifestu)
      zwraca tylko migracje historyczne.
- [ ] `0136` na bazie `*_test`: preflight odmawia przy komórce bez
      manifestu; upgrade usuwa kolumnę i gałęzie CHECK; downgrade odmawia;
      nowa gra provisionowana po `0136` bez kolumny.
- [ ] Zapis komórek (import wirtualny, ręczna geometria, konwersja,
      rezolucja odroczonej planszy) działa bez kolumny — testy PG z
      TASK-0790/0791/0792 zielone.
- [ ] ruff, mypy --strict, pytest zielone poza znanymi niepowodzeniami HEAD;
      `pytest services/api/tests --collect-only` OK.

## Technical notes

- Kolejność jak w `0135`: CHECK-i przed `DROP COLUMN` (CHECK odwołujący
  się do kolumny blokuje DROP).
- `DROP COLUMN` nie zwalnia miejsca; TOAST znika dopiero przy przepisaniu
  (`VACUUM FULL`); partycje `cf300bc1…`/`2a46d3a6…` są małe.
- Chronione: sumy kontrolne komórek, manifesty, zdarzenia; `render_spec_checksum_sha256`
  zostaje.

## Expected files

- Nowe: `services/api/alembic/versions/0136_drop_cell_render_spec.py`,
  `services/api/tests/integration/test_drop_cell_render_spec_postgres.py`.
- Zmienione: `storage/models.py`, `storage/image_symbol_review_repository.py`,
  `storage/virtual_grid_geometry_repository.py`, `storage/schema_readiness.py`
  + test, `scripts/vision_lab_export.py`, testy, docs.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t793
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_drop_cell_render_spec_postgres.py services/api/tests/integration/test_cell_render_specs_postgres.py services/api/tests/integration/test_virtual_deferred_resolution_postgres.py services/api/tests/integration/test_convert_legacy_boards_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t793pg
```

## Risks / open questions

- Okno `VACUUM FULL` partycji 34 GB: ACCESS EXCLUSIVE, szacunkowo
  10–30 min, weryfikacja symboli stoi; miejsce wewnątrz VHDX wystarcza
  (ok. 65 GB wolnych bloków), plik VHDX nie rośnie.
- Podglądy rekonsyliacji sprzed TASK-0792 wymagają ponownego wygenerowania
  (`guardSha256` liczony bez `render_spec`).

## Outcome

Wypełnione przez implementera 2026-10-01 (przed commitem; status zostaje
`in_progress`, zadanie zamyka orkiestrator). Audyt zawieszony — samodzielny
przegląd diffu.

### Changed

- Nowa migracja `services/api/alembic/versions/0136_drop_cell_render_spec.py`:
  `SET LOCAL lock_timeout '5s'`, `statement_timeout '120s'`, `LOCK` rodzica
  komórek `ACCESS EXCLUSIVE` i manifestów `SHARE`; preflight w bloku `DO`:
  liczba komórek `virtual_source` bez wiersza `board_render_manifests` dla
  `(game_id, recognized_board_id, geometry_revision)` (anti-join po PK
  manifestu, bez JSONB) > 0 → `CELL_RENDER_MANIFEST_MISSING: N virtual review
  cells …`; podmiana `ck_image_symbol_review_cells_asset_provenance` (0135
  bez `jsonb_typeof(render_spec) = 'object'`) i
  `ck_image_symbol_review_cells_source_asset` (0126 bez `render_spec IS
  NULL`), obie `NOT VALID`; `ALTER TABLE … DROP COLUMN render_spec` na
  rodzicu (partycje dziedziczą). Downgrade odmawia
  (`CELL_RENDER_SPEC_DROP_IRREVERSIBLE`). `EXPECTED_ALEMBIC_HEAD` = `0136` +
  test (`0135` na liście odrzucanych).
- `storage/models.py`: kolumna i obie gałęzie CHECK usunięte.
  `image_symbol_review_repository`: `_asset_provenance_values` (oba tryby),
  `_apply_cell_projection`, pozycje `outside` bez `render_spec` i bez
  `flag_modified` (import usunięty; porównanie wartości znów po wszystkich
  kluczach). `virtual_grid_geometry_repository`: `_replace_current_cells` i
  `_convert_current_cells` bez przypisania. `partial_board_reconciliation_repository`:
  `to_jsonb(c)` bez `- 'render_spec'` (wynik identyczny, guard bez zmian).
  `cell_render_specs.py`: docstring.
- `scripts/vision_lab_export.py`: wiersz komórki traci pole automatycznie
  (tabela z ORM); żeby eksport nadal pozwalał odtworzyć wirtualny crop
  rewizji 0, eksporter zamraża i zapisuje `board_render_manifests` plansz
  eksportu (`records/<gra>/board_render_manifests.jsonl`, warunek `game_id` +
  `recognized_board_id`). Wersja eksportera bez zmian (`vision-lab-export-v1`),
  konsument `symbol_snapshot` nie czytał pola; opis w `VISION_LAB_EXPORT.md`.
- Testy: nowe `services/api/tests/integration/test_drop_cell_render_spec_postgres.py`
  i `services/api/tests/test_drop_cell_render_spec_migration.py` (kolejność
  instrukcji, CHECK-i bez kolumny, `NOT VALID`, odmowa downgrade);
  `test_cell_render_specs_postgres` porównuje czytelników z wpisem manifestu
  czytanym niezależnie w SQL i związanym sumą komórki (kolumny już nie ma —
  test to sprawdza); `test_convert_legacy_boards_postgres` buduje schemat
  `0134` na świeżej bazie (downgrade z `0136` niemożliwy), domyślna wartość
  `'{}'` kolumny zastępuje na tej bazie testowej zapis dawnego pisarza, test
  kończy się upgrade'em do `0136` i sprawdza, że skonwertowane komórki i
  decyzje się nie zmieniły; `test_cell_render_specs.py` sprawdza brak
  kolumny w modelu i CHECK-ach; `test_image_symbol_review_virtual_source`,
  `test_cell_level_verification_migration`, `test_outside_current_owner_postgres`
  bez pola.
- Kryterium „`git grep "render_spec\b"` tylko w migracjach” jest dosłownie
  nieosiągalne — `render_spec` to też nazwa pól domenowych (asset, kandydat,
  rekordy renderu, komórka kohorty `verified_training_cohort_cells.render_spec`,
  vision lab). Po zmianie w `services/*/src` nie ma żadnego odwołania do
  kolumny komórki (ani atrybutu ORM, ani SQL), poza migracjami historycznymi.

### Verification results

- `alembic heads` = `0136_drop_cell_render_spec`. ruff check, `ruff format
  --check` czyste dla 18 zmienionych plików `.py`; mypy --strict: 0 błędów
  (`models`, `image_symbol_review_repository`, `virtual_grid_geometry_repository`,
  `partial_board_reconciliation_repository`, `cell_render_specs`,
  `schema_readiness`, `scripts/vision_lab_export.py`, migracja `0136`).
  `git diff --check` czysto; `pytest services/api/tests --collect-only`:
  1 871 testów.
- PostgreSQL (bazy `*_test` utworzone i usunięte, 0 pozostałych):
  `test_drop_cell_render_spec_postgres` 1/1 (schemat `0135`, plansza pełna i
  częściowa; preflight po usunięciu manifestu odmawia
  `CELL_RENDER_MANIFEST_MISSING: 15 virtual review cells`, wersja i kolumna
  bez zmian; upgrade: kolumny nie ma w rodzicu ani w żadnej partycji, oba
  CHECK-i `NOT VALID` bez `render_spec`, 30 wierszy komórek identycznych,
  `VALIDATE CONSTRAINT` obu przechodzi; downgrade odmawia i zostawia `0136`;
  gra provisionowana po `0136` bez kolumny, jej odroczone plansze
  rozwiązane endpointem Reviewera, 24 assety z `get_assets` z manifestu),
  `test_cell_render_specs_postgres` 1/1, `test_convert_legacy_boards_postgres`
  1/1, `test_virtual_deferred_resolution_postgres` 9/9,
  `test_drop_cell_observations_postgres` 1/1, `test_symbol_source_visibility_migration`,
  `test_game_data_v2_postgres` 4/4 (jeden przebieg dał błąd teardownu
  „Refusing DROP while a test connection remains”, powtórka zielona — wyścig
  zamykania połączeń, nie dane). Niepowodzenia jak na HEAD (fixture plansz
  `legacy_file` vs CHECK `0135` albo lokalizacja manifestu v4):
  `test_board_render_manifests_postgres` 2, `test_cell_level_verification_migration` 1,
  `test_outside_current_owner_postgres` 1.
- Testy jednostkowe porcjami ≤ 115 s: API — 20 niepowodzeń, ten sam zbiór
  co na HEAD (`test_reviews` 6, `test_image_import_geometry_guard_api` 7,
  `test_openapi_contract` 2, `test_virtual_grid_geometry` 2,
  `test_image_symbol_reviews_api` 1, `test_migration_baseline` 1,
  `test_lateral_managed_reprocess` 1), reszta zielona; worker — 36
  niepowodzeń korpusu jak na HEAD, reszta zielona (w tym
  `test_vision_lab_export`).
- Tylko do odczytu na bazie operatora: preflight (anti-join) 0 braków w
  6,7 s; 7 500 390 komórek spełnia oba nowe wyrażenia CHECK (0 naruszeń,
  64 s); brak widoków, indeksów i triggerów zależnych od `render_spec`.
  Partycja 777 przed: wiersze 6,7 GB, TOAST 18 GB, indeksy 8,5 GB, razem
  34 GB.

### Not completed

- Migracja `0136` i `VACUUM FULL` na bazie operatora (poza zakresem —
  orkiestrator, osobna zgoda); `CURRENT_STATE.md` zostawiony orkiestratorowi.
- Test PG odmowy migracji `0135` przy planszy `legacy_file` zostaje w
  `test_convert_legacy_boards_postgres` (schemat `0134` + domyślna wartość
  kolumny); nie ma już ścieżki produkcyjnej, która by takiej planszy dała.

### Documentation updates

- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (cutover `0136`, walidacja obu
  CHECK-ów, brak wycofania), `ai_docs/guides/DATABASE_MAINTENANCE.md` 2.6
  (przepisanie partycji 777: okno, `lock_timeout`, wolne miejsce, pomiar
  przed/po), `ai_docs/guides/VISION_LAB_EXPORT.md`,
  `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/process/DECISION_LOG.md`
  (D-467, nota TASK-0793), `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`.

### Recommended next task

- Commit (orkiestrator), cutover `0136` według `LOCAL_OPERATION_GUIDE.md`
  (stop wszystkich procesów → merge → kopia → `db:migrate` → start →
  `VALIDATE CONSTRAINT`), potem okno `VACUUM (FULL, ANALYZE)` partycji 777
  i pomiar; następnie S8 (TASK-0794).
