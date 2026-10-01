---
title: TASK-0791 — S6 — konwersja 461 plansz `legacy_file` na `virtual_source` i zawężenie trybów zasobów
status: done
last_updated: 2026-10-01
---

# TASK-0791 — S6 — konwersja 461 plansz `legacy_file` na `virtual_source` i zawężenie trybów zasobów

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.117; konwersja i `0135` na bazie operatora po commicie)

## Goal

Każda plansza i komórka weryfikacji w bazie jest w trybie `virtual_source`
(albo `none` dla komórek poza źródłem), CHECK-i `asset_mode` i enumy API
dopuszczają tylko te tryby, a kod nie ma już ścieżek plików cropów v19.

## Context

D-467, etap S6, drugie zadanie (po TASK-0790 i S5). Po `0134` jedynym
śladem trybu `legacy_file` są 461 plansz w 777 z ręcznej rezolucji
odroczonych plansz sprzed TASK-0790 oraz ich komórki i rewizje geometrii.

Fakty z bazy operatora (2026-10-01 po `0134`, tylko `SELECT`):

- `recognized_boards` `legacy_file`: 461 (297 na rewizji 1, 164 na rewizji
  2), wszystkie w 777 (`bfc4f949…`); `source_geometry_revision_id` jest
  `NULL` dla wszystkich.
- Każda z tych plansz ma dokładnie jeden rekord
  `image_board_geometry_revisions` (`asset_mode = legacy_file`,
  `crop_artifacts` z 15 plikami cropów, `corners`, bez `virtual_render_spec`).
- Wszystkie 461 źródeł (`source_images`) ma rewizję geometrii źródła
  (`image_source_geometry_revisions`) — plansze powstały na importach
  wirtualnych, więc ścieżka wirtualna (`VirtualGridGeometryService`) ma dla
  nich kontekst źródła.
- `image_symbol_review_cells` tych plansz: 3 960 komórek, wszystkie
  `legacy_file`, `source_available = true`, wszystkie z decyzją człowieka
  (`assigned_symbol_id IS NOT NULL`).
- CHECK-i dziś: `ck_recognized_boards_asset_provenance`,
  `ck_image_symbol_review_cells_asset_provenance`,
  `ck_image_symbol_review_cells_source_asset`,
  `ck_image_board_geometry_revisions_asset` (gałęzie `legacy_file` i
  `virtual_source`; komórki także `none`).
- Kod ścieżek legacy po S5: korekta geometrii v19 Reviewera
  (`api/image_reviews.py::createOperationalImageReviewGeometryRevision` →
  `application/image_reviews.py::correct_geometry` →
  `storage/image_review_repository.py::save_geometry_revision`, previewer
  plików cropów, odmowa `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED` dla
  plansz wirtualnych), worker `pending_grid_reinference._run_v1` (tylko
  plansze `legacy_file`), gałęzie `legacy_file` w mapperze
  (`current_board_cell_sources`, `image_review_repository`), stale-check,
  projekcji wyszukiwarki, `pending_symbol_reinference` (rewizja > 0 legacy
  czyta `crop_artifacts`), `_run_v1`, `get_assets` (cropy plików), enumy
  API `assetMode` / `cellAssetMode` / `ImageReviewCell.assetMode` i
  odpowiedniki w kliencie, Adminie i Reviewerze.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.116`, `alembic heads` = `0134`, baza operatora na `0134`.
- Fakt: ścieżka wirtualna dla istniejącej planszy
  (`save_virtual_geometry_revision`, `_replace_current_cells`,
  `_recheck_after_virtual_recrop`) i dla slotu odroczonego działa
  (TASK-0790); reguła rewizji TASK-0702 (`max(pinned, R) + 1`) obowiązuje.
- Decyzja operatora (2026-10-01): jeden tryb danych; konwersja za zgodą
  `--execute` — orkiestrator wykonuje ją po audycie (zgoda blankietowa
  „dokończ wszystkie zadania jeśli przejdą audyt”).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S5–S6)
- `ai_docs/process/DECISION_LOG.md` (D-467, D-447)
- `ai_docs/tasks/completed/0790-virtual-only-manual-resolution-and-import-policy.md`
- `ai_docs/tasks/completed/0759-drop-cell-observations-and-legacy-archive.md`
- `ai_docs/architecture/DATA_MODEL.md` (asset modes, reguła rewizji)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`

## Scope

