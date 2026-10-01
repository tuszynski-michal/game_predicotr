---
title: TASK-0757 — S4 — manifest renderu per plansza (`board_render_manifests`)
status: done
last_updated: 2026-10-01
---

# TASK-0757 — S4 — manifest renderu per plansza (`board_render_manifests`)

## Status

`done` (implementacja i poprawki po audycie Opus (FAIL warunkowy)
zakończone; czeka na ponowny audyt, commit, migrację i backfill na bazie
operatora za zgodą)

## Goal

Każda bieżąca rewizja wirtualnej planszy ma jeden wiersz w nowej tabeli V2
`board_render_manifests` (kształt `virtual_render_spec`), tak aby TASK-0758
mógł przepiąć wszystkich czytelników z `cell_observations`.

## Context

D-467, S4. Dla 372 355 plansz gry 777 na `geometry_revision = 0`
specyfikacje renderu istnieją wyłącznie w `cell_observations`
(15 wierszy/plansza, `render_spec` ok. 2,5 KB); dla 137 574 plansz na
rewizji > 0 źródłem jest `image_board_geometry_revisions.virtual_render_spec`;
461 plansz `legacy_file` nie ma specyfikacji. Bez jednego źródła nie da się
usunąć `cell_observations` (S5).

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.110`, `alembic heads` = `0130_board_search_share_sessions`
  przed zadaniem; baza operatora na `0130`, rejestr magazynu
  `game-data-v2-manifest-v1` dla 3 gier, wszystkie operacje cyklu życia
  partycji `done`.
- Fakt: `game_data_v2_manifest_v1` jest zamrożony („Do not edit version 1
  to add tables. Add a migration and a new manifest version”); `v2` istniał
  tylko jako klasyfikacja tabel publicznych, bez wpisu w rejestrze.
- Decyzje wejściowe orkiestratora (niepodważane): tabela per gra
  `board_render_manifests`, PK `(game_id, recognized_board_id,
  geometry_revision)`, FK do planszy z `ON DELETE CASCADE`, migracja `0131`,
  backfill porcjami z podglądem, writery piszą manifest obok obserwacji
  (obserwacje zostają do S5), czytelnicy bez zmian (TASK-0758).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S4)
- `ai_docs/process/DECISION_LOG.md` (D-467)

## Scope

- Manifest magazynu `game-data-v2-manifest-v3`: zbiór tabel gry v1 +
  `board_render_manifests` (66 tabel), klasyfikacja tabel publicznych v2 +
  `board_search_share_*`; routing, cykl życia partycji i katalog przechodzą
  na v3.
- Migracja `0131_board_render_manifests`: tabela partycjonowana listą po
  `game_id`, RLS `game_scope_v1`, domyślny `game_id`, FK (plansza CASCADE,
  rewizja geometrii źródła RESTRICT, właściciel `games` RESTRICT), partycja
  dla każdej zarejestrowanej gry, wiersze rejestru v3, CHECK lokalizacji
  v1 → v3 z podbiciem `revision`; downgrade przywraca v1 i usuwa tabelę.
- Domena `board_render_manifests.py`: budowa manifestu revision 0 z komórek
  (kontrola sumy `renderSpec` per komórka, maska dostępności, tożsamości),
  kopia rewizji > 0 z kontrolą sumy całości i per komórka.
- Writer importu (`pipeline_store.py`) i ręczna geometria
  (`virtual_grid_geometry_repository.py`, trzy ścieżki zapisu rewizji)
  zapisują manifest w tej samej transakcji.
- Backfill `scripts/backfill_board_render_manifests.py` (`--preview`,
  `--execute`, checkpoint, raport odrzuceń, `--min-free-gb`) na bibliotece
  `storage/board_render_manifest_backfill.py`; uruchamiany dla każdej gry z
  wirtualnymi planszami: 777 (`bfc4f949…`) i `cf300bc1-c0c1-4bf9-b607-4c4e1e4f031c`
  (26 plansz).
- Strażnik głowy Alembic (`storage/schema_readiness.py`,
  `ALEMBIC_HEAD_MISMATCH`) w starcie API (`__main__`), workera (`cli`) i w
  skrypcie backfillu.
- Stary backfill tożsamości v2 (`image_geometry_rollout_backfill_repository`)
  odmawia mutacji obserwacji planszy, która ma manifest
  (`BOARD_RENDER_MANIFEST_PRESENT`).

## Out of scope

- Przepięcie czytelników (TASK-0758), usunięcie `cell_observations` (S5).
- Manifesty historycznych rewizji (np. revision 0 plansz, które są dziś na
  rewizji > 0) — tylko bieżąca rewizja.
- Zastosowanie migracji i uruchomienie `--execute` na bazie operatora.

## Acceptance criteria

- [x] `alembic heads` = jedna głowa `0131_board_render_manifests`.
- [x] Migracja w górę i w dół na izolowanej bazie; partycje dla istniejących
      i nowo provisionowanych gier; RLS wymuszone; rejestr v3.
- [x] Backfill buduje manifest z sumą kontrolną równą sha256 kanonicznego
      JSON; drugi przebieg nic nie zapisuje; plansza z niezgodną sumą
      komórki jest odrzucona i raportowana, pozostałe przetwarzane.
- [x] Manifest z writera importu jest bajtowo identyczny z manifestem
      zbudowanym przez backfill z obserwacji tej samej planszy.
- [x] Podgląd tylko do odczytu na bazie operatora dla gry 777 z liczbami.

## Technical notes

- **Reguła dla TASK-0758: brak manifestu ⇔ brak komórek.** Wirtualna
  plansza bez renderowalnych komórek (kwalifikacja V3 z wszystkimi polami
  poza zdjęciem, ręczna geometria z 15 polami poza źródłem, maska
  `unavailable_cell_indices` = wszystkie pola) nie ma wiersza manifestu —
  writery go nie piszą, backfill liczy ją jako `no_cells_skipped`.
  Czytelnik po przepięciu traktuje brak wiersza dla takiej planszy jako
  zero komórek, a brak wiersza dla planszy z niepustą maską dostępności
  jako błąd (backfill odrzuca ją jako `OBSERVATIONS_MISSING`).
- Kontrola pochodzenia cropa: backfill odrzuca planszę, gdy obserwacja ma
  `cropper_version != extractor_version` albo `crop_checksum_sha256 !=
  rendered_pixel_checksum_sha256` (`CROP_PROVENANCE_MISMATCH`); writer
  importu wymaga `cropperVersion == extractorVersion`.

- Kształt `cells`: `{"assetMode", "cells": [{"cellIndex", "cropSampleId",
  "logicalCellKeySha256", "logicalCellKeyV2Sha256", "renderIdentityV2Sha256",
  "renderSpec", "renderSpecChecksumSha256", "renderedPixelChecksumSha256"}],
  "schemaVersion": "board-render-manifest-observations-v1"}` dla revision 0
  (te same klucze co komórki `virtual_render_spec`; `cropSampleId` liczony
  jak w `image_review_repository`). Dla revision > 0 kopia 1:1
  `virtual_render_spec`, więc `manifest_checksum_sha256` =
  `virtual_render_spec_checksum_sha256`.
- Kolumny dodane poza listą z decyzji: `source_geometry_revision_id`
  (FK) i `extractor_version` — czytelnicy potrzebują ich dla revision 0,
  a po S5 nie będzie obserwacji (dla revision > 0 kopiowane z rewizji:
  `source_geometry_revision_id`, `cropper_version`).
- Suma kontrolna: `sha256(canonical_json_bytes(...))` z
  `domain/image_geometry_v2.py` (ta sama funkcja, którą liczy
  `render_spec_checksum_sha256` w `virtual_cell_extraction`).
- Backfill: porcje po `recognized_boards.id` (keyset), istniejące manifesty
  pomijane przed odczytem obserwacji, `INSERT ... ON CONFLICT DO NOTHING`,
  jedna transakcja zapisu z wiązaniem routera na porcję. Oczekiwane komórki
  revision 0 = `available_cell_indices` planszy.
- Migracja odmawia przy operacji cyklu życia w toku, lokalizacji
  `migrating`/`deleting` lub lokalizacji innej niż v1.

## Expected files

- Nowe: `services/api/alembic/versions/0131_board_render_manifests.py`,
  `services/api/src/game_predictor_api/storage/game_data_v2_manifest_v3.py`,
  `services/api/src/game_predictor_api/domain/board_render_manifests.py`,
  `services/api/src/game_predictor_api/storage/board_render_manifest_repository.py`,
  `services/api/src/game_predictor_api/storage/board_render_manifest_backfill.py`,
  `scripts/backfill_board_render_manifests.py`,
  `services/api/src/game_predictor_api/storage/schema_readiness.py`,
  `services/api/tests/test_board_render_manifests.py`,
  `services/api/tests/test_schema_readiness.py`,
  `services/api/tests/integration/test_board_render_manifests_postgres.py`.
- Zmienione: `storage/models.py` (`BoardRenderManifestModel`),
  `storage/game_storage_routing.py`, `storage/game_partition_lifecycle.py`,
  `storage/catalog_repository.py`, `domain/catalog.py`,
  `storage/virtual_grid_geometry_repository.py`,
  `worker/images/pipeline_store.py`, `game_predictor_api/__main__.py`,
  `game_predictor_worker/cli.py`,
  `storage/image_geometry_rollout_backfill_repository.py`, testy wersji
  manifestu, `test_api_entrypoint.py`, `test_worker_cli.py`.

## Test cases

- Unit: suma kanoniczna, kształt i stabilność manifestu, odrzucenia
  (niezgodna suma, duplikat, brak komórki, niepełna tożsamość v2, zły klucz,
  pusta lista), kopia rewizji i niezgodność sumy całości/komórki, SQL
  offline migracji w górę i w dół, writer ręcznej geometrii (mock sesji).
- PostgreSQL: backfill (2 plansze revision 0 w tym częściowa 14 komórek,
  1 kopia rewizji, 1 legacy pominięta, 1 odrzucona z komórką 7), drugi
  przebieg no-op, wznowienie od kursora, CASCADE przy usunięciu planszy;
  migracja w dół/w górę; równoważność writer importu ↔ backfill.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check <zmienione pliki>
.\.venv\Scripts\python.exe -m mypy <zmienione moduły src + skrypt>
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_render_manifests.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_render_manifests_postgres.py
```

