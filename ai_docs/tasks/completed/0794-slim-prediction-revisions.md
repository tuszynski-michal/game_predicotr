---
title: TASK-0794 — S8 — odchudzenie rewizji predykcji (`predictions[].virtualCell` bez `renderSpec`)
status: done
last_updated: 2026-10-01
---

# TASK-0794 — S8 — odchudzenie rewizji predykcji (`predictions[].virtualCell` bez `renderSpec`)

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.122; cutover `0137`, odchudzenie i `VACUUM FULL` po commicie)

## Goal

`image_symbol_prediction_revisions.predictions[].virtualCell` zawiera tylko
sumy kontrolne i klucze tożsamości (bez pełnego `renderSpec`), nowe rewizje
są pisane w tej postaci, istniejące 794 214 rewizji są odchudzone
wznawialnym skryptem, a `apply-revert` zakończonych przebiegów biblioteki
wzorców (D-466) nadal rozpoznaje swoje kotwice.

## Context

D-467, etap S8. Tabela `image_symbol_prediction_revisions`: 794 214 wierszy,
partycja 777 = 11 GB; `predictions` to lista 15 wpisów
(`rowIndex`, `columnIndex`, `symbolCode`, `confidence`, `alternatives`,
`virtualCell`), a `virtualCell` = `renderSpec` (ok. 2,5 KB, duplikat
manifestu renderu) + `extractorVersion`, `cropChecksumSha256`,
`logicalCellKeySha256`, `logicalCellKeyV2Sha256`, `renderIdentityV2Sha256`,
`renderSpecChecksumSha256`, `renderedPixelChecksumSha256`. Średni rozmiar
`predictions` (próbka 2 000): 12 kB po kompresji TOAST.

Pisarze/czytelnicy `virtualCell` (`git grep -i virtualcell` w `services/*/src`):
`api/image_symbol_reviews.py` (22), `schemas/image_symbol_reviews.py` (7),
`worker/images/pending_symbol_reinference.py` (6), `domain/image_geometry_v2.py`
(6), `worker/images/production_workflow.py` (4), `application/virtual_grid_geometry.py`
(4), `worker/symbols/training_dataset.py` (2), `worker/images/__init__.py` (2),
`main.py` (2), `application/image_symbol_reviews.py` (2),
`worker/images/pipeline_store.py` (1), `storage/image_review_repository.py` (1).

Biblioteka wzorców (D-466): `worker/symbols/reference_library_writer.py`
— `predictions_digest(predictions)` = sha256 kanonicznego JSON całej listy;
`apply` sprawdza `predictions_digest(latest.predictions) == plan.predictions_sha256`
(linia 319), `revert` sprawdza `predictions_digest(previous.predictions) ==
plan.predictions_sha256` (linia 393); manifesty zakończonych przebiegów na
dysku (`artifacts/.../apply-manifest*.json`) niosą `predictionsSha256`
liczone po pełnej postaci. Skrypt `scripts/evaluate_symbol_reference_library.py`
liczy `predictionsSha256` w `apply-preview` (linia 2153).