- Skrypt konwersji `scripts/convert_legacy_boards_to_virtual.py`
  (`--game-id`, `--preview` domyślnie, `--execute`, `--max-seconds`,
  wznawialny, raport JSON): dla każdej planszy `legacy_file` renderuje
  komórki z bieżących `corners` rewizji legacy tą samą ścieżką co ręczna
  geometria wirtualna (render spec v2, sumy pikseli, manifest renderu),
  tworzy rewizję geometrii `virtual_source` o numerze zgodnym z regułą
  TASK-0702, przestawia planszę na `virtual_source` (`board_relative_path`
  i `board_checksum_sha256` → `NULL`, `source_geometry_revision_id`,
  `geometry_engine_*`, `geometry_checksum_sha256` wypełnione), podmienia
  bieżące komórki weryfikacji na wirtualne z zachowaniem decyzji człowieka
  (`assigned_symbol_id`, stan, aktor, zdarzenia; nowe sumy cropów,
  `crop_sample_id`, klucze logiczne) i synchronizuje projekcje
  (write-through, board-search, stale-check). Podgląd: liczba plansz,
  komórek z decyzją, plansze bez kontekstu źródła, szacunek czasu.
  Wykonanie: porcje w transakcjach per plansza (albo per źródło) z blokadami
  sekwencji jak w ścieżce wirtualnej; idempotentne (plansza już wirtualna
  = pominięta). Historyczne rekordy rewizji `legacy_file` zostają jako
  historia (CHECK rewizji nie jest zawężany; decyzja do potwierdzenia w
  Outcome, jeśli implementer znajdzie powód, by było inaczej).
- Migracja `0135_virtual_only_asset_modes`: preflight (0 plansz i 0 komórek
  `legacy_file`, inaczej odmowa z kodem), zawężenie
  `ck_recognized_boards_asset_provenance` i obu CHECK-ów komórek do
  `virtual_source`/`none`, domyślne wartości kolumn; downgrade przywraca
  poprzednie CHECK-i (dane się nie zmieniają). `EXPECTED_ALEMBIC_HEAD` =
  `0135`.
- Usunięcie ścieżek legacy z kodu: korekta geometrii v19
  (`save_geometry_revision`, `correct_geometry`, previewer plików cropów;
  endpoint `createOperationalImageReviewGeometryRevision` deleguje do
  ścieżki wirtualnej jak `manual-resolution` w TASK-0790 — Reviewer
  zachowuje kontrakt i allowlistę — albo jest usunięty, jeśli Reviewer go
  nie używa; decyzja w Outcome), `pending_grid_reinference._run_v1`,
  gałęzie `legacy_file` w mapperze, stale-check, projekcji wyszukiwarki,
  `pending_symbol_reinference`, `get_assets`; enumy API `assetMode` /
  `cellAssetMode` zawężone pionem (OpenAPI, klient, wrapper, Admin,
  Reviewer, `shared-ts` jeśli dotyczy); kod błędu
  `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED` znika razem ze ścieżką.
- Testy: skrypt (podgląd i wykonanie na bazie `*_test` z planszą legacy z
  decyzjami: po konwersji decyzje, sumy i manifest zgodne z ścieżką
  wirtualną; powtórka = 0 zmian), migracja `0135` (odmowa przy planszy
  legacy, upgrade, downgrade), usunięte ścieżki (404/brak w OpenAPI),
  kontrakt Reviewera.
- Dokumentacja: `DECISION_LOG.md` (nota D-467 S6), plan D-467, `DATA_MODEL.md`,
  `API_CONTRACT.md`, `LOCAL_OPERATION_GUIDE.md` (cutover `0135` + skrypt
  konwersji przed migracją), `REMOTE_REVIEWER_THREAT_MODEL.md` jeśli
  zmienia się endpoint Reviewera.

## Out of scope

- `render_spec` poza komórkami (S7), odchudzenie predykcji (S8), rola bez
  `BYPASSRLS` (TASK-0795).
- Usuwanie plików cropów v19 z dysku (`artifacts/data/image-review-board-cell-geometry-v19`,
  6 990 plików, 0,05 GB) — osobne sprzątanie po potwierdzeniu konwersji.

## Acceptance criteria

- [ ] Podgląd skryptu na bazie operatora: 461 plansz, 3 960 komórek z
      decyzją, 0 bez kontekstu źródła.
- [ ] Po `--execute` (orkiestrator): 0 plansz i 0 komórek `legacy_file`;
      każda skonwertowana plansza ma manifest bieżącej rewizji i 15 (albo
      tyle, ile dostępnych) komórek wirtualnych; decyzje człowieka
      zachowane (3 960 `assigned_symbol_id` bez zmian).
- [ ] `0135` przechodzi tylko po konwersji; `EXPECTED_ALEMBIC_HEAD` = `0135`.
- [ ] `git grep -n "legacy_file"` w `services/*/src`, `apps/*/src`,
      `packages/*/src` zwraca tylko migracje historyczne i ewentualne
      komentarze o historii.
- [ ] OpenAPI, klient, wrapper, Admin, Reviewer spójne; ruff, mypy, pytest
      (api + worker, PG) zielone poza znanymi niepowodzeniami HEAD.

