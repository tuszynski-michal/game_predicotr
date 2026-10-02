---
title: TASK-0792 — S7 — odczyty `render_spec` komórek przepięte na manifest renderu
status: done
last_updated: 2026-10-01
---

# TASK-0792 — S7 — odczyty `render_spec` komórek przepięte na manifest renderu

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.120)

## Goal

Żaden czytelnik runtime nie czyta kolumny `image_symbol_review_cells.render_spec`;
specyfikację renderu komórki dostarcza manifest planszy
(`board_render_manifests.cells[].renderSpec` dla
`(recognized_board_id, geometry_revision, cell_index)`), a komórka zachowuje
wyłącznie `render_spec_checksum_sha256` i klucze tożsamości — tak aby
TASK-0793 mógł usunąć kolumnę (19 GB TOAST w 777).

## Context

D-467, etap S7. Partycja komórek 777: 34 GB łącznie, z czego 6,7 GB to
wiersze, reszta to TOAST (`render_spec`, ok. 2,5 KB na komórkę, 7,5 mln
komórek) i indeksy. Manifest renderu (S4) przechowuje ten sam `renderSpec`
per komórka bieżącej rewizji planszy (klucze manifestu: `cellIndex`,
`renderSpec`, `cropSampleId`, `logicalCellKeySha256`, `logicalCellKeyV2Sha256`,
`renderIdentityV2Sha256`, `renderSpecChecksumSha256`,
`renderedPixelChecksumSha256`; `renderSpec` ma `schemaVersion`,
`configuration`, `sourceQuad`, `paddedSourceQuad`, `boardSlot`, `topology`,
`geometryRevision`, `geometryVersion`, `coordinateSpace`, `rowIndex`,
`columnIndex`, `cellIndex`).

Czytelnicy i pisarze `render_spec` komórek (`git grep "\.render_spec\b|render_spec="`
bez `*_checksum` i `virtual_render_spec`, stan po TASK-0791):

- `storage/virtual_grid_geometry_repository.py` (6: `_pending_render_configuration`
  czyta konfigurację z pierwszej komórki źródła; `_context_from_row`
  konfiguracje; `_replace_current_cells` i `_convert_current_cells`
  zapisują `cell.render_spec`),
- `storage/image_symbol_review_repository.py` (6: zapis komórek z renderu,
  odczyt do `get_assets` / podglądów),
- `scripts/evaluate_symbol_reference_library.py` (5),
- `storage/symbol_cell_training_source_repository.py` (4),
- `worker/images/virtual_cell_extraction.py` (3), `worker/images/pending_symbol_reinference.py` (3),
- `application/virtual_grid_geometry.py` (3), `worker/symbols/training_dataset.py` (2),
- `worker/images/production_workflow.py` (2), `storage/image_review_repository.py` (2),
- `storage/image_geometry_rollout_backfill_repository.py` (2),
- `domain/symbol_cell_training_cohorts.py` (2), `domain/board_render_manifests.py` (2),
- `application/virtual_cell_previews.py` (2), `worker/vision_lab/symbol_store.py` (1),
- `worker/vision_lab/symbol_crops.py` (1), `worker/images/pipeline_store.py` (1),
- `storage/verified_training_cohort_repository.py` (1),
- `storage/symbol_references_repository.py` (1), `domain/image_symbol_reviews.py` (1),
- `scripts/verify_partial_geometry_sources.py` (1).