Kotwice `apply-revert`: 86 453 zastąpione rewizje modelu pod rewizją
biblioteki — zostają (D-467).

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.121`, `alembic` = `0136` na bazie operatora; żaden
  przebieg zapisu biblioteki nie trwa (TASK-0749/0750 zakończone).
- Fakt: specyfikacja renderu bieżącej rewizji każdej planszy jest w
  `board_render_manifests`; dla rewizji geometrii > 0 także w
  `image_board_geometry_revisions.virtual_render_spec`. Rewizja predykcji
  starszej rewizji geometrii 0 (po zmianie geometrii planszy) traci pełny
  `renderSpec` po odchudzeniu — zostają sumy i klucze (świadoma utrata,
  bez konsumenta runtime; opisać w DECISION_LOG).
- Decyzja operatora 2026-10-01: audyty zawieszone; odchudzenie istniejących
  rewizji wykonuje orkiestrator skryptem z podglądem.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S8)
- `ai_docs/process/DECISION_LOG.md` (D-466, D-467)
- `ai_docs/tasks/completed/0792-render-spec-readers-on-manifests.md`,
  `0793-drop-cell-render-spec-column.md`
- `ai_docs/architecture/DATA_MODEL.md` (rewizje predykcji)

## Scope

- Kontrakt odchudzonej rewizji: `virtualCell` bez klucza `renderSpec`,
  pozostałe pola bez zmian; wersja kształtu w domenie (stała, np.
  `PREDICTION_VIRTUAL_CELL_SCHEMA = "slim-v2"`), walidacja przy zapisie
  odrzuca `renderSpec` w `virtualCell`. Pisarze (`pending_symbol_reinference`,
  `production_workflow`/`pipeline_store`, ręczna geometria,
  `reference_library_writer`) i schematy API (`schemas/image_symbol_reviews.py`,
  `api/image_symbol_reviews.py` — jeśli eksponują `virtualCell`, OpenAPI +
  klient + wrapper pionem; sprawdzić, czy Admin/Reviewer używają `renderSpec`
  z predykcji — jeśli tak, przepiąć na czytelnik manifestu z TASK-0792).
- Digest v2: `predictions_digest` liczony po odchudzonej projekcji
  (usunięcie `virtualCell.renderSpec` przed kanonizacją) — ta sama funkcja
  dla rewizji pełnych i odchudzonych; `apply-preview` zapisuje
  `predictionsDigestVersion: 2` w manifeście. Zgodność wsteczna dla
  zakończonych przebiegów: kolumna
  `image_symbol_prediction_revisions.legacy_predictions_sha256` (varchar 64,
  nullable) wypełniana przez skrypt odchudzania digestem v1 (po pełnej
  postaci) tuż przed usunięciem `renderSpec`; `apply`/`revert` akceptują
  `plan.predictions_sha256` równe digestowi v2 albo `legacy_predictions_sha256`.
  Migracja `0137_prediction_revisions_slim` dodaje kolumnę (bez
  przepisania danych; downgrade usuwa kolumnę). `EXPECTED_ALEMBIC_HEAD` =
  `0137` + test.
- Skrypt `scripts/slim_prediction_revisions.py` (`--game-id`, `--preview`
  domyślnie, `--execute`, `--max-seconds`, `--batch-size`, wznawialny po
  `id`): dla każdej rewizji z `renderSpec` w `virtualCell`: oblicza digest v1,
  zapisuje `legacy_predictions_sha256`, usuwa `renderSpec` z każdego wpisu,
  sprawdza, że digest v2 po zapisie == digest v2 przed zapisem; porcje w
  osobnych transakcjach; raport JSON (liczby, bajty przed/po z
  `pg_column_size`). Podgląd: liczba rewizji do odchudzenia, próbka
  rozmiarów.
- Retencja: usunięcie rewizji zastąpionych review items bez komórek
  (plan: 0,12 GB) — skrypt z podglądem i `--execute` (osobny tryb tego
  samego skryptu albo osobny skrypt), bez dotykania kotwic (rewizje
  wskazywane przez `model_checksum_sha256` biblioteki albo przez komórki).
- Testy: jednostkowe (digest v2 = stały dla pełnej i odchudzonej postaci;
  pisarze odrzucają `renderSpec`; `apply`/`revert` z `legacy_predictions_sha256`),
  PG (skrypt odchudzania na bazie `*_test` z rewizją pełną: kolumna
  legacy wypełniona, `renderSpec` usunięty, digest v2 niezmieniony,
  powtórka = 0 zmian; migracja `0137`).
- Dokumentacja: `DATA_MODEL.md`, `DECISION_LOG.md` (nota D-467 S8 + D-466
  digest v2 i kolumna legacy), plan, `LOCAL_OPERATION_GUIDE.md` (cutover
  `0137` + skrypt), `DATABASE_MAINTENANCE.md` (VACUUM FULL partycji rewizji
  po odchudzeniu), Outcome.

## Out of scope

- Wykonanie skryptu i `VACUUM FULL` na bazie operatora (orkiestrator).
- TASK-0796 (ścieżki v19/enumy/ORM), TASK-0795 (rola bazy).

## Acceptance criteria

- [ ] Nowe rewizje predykcji nie zawierają `virtualCell.renderSpec`
      (pisarze + walidacja), `git grep "renderSpec"` w kodzie rewizji
      predykcji dotyczy tylko odczytu starych postaci / skryptu.
- [ ] `predictions_digest` v2 daje tę samą wartość dla rewizji przed i po
      odchudzeniu; `apply` i `revert` biblioteki działają dla manifestu v1
      (`legacy_predictions_sha256`) i v2 — testy.
- [ ] Skrypt: podgląd read-only; `--execute` wznawialny; raport; test PG.
- [ ] `0137` + `EXPECTED_ALEMBIC_HEAD`; ruff/mypy/pytest zielone poza
      znanymi niepowodzeniami HEAD; `--collect-only` OK.

## Technical notes

- Nie zmieniać `crop_manifest_checksum_sha256` (idempotencja przeliczeń)
  ani `model_checksum_sha256` (kotwice biblioteki).
- Kanonizacja JSON jak w `reference_library_writer.canonical_json`.
- Czytelnicy `virtualCell.renderSpec` w runtime: sprawdzić `pending_symbol_reinference`
  (porównanie sum przy przeliczeniu — powinno iść po `renderSpecChecksumSha256`),
  `application/virtual_grid_geometry.py`, `image_review_repository`
  (mapper predykcji); każdy przepiąć na sumy albo czytelnik manifestu.
- Chronione: kotwice `apply-revert`, decyzje, zdarzenia.

## Expected files

- Nowe: `scripts/slim_prediction_revisions.py`,
  `services/api/alembic/versions/0137_prediction_revisions_slim.py`,
  testy (`services/worker/tests/test_reference_library_digest_v2.py`,
  `services/api/tests/integration/test_slim_prediction_revisions_postgres.py`).
- Zmienione: `worker/symbols/reference_library_writer.py`,
  `scripts/evaluate_symbol_reference_library.py`, pisarze z Context,
  `storage/models.py`, `storage/schema_readiness.py` + test, docs.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t794
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_slim_prediction_revisions_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t794pg
.\.venv\Scripts\python.exe scripts/slim_prediction_revisions.py --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --preview
```