## Cutover

Router magazynu akceptuje tylko manifest v3, więc stary kod nie działa po
`0131`, a nowy przed nią. API, worker i skrypt backfillu odmawiają startu
(`ALEMBIC_HEAD_MISMATCH`), gdy `alembic_version` różni się od głowy kodu.
Strażnik działa tylko przy świeżym starcie procesu: `api:dev --reload`
przeładowuje wyłącznie proces potomny (bez `__main__`), a już działające
procesy nie są sprawdzane po migracji — dlatego kroki 1–2 są obowiązkowe.

1. Zakończ lub bezpiecznie zatrzymaj aktywne joby.
2. Zatrzymaj API, workery (wszystkie lane'y) i Reviewera we **wszystkich**
   checkoutach i worktree.
3. Merge kodu.
4. `npm run db:migrate` → `npm run db:current` = `0131_board_render_manifests`.
   Migracja bierze `LOCK ... ACCESS EXCLUSIVE` na
   `public.game_storage_locations` z `lock_timeout = 5s`: aktywna transakcja
   innego procesu kończy migrację błędem (bez zmian, można powtórzyć).
   Odmawia też przy provisionowaniu/usuwaniu gry w toku.
5. Start usług nowego kodu.
6. Za osobną zgodą: backfill `--preview`, potem `--execute` dla 777 i
   `cf300bc1…`, na końcu `VACUUM (ANALYZE)` tabeli.

Wycofanie: zatrzymaj procesy nowego kodu, z nowym kodem
`alembic downgrade 0130_board_search_share_sessions` (usuwa tabelę,
przywraca rejestr v1), następnie uruchom stary kod. Runbook operatora:
`ai_docs/guides/LOCAL_OPERATION_GUIDE.md`.

## Risks / open questions

- Rozmiar: ok. 45 KB kanonicznego JSON na planszę (≈ 50 KB JSONB przed
  kompresją TOAST; `render_spec` obserwacji zajmuje dziś ok. 30 KB/plansza
  po kompresji). Szacunkowo 13–17 GB na 510 tys. plansz do czasu S5
  (tymczasowe zdublowanie) plus porównywalny wolumen WAL podczas
  `--execute`; potrzebne potwierdzenie wolnego miejsca.
- Tylko bieżąca rewizja: specyfikacje revision 0 ok. 138 tys. plansz na
  rewizji > 0 zostają wyłącznie w obserwacjach; TASK-0758/0759 muszą
  potwierdzić, że nic ich nie czyta (np. `observation_id`,
  `symbol_reference_images.source_observation_id`, stale-base-crop).
- Zgodność planu: S4 zajmuje migrację `0131` i manifest magazynu v3, więc
  S5 przechodzi na v4 i `0132`, a kolejne migracje planu przesuwają się o
  jeden (plan i D-467 zaktualizowane).
- Przejście wymaga zatrzymania wszystkich procesów (patrz Cutover).

## Outcome

### Execution (2026-10-01, zgoda operatora na cały plan)

- Audyt `claude-opus-5-5`: FAIL warunkowy (P1: cutover kod↔baza, writery
  dla plansz bez komórek; P2: `cropper_version`, rollout backfill,
  dokumenty) → poprawki (strażnik `ALEMBIC_HEAD_MISMATCH` w API, workerze i
  backfillu; reguła „brak manifestu ⇔ brak komórek”; kontrola
  `cropper_version`/`crop_checksum`; odmowa `BOARD_RENDER_MANIFEST_PRESENT`;
  `--min-free-gb`) → PASS; P3 wdrożone (kontrola sumy i maski przy pustej
  rewizji, nota o `--reload` w cutover).
- Cutover 2026-10-01 02:00 UTC: zatrzymane API 8000/8010 z głównego
  checkoutu (proces potomny uvicorna `--reload` przeżył `taskkill` i trzymał
  port ze starym kodem — usunięty ręcznie), merge v1.7.111 do
  `v1.1-vision-lab-hybrid-geometry`, `alembic upgrade head` → `0131`,
  3 lokalizacje na `game-data-v2-manifest-v3` (revision 2), API wznowione.
  API z worktree `v7-t0603-v2-calibration` (port 8110, inna sesja) zwraca
  500 do czasu scalenia v1.1 w tamtym worktree.
- Backfill: `cf300bc1…` 26/26; `777` 509 929 manifestów (372 355 revision 0
  zbudowanych z obserwacji, 137 574 skopiowanych z rewizji > 0, 461 legacy
  pominiętych), 0 odrzuceń, ok. 150 plansz/s, 58 min; partycja 6,9 GB
  (lepsza kompresja TOAST niż szacowane 13–17 GB). Wolne miejsce na C:
  43 → 28 GB (zmiana większa niż partycja przez WAL i checkpointy).


### Changed

- Nowa tabela V2 `board_render_manifests` (migracja `0131`, manifest
  magazynu v3), domena budowy/kontroli manifestu, repozytorium zapisu,
  biblioteka i skrypt backfillu, zapis manifestu w writerze importu i w
  trzech ścieżkach ręcznej geometrii wirtualnej.
- Poprawki po audycie: pomijanie plansz bez komórek (writery i backfill,
  `no_cells_skipped`), strażnik `ALEMBIC_HEAD_MISMATCH`
  (`storage/schema_readiness.py`, `game_predictor_api/__main__.py`,
  `game_predictor_worker/cli.py`, skrypt backfillu), kontrola
  `cropper_version`/`crop_checksum_sha256`, blokada
  `BOARD_RENDER_MANIFEST_PRESENT` w `image_geometry_rollout_backfill_repository`,
  kontrola wolnego miejsca (`--min-free-gb`, domyślnie 10, przed startem i
  po każdej porcji), fixture testu PostgreSQL czeka do 5 s na zamknięcie
  połączeń przed `DROP DATABASE`.
- Testy wersji manifestu przepięte na v3; `test_game_storage_routing_postgres`
  działa na schemacie `head` (router akceptuje tylko v3), asercje o
  usuniętych tabelach `public.*` zamienione na `to_regclass(...) IS NULL`.

### Verification results

- `alembic heads`: `0131_board_render_manifests (head)`.
- ruff check + ruff format: czysto dla zmienionych plików; mypy --strict:
  0 błędów w zmienionych plikach (27 wcześniejszych błędów w innych
  modułach workera/API bez zmian).
- Nowe testy po poprawkach: `test_board_render_manifests.py` 17 passed,
  `test_schema_readiness.py` 5 passed, PostgreSQL
  `test_board_render_manifests_postgres.py` 4 passed (w tym plansze bez
  komórek w ścieżce importu i ręcznej); zestaw dotkniętych testów unit
  (entrypoint API, CLI workera, adaptery selekcji, rollout backfill,
  geometria wirtualna, pipeline, schemat V2, routing, katalog) 179 passed,
  4 skipped.
- Regresja (PostgreSQL, izolowane bazy): `test_game_data_v2_postgres` 4/4,
  `test_game_partition_lifecycle_postgres` + `test_pipeline_state_compaction_v2`
  5/6, `test_board_search_approximate_win_repository` pass,
  `test_board_search_share_repository` pass, `test_game_storage_routing_postgres`
  11/12, `test_image_batch_store` 11/16. Wszystkie niepowodzenia występują
  identycznie na czystym HEAD `v1.7.110` (sprawdzone w osobnym worktree):
  `greenfield_catalog_create` (brak `public.image_geometry_rollout_states`),
  `grid_review_source_asset` (brak `image_review_items` bez scope),
  5 testów `test_image_batch_store`, 8 testów
  `test_board_import_coverage_repository`, 2 testy unit
  `test_qualified_partial_preview_*`. `test_game_data_v2_schema` (na HEAD
  nieprzechodzący przez niesklasyfikowane `board_search_share_*`) oraz
  `test_page_geometry_snapshot_reads_v2_*` przechodzą po zmianie.
- Podgląd tylko do odczytu na bazie operatora (gra 777, migracja `0131`
  niezastosowana, więc adapter bez złączenia z nową tabelą i bez routera
  v3; transakcje `READ ONLY`): 510 390 plansz, 461 legacy (pominięte),
  372 355 revision 0 do zbudowania (w tym 105 `pending_partial`, 0 bez
  obserwacji), 137 574 revision > 0 do skopiowania (0 bez użytecznej
  rewizji); liczenie 8,2 s. Walidacja 2 000 + 2 000 pierwszych plansz:
  0 odrzuceń. Próbka 100 plansz: średnio 45 527 B (revision 0) i 44 650 B
  (revision > 0) kanonicznego JSON, 50 781 / 49 840 B JSONB bez kompresji;
  obecne `render_spec` obserwacji 30 094 B/plansza po kompresji.

### Not completed

- Migracja `0131` i `--execute` na bazie operatora (wymagają zgody,
  sprawdzenia wolnego miejsca i okna bez importów).
- Commit i ponowny audyt.

### Documentation updates

- `DECISION_LOG.md` D-467 (nota TASK-0757: manifest v3, `0131`, kolumny,
  zakres bieżącej rewizji, reguła braku komórek, pomiar rozmiaru, numeracja
  S5–S7), plan D-467 (S4 „obok obserwacji”, S5 v4/`0132`, S6 `0133`, S7
  `0134`, rozmiar), `CURRENT_STATE.md`, `LOCAL_OPERATION_GUIDE.md` (sekcja
  przejścia na manifest v3).

### Recommended next task

- Audyt TASK-0757, potem migracja + `--execute` za zgodą, następnie
  TASK-0758.