## Technical notes

- Źródło prawdy renderu: `domain/board_render_manifests.py`, render spec v2,
  `virtual_grid_geometry_repository._replace_current_cells` /
  `_recheck_after_virtual_recrop`. Konwersja = ręczna geometria wirtualna z
  narożnikami dotychczasowej rewizji; nie wprowadzać drugiego renderera.
- Decyzje człowieka: `_replace_current_cells` zapisuje zdarzenia
  `previous_*` — sprawdzić, że decyzja (`assigned_symbol_id`, stan) nie jest
  resetowana przez re-crop (`_recheck_after_virtual_recrop` zatwierdza nową
  sumę); jeśli ścieżka Adminu resetuje decyzje przy zmianie geometrii, skrypt
  musi je jawnie przenieść i udokumentować regułę.
- Reguła rewizji: nowa rewizja = `max(bieżąca rewizja planszy, R komórek) + 1`
  (TASK-0702), ta sama w planszy, rekordzie rewizji, manifeście, komórkach.
- Blokady: sekwencje → źródło → plansza/komórki (kolejność z TASK-0790).
- Chronione: zdarzenia, rewizje predykcji (kotwice apply-revert), 461
  historycznych rekordów rewizji legacy.
- Niedozwolone skróty: `UPDATE asset_mode` bez renderu i manifestu;
  migracja CHECK-ów przed konwersją.

## Expected files

- Nowe: `scripts/convert_legacy_boards_to_virtual.py`,
  `services/api/alembic/versions/0135_virtual_only_asset_modes.py`,
  `services/api/tests/integration/test_convert_legacy_boards_postgres.py`,
  `services/api/tests/test_virtual_only_asset_modes_migration.py`
  (nazwy orientacyjne); wpis `package.json` (`db:convert-legacy-boards`?).
- Zmienione/usunięte: pliki z Context i Scope, `storage/schema_readiness.py`
  i test, `storage/models.py` (CHECK-i), dokumentacja.

## Test cases

- Konwersja planszy legacy z 15 komórkami i decyzjami → plansza wirtualna,
  rewizja N+1 z `virtual_render_spec`, manifest, komórki wirtualne z tymi
  samymi decyzjami, projekcje zsynchronizowane; powtórka → 0 zmian.
- Plansza legacy, której sekwencja ma komplet komórek na rewizji R > N →
  rewizja `R + 1`.
- Plansza bez rewizji geometrii źródła → raport „bez kontekstu”, pominięta
  w `--execute`, kod wyjścia ≠ 0.
- `0135`: odmowa przy planszy legacy; upgrade; downgrade przywraca CHECK-i.
- API: `assetMode` poza enumem → 422; usunięta trasa v19 → 404 i brak w
  OpenAPI; Reviewer korekta geometrii (jeśli zostaje) → rewizja wirtualna.

## Verification