## Risks / open questions

- Utrata pełnego `renderSpec` dla rewizji predykcji starszych rewizji
  geometrii 0 (patrz Dependencies) — akceptowana.
- Zmiana digestu: manifesty zakończonych przebiegów działają przez kolumnę
  legacy; nowe `apply-preview` liczą v2.
- `VACUUM FULL` partycji rewizji (11 GB) — okno jak w S7.

## Outcome

Wypełnione przez implementera 2026-10-01 (przed commitem; status zostaje
`in_progress`, zamyka orkiestrator). Audyt zawieszony — samodzielny przegląd
diffu.

### Changed

- Domena `services/api/src/game_predictor_api/domain/prediction_revisions.py`:
  `PREDICTION_VIRTUAL_CELL_SCHEMA = "slim-v2"`, `PREDICTIONS_DIGEST_VERSION = 2`,
  `canonical_json` (bajtowo jak dotąd w D-466), `slim_predictions`,
  `has_virtual_render_spec`, `require_slim_predictions`
  (`PREDICTION_REVISION_RENDER_SPEC_PRESENT`, `…_PREDICTIONS_INVALID`),
  `predictions_digest_v1` (dawna funkcja), `predictions_digest` (v2 = v1
  postaci odchudzonej) i `predictions_match` (plan pasuje do v2, v1 bieżącej
  postaci albo `legacy_predictions_sha256`).
- `storage/models.py`: `ImageSymbolPredictionRevisionModel.legacy_predictions_sha256`
  + CHECK formatu; `@validates("predictions")` odrzuca `virtualCell.renderSpec`
  przy każdym zapisie ORM. Migracja `0137_prediction_revisions_slim`
  (`lock_timeout` 5 s, `ACCESS EXCLUSIVE` na rodzicu, `ADD COLUMN`, CHECK
  `NOT VALID` + `VALIDATE` w tej samej migracji; downgrade usuwa kolumnę, ale
  odmawia `PREDICTION_REVISION_LEGACY_DIGEST_PRESENT`, gdy skrypt ją
  wypełnił — inaczej manifesty v1 zakończonych przebiegów straciłyby
  kotwice). `EXPECTED_ALEMBIC_HEAD` = `0137` + test (`0136` na liście
  odrzucanych).
