---
title: TASK-0790 — S6 — ręczna rezolucja odroczonych plansz i polityki importu wyłącznie w trybie wirtualnym
status: done
last_updated: 2026-10-01
---

# TASK-0790 — S6 — ręczna rezolucja odroczonych plansz i polityki importu wyłącznie w trybie wirtualnym

## Status

`done` (audyt Opus FAIL→PASS, commit v1.7.114; cutover `0133` na bazie operatora po commicie)

## Goal

Żadna ścieżka zapisu (import, ręczna rezolucja odroczonej planszy, korekta
geometrii Reviewera) nie tworzy już planszy `legacy_file` ani wierszy
`cell_observations`, a domyślna i jedyna dostępna polityka importu to tryb
wirtualny — tak aby TASK-0759 (S5) mógł usunąć `cell_observations`.

## Context

D-467, etap S6, wykonywany przed S5 (plan dopuszcza tę kolejność: warunek S4
„0 plansz `legacy_file` na rewizji 0 i brak ścieżki, która je tworzy —
TASK-0790 przed S5 albo blokada importu `legacy` w S5”). Po TASK-0758
plansze `legacy_file` na rewizji 0 są czytane wyłącznie przez
`storage/legacy_cell_observation_adapter.py`; S5 usuwa adapter razem z
tabelą. Dlatego najpierw trzeba zamknąć pisarzy legacy.

Fakty z bazy operatora (2026-10-01, tylko `SELECT`):

- `recognized_boards`: 372 381 wirtualnych na rewizji 0, 137 574 wirtualnych
  na rewizji > 0, 461 `legacy_file` (wszystkie na rewizji 1–2, w 777).
- `image_geometry_rollout_states`: 777 (`bfc4f949…`) =
  `structured_lattice_v3` / `virtual_default` / rewizja 1; gry
  `cf300bc1…` i `2a46d3a6…` = `legacy` / `legacy_files` / rewizja 0 (nigdy
  nie zmieniane, czyli domyślne z `game_partition_lifecycle`).
- `image_board_geometry_pending`: 20 577 wierszy, 10 `pending`,
  20 567 `resolved`.

Istniejące ścieżki zapisu plansz legacy (do zamknięcia):

1. Import z polityką `VERIFIED_V19` (`legacy` / `legacy_files`):
   `worker/images/pipeline_store.py` (zapisuje planszę `legacy_file`,
   cropy plików i `CellObservationModel`), kontrakt w
   `worker/images/pipeline_contract.py`, `worker/images/production_workflow.py`,
   polityka w `domain/image_import_engine_policy.py`, `application/jobs.py`,
   `schemas/jobs.py`, `schemas/image_imports.py`, `api/image_imports.py`,
   `storage/game_partition_lifecycle.py` (domyślny stan rolloutu nowej gry),
   `storage/catalog_repository.py`, `domain/image_geometry_cutover.py`,
   `storage/image_geometry_v2_repository.py`; Admin:
   `apps/admin/src/features/imports/board-cell-processing-mode.ts`,
   `image-folder-import-actions.ts`, `image-folder-import-panel.tsx`.
2. Ręczna rezolucja odroczonej planszy Reviewera:
   `POST /api/v1/admin/games/{game_id}/image-imports/{job_id}/board-cell-geometry-pending/{pending_id}/manual-resolution`
   (`api/board_cell_geometry_pending.py`,
   `application/board_cell_geometry_pending.py::materialize_manual_resolution`,
   `storage/board_cell_geometry_pending_repository.py::materialize_manual_resolution`
   — tworzy `RecognizedBoardModel` `legacy_file` z plikami cropów i 15
   `CellObservationModel`). Konsument: Reviewer
   `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx`,
   allowlista `apps/reviewer/src/security/reviewer-proxy-policy.ts`.
   Ścieżka wirtualna dla tego samego celu już istnieje:
   `application/virtual_grid_geometry.py::save_virtual_source_geometry_revision`
   z komendą o `pending_geometry_id` →
   `storage/virtual_grid_geometry_repository.py::_materialize_pending_source_slot`
   (plansza `virtual_source`, rewizja z `virtual_render_spec`, manifest
   renderu, komórki weryfikacji). Używa jej Admin
   (`POST /api/v1/admin/image-reviews/{review_item_id}/geometry-revisions`,
   `api/image_grid_reviews.py`, `createImageGridReviewGeometryRevision`).