```powershell
# katalog: worktree zadania; każdy krok ≤ 120 s
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe scripts/convert_legacy_boards_to_virtual.py --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --preview
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t791
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_convert_legacy_boards_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t791pg
.\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Decyzje człowieka a re-crop: ścieżka wirtualna może traktować nową sumę
  cropa jako zmianę wymagającą ponownej weryfikacji; skrypt musi zachować
  decyzje jawnie (patrz Technical notes).
- Konwersja 461 plansz renderuje 6 915 komórek i liczy sumy — kilka minut;
  wykonanie w porcjach z `--max-seconds`.
- Cutover `0135` jak poprzednie (stop → merge → konwersja `--execute` →
  `db:migrate` → start); kolejność: konwersja przed migracją.

## Outcome

Implementer Opus został przerwany po warstwie aplikacji i repozytorium;
resztę dokończył orkiestrator (Fable 5.1) za zgodą operatora.

### Changed

- `application/virtual_grid_geometry.py`: `LegacyConversionTarget`,
  `prepare_legacy_conversion` (ta sama walidacja komendy, kwalifikacja,
  `_render_source_entries` wspólne z zapisem źródła, bez predykcji).
- `application/legacy_board_conversion.py` (nowy): plan per źródło
  (`LegacyConversionBoardPlan` z kodami problemów, `next_geometry_revision`
  = `max(N, R) + 1`), `LegacyBoardConversionService` (`source_ids`, `plan`,
  `render_check`, `convert_source` — jedno źródło na transakcję, odmowa przy
  problemie, idempotencja).
- `storage/virtual_grid_geometry_repository.py`: `legacy_conversion_source_ids`,
  `legacy_conversion_plan` (blokady: sekwencje → `source_images FOR UPDATE`
  → plansze → review item → komórki; kontekst z najnowszej rewizji geometrii
  źródła; konfiguracja renderu z komórek źródła z przypięciem bieżącej
  wersji renderera `VIRTUAL_CELL_RENDERER_VERSION`, bo komórki 777 mają
  `…-v1`, a renderer odrzuca inne przypięcie — TASK-0663 podbijał wersję
  kontraktu bez zmiany pikseli), `convert_legacy_source` (rewizja geometrii
  źródła `manual_v1`, rekord rewizji `virtual_source`, manifest renderu,
  plansza na `virtual_source`, zatwierdzenie geometrii przepięte,
  `_convert_current_cells` — decyzje bez zmian, zatwierdzenie na nowy render,
  zdarzenie `geometry_invalidated` per komórka, kontrola
  `LEGACY_CONVERSION_DECISION_DRIFT`, liczniki stanu), synchronizacja
  board-search i write-through.
- `scripts/convert_legacy_boards_to_virtual.py` (nowy): `--preview`
  (READ ONLY, `--render-sources N`), `--execute` (`--max-seconds`,
  `--max-sources`), raport JSON w `artifacts/data/exports/legacy-board-conversion/`.
- `alembic/versions/0135_virtual_only_asset_modes.py` (nowy),
  `storage/schema_readiness.py` + test: `EXPECTED_ALEMBIC_HEAD` = `0135`.
- `tests/integration/test_convert_legacy_boards_postgres.py` (nowy).
- Docs: plan D-467 (TASK-0791 wykonanie, TASK-0796 dopisane z wierszem
  modelu), `DECISION_LOG.md` (nota D-467), `DATA_MODEL.md`,
  `LOCAL_OPERATION_GUIDE.md` (cutover `0135`), `CURRENT_STATE.md`.

### Verification results

- Podgląd na bazie operatora (READ ONLY): 243 źródła, 461 plansz, 3 960
  komórek (wszystkie z `assigned_symbol_id`, 183 zatwierdzone / z decyzją
  człowieka wg `assignment_source`), 0 problemów; render 3 źródeł w pamięci
  0,08–0,17 s na źródło.
- PG `test_convert_legacy_boards_postgres.py`: 1/1 (plansza wirtualna
  przepisana na kształt legacy z decyzjami i jedną zatwierdzoną komórką →
  `0135` odmawia `LEGACY_FILE_BOARDS_PRESENT` → podgląd 15/15/1 → konwersja:
  plansza i rewizja `virtual_source`, rewizja 2, manifest = komórki rewizji,
  15 komórek wirtualnych bez ścieżek plików, decyzje identyczne,
  zatwierdzenie przepięte na nowy render (`approved_asset_mode`
  `virtual_source`, suma pikseli = bieżąca), 15 zdarzeń
  `geometry_invalidated`, historyczna rewizja 1 nadal `legacy_file`,
  rewizje źródła `[0, 1, 2]`; powtórka → 0 plansz, `source_ids` puste;
  `0135` upgrade → domyślne `virtual_source`, CHECK bez `legacy_file`,
  `UPDATE` na legacy odrzucony; downgrade przywraca CHECK; ponowny upgrade).
- PG `test_virtual_deferred_resolution_postgres.py` (rezolucja Reviewera,
  równoważność z Adminem, reguła rewizji × 2): 4/4.
- Unit: `test_virtual_grid_geometry.py`, `test_virtual_grid_geometry_repository.py`,
  `test_board_cell_geometry_pending.py`, `test_schema_readiness.py`,
  `test_lateral_lock_order.py`: 69 passed, 2 failed (znane z HEAD:
  `test_qualified_partial_preview…[False/True]`).
- ruff check/format: czysto dla zmienionych plików; mypy --strict:
  0 błędów w zmienionych modułach i skrypcie; `alembic heads` = `0135`.

### Not completed

- Przeniesione do TASK-0796: usunięcie ścieżek plików cropów v19 (korekta
  geometrii Reviewera, `_run_v1`, gałęzie `legacy_file` w mapperze,
  stale-check, projekcji wyszukiwarki, `pending_symbol_reinference`,
  `get_assets`), zawężenie enumów API `assetMode`/`cellAssetMode` pionem,
  zawężenie CHECK-ów w `storage/models.py` i przepięcie fixture testów
  jednostkowych (ORM pozostaje luźniejszy niż baza od `0135`; kryterium
  akceptacji `git grep legacy_file` niespełnione do TASK-0796).
- Wykonanie `--execute` i migracja `0135` na bazie operatora (orkiestrator
  po audycie, kolejność z runbooka).

### Documentation updates

- Jak w Changed.

### Recommended next task

- Commit, cutover (konwersja → `0135`), potem TASK-0796 albo S7
  (TASK-0792) według decyzji operatora; TASK-0796 jest warunkiem pełnego
  domknięcia S6.