- Pisarze: `pipeline_store` (rewizja importu) i `pending_symbol_reinference`
  (przeliczenie) bez `renderSpec` w `virtualCell`;
  `reference_library_writer`: digesty z domeny (re-eksport, `__all__`),
  `apply`/`revert` porównują plan przez `predictions_match`, `apply` zapisuje
  odchudzoną listę, `revert` przywraca odchudzoną kopię poprzedniej rewizji
  (ten sam digest v2); `crop_manifest_checksum_sha256` i
  `model_checksum_sha256` bez zmian. `scripts/evaluate_symbol_reference_library.py`:
  `apply-preview` liczy v2 (ta sama funkcja `predictions_digest`) i zapisuje
  `predictionsDigestVersion: 2` (format manifestu bez zmian, stare manifesty
  bez pola = v1).
- Czytelnicy runtime `virtualCell`: `image_review_repository`
  (mapper rewizji kwalifikowanej) i `board_search_projection_repository`
  porównywali już tylko `renderSpecChecksumSha256` — bez zmian.
  `api/`, `schemas/`, Admin i Reviewer nie eksponują `virtualCell` ani
  `renderSpec` predykcji (wystąpienia `virtualcell` w `git grep -i` to
  atlas podglądów i klasa domenowa `VirtualCell`) — kontrakt API bez zmian,
  bez OpenAPI/klienta.
- Skrypt `scripts/slim_prediction_revisions.py` + biblioteka
  `storage/prediction_revision_slimming.py`: `--mode slim|retention`,
  `--preview` (domyślnie; transakcja READ ONLY, `lock_timeout` 5 s, działa
  też na `0136` bez kolumny), `--execute` (porcja = transakcja, `--batch-size`
  domyślnie 500, `--max-seconds`, checkpoint `slim-checkpoint.json` z
  ostatnim `id`, raport JSON w `artifacts/data/exports/prediction-revision-slim/<gra>/`).
  Slim: `SELECT … WHERE legacy_predictions_sha256 IS NULL AND id > kursor
  ORDER BY id LIMIT n FOR UPDATE`, digest v1 → kolumna, usunięcie
  `renderSpec`, kontrola v2 przed zapisem i po odczycie zwrotnym w tej samej
  transakcji (`PREDICTION_REVISION_SLIM_DIGEST_DRIFT` / `…_VERIFY_FAILED`
  wycofują porcję), bajty `pg_column_size` przed/po; rewizja już odchudzona
  dostaje digest v1 (= v2) jako znacznik przetworzenia. Retencja: rewizje
  review items `superseded` bez komórek, na które nie wskazuje żadna
  komórka, których item nie ma rewizji `symbol-reference-library-v1`
  (kotwice `apply-revert`); usuwanie porcjami z `FOR UPDATE`.
- Testy: nowe `services/worker/tests/test_reference_library_digest_v2.py`
  (11: v2 stały dla pełnej i odchudzonej postaci, v1 = dawna funkcja,
  dopasowanie v1/v2/legacy, walidacja ORM, `apply` dla manifestu v1 i v2 na
  rewizji pełnej i odchudzonej (zapis odchudzony), odmowa bez kolumny
  legacy, `revert` z odchudzoną kotwicą v1/v2 i z pełną kotwicą),
  `services/api/tests/integration/test_slim_prediction_revisions_postgres.py`;
  `test_image_pipeline_execution` oczekuje kształtu `slim-v2` (świadoma
  zmiana kontraktu); `test_drop_cell_render_spec_postgres` i
  `test_convert_legacy_boards_postgres` (schematy sprzed `0137` z bieżącym
  ORM) dostają kolumnę `legacy_predictions_sha256` na bazie testowej.

### Verification results

- `alembic heads` = `0137_prediction_revisions_slim`; ruff, `ruff format
  --check` czyste dla 16 plików `.py`; mypy --strict 0 błędów w 10 modułach
  (domena, slimming, models, schema_readiness, writer, reinference,
  pipeline_store, oba skrypty, migracja); `git diff --check` czysto;
  `--collect-only` 1 873 testy.