Fakty z bazy operatora (2026-10-01, po `0135`): 510 416 plansz
`virtual_source`, każda plansza z dostępnymi komórkami ma manifest bieżącej
rewizji (preflight `0134` = 0 braków); komórki 777: 7,49 mln z rendererem
`…-v1`, 9 387 z `…-v4`, 6 915 skonwertowanych (TASK-0791, `…-v4`).

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.119`, `alembic heads` = `0135`, baza operatora na `0135`
  (CHECK komórek walidowany po cutoverze).
- Fakt: `storage/board_render_manifest_reader.py` (TASK-0758) czyta manifest
  bieżącej rewizji (`current_render_manifest_from_record`) i jest używany
  przez mapper i `pending_symbol_reinference`.
- Założenie do sprawdzenia: komórka na rewizji innej niż bieżąca rewizja
  planszy nie występuje w ścieżkach runtime (komórki są zawsze podmieniane
  przy zmianie rewizji); jeśli jakiś czytelnik potrzebuje specyfikacji
  historycznej rewizji, bierze ją z `image_board_geometry_revisions.virtual_render_spec`
  (rewizje > 0) — opisać w Outcome.
- Decyzja operatora 2026-10-01: audyty per zadanie zawieszone; po
  implementacji orkiestrator commituje i wykonuje cutover.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony
(decyzja operatora 2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S4, S7)
- `ai_docs/process/DECISION_LOG.md` (D-467, D-462)
- `ai_docs/tasks/completed/0757-board-render-manifests.md`
- `ai_docs/tasks/completed/0758-switch-readers-to-render-manifests.md`
- `ai_docs/architecture/DATA_MODEL.md` (komórki weryfikacji, manifest renderu)

## Scope

- Wspólny czytelnik specyfikacji komórki: funkcja/klasa w
  `storage/board_render_manifest_reader.py` (albo nowy moduł
  `storage/cell_render_specs.py`) zwracająca `renderSpec` dla
  `(game_id, recognized_board_id, geometry_revision, cell_index)` oraz
  wsadowo dla listy komórek (jedno zapytanie po manifestach, rozwinięcie
  w Pythonie), z kontrolą `renderSpecChecksumSha256` manifestu ==
  `cell.render_spec_checksum_sha256` (niezgodność = jawny błąd
  `IMAGE_REVIEW_RENDER_SPEC_MISMATCH`, nie cicha podmiana).
- Przepięcie wszystkich czytelników z listy w Context na ten czytelnik:
  `get_assets` / `virtual_cell_previews` (atlas i podgląd pojedynczej
  komórki; kontrakt pikseli bez zmian — ta sama suma `renderedPixelChecksumSha256`),
  `symbol_references_repository` (kandydaci wzorców i render kandydata),
  `symbol_cell_training_source_repository` i kohorty treningowe
  (`verified_training_cohort_repository`, `domain/symbol_cell_training_cohorts.py`,
  `worker/symbols/training_dataset.py`, vision_lab `symbol_store`/`symbol_crops`
  — manifest kohorty/datasetu liczony z tych samych pól, więc sumy
  nie mogą się zmienić; test porównawczy), `virtual_grid_geometry_repository`
  (`_pending_render_configuration` i `_context_from_row` czytają
  konfigurację z manifestu albo z `virtual_render_spec` rewizji),
  `pending_symbol_reinference` (już manifest; usunąć resztki),
  `image_geometry_rollout_backfill_repository`, `production_workflow`
  (jeśli czyta komórki), `scripts/evaluate_symbol_reference_library.py`,
  `scripts/verify_partial_geometry_sources.py`.
- Pisarze: `image_symbol_review_repository`, `virtual_grid_geometry_repository`
  (`_replace_current_cells`, `_convert_current_cells`), `pipeline_store`,
  `production_workflow` przestają zapisywać `cell.render_spec` (kolumna
  zostaje do TASK-0793, zapis `NULL`); CHECK `ck_image_symbol_review_cells_asset_provenance`
  wymaga dziś `jsonb_typeof(render_spec) = 'object'` dla `virtual_source`
  — migracja `0136a`? Nie: TASK-0793 usuwa kolumnę i CHECK razem; do tego
  czasu pisarze muszą nadal zapisywać `render_spec` (inaczej CHECK odrzuci
  wiersz). Decyzja: w tym zadaniu pisarze zapisują nadal, czytelnicy już
  nie czytają; TASK-0793 w jednej migracji zdejmuje CHECK, usuwa kolumnę i
  pisarzy. Opisać w Outcome, jeśli implementer znajdzie powód, by było
  inaczej.
- Modele domenowe: `ImageReviewCell` / `SymbolCellReviewAsset` i inne
  struktury przestają nosić `render_spec` z komórki, jeśli nie jest
  potrzebny poza renderem; tam, gdzie jest potrzebny (render podglądu),
  dostarcza go czytelnik manifestu.
- Testy: jednostkowe czytelnika (manifest brak/komórka brak/niezgodna suma),
  porównawcze dla kohort i kandydatów wzorców (ten sam manifest/suma przed
  i po), PG: podgląd komórki i atlas renderują te same piksele z manifestu
  co dotąd z komórki (dla planszy pełnej i częściowej), `get_assets`.
- Dokumentacja: `DATA_MODEL.md` (źródło specyfikacji = manifest),
  `DECISION_LOG.md` nota D-467 S7, plan, Outcome.

## Out of scope

- Usunięcie kolumny i przepisanie partycji (TASK-0793, migracja `0136`).
- Odchudzenie rewizji predykcji (S8), ścieżki v19/enumy (TASK-0796).

## Acceptance criteria

- [ ] `git grep "\.render_spec\b"` w `services/*/src` i `scripts` (bez
      `*_checksum`, `virtual_render_spec`, `approved_render_spec`) zwraca
      tylko pisarzy wymienionych w Scope i model ORM.
- [ ] Podgląd komórki, atlas, kandydaci wzorców, kohorty treningowe i
      dataset dają te same sumy (pikseli, manifestów kohort) co przed zmianą
      — testy porównawcze.
- [ ] Czytelnik manifestu odrzuca niezgodną sumę jawnym kodem.
- [ ] ruff, mypy --strict, pytest (api + worker, PG dla nowych testów)
      zielone poza znanymi niepowodzeniami HEAD; `pytest services/api/tests --collect-only` OK.

## Technical notes

- Źródło prawdy: `domain/board_render_manifests.py` (kształt manifestu,
  `sha256_canonical_json`), `storage/board_render_manifest_reader.py`.
- Wydajność: wsadowe odczyty po `(recognized_board_id, geometry_revision)`
  (PK manifestu z `game_id`), nie per komórka w pętli; atlas renderuje do
  kilkuset komórek na żądanie — jedno zapytanie po manifestach plansz z
  partii.
- Chronione: sumy kontrolne komórek, manifesty kohort, digesty planów
  biblioteki (D-466), kotwice apply-revert.
- Niedozwolone skróty: kopiowanie `render_spec` do innej tabeli; cicha
  tolerancja braku manifestu (poza planszą bez renderowalnych komórek).

## Expected files

- Zmienione: pliki z Context; nowe testy
  `services/api/tests/test_cell_render_specs.py`,
  `services/api/tests/integration/test_cell_render_specs_postgres.py`
  (nazwy orientacyjne).

## Test cases

- Czytelnik: manifest obecny → spec identyczny z `cell.render_spec`
  (porównanie na fixture); brak manifestu przy dostępnych komórkach →
  `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`; niezgodna suma → `…_MISMATCH`.
- Atlas/podgląd: piksele i nagłówki identyczne przed/po (PG, prawdziwy
  renderer).
- Kohorta treningowa / dataset: manifest i sumy identyczne przed/po.
- Kandydat wzorca: render identyczny; `cellReviewId` bez zmian.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t792
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowe> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t792pg
.\.venv\Scripts\python.exe -m pytest services/api/tests --collect-only -q
```

## Risks / open questions

- Komórki historyczne (rewizja komórki ≠ rewizja planszy) — patrz założenie
  w Dependencies.
- Koszt dodatkowego zapytania po manifestach w atlasie i kandydatach —
  wsadowo, mierzyć na 777 (tylko odczyt).

## Outcome

Wypełnione przez implementera 2026-10-01 (przed commitem; status zostaje
`in_progress`, zadanie zamyka orkiestrator). Audyt zawieszony decyzją
operatora — poniżej samodzielny przegląd.

### Changed

- Nowy wspólny czytelnik `services/api/src/game_predictor_api/storage/cell_render_specs.py`:
  `CellRenderSpecKey(recognized_board_id, geometry_revision, cell_index,
  render_spec_checksum_sha256)`, `load_cell_render_specs(session|connection,
  game_id, keys, schema=None|"game_data_v2")` i czysta
  `verified_cell_render_spec`. Jedno zapytanie na porcję do 2 000 komórek
  (`unnest` żądanych pozycji → `LEFT JOIN board_render_manifests` po PK z
  `game_id` → `jsonb_array_elements` z filtrem `cellIndex`), więc do klienta
  trafiają wyłącznie potrzebne wpisy, nie całe manifesty. Kontrola:
  zadeklarowana `renderSpecChecksumSha256` wpisu i kanoniczna suma jego
  `renderSpec` muszą być równe sumie komórki. Błąd `CellRenderSpecError`
  (podklasa `ImageReviewConflictError`, szczegóły pozycji) z kodami
  `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`, `IMAGE_REVIEW_RENDER_SPEC_MISSING`
  (brak lub duplikat wpisu, wpis bez `renderSpec`),
  `IMAGE_REVIEW_RENDER_SPEC_MISMATCH`. Bez rezerwy na kolumnę ani
  `virtual_render_spec`.
- Przepięci czytelnicy:
  - `image_symbol_review_repository.get_assets` (podgląd, atlas, PNG
    wzorca): jeden odczyt manifestów dla partii; komórka wirtualna z rewizją
    lub geometrią źródła inną niż bieżąca planszy jest odrzucana od razu
    `SYMBOL_CELL_REVIEW_CROP_DRIFT` (wcześniej ten sam kod zwracała warstwa
    aplikacji). `SymbolCellReviewAsset.render_spec` zostaje, ale pochodzi z
    manifestu.
  - `_cell_matches_projection`: porównanie komórki z projekcją po sumie
    specyfikacji zamiast JSON; ścieżka pozycji `outside` nie porównuje
    `render_spec` (decyduje suma i CHECK trybu).
  - `symbol_references_repository._to_candidates` (lista, kandydat,
    kandydat komórki, zablokowany kandydat przy wyborze): jeden odczyt na
    stronę; `cellReviewId` bez zmian.
  - `symbol_cell_training_source_repository.inventory`: jawne kolumny
    zamiast `c.*` w obu CTE, specyfikacje dołączane jednym odczytem
    (`_with_manifest_render_specs`); błąd manifestu przerywa inwentarz
    (bez cichego wykluczenia). `ApprovedSymbolCellCandidate.render_spec` i
    manifest kohorty bez zmian kształtu.
  - `virtual_grid_geometry_repository`: `_context_from_row` bierze
    konfigurację z manifestu przez `_review_cell_configurations` (wsadowo;
    komórka bez wirtualnej tożsamości →
    `IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID` jak dotąd);
    `_pending_render_configuration` czyta `cells['cells'][0]['renderSpec']`
    manifestu bieżącej rewizji planszy tego źródła (kolejność
    `position_index`, `id`), potem planszy importu, potem payload joba (jak
    dotąd).
  - `image_geometry_rollout_backfill_repository`: walidacja komórek
    weryfikacji pobiera specyfikacje wsadowo (`_review_cell_render_specs`;
    błąd czytelnika → `_invalid_source` z jego kodem);
    `_backfill_render_identity` dostaje `render_spec` jawnie dla komórek
    weryfikacji, komórki kohort nadal używają własnej zamrożonej kolumny.
  - `partial_board_reconciliation_repository._cells`: `to_jsonb(c) -
    'render_spec'` — strażnik nie zależy od kolumny (suma zostaje), więc
    `guardSha256` nie zmieni się przy jej usunięciu. Podglądy rekonsyliacji
    wygenerowane przed tą zmianą trzeba wygenerować ponownie (inny guard);
    pokwitowania nie są przeliczane.
  - `scripts/evaluate_symbol_reference_library.py`: SQL wybiera
    `recognized_board_id`, `geometry_revision`, `render_spec_checksum_sha256`
    zamiast `render_spec` (filtry `IS NOT NULL` i powód
    `render_spec_missing` po sumie), `_with_render_specs` dołącza
    specyfikacje z `game_data_v2.board_render_manifests` w tej samej
    transakcji REPEATABLE READ; błąd czytelnika → `EvaluationError` z jego
    kodem.
- Pisarze nadal zapisują kolumnę (CHECK
  `ck_image_symbol_review_cells_asset_provenance` wymaga obiektu dla
  `virtual_source`): `_asset_provenance_values`, `_apply_cell_projection` i
  pozycje `outside` (zapis `NULL`) w `image_symbol_review_repository`,
  `_replace_current_cells` / `_convert_current_cells` w
  `virtual_grid_geometry_repository`. `pipeline_store` i
  `production_workflow` nie zapisują komórek (manifest i payload etapu),
  więc nie wymagały zmian. Powód, by było inaczej, nie znalazł się.
- `storage/models.py`: `ImageSymbolReviewCellModel.render_spec` jest
  `deferred=True, deferred_raiseload=True` — ładowanie komórki z bazy nie
  czyta kolumny (mniej TOAST w każdym zapytaniu ORM po komórkach), a próba
  odczytu atrybutu z bazy zgłasza błąd zamiast cichego odczytu. Zapis
  atrybutu działa bez zmian.
- Świadomie niezmienione (nie czytają kolumny komórki):
  `pending_symbol_reinference` (już manifest; resztek brak),
  `virtual_cell_extraction`, `production_workflow`, `pipeline_store`,
  `application/virtual_grid_geometry.py` (obiekty renderu w pamięci budujące
  nowy manifest), `domain/board_render_manifests.py` (`ObservedRenderCell`),
  `domain/image_symbol_reviews.py` (pole assetu, teraz z manifestu),
  `domain/symbol_cell_training_cohorts.py` i
  `worker/symbols/training_dataset.py` (czytają kandydata albo zamrożony
  manifest kohorty), `verified_training_cohort_repository` (pisze własną
  zamrożoną kopię kohorty `verified_training_cohort_cells.render_spec` —
  zapis treningu, nie duplikat komórki), `worker/vision_lab/symbol_store.py`
  i `symbol_crops.py` (własna stała specyfikacja cropów laboratorium, inny
  byt), `scripts/verify_partial_geometry_sources.py` (render w pamięci, bez
  bazy), `scripts/vision_lab_export.py` (eksport całych wierszy tabel przez
  Core `__table__`; pole znika z eksportu razem z ORM w TASK-0793; żaden
  konsument eksportu go nie czyta).
- `git grep "\.render_spec\b"` w `services/*/src` i `scripts` (bez
  `*_checksum`, `virtual_render_spec`, `approved_render_spec`) zwraca po
  zmianie: przypisania pisarzy (`cell.render_spec = …` ×3), wartości
  `ImageReviewCell` pisane do kolumny (`_asset_provenance_values`) oraz
  pola obiektów spoza kolumny wymienionych wyżej (asset, kandydat, rekordy
  renderu, `ObservedRenderCell`, komórka kohorty, vision lab). Żadnego
  odczytu `ImageSymbolReviewCellModel.render_spec` ani `c.render_spec` w
  SQL.
- Założenie z Dependencies potwierdzone na bazie operatora (tylko odczyt,
  2026-10-01): każda z 7 500 357 komórek `virtual_source` (777: 7 499 967,
  `cf300bc1`: 390) jest na bieżącej rewizji i geometrii źródła planszy i ma
  wpis manifestu tej rewizji; 0 różnic `renderSpecChecksumSha256`,
  `renderedPixelChecksumSha256`, `logicalCellKeySha256`. Próbka 34 995
  komórek (0,5% plansz): `render_spec` == JSONB `renderSpec` wpisu w 100%.
  Czytelnik nie potrzebuje więc `virtual_render_spec` historycznych rewizji;
  komórka historycznej rewizji bez manifestu dostałaby jawny
  `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`.

### Verification results

- ruff check i `ruff format --check`: czysto dla 9 zmienionych modułów
  src/skryptu i 7 plików testów; mypy --strict: 0 błędów w
  `cell_render_specs`, `image_symbol_review_repository`,
  `symbol_references_repository`, `symbol_cell_training_source_repository`,
  `virtual_grid_geometry_repository`,
  `image_geometry_rollout_backfill_repository`,
  `partial_board_reconciliation_repository`, `models`,
  `scripts/evaluate_symbol_reference_library.py`. `git diff --check`
  czysto. `pytest services/api/tests --collect-only -q`: 1 866 testów.
- Nowe testy: `services/api/tests/test_cell_render_specs.py` (15: jedno
  zapytanie na partię, porcjowanie i deduplikacja, schemat skryptu, brak
  manifestu, manifest innej rewizji, brak/duplikat/brak `renderSpec`,
  niezgodna suma deklarowana i kanoniczna, równość z kolumną, ORM
  `raiseload`); dopisane w `test_virtual_grid_geometry_repository.py`
  (wsadowy odczyt kontekstu, komórka bez tożsamości, konfiguracja z
  manifestu źródła i importu — SQL bez `image_symbol_review_cells`),
  `test_image_geometry_rollout_validation_binding.py`,
  `test_symbol_cell_training_source_repository.py` (scalanie, SQL bez
  `c.*`/`render_spec`), `test_symbol_references_repository.py`;
  `test_additive_virtual_geometry_backfill.py` przekazuje specyfikację
  jawnie (świadoma zmiana kontraktu `_backfill_render_identity`). Zestaw
  dotkniętych testów jednostkowych: 135 passed.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, bazy `*_test`
  utworzone i usunięte, 0 pozostałych):
  `integration/test_cell_render_specs_postgres.py` 1/1 — plansza pełna i
  częściowa (maska lewej krawędzi) rozwiązane endpointem Reviewera:
  `get_assets` = kolumna dla 24 komórek, PNG pełnej rozdzielczości i atlas
  bajtowo identyczne z renderem ze specyfikacji kolumny (także przez
  `render_batch`), kandydaci wzorca (5 zatwierdzonych komórek, te same
  `cellReviewId`, ten sam PNG), inwentarz treningowy (ta sama specyfikacja,
  ta sama suma i bajty manifestu kohorty), kontekst ręcznej geometrii (ta
  sama konfiguracja), niezgodna suma → `IMAGE_REVIEW_RENDER_SPEC_MISMATCH`,
  usunięty manifest → `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`.
  `test_virtual_deferred_resolution_postgres.py` 9/9,
  `test_convert_legacy_boards_postgres.py` 1/1 (pisarze przy `raiseload`),
  `test_symbol_visibility_groups_postgres`,
  `test_symbol_review_query_cancellation` zielone,
  `test_game_data_v2_postgres` zielony. Niepowodzenia PG niezależne od
  zadania (fixture plansz `legacy_file` odrzucane przez CHECK `0135` albo
  wiersz lokalizacji v4 — przepina je TASK-0796):
  `test_partial_board_reconciliation_postgres` 5,
  `test_verified_cell_search_projection` 4,
  `test_board_render_manifests_postgres` 2,
  `test_outside_current_owner_postgres` 1.
- Pełne testy jednostkowe (porcjami ≤ 115 s): API — niepowodzenia tylko
  znane z HEAD: `test_reviews` 6, `test_image_import_geometry_guard_api` 7,
  `test_openapi_contract` 2, `test_virtual_grid_geometry` 2
  (`qualified_partial_preview`), `test_image_symbol_reviews_api` 1
  (limity bounded read), `test_migration_baseline` 1 (głowa `0135`),
  `test_lateral_managed_reprocess` 1 (payload importu) — razem 20; worker —
  36 niepowodzeń testów korpusu i realnych danych (jak na HEAD), reszta
  zielona.
- Pomiar tylko do odczytu na bazie operatora (777, czytelnik ze schematem
  `game_data_v2`): 100 komórek z 7 plansz (atlas) 31 ms przy ciepłym cache
  (kolumna 12 ms), 58 ms / 80 ms przy zimnym; 2 000 komórek z 2 000 różnych
  plansz 0,59 s (kolumna 0,24 s), zimny 2,3 s / 1,3 s. Wszystkie 2 100
  specyfikacji równe kolumnie. Koszt rośnie z liczbą różnych plansz
  (dekompresja manifestu ok. 45 KB na planszę); dla inwentarza kohorty (do
  ok. 32 tys. komórek, głównie z różnych plansz) to szacunkowo ok. 10 s
  więcej, raz na zamrożenie kohorty.

### Not completed

- `CURRENT_STATE.md` nie jest aktualizowany przez implementera (zamyka
  orkiestrator razem z commitem).
- Brak testu PG ścieżki `_pending_render_configuration` z rezerwą na
  planszę importu (pokryta testem jednostkowym SQL i pośrednio testami
  rozwiązania odroczonych plansz).
- Skrypt ewaluacji nie był uruchamiany end-to-end na bazie operatora
  (ciężki model); czytelnik w trybie skryptu sprawdzony odczytem 2 100
  komórek.

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` (źródło specyfikacji komórki =
  manifest, kody, kolumna write-only do TASK-0793, mapa własności
  geometrii), `ai_docs/process/DECISION_LOG.md` (D-467, nota TASK-0792 S7),
  `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S7,
  wykonanie).

### Risks for TASK-0793

- Migracja `0136` musi w jednej transakcji zdjąć `render_spec` z CHECK-ów
  `ck_image_symbol_review_cells_asset_provenance` (wymaga obiektu) i
  `ck_image_symbol_review_cells_source_asset` (wymaga `NULL` dla `none`) — w
  ORM i w bazie — oraz usunąć kolumnę; pisarze (`_asset_provenance_values`,
  `_apply_cell_projection`, pozycje `outside` z `flag_modified(cell,
  "render_spec")`, `_replace_current_cells`, `_convert_current_cells`) i
  atrybut ORM muszą zniknąć w tym samym commicie, inaczej INSERT/UPDATE
  odwołają się do nieistniejącej kolumny.
- `test_cell_render_specs_postgres` używa kolumny jako punktu odniesienia
  „przed”; po jej usunięciu trzeba go przepiąć na porównanie z sumą.
- `scripts/vision_lab_export.py` eksportuje cały wiersz komórki — po
  usunięciu kolumny format eksportu traci pole (brak konsumenta).
- Podglądy rekonsyliacji plansz częściowych wygenerowane przed TASK-0792
  mają inny `guardSha256`; od TASK-0792 guard jest niezależny od kolumny.
- Odzyskanie miejsca wymaga przepisania partycji (ACCESS EXCLUSIVE, ok.
  15 GB wolnego miejsca); kod po TASK-0792 nie czyta kolumny, ale
  weryfikacja symboli stoi na czas przepisania.

### Recommended next task

- Commit TASK-0792 (orkiestrator), wdrożenie bez migracji (zmiana tylko
  kodu; restart API, workerów i Reviewera), potem TASK-0793 (`0136`).