3. Korekta geometrii v19 Reviewera:
   `POST /api/v1/admin/image-review-items/{id}/geometry-revisions`
   (`api/image_reviews.py::createOperationalImageReviewGeometryRevision`,
   `application/image_reviews.py::correct_geometry`,
   `storage/image_review_repository.py::save_geometry_revision`) — rewizja
   z plikami cropów; od TASK-0758 odmawia planszy wirtualnej
   (`IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED`). Działa tylko dla 461
   plansz legacy; po TASK-0791 (konwersja) nie będzie miała celu.
4. Worker `worker/images/pending_grid_reinference.py::_run_v1` (tylko
   plansze `legacy_file`, od TASK-0758 filtr w zapytaniu) oraz fixture
   benchmarków `worker/images/real_workbench_fixture.py`,
   `worker/images/workbench_acceptance.py` (seedują plansze legacy z
   obserwacjami; S5 je przepina albo usuwa — tutaj poza zakresem).

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.113` (TASK-0758), `alembic heads` = `0132`; baza
  operatora na `0132`.
- Fakt: ścieżka wirtualna dla celów `pending_geometry_id` działa w Adminie
  (TASK-0675/… w `VISION_LAB_EXECUTION_PLAN.md` i D-447); Reviewer jej nie
  używa.
- Założenie do sprawdzenia przez implementera: polityka
  `STRUCTURED_DEFAULT` (`structured_default` / `virtual_default`) importuje
  nową grę bez profilu kalibracji siatki; jeśli nie, domyślną polityką nowej
  gry zostaje `STRUCTURED_LATTICE_V3` i trzeba to opisać w Outcome.
- Decyzja operatora (2026-10-01, „Wyrzuć wszystko, co jest legacy”,
  „dokończ wszystkie zadania jeśli przejdą audyt”): polityki `VERIFIED_V19`
  i `STRUCTURED_SHADOW` są usuwane; nie ma gry, która ich świadomie używa
  (dwie gry na `legacy` mają rewizję 0 = nigdy nie ustawiono).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S4–S6)
- `ai_docs/process/DECISION_LOG.md` (D-467, D-447)
- `ai_docs/tasks/completed/0758-switch-readers-to-render-manifests.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` (allowlista Reviewera)

## Scope

- Ręczna rezolucja odroczonej planszy w Reviewerze zapisuje planszę
  `virtual_source` tą samą ścieżką co Admin (`save_virtual_source_geometry_revision`
  z `pending_geometry_id`): albo endpoint `manual-resolution` deleguje do
  serwisu wirtualnego (ten sam kontrakt wejścia dla Reviewera, odpowiedź
  z rewizją wirtualną), albo Reviewer przechodzi na endpoint wirtualny
  (allowlista proxy zaktualizowana, test polityki proxy). Implementer
  wybiera wariant o mniejszym ryzyku dla Reviewera przez tunel i
  uzasadnia go w Outcome. `geometry-preview` dla odroczonej planszy
  pokazuje podgląd z renderu wirtualnego (jak Admin), nie z plików cropów.
- Usunięcie legacy z `materialize_manual_resolution`: repozytorium i
  aplikacja nie tworzą `RecognizedBoardModel` `legacy_file`, plików cropów
  ani `CellObservationModel`; kod martwy po przepięciu usunięty (łącznie z
  previewerem plików cropów, jeśli nie ma innych konsumentów).
- Polityki importu: enum `ImageImportEnginePolicy` bez `VERIFIED_V19` i
  `STRUCTURED_SHADOW`; `policy_rollout_modes` / `policy_from_rollout_modes`
  tylko dla trybów wirtualnych; domyślny stan rolloutu nowej gry
  (`game_partition_lifecycle`) = polityka wirtualna; API
  (`schemas/jobs.py`, `schemas/image_imports.py`, `api/image_imports.py`,
  `api/image_grid_reviews.py` policy preview/update) odrzuca tryby legacy
  jawnym kodem błędu; Admin (`board-cell-processing-mode.ts`,
  `image-folder-import-*`) bez opcji legacy/shadow; OpenAPI + klient +
  wrapper + test pionem.
- Worker: `pipeline_store.py` odmawia zapisu planszy niewirtualnej nowym
  kodem błędu (job kończy się błędem, nie cichym pominięciem); gałęzie
  `legacy` / `structured_shadow` w `pipeline_contract.py`,
  `production_workflow.py` i powiązane usunięte, jeśli bez nich kontrakt
  pozostaje spójny (inaczej opisać, co zostaje i dlaczego).
- Migracja danych rolloutu dwóch gier na `legacy` / `legacy_files`
  rewizja 0: migracja Alembic `0133` (S6 przejmuje numer; S5 dostaje
  `0134`, S7 `0135`) ustawia dla stanów `legacy`/`legacy_files` tryb
  wirtualny domyślny (ten sam, który dostaje nowa gra) i podbija rewizję;
  downgrade odmawia (stan poprzedni nieodtwarzalny bez kopii). Jeśli
  implementer uzna, że stan rolloutu może zmienić zwykły skrypt z
  podglądem zamiast migracji, uzasadnia to w Outcome — ale CHECK-i
  kolumn trybów (jeśli istnieją) i tak wymagają migracji.
- Korekta geometrii v19 (`save_geometry_revision`, ścieżka 3): zostaje do
  TASK-0791 (działa dla 461 plansz legacy); tutaj tylko upewnić się, że
  Reviewer dla planszy wirtualnej dostaje czytelny błąd albo trafia na
  ścieżkę wirtualną, jeśli przepięcie jest tanie (decyzja w Outcome).
- Testy: jednostkowe i PG dla rezolucji odroczonej planszy ścieżką
  wirtualną (plansza pełna i częściowa z maską), polityk (odrzucenie
  legacy), domyślnego rolloutu nowej gry, migracji `0133` (upgrade,
  downgrade odmawia), kontraktu Reviewera (proxy policy) i odmowy workera.
- Dokumentacja: `DECISION_LOG.md` (nota D-467: jedyny tryb danych w
  pisarzach, numeracja migracji), plan D-467 (S6 przed S5, `0133` w S6),
  `LOCAL_OPERATION_GUIDE.md` / `REMOTE_REVIEWER_THREAT_MODEL.md`, jeśli
  zmienia się allowlista lub endpoint Reviewera.

## Out of scope

- Konwersja 461 istniejących plansz `legacy_file` i zawężenie CHECK-ów
  `asset_mode` oraz enumów API (TASK-0791).
- Usunięcie `cell_observations`, adaptera legacy, fixture benchmarków
  (TASK-0759, S5).
- Zmiany modelu symboli, geometrii V3 i kalibracji.

## Acceptance criteria

- [ ] `git grep` w `services/*/src`: `CellObservationModel` tworzony
      wyłącznie w fixture benchmarków (`real_workbench_fixture`,
      `workbench_acceptance`); `pipeline_store.py`,
      `board_cell_geometry_pending_repository.py`,
      `virtual_grid_geometry_repository.py` nie dodają obserwacji.
- [ ] Reviewer rozwiązuje odroczoną planszę i w bazie powstaje plansza
      `virtual_source` z manifestem renderu i komórkami weryfikacji; test PG
      to pokazuje.
- [ ] `ImageImportEnginePolicy` ma tylko tryby wirtualne; żądanie z
      `verified_v19` / `structured_shadow` dostaje 4xx z jawnym kodem.
- [ ] Nowa gra dostaje wirtualny domyślny stan rolloutu; migracja `0133`
      przestawia dwie gry na `legacy`.
- [ ] Worker odmawia zapisu planszy niewirtualnej jawnym kodem.
- [ ] OpenAPI, klient, wrapper, Admin i Reviewer spójne (`openapi:check`,
      `check:generated`, testy TS, typecheck).
- [ ] ruff, mypy --strict, pytest (api + worker, PG dla nowych testów)
      zielone; niepowodzenia tylko te same co na HEAD.

## Technical notes

- Źródło prawdy dla ścieżki wirtualnej: `VirtualGridGeometryService`
  (`application/virtual_grid_geometry.py`) i
  `SqlAlchemyVirtualGridGeometryRepository._materialize_pending_source_slot`.
  Rezolucja Reviewera ma dawać ten sam stan bazy co rezolucja Adminem tej
  samej odroczonej planszy (test porównawczy: ten sam `pending_id`, te same
  narożniki → identyczne `virtual_render_spec_checksum_sha256`,
  `manifest_checksum_sha256`, komórki).
- Reviewer przez tunel widzi tylko allowlistę proxy; każdy nowy endpoint
  wymaga wpisu w `reviewer-proxy-policy.ts` i testu polityki oraz wzmianki
  w modelu zagrożeń. Autoryzacja sesji Reviewera (`authorize(...)` z
  `reviewer_access`) musi obowiązywać na nowej ścieżce tak samo jak na
  `manual-resolution`.
- Idempotencja: `pending_id` + `idempotency_key` Reviewera muszą dalej
  zwracać ten sam wynik przy powtórce (`manual_resolution_by_idempotency`
  albo odpowiednik w ścieżce wirtualnej).
- Nie wprowadzać drugiego implementacyjnego wariantu renderu: Reviewer
  używa tych samych funkcji renderu/sum kontrolnych co Admin
  (`domain/board_render_manifests.py`, render spec v2).
- Migracja `0133`: `SET LOCAL lock_timeout`, zamrożona lista trybów bez
  importu ORM, `UPDATE … WHERE geometry_mode = 'legacy'`, podbicie
  `revision`; downgrade odmawia.
- Chronione: 461 plansz legacy i ich komórki zostają nietknięte (TASK-0791);
  decyzje człowieka i zdarzenia nietknięte.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/board_cell_geometry_pending.py`,
  `application/board_cell_geometry_pending.py`,
  `storage/board_cell_geometry_pending_repository.py`,
  `application/virtual_grid_geometry.py`,
  `storage/virtual_grid_geometry_repository.py`,
  `domain/image_import_engine_policy.py`, `application/jobs.py`,
  `schemas/jobs.py`, `schemas/image_imports.py`, `api/image_imports.py`,
  `api/image_grid_reviews.py`, `storage/game_partition_lifecycle.py`,
  `storage/catalog_repository.py`, `domain/image_geometry_cutover.py`,
  `storage/image_geometry_v2_repository.py`,
  `services/worker/src/game_predictor_worker/images/pipeline_store.py`,
  `pipeline_contract.py`, `production_workflow.py`,
  `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx`,
  `apps/reviewer/src/security/reviewer-proxy-policy.ts`,
  `apps/admin/src/features/imports/board-cell-processing-mode.ts`,
  `image-folder-import-actions.ts`, `image-folder-import-panel.tsx`,
  `packages/admin-api-client/openapi/openapi.json`, `src/generated/*`,
  `src/index.ts`, testy.
- Nowe: `services/api/alembic/versions/0133_virtual_only_import_policies.py`
  (nazwa orientacyjna), testy PG rezolucji Reviewera ścieżką wirtualną.

## Test cases

- Reviewer: `manual-resolution` (albo endpoint wirtualny) dla odroczonej
  planszy pełnej → plansza `virtual_source`, rewizja z `virtual_render_spec`,
  manifest, 15 komórek; powtórka z tym samym `idempotency_key` → ten sam
  wynik, `created=false`; inna komenda z tym samym kluczem → konflikt.
- Odroczona plansza częściowa (maska) → komórki tylko dla dostępnych
  indeksów, manifest zgodny.
- Policy preview/update z `verified_v19` → 4xx z kodem; Admin nie oferuje
  opcji.
- Nowa gra → `image_geometry_rollout_states` w trybie wirtualnym.
- Migracja `0133` na bazie `*_test` z dwoma stanami `legacy` → oba
  wirtualne, rewizja +1; downgrade → odmowa.
- Worker: payload joba z trybem legacy → job `failed` z kodem.
- Proxy Reviewera: ścieżki legacy niedostępne (jeśli usunięte), nowa
  ścieżka dozwolona tylko dla metod z zakresu.

## Verification

```powershell
# katalog: worktree zadania; każdy krok ≤ 120 s
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t760
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowe testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t760pg
.\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Reviewer przez tunel: zmiana endpointu wymaga zgodności wersji Reviewera
  i API (oba lokalne, wdrażane razem; sesje Reviewera w trakcie
  wdrożenia mogą dostać 4xx — akceptowane, okno nocne).
- `STRUCTURED_DEFAULT` może wymagać profilu kalibracji; patrz założenie w
  Dependencies.
- Cutover `0133` wymaga zatrzymania API (jak TASK-0757/0758).

## Outcome

Implementacja bez commita (commit i zamknięcie po audycie przez
orkiestratora).

### Audit (Opus 5.5, high)

- Pierwszy audyt FAIL: P1 — rezolucja odroczonej planszy przejmującej
  sekwencję z kompletem komórek na rewizji R dostawała rewizję
  `expected + 1` zamiast `max(expected, R) + 1` (reguła TASK-0702) i
  kończyła się 422; P2 — wyścig dwóch rezolucji slotów jednego źródła bez
  blokady `source_images`; P2 — dokumenty wymagań/architektury opisywały
  `verified_v19` i rezolucję z plikami cropów. Poprawione (reguła rewizji w
  kontekście slotu i ponowne porównanie pod blokadą, `FOR UPDATE` źródła po
  blokadach sekwencji, 6 dokumentów), testy PG 9/9 w tym przejęcie
  sekwencji i wyścig dwóch sesji. Re-audyt PASS; P3 domknięte przez
  orkiestratora: `IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT` → 409, noty
  historyczne w `ITERATIVE_IMAGE_IMPORT.md` (requirements i architecture).
- Identyfikator zadania zmieniony z TASK-0760 na TASK-0790 (kolizja z torem
  D-470); migracje: S5 `0134`, TASK-0791 `0135`, S7 `0136`.

### Changed

- **Wariant Reviewera:** endpointy `geometry-preview` i `manual-resolution`
  zostają (ten sam kontrakt wejścia i odpowiedzi, ta sama allowlista proxy,
  ta sama autoryzacja `authorize_scope` i aktor `reviewer-session:<id>`),
  a `BoardCellGeometryPendingService` deleguje do
  `VirtualGridGeometryService` w tej samej sesji/transakcji. Uzasadnienie:
  najmniejsze ryzyko przez tunel — bez zmiany allowlisty, bez nowego
  endpointu i bez zmiany UI Reviewera; kody błędów Reviewera zachowane
  (`IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT`,
  `..._RESOLUTION_CONFLICT`), a stare kody ścieżki wirtualnej
  (`IMAGE_GRID_REVIEW_REVISION_CONFLICT`, `..._SOURCE_SLOT_CONFLICT`,
  `..._ITEM_NOT_FOUND`) Reviewer traktuje jako konflikt (przeładowanie).
- **Ścieżka wirtualna dla jednego odroczonego slotu:** nowe
  `VirtualGridGeometryService.preview_pending_slot` i `save_pending_slot`.
  Fakt sprostowany względem Context: Admin nie miał endpointu HTTP dla
  `pending_geometry_id` — `save_source` wymagał kompletu slotów źródła i był
  wołany tylko w testach. `save_pending_slot` renderuje jeden odroczony slot
  względem najnowszej rewizji geometrii źródła (pozostałe sloty zachowują
  quady), replay po `idempotency_key`, ten sam `_prepare_source`
  (`require_complete_source=False` tylko dla dokładnie jednego slotu
  odroczonego), ten sam render, sumy kontrolne i
  `save_virtual_source_geometry_revision` → `_materialize_pending_source_slot`.
  Plansza istniejąca już na tej samej pozycji tego samego źródła
  (`source + position`) → odroczony slot `superseded`, `created=false` (jak
  dawny legacy). Nowszy import to inne źródło; przejęcie jego sekwencji
  obsługuje `create_owned_pending_review_item` razem z regułą rewizji niżej.
- **Poprawki po audycie (FAIL → naprawione):**
  - P1: reguła przejęcia sekwencji z TASK-0702 (dawny
    `_next_manual_geometry_revision`) wróciła w ścieżce wirtualnej. Kontekst
    odroczonego slotu (`_pending_context`) odczytuje wspólną rewizję R
    bieżących 15 komórek `game_id + sequence_number`
    (`sequence_geometry_revision`, pod blokadą `FOR UPDATE` w zapisie), a
    `VirtualGridGeometryContext.next_geometry_revision` = `max(expected, R) + 1`
    trafia do specyfikacji renderu (`geometryRevision`), planszy, rekordu
    rewizji, manifestu i `resolved_geometry_revision`. Zmiana R między
    renderem a zapisem → `IMAGE_GRID_REVIEW_REVISION_CONFLICT`. Reprodukcja
    audytora (`scratchpad/a760/test_handoff_repro.py`) przechodzi: druga
    rezolucja tej samej sekwencji dostaje rewizję 2.
  - P2-1: `save_virtual_source_geometry_revision` po blokadach sekwencji
    blokuje wiersz `source_images` (`FOR UPDATE`, ta sama kolejność co writer
    importu) przed ponownym odczytem kontekstów; druga rezolucja innego slotu
    tego samego źródła czeka i kończy się konfliktem zamiast budować rewizję z
    nieaktualnej bazy. Test PG z dwiema sesjami (sprawdzone, że bez blokady
    przegrany commituje).
  - P2-2: zaktualizowane `requirements/IMAGE_INGESTION.md`,
    `requirements/ADMIN_APP.md`, `architecture/API_CONTRACT.md`,
    `architecture/DATA_MODEL.md` (stany rolloutu, reguła rewizji w ścieżce
    wirtualnej), `architecture/SYSTEM_ARCHITECTURE.md`,
    `architecture/ITERATIVE_IMAGE_IMPORT.md`.
  - P3: pozostawiona baza `game_predictor_task0760_a9be23bf1f38_test` usunięta
    (`DROP DATABASE` tylko tej bazy, 0 połączeń).
- **Predykcje:** rezolucja wirtualna liczy predykcje komórek modelem
  przypiętym do importu (`ManualBoardCellSymbolPredictor.predict_rendered_cells`
  na renderach w pamięci; kontekst odroczonego slotu niesie
  `pending_symbol_model`). Bez predyktora komórki zostają `?`
  (`manual-unclassified-v1`, jak dotąd). Admin `save_source` i Reviewer dają
  ten sam stan (test PG).
- **Usunięte legacy:** `materialize_manual_resolution`,
  `manual_resolution_by_idempotency`, `_next_manual_geometry_revision`,
  `BoardCellGeometryManualResolutionProjection`, payload geometrii v19 i
  zapis plików cropów w rezolucji; `predict(preview)` predyktora zastąpione
  `predict_rendered_cells`. `ManualBoardCellGeometryPreviewer` zostaje (używa
  go korekta v19 ścieżki 3 do TASK-0791).
- **Brak obserwacji w pisarzach:** `pipeline_store.py` (import),
  `virtual_grid_geometry_repository.py` (odroczony slot) i
  `board_cell_geometry_pending_repository.py` nie tworzą `CellObservationModel`;
  manifest renderu jest jedynym rekordem komórek (idempotencja importu przez
  `ensure_board_render_manifest`). `CellObservationModel` jest tworzony tylko
  w fixture benchmarków (`real_workbench_fixture`, `workbench_acceptance`).
  Walidacja rolloutu (`image_geometry_rollout_backfill_repository`) dla
  planszy bez obserwacji sprawdza manifest.
- **Worker:** `pipeline_store` odmawia planszy/komórki niewirtualnej
  (`IMAGE_PIPELINE_NON_VIRTUAL_BOARD_REJECTED`), import z rolloutem innym niż
  `virtual_default` (także job bez snapshotu = historyczny legacy) kończy się
  `IMAGE_PIPELINE_NON_VIRTUAL_ROLLOUT_REJECTED` przed jakimkolwiek zapisem;
  gałąź `virtualShadow` w `pipeline_store` usunięta. Gałęzie `legacy` /
  `structured_shadow` w `production_workflow.py` i enumy
  `pipeline_contract.py` zostają: historyczne snapshoty jobów muszą się dalej
  parsować (odpowiedzi jobów, raporty, rekonstrukcja guardów), a wykonanie
  jest zablokowane bramką na wejściu; usunięcie gałęzi to sprzątanie po
  TASK-0791.
- **Polityki:** `ImageImportEnginePolicy` = `structured_default`,
  `structured_lattice_v3`; usunięte wartości odrzucane w schematach
  (`targetPolicy`, `boardCellProcessingMode`, `imageEnginePolicy`) kodem
  `IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED` (422; handler walidacji podnosi go
  do pola `code`); `create_image_import_job` bez `use_verified_board_cell_geometry`;
  `_pin_image_geometry_rollout` nigdy nie przypina legacy (stan legacy →
  `IMAGE_ENGINE_POLICY_UNSUPPORTED_STATE`); reuse joba bez snapshotu wyłączony.
- **Domyślna polityka nowej gry:** `structured_lattice_v3` / `virtual_default`
  (`game_partition_lifecycle`, `catalog_repository`, `backfill_legacy_states`,
  domyślne kolumn modelu). Założenie z Dependencies nie zostało
  potwierdzone: `structured_default` bez wariantu nie był uruchamiany na nowej
  grze (wymaga dodatkowo profilu siatki i preflightu), a każdy import
  browserowy i tak przypina `structured_lattice_v3` przez wariant silnika —
  dlatego domyślną jest `STRUCTURED_LATTICE_V3`.
- **Migracja `0133_virtual_only_import_policies`:** `SET LOCAL lock_timeout
  5s`/`statement_timeout 120s`, `LOCK ... ACCESS EXCLUSIVE`, zamrożone
  wartości bez ORM; odmowa `IMAGE_ENGINE_POLICY_MIGRATION_BUSY`, gdy stan
  niewirtualny ma backfill `processing`; `UPDATE` wszystkich stanów spoza par
  wirtualnych (`legacy`, `structured_shadow`, `structured_review`) →
  `structured_lattice_v3`/`virtual_default`, `revision + 1`, postęp walidacji
  wyzerowany jak w `apply_engine_policy`; CHECK-i trybów zawężone do par
  wirtualnych (na rodzicu → wszystkie partycje), domyślne kolumn zmienione;
  downgrade odmawia (`IMAGE_ENGINE_POLICY_MIGRATION_IRREVERSIBLE`).
  `EXPECTED_ALEMBIC_HEAD` = `0133`. Migracja zamiast skryptu, bo CHECK-i
  trybów i domyślne kolumn i tak wymagały DDL.
- **Admin:** `board-cell-processing-mode.ts` bez `verified_v19` i
  `structured_shadow` jako trybów do wyboru (etykiety historycznych jobów
  zostają z dopiskiem „usunięty”), domyślny tryb panelu
  `structured_lattice_v3`, dopasowanie joba do raportu wymaga snapshotu
  rolloutu. OpenAPI + wygenerowany klient (enum i opisy) + test żądania
  wrappera polityki.
- **Ścieżka 3 (korekta v19 Reviewera):** bez zmian — dla planszy wirtualnej
  zwraca czytelny `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED` (od
  TASK-0758); przepięcie na ścieżkę wirtualną wymaga zmiany UI Reviewera
  (nie jest tanie), zostaje do TASK-0791.

### Verification results

- `alembic heads` = `0133_virtual_only_import_policies`; `ruff check`
  (`services/api/src`, `services/worker/src`, `scripts` i zmienione testy):
  czysto; `ruff format --check`: czysto poza dwoma plikami niesformatowanymi
  już na HEAD (`schemas/image_imports.py`, `tests/test_image_imports_api.py`,
  hunki zadania sformatowane); `mypy --strict` 22 zmienione moduły src: 0
  błędów; `git diff --check` czysto.
- PostgreSQL, nowy `integration/test_virtual_deferred_resolution_postgres.py`
  9/9 (po audycie: + `test_manual_resolution_continues_the_canonical_crop_revision`
  — dwa importy tej samej sekwencji przez endpoint Reviewera, druga rezolucja
  rewizja 2 w odpowiedzi, planszy, specyfikacji renderu i komórkach nowego
  właściciela; + `test_manual_resolution_uses_pending_revision_without_current_crops`
  — przypięta rewizja 3 → 4; + `test_concurrent_resolutions_of_one_source_never_build_on_a_stale_revision`
  — dwie sesje, przegrany `IMAGE_GRID_REVIEW_REVISION_CONFLICT`, rewizje źródła
  `[0, 1]`, ponowienie buduje rewizję 2 z obydwoma slotami): domyślny rollout
  nowej gry; rezolucja Reviewera przez prawdziwą
  aplikację (`create_app`, ten sam wiring co produkcja): podgląd PNG 15
  komórek, plansza pełna i częściowa (lewa krawędź, maska 0/1/5/6/10/11) →
  `virtual_source`, rewizja z `virtual_render_spec`, manifest = komórki
  rewizji = komórki weryfikacji, 0 obserwacji, 0 nowych plików, predykcje
  przypiętego modelu, replay `created=false`, inny command z tym samym kluczem
  → `IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT`; Reviewer vs Admin
  (`save_source`) tego samego `pending_id` i narożników → identyczne
  `virtual_render_spec_checksum_sha256`, manifest (suma i komórki), komórki
  weryfikacji i predykcje; drugi klucz po rezolucji →
  `IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT`; plansza powstała po
  odroczeniu → slot `superseded`, bez nowej planszy i rewizji źródła;
  migracja `0133` (odmowa przy `processing`, przeniesienie `legacy` ×2 i
  `structured_shadow` z rewizją + 1, `structured_default` bez zmian,
  zawężone CHECK-i na rodzicu i partycjach, domyślne kolumn, wstawienie
  `legacy` odrzucone, downgrade odmawia i zostawia `0133`).
- PostgreSQL, istniejące pliki dotknięte zmianą (13 plików, każdy test osobno,
  porównanie z czystym HEAD w tymczasowym worktree): po poprawkach 51 passed,
  16 failed — zbiór niepowodzeń identyczny z HEAD (m.in. `test_image_batch_store`
  4, `test_board_import_coverage_repository` 5,
  `test_game_partition_lifecycle_postgres` z odczytem `public`); dostosowane: testy migracji `0131`/`0132` (budują bazę
  na `0132`, bo `0133` nie ma downgrade'u), fixture routingu
  (`legacy` → tryb wirtualny), usunięty test dawnej rezolucji legacy w
  `test_image_batch_store` (na HEAD i tak nie przechodził; zastąpiony nowym
  plikiem).
- Unit API (chunki po 6 plików): 1 671 passed, 28 failed, 4 skipped; 20
  niepowodzeń identycznych z HEAD (`test_image_import_geometry_guard_api` 7,
  `test_reviews` 6, `test_openapi_contract` 2, `test_virtual_grid_geometry` 2,
  `test_image_symbol_reviews_api` 1, `test_lateral_managed_reprocess` 1,
  `test_migration_baseline` 1), 8 to artefakt długiej ścieżki `--basetemp`
  w chunkach (`test_remote_manual_selection_recovery` 3, `test_storage_gc` 1,
  `test_symbol_references_*` 4) — ten sam zestaw plików: 163/163 passed z
  krótką ścieżką. Nowe/zmienione testy API: 0 niepowodzeń.
- Unit worker: 2 038 passed / 44 failed / 9 skipped w przebiegu chunkowym;
  37 niepowodzeń identycznych z HEAD (testy korpusu), 2 naprawione
  (`test_production_image_workflow` — fixture bramki rolloutu), 5 testów
  vision-lab niestabilnych pod obciążeniem (11/11 osobno); nowy
  `test_virtual_only_import_writers.py` 9/9, predyktor 5/5.
- Po audycie: unit `test_virtual_grid_geometry.py` + 5 przypadków reguły
  rewizji (`max(pinned, R) + 1`), `test_lateral_lock_order.py` 5/5,
  `test_board_cell_geometry_pending.py` 13/13; mypy --strict i ruff czyste dla
  zmienionych modułów.
- TS: `admin-api-client` 71/71 (nowy test żądania polityki), Admin 597/597 +
  typecheck + lint (0 błędów), Reviewer 193/193 + typecheck + interakcje
  geometrii 7/7; `export_admin_openapi.py --check` i `check:generated`
  aktualne.

### Not completed

- Migracja `0133` i cutover na bazie operatora (po commicie; zatrzymanie
  API/workerów/Reviewera → merge → `npm run db:migrate` → start).
- Usunięcie gałęzi legacy/shadow z `production_workflow.py` i enumów
  `pipeline_contract.py` (zablokowane bramką, potrzebne do parsowania
  historycznych snapshotów) oraz `domain/image_geometry_cutover.py` (czysta
  funkcja oceny bez konsumentów runtime; nie zapisuje stanu).
- Ścieżka 3 i `pending_grid_reinference._run_v1` (plansze legacy) — TASK-0791.
- `test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`
  (`npm run db:baseline:verify`) robi downgrade do `base`; `0133` (jak wcześniej
  `0125` i `0129`) odmawia downgrade'u, a test jest nieaktualny już na HEAD
  (`HEAD_REVISION = 0065`). Nie naprawiany w tym zadaniu.
- Admin `save_source` (wszystkie sloty źródła naraz) zwraca
  `IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT` dla źródła z częściowo rozwiązanymi
  slotami odroczonymi (kontekst rozwiązanego slotu ma już `review_item_id`);
  metoda nie ma endpointu HTTP — P3 do ewentualnego uporządkowania.
- Historyczne skrypty `scripts/run_v20_layout_import.py` i
  `scripts/start_v20_ready_staging.py` (bez wpisu w `package.json`) wysyłają
  `verified_v19` i dostaną teraz 422 z jawnym kodem; do usunięcia przy
  sprzątaniu (TASK-0759/0761).

### Documentation updates

- `DECISION_LOG.md` D-467: nota TASK-0790 (jeden tryb danych w pisarzach,
  wariant Reviewera, domyślna polityka, `0133`, numeracja S5 = `0134`,
  S7 = `0135`).
- Plan D-467: S6 TASK-0790 przed S5 z `0133`, S5 → `0134`, uwaga o
  numeracji TASK-0791, zakres S5 zawężony o to, co zrobił TASK-0790.
- `LOCAL_OPERATION_GUIDE.md`: sekcja cutoveru `0133` i zmian zachowania,
  sekcja v18/v20 zastąpiona opisem wirtualnej geometrii.
- `REMOTE_REVIEWER_THREAT_MODEL.md`: nota, że trasa i allowlista się nie
  zmieniają, a zapis idzie ścieżką wirtualną.
- `CURRENT_STATE.md`: wpis TASK-0790.
- Po audycie: `requirements/IMAGE_INGESTION.md`, `requirements/ADMIN_APP.md`,
  `architecture/API_CONTRACT.md`, `architecture/DATA_MODEL.md`,
  `architecture/SYSTEM_ARCHITECTURE.md`, `architecture/ITERATIVE_IMAGE_IMPORT.md`;
  nota D-467 uzupełniona o regułę rewizji i blokadę źródła.

### Recommended next task

- Audyt TASK-0790, commit, cutover `0133`, potem TASK-0759 (S5, migracja
  `0134`) albo TASK-0791.