- PostgreSQL (bazy `*_test` usunięte; dwie bazy po przerwanym przez timeout
  równoległym przebiegu usunąłem ręcznie, 0 pozostałych):
  `test_slim_prediction_revisions_postgres` 1/1 (podgląd tylko do odczytu;
  skrypt `--execute` w 2 porcjach: 4/4 odchudzone, kolumna legacy = dawny
  digest v1, digest v2 i sumy modelu/cropa bez zmian, bajty po < przed,
  checkpoint zamknięty; powtórka `scanned: 0`; retencja 0 przy kotwicy
  biblioteki, 2 po jej usunięciu, rewizja planszy z komórkami zostaje;
  CHECK formatu działa i jest walidowany; downgrade odmawia przy wartości
  legacy, bez niej usuwa kolumnę; ponowny upgrade),
  `test_virtual_deferred_resolution_postgres` 9/9,
  `test_cell_render_specs_postgres` 1/1, `test_drop_cell_render_spec_postgres`
  1/1, `test_convert_legacy_boards_postgres` 1/1.
  `test_image_batch_store` 4/15 — 11 niepowodzeń, wszystkie
  `ck_recognized_boards_asset_provenance` przy fixture planszy `legacy_file`
  (stan od `0135`, TASK-0796), niezależne od zadania.
- Jednostkowe porcjami ≤ 115 s: API — 20 niepowodzeń jak na HEAD
  (`test_reviews` 6, `test_image_import_geometry_guard_api` 7,
  `test_openapi_contract` 2, `test_virtual_grid_geometry` 2,
  `test_image_symbol_reviews_api` 1, `test_migration_baseline` 1,
  `test_lateral_managed_reprocess` 1); worker — 36 niepowodzeń korpusu jak
  na HEAD (po poprawieniu `test_image_pipeline_execution`).
- Podgląd na bazie operatora (tylko odczyt, baza na `0136`, skrypt z tego
  worktree, raporty w katalogu tymczasowym):
  - slim: 794 214 rewizji 777, wszystkie do przetworzenia (kolumny jeszcze
    nie ma), `predictions` 10 086 066 877 B (`pg_column_size`); próbka 2 000
    rewizji: 100% z `renderSpec`, 0 różnic digestu v2, JSON kanoniczny
    99,5 MB → 25,6 MB (0,258), zlib 15,6 MB → 7,6 MB (0,488); szacunek po
    odchudzeniu 4,93 GB (oszczędność 5,16 GB; bez kompresji ok. 7,5 GB);
  - retencja: 10 191 rewizji z 10 191 review items, 128 986 900 B
    (zapytanie 0,4 s);
  - partycja rewizji 777 `gpv2_bfc4f9495c14_495aa1afbdfc`: wiersze 236 MB,
    TOAST 10 GB, indeksy 400 MB, razem 11 GB.

### Not completed

- Migracja `0137`, `--execute` (slim i retencja) i `VACUUM FULL` na bazie
  operatora — orkiestrator za zgodą; `CURRENT_STATE.md` zostawiony
  orkiestratorowi.
- Dokładna liczba rewizji z `renderSpec` w podglądzie jest szacunkiem z
  próbki (pełne zliczenie wymagałoby dekompresji 10 GB; po `--execute`
  raport podaje dokładne liczby).
- Brak testu PG `apply`/`apply-revert` biblioteki na prawdziwej bazie po
  odchudzeniu (pokryte jednostkowo; PG test sprawdza kolumnę legacy = dawny
  digest v1).

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` (kształt `slim-v2`, kolumna legacy,
  digesty, retencja), `ai_docs/process/DECISION_LOG.md` (D-466 digest v2,
  D-467 nota S8), `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`
  (S8 wykonanie), `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (cutover `0137`,
  skrypt, kontrola, wycofanie), `ai_docs/guides/DATABASE_MAINTENANCE.md` 2.7
  (`VACUUM FULL` partycji rewizji, pomiar).

### Recommended next task

- Commit (orkiestrator), cutover `0137`, `--execute` slim do
  `completed: true`, retencja, `VACUUM (FULL, ANALYZE)` partycji rewizji i
  pomiar; potem TASK-0796 (fixture `legacy_file`, ścieżki v19).
