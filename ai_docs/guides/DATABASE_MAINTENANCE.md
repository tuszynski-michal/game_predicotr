---
title: Utrzymanie bazy danych — VACUUM, kompaktacja pipeline, VHDX i migracja dysku
status: active
last_updated: 2026-10-10
---

# Runbook: utrzymanie bazy danych

Dotyczy lokalnego PostgreSQL 18 w kontenerze Docker Desktop
`game-predictor-postgres-1` (baza i rola `game_predictor`, wolumen
`game-predictor_game_predictor_postgres_data`), którego dane leżą w pliku
`D:\docker\DockerDesktopWSL\disk\docker_data.vhdx`. Lokalizację ustawia
Docker Desktop → Settings → Resources → Advanced → „Disk image location”
(w pliku `%APPDATA%\Docker\settings-store.json` klucz `CustomWslDistroDir`
= `D:\docker\DockerDesktopWSL`). Do 2026-10-10 obraz leżał w
`C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx`; ten plik
jest nieużywany i zostaje do etapu C planu przeniesienia (TASK-0957, osobna
zgoda). Kopie zapasowe leżą w `D:\game_predictor_backup` (sekcje 4 i 5.1).
Źródła: D-467 (plan
`ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`, S3),
TASK-0756, D-540 (plan `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`,
TASK-0955).

## Zasady bezpieczeństwa

- Raport zajętości (sekcja 1) i `preview` kompaktacji są tylko do odczytu
  (preview zapisuje wyłącznie plik raportu w `artifacts`).
- `start --confirm`, uruchomienie workera z jobem kompaktacji, `VACUUM FULL`,
  kompaktowanie VHDX i przenoszenie danych wymagają osobnej, jawnej zgody
  operatora na każdą operację (wzorzec D-448/D-467). Zatwierdzenie planu nie
  jest tą zgodą.
- Przed `VACUUM FULL`, kompaktowaniem VHDX i migracją dysku wykonaj kopię
  (sekcja 4) i sprawdź jej czytelność.
- Polecenia uruchamiaj z katalogu repozytorium
  `D:\game_predicotr` w PowerShell (od 2026-10-10; wcześniej
  `C:\Users\tuszy\Documents\game_predicotr`). Pliki SQL zapisuj
  wyłącznie znakami ASCII: PowerShell 5.1 przekazuje potok do `docker exec`
  w kodowaniu ASCII.
- `df` wewnątrz kontenera pokazuje rozmiar wirtualnego dysku (ok. 1 TB), nie
  realne wolne miejsce. Miarodajne jest wolne miejsce dysku Windows, na którym
  leży `docker_data.vhdx`:

```powershell
Get-PSDrive D | Select-Object Name, @{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}
Get-Item D:\docker\DockerDesktopWSL\disk\docker_data.vhdx |
  Select-Object FullName, @{n='GB';e={[math]::Round($_.Length/1GB,1)}}
```

## 1. Raport zajętości

Zapisz zapytania do pliku, np. `artifacts\maintenance\zajetosc.sql`, i uruchom:

```powershell
Get-Content -Raw artifacts\maintenance\zajetosc.sql |
  docker exec -i game-predictor-postgres-1 psql -U game_predictor -d game_predictor -v ON_ERROR_STOP=1
```

```sql
-- A. Largest tables; a partitioned table is the sum of its partitions.
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       pg_size_pretty(s.bytes) AS total_size,
       s.bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
CROSS JOIN LATERAL (
    SELECT CASE
               WHEN c.relkind = 'p' THEN (
                   SELECT coalesce(sum(pg_total_relation_size(t.relid)), 0)
                   FROM pg_partition_tree(c.oid) AS t
               )
               ELSE pg_total_relation_size(c.oid)
           END AS bytes
) AS s
WHERE n.nspname IN ('public', 'game_data_v2')
  AND c.relkind IN ('r', 'p')
  AND NOT c.relispartition
ORDER BY s.bytes DESC
LIMIT 20;

-- B. game_data_v2 size per game (LIST partitions by game_id).
SELECT g.code,
       p.game_id,
       pg_size_pretty(sum(pg_total_relation_size(p.oid))) AS total_size
FROM (
    SELECT c.oid,
           substring(pg_get_expr(c.relpartbound, c.oid)
                     FROM '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')::uuid
               AS game_id
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'game_data_v2' AND c.relispartition AND c.relkind = 'r'
) AS p
LEFT JOIN public.games AS g ON g.id = p.game_id
GROUP BY g.code, p.game_id
ORDER BY sum(pg_total_relation_size(p.oid)) DESC;

-- C. Dead tuples and last (auto)vacuum, partitions named by their parent.
SELECT s.schemaname,
       coalesce(parent.relname, s.relname) AS table_name,
       s.relname AS relation,
       s.n_live_tup, s.n_dead_tup,
       s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze
FROM pg_stat_user_tables AS s
LEFT JOIN pg_inherits AS i ON i.inhrelid = s.relid
LEFT JOIN pg_class AS parent ON parent.oid = i.inhparent
WHERE s.schemaname IN ('public', 'game_data_v2')
ORDER BY s.n_dead_tup DESC
LIMIT 15;

-- D. Whole database.
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

-- E. Pipeline payloads on disk per stage (TOAST-compressed size).
SELECT stage, count(*) AS row_count,
       pg_size_pretty(sum(pg_column_size(result_payload))::bigint) AS payload_on_disk
FROM public.image_pipeline_stage_results
GROUP BY stage
ORDER BY sum(pg_column_size(result_payload)) DESC;
```

Stan 2026-09-30 (odczyt): baza 89 GB, gra `7` 83 GB w `game_data_v2`;
największe tabele `image_symbol_review_cells` 34 GB, `cell_observations` 28 GB,
`image_symbol_prediction_revisions` 11 GB,
`public.image_pipeline_stage_results` 6,8 GB (z tego `board_crops` 5,36 GB).
Migracja `0134` (TASK-0759, D-467 S5) usuwa `cell_observations` w całości —
patrz sekcja 2.5.

## 2. Kolejność po dużych przebiegach zapisu

Duży przebieg to np. zapis biblioteki wzorców (D-466), masowe zatwierdzenia
albo przeliczenie predykcji. Kolejność:

### 2.1. Preflight

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT job_type, status, count(*) FROM public.jobs WHERE status IN ('created', 'processing') GROUP BY 1, 2"
```

Wynik powinien być pusty (brak aktywnych jobów). Wykonaj raport z sekcji 1
(zapytania A, C) i zapisz wynik jako punkt odniesienia.

### 2.2. `VACUUM (ANALYZE)` tabel komórek i rewizji

Zwykły `VACUUM` nie blokuje odczytów ani zapisów i nie zmniejsza plików;
oznacza martwe krotki do ponownego użycia i odświeża statystyki planera.
`VACUUM` na tabeli partycjonowanej obejmuje wszystkie jej partycje. Przy
34 GB trwa to wiele minut; uruchom w osobnym terminalu:

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "VACUUM (ANALYZE, VERBOSE) game_data_v2.image_symbol_review_cells"
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "VACUUM (ANALYZE, VERBOSE) game_data_v2.image_symbol_prediction_revisions"
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "VACUUM (ANALYZE, VERBOSE) game_data_v2.image_symbol_review_events"
```

### 2.3. Kompaktacja wyników pipeline

Job `storage_pipeline_compaction` usuwa z
`public.image_pipeline_stage_results` odtwarzalne payloady `board_crops`,
`symbol_inference`, `board_cell_geometry` i `sequence_ocr`, zostawiając
`discovery`, `normalization` i `board_detection` oraz kompaktowy manifest
terminalny w `image_pipeline_terminal_manifests`.

Kandydaci pochodzą z globalnych `image_file_executions` (status
`waiting_for_review`/`completed`, starsze niż retencja). Wykluczenia są liczone
osobno w każdym magazynie gry (`game_data_v2`, osobna transakcja z wiązaniem
gry): aktywny job importu (`created`/`processing`), link importu `failed`,
nierozwiązana geometria planszy. Wykonanie bez żadnej gry (osierocone) i
wykonanie gry w stanie innym niż `active` nie są kompaktowane. Worker
powtarza tę kontrolę przed każdym `DELETE`.

1. Podgląd (tylko odczyt, zapisuje manifest w
   `artifacts\data\exports\storage-gc\pipeline-state\<id>\manifest.jsonl`):

   ```powershell
   .venv\Scripts\python.exe scripts\compact_image_pipeline_state.py preview --retention-hours 24
   ```

   `candidateBytes` to długość tekstu JSON payloadów (bez kompresji). Realnie
   zwolnione miejsce na dysku jest mniejsze — szacuj je zapytaniem E z
   sekcji 1 (suma stron etapów usuwanych). Podgląd 2026-09-30: 56 710
   wykonań, 226 840 wyników etapów, `candidateBytes` 27,85 GB tekstu JSON, na
   dysku ok. 6,0 GB.

2. Wykonanie — tylko za osobną zgodą, z wartościami z tego samego podglądu:

   ```powershell
   .venv\Scripts\python.exe scripts\compact_image_pipeline_state.py start `
     --manifest-relative-path <manifestRelativePath> `
     --manifest-checksum-sha256 <manifestChecksumSha256> `
     --preview-token <previewToken> `
     --confirm DELETE_REPRODUCIBLE_PIPELINE_PAYLOADS
   ```

   Job trafia do general lane; wykona go działający `npm run worker:poll`
   (albo jednorazowo `npm run worker:once`). Worker musi działać z checkoutu
   zawierającego TASK-0756 (kompaktacja na V2; starszy worker kończy job
   błędem `UndefinedTable`, bez usuwania). Sam `preview` trwa ok. 3 min na
   57 tys. wykonań. Job jest checkpointowany co 200
   wpisów i wznawialny; wpis zmieniony po podglądzie liczy się jako konflikt
   i nie jest usuwany. Po zakończeniu job sam wykonuje
   `VACUUM (ANALYZE) image_pipeline_stage_results`.

3. Kontrola: zapytanie E z sekcji 1 (etapy usuwane mają mniej wierszy),
   `SELECT count(*) FROM public.image_pipeline_terminal_manifests`, stan joba
   w panelu Admina.

### 2.4. Opcjonalnie `VACUUM FULL`

Zwykły `VACUUM` nie oddaje miejsca systemowi plików. `VACUUM FULL` przepisuje
tabelę do nowego pliku i zwalnia stary, ale:

- bierze blokadę `ACCESS EXCLUSIVE` — wymaga okna bez zapisów i odczytów:
  zatrzymaj API (8000), Admin (3000), Reviewer (3001) i wszystkie workery;
- potrzebuje wolnego miejsca na dysku Windows z `docker_data.vhdx` co najmniej
  równego rozmiarowi żywych danych tabeli z indeksami plus zapas (przyjmij
  pełny bieżący rozmiar tabeli + 10 GB); sprawdź `Get-PSDrive` z sekcji
  zasad i zapytanie A;
- nie zmniejsza pliku VHDX — do tego służy sekcja 3.

Po kompaktacji pipeline tabela ma głównie martwe miejsce, więc przepisanie
jest krótkie:

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SET lock_timeout = '5s'" -c "VACUUM (FULL, ANALYZE, VERBOSE) public.image_pipeline_stage_results"
```

Warunek: job kompaktacji ma status `completed`, a API, worker i Admin nie
wykonują zapisów (`lock_timeout` przerywa próbę, jeśli tabela jest w użyciu).

`VACUUM FULL` dużych tabel `game_data_v2` (np. 34 GB komórek) wymaga
osobnego planu: przy 43 GB wolnego miejsca na `C:` (2026-09-30) nie ma
bezpiecznego zapasu.

### 2.5. Po migracji `0134` (usunięcie `cell_observations`)

`DROP TABLE` partycji usuwa ich pliki natychmiast — `VACUUM` ani
`VACUUM FULL` nie są potrzebne dla usuniętych tabel. Po cutoverze:

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT pg_size_pretty(pg_database_size('game_predictor'))"
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT to_regclass('game_data_v2.cell_observations') IS NULL AS dropped"
Get-PSDrive C
```

Oczekiwany spadek rozmiaru bazy to ok. 28 GB. Miejsce na dysku Windows
zwalnia dopiero kompaktowanie `docker_data.vhdx` (sekcja 3). Statystyki
planisty dla tabel weryfikacji symboli odświeża `refresh_symbol_review_query_statistics`
przy następnym pełnym przebudowaniu projekcji (lista tabel zawiera teraz
`board_render_manifests` zamiast `cell_observations`).

### 2.6. Po migracji `0136`: przepisanie partycji komórek (TASK-0793)

`0136` usuwa kolumnę `image_symbol_review_cells.render_spec` tylko z
katalogu: stare wiersze i ich TOAST zostają na dysku, dopóki partycja nie
zostanie przepisana. Stan przed migracją (2026-10-01, partycja 777
`game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d`): wiersze 6,7 GB, TOAST 18 GB,
indeksy 8,5 GB, razem 34 GB; partycje `cf300bc1…` (2 MB) i `2a46d3a6…`
(0,2 MB) nie wymagają przepisania.

Przepisanie wykonuje się raz, po cutoverze `0136` i walidacji CHECK-ów
(`LOCAL_OPERATION_GUIDE.md`), w oknie bez zapisów i odczytów komórek:

- `VACUUM FULL` bierze `ACCESS EXCLUSIVE` na partycji: weryfikacja symboli,
  wyszukiwarka i joby stoją przez cały czas przepisania (szacunkowo
  10–30 min). Zatrzymaj API (wszystkie porty), Admin, Reviewer i workery we
  wszystkich checkoutach.
- Wolne miejsce wewnątrz bazy (VHDX) musi pomieścić nową kopię: ok. rozmiar
  wierszy + indeksów po usunięciu kolumny, przyjmij 15 GB + 5 GB zapasu.
  Stara kopia (34 GB) jest zwalniana dopiero na końcu. Sprawdź wolne miejsce
  Dockera (`docker system df`, `Get-PSDrive C`) i nie zaczynaj przy mniej niż
  20 GB.
- Zrób kopię zapasową przed oknem (sekcja 4).

Pomiar przed:

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT pg_size_pretty(pg_relation_size('game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d')) AS heap, pg_size_pretty(pg_relation_size(reltoastrelid)) AS toast, pg_size_pretty(pg_indexes_size('game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d')) AS indexes, pg_size_pretty(pg_total_relation_size('game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d')) AS total FROM pg_class WHERE oid = 'game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d'::regclass"
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT pg_size_pretty(pg_database_size('game_predictor'))"
```

Przepisanie (`lock_timeout` przerywa próbę, gdy jakikolwiek proces trzyma
partycję; `statement_timeout = 0`, bo przepisanie trwa długo — komenda jest
jedynym procesem w oknie, uruchom ją w osobnym terminalu i nie przerywaj):

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SET lock_timeout = '5s'" -c "SET statement_timeout = 0" -c "VACUUM (FULL, ANALYZE, VERBOSE) game_data_v2.gpv2_bfc4f9495c14_08b43e8e744d"
```

Pomiar po: te same zapytania co przed. Oczekiwane: TOAST bliski 0, razem ok.
12–15 GB (wiersze bez wskaźników TOAST i martwych krotek, indeksy
przebudowane), baza mniejsza o ok. 19–22 GB. Przerwanie `VACUUM FULL` (np.
utrata połączenia) wycofuje przepisanie i zostawia starą kopię bez zmian;
wtedy można je powtórzyć. Plik `docker_data.vhdx` nie maleje sam — sekcja 3.

### 2.7. Po odchudzeniu rewizji predykcji: przepisanie partycji (TASK-0794)

`scripts/slim_prediction_revisions.py --execute` zapisuje nowe, mniejsze
wersje `predictions`; stare wersje TOAST zostają jako martwe miejsce do
przepisania partycji. Stan przed (2026-10-01, partycja 777
`game_data_v2.gpv2_bfc4f9495c14_495aa1afbdfc`): wiersze 236 MB, TOAST
10 GB, indeksy 400 MB, razem 11 GB; `predictions` 10,1 GB wg
`pg_column_size`. Podgląd skryptu szacuje 5,2–7,5 GB oszczędności.

Warunki: skrypt zakończony (`completed: true`, `legacy_predictions_sha256 IS
NULL` = 0), retencja wykonana albo świadomie pominięta, okno bez zapisów
(`ACCESS EXCLUSIVE`: weryfikacja symboli, przeliczanie predykcji i
`apply` biblioteki stoją; szacunkowo 5–15 min), wolne miejsce w bazie na
nową kopię (przyjmij 6 GB + 5 GB zapasu), kopia zapasowa. Pomiar przed i
po:

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT pg_size_pretty(pg_relation_size(oid)) AS heap, pg_size_pretty(pg_relation_size(reltoastrelid)) AS toast, pg_size_pretty(pg_indexes_size(oid)) AS indexes, pg_size_pretty(pg_total_relation_size(oid)) AS total FROM pg_class WHERE oid = 'game_data_v2.gpv2_bfc4f9495c14_495aa1afbdfc'::regclass"
```

Przepisanie (osobny terminal, nie przerywać; przerwanie wycofuje je bez
zmian):

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SET lock_timeout = '5s'" -c "SET statement_timeout = 0" -c "VACUUM (FULL, ANALYZE, VERBOSE) game_data_v2.gpv2_bfc4f9495c14_495aa1afbdfc"
```

Plik `docker_data.vhdx` nie maleje sam — sekcja 3.

### 2.8. Usunięcie martwych zdjęć zduplikowanego importu (TASK-0811)

`scripts/remove_superseded_import_images.py` (`npm run
images:remove-superseded-import-images -- ...`) usuwa z magazynu gry tylko
te zdjęcia wskazanego importu, które są w całości zastąpione innym importem
tej gry i nie niosą pracy człowieka ani żywych danych. Każde inne zdjęcie
importu zostaje w całości (nigdy nie usuwa się części plansz zdjęcia) i
trafia do raportu z powodami. Pliki na dysku i job importu zostają.

Zdjęcie kwalifikuje się, gdy spełnia wszystkie warunki:

1. należy do gry i importu;
2. ma plansze, każda ma `status = 'rejected'` i element review, każdy
   element review tych plansz ma `status = 'superseded'` i numer sekwencji;
3. każdy numer sekwencji jego elementów, plansz i oczekiwanych pozycji
   najnowszej rewizji źródła ma żywy element review (`pending`/`accepted`/
   `corrected`, na planszy nie `rejected`) na zdjęciu innego importu tej
   gry, a raport kompletności (D-484) klasyfikuje zdjęcie jako `superseded`;
4. brak jego wierszy w tabelach chronionych (`image_symbol_review_cells`,
   `image_symbol_review_events`, `image_symbol_review_bulk_targets`,
   `symbol_reference_images`, `verified_training_cohort_items`/`_cells`,
   `image_sequence_canonical`, `image_sequence_alternatives` (import i suma
   pliku albo numer sekwencji), `image_sequence_source_override_events`
   (element albo numer sekwencji), `image_board_search_candidates`,
   `image_board_search_fast_documents`, `image_layout_staging_rows`);
5. żadna plansza nie ma zatwierdzonej geometrii ani zdarzenia
   `image_board_geometry_review_events`; rewizje geometrii plansz i źródła,
   rozstrzygnięcia elementów review i ich zdarzenia zapisał aktor
   `system:%`; brak otwartego wiersza odroczonej geometrii;
6. żaden wiersz spoza zbioru usuwania (innego zdjęcia, importu lub tabeli)
   nie wskazuje na jego wiersze: wszystkie klucze obce z katalogu
   `pg_constraint` do tabel usuwanych, `ownerReviewItemId` w
   `resolved_value` elementów review i zdarzeń rozstrzygnięć oraz znane
   kolumny bez FK (`image_symbol_review_states.last_review_item_id`,
   `count_rebuild_cursor`, `layouts.source_board_id`);
7. brak wyjątku geometrii;

a jego plik importu ma stan `waiting_for_review`/`completed` i nie jest
współdzielony z innym zdjęciem tego importu.

Zakres usuwania zdjęcia: elementy kolejki review (usuwa je istniejący
trigger `project_image_review_queue_delete_v1`, który też przelicza
`image_review_queue_states`), zdarzenia rozstrzygnięć, odroczona geometria,
rewizje geometrii plansz, rewizje predykcji, manifesty renderu, elementy
review, plansze, rewizje geometrii źródła, zdjęcia, pliki joba importu, a w
`public` wyniki etapów, manifesty terminalne i wykonania plików — te trzy
tylko, gdy po usunięciu żaden wiersz żadnej gry nie odwołuje się do
`file_execution_key`. Kolejność dzieci przed rodzicami wynika z kluczy obcych
katalogu; polecenia nie używają `CASCADE`. Liczniki
`image_symbol_review_states` i `image_board_search_projection_states` nie
zależą od usuwanych wierszy (zakwalifikowane zdjęcie nie ma komórek ani
dokumentów wyszukiwarki; `skipped_review_item_count` jest raportem ostatniej
przebudowy, a nie licznikiem utrzymywanym na bieżąco).

Rola: skrypt łączy się rolą właściciela schematu (silnik utrzymaniowy, jak
`CrossGameOwnerSession` i usuwanie gry) i odmawia roli objętej RLS, bo
kontrola wykonań wszystkich gier i usunięcia w `public` muszą być w tej
samej transakcji co usunięcia w magazynie gry. Gra jest i tak wiązana przez
`GameStorageRouter`, a każde zapytanie gry ma jawny predykat `game_id`.

Zatrzymaj API, workery i Reviewera wszystkich checkoutów. Polecenia z
katalogu repozytorium:

1. Podgląd (tylko odczyt: jedna transakcja `REPEATABLE READ READ ONLY`;
   zapisuje wyłącznie raport
   `artifacts\data\exports\remove-superseded-import-images\<gra>\<znacznik>-preview.json`
   z `planSha256`, licznikami wierszy per tabela i listą zdjęć zachowanych z
   powodami):

   ```powershell
   .venv\Scripts\python.exe scripts\remove_superseded_import_images.py `
     --game-id <gra> --import-job-id <import>
   ```

2. Wykonanie — tylko za osobną zgodą operatora, z `planSha256` przejrzanego
   podglądu:

   ```powershell
   .venv\Scripts\python.exe scripts\remove_superseded_import_images.py `
     --game-id <gra> --import-job-id <import> `
     --execute --confirm-plan-sha256 <planSha256>
   ```

   Skrypt bierze wyłączną blokadę advisory gry używaną przez lifecycle
   (`hashtextextended(game_id, 519)`, na poziomie sesji, przed migawką; zajęta
   blokada → odmowa `REMOVAL_GAME_LOCKED`), a następnie w jednej transakcji
   `REPEATABLE READ`: wylicza plan ponownie i odmawia, gdy `planSha256` się
   różni albo istnieje blokada (aktywny job gry, niespójna projekcja
   kolejki); zapisuje kopię każdego usuwanego wiersza (JSON Lines per tabela
   plus stan kolejki importu i `manifest.json` z licznikami i SHA-256) do
   `artifacts\data\exports\remove-superseded-import-images\<gra>\<znacznik>\`;
   usuwa i sprawdza liczbę usuniętych wierszy każdego polecenia; przed
   `COMMIT` sprawdza niezmienniki: liczby żywych plansz, żywych elementów
   review, komórek, zdarzeń symboli, dokumentów i kandydatów wyszukiwarki i
   kanonu gry bez zmian; zbiór numerów sekwencji z żywym elementem review
   bez zmian (liczba i skrót MD5); inne importy bez zmian (zdjęcia, plansze,
   elementy); różnica wierszy każdej tabeli równa planowi; wiersze
   zachowanych współdzielonych wykonań bez zmian; statusy jobów gry bez
   zmian; stan kolejki importu mniejszy dokładnie o usunięte elementy
   (`superseded`); raport kompletności: `complete`, `incomplete_*`,
   `no_source_geometry`, `import_failed` bez zmian, `superseded` i `total`
   mniejsze dokładnie o liczbę usuniętych zdjęć. Naruszenie → `ROLLBACK`,
   kod wyjścia 3, raport `<znacznik>-execute-rolled-back.json`. Raport
   wykonania: `<znacznik>\report.json`. Ponowne uruchomienie po wykonaniu
   nie usuwa nic.

Kopia JSON Lines nie jest automatycznym mechanizmem przywracania.

Podgląd na bazie deweloperskiej (2026-10-02, gra 777, import `7d10ae0a`):
0 z 1 160 zdjęć kwalifikuje się. 993 zdjęcia (8 937 plansz) blokuje
wyłącznie klucz obcy
`image_symbol_review_events(previous_source_geometry_revision_id)`: 152 865
zdarzeń weryfikacji symboli (`system:image-pipeline`, 10 191 elementów review
importu `f4ef3449`) wskazuje rewizje geometrii źródła tych zdjęć. Pozostałe
167 ma dodatkowo pracę człowieka (161 zdjęć z rewizjami geometrii plansz
`reviewer-operator`) albo żywe dane (6 zdjęć z 51 żywymi planszami).

## 3. Kompaktowanie `docker_data.vhdx`

Plik VHDX rośnie, ale sam się nie zmniejsza. Kompaktowanie odzyskuje bloki
zwolnione wewnątrz dysku (np. po `VACUUM FULL`). Efekt trzeba zmierzyć:
porównaj rozmiar pliku przed i po.

`Optimize-VHD` wymaga modułu Hyper-V, którego nie ma w Windows 11 Home
(sprawdzone: `Get-Command Optimize-VHD` nic nie zwraca). Na tym komputerze
używaj `diskpart`.

1. Zatrzymaj API, Admin, Reviewer i workery. Zatrzymaj bazę:

   ```powershell
   docker compose -f infra/docker/compose.yaml stop postgres
   ```

2. Zwolnij bloki wewnątrz dysku gościa (ext4 nie zgłasza ich sam; bez
   tego `diskpart` nie ma czego odzyskać):

   ```powershell
   docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -- fstrim -av
   ```

   Zamknij Docker Desktop (ikona w zasobniku → Quit Docker Desktop), potem
   (uwaga: zatrzymuje wszystkie dystrybucje WSL):

   ```powershell
   wsl --shutdown
   wsl --list --verbose
   ```

   Wszystkie dystrybucje muszą mieć stan `Stopped`.

3. Zapisz rozmiar i utwórz skrypt `diskpart` (np.
   `artifacts\maintenance\compact-vhdx.txt`):

   ```text
   select vdisk file="D:\docker\DockerDesktopWSL\disk\docker_data.vhdx"
   attach vdisk readonly
   compact vdisk
   detach vdisk
   exit
   ```

4. W PowerShell uruchomionym jako administrator:

   ```powershell
   diskpart /s D:\game_predicotr\artifacts\maintenance\compact-vhdx.txt
   ```

5. Uruchom Docker Desktop, potem `npm run db:up` i `npm run db:current`.
   Porównaj rozmiar VHDX i wykonaj zapytanie D z sekcji 1.

Jeżeli kompaktowanie niczego nie odzyskało, bloki nie zostały zwolnione
wewnątrz dysku. Dalsze kroki (np. zrzut i odtworzenie do nowego wolumenu)
wymagają osobnego planu.

## 4. Kopia zapasowa

Kopia CUSTOM z kompresją 1 (ostatnia pełna: 22 GB, ok. 25 min). Użyj
przekierowania `cmd`, bo `>` w PowerShell 5.1 psuje dane binarne. Katalog
docelowy musi mieć ok. 25 GB wolnego miejsca (najlepiej inny dysk niż `C:`):

```powershell
$dump = 'D:\game_predictor_backup\game_predictor-' + (Get-Date -Format 'yyyyMMdd-HHmm') + '.dump'
cmd /c "docker exec game-predictor-postgres-1 pg_dump -U game_predictor -d game_predictor -Fc -Z 1 > `"$dump`""
if ($LASTEXITCODE -ne 0) { throw 'pg_dump nie powiódł się.' }
Get-FileHash $dump -Algorithm SHA256
cmd /c "docker exec -i game-predictor-postgres-1 pg_restore --list < `"$dump`"" | Select-Object -First 12
```

Katalog kopii to `D:\game_predictor_backup`. Stan 2026-10-10: zrzuty
`game_predictor-20261010-0100.dump` i `game_predictor-20261010-1527.dump`
(34,4 GB; SHA-256 i pełny odczyt `pg_restore --file=/dev/null` w
`task0952-20261010-1527.log`), role `globals-20261010-*.sql`, kopia obrazu
dysku sprzed przeniesienia `docker-wsl-20261010\` (SHA-256 w
`b1-vhdx-copy.log`) i raporty stanu baz `db-state-*.txt`. Kopie usuwa się
tylko za osobną zgodą operatora. `pg_restore --list` potwierdza czytelność
spisu archiwum, nie pełne odtworzenie.

## 5. Migracja danych na inny dysk

Przed każdym krokiem: kopia (sekcja 4), zatrzymane API, Admin, Reviewer,
workery i baza (`docker compose -f infra/docker/compose.yaml stop postgres`).
Stare lokalizacje usuwaj dopiero po weryfikacji i osobnej zgodzie.

### 5.1. Dysk Dockera (baza)

Wykonane 2026-10-10 (TASK-0955, D-540): obraz przeniesiony z
`C:\Users\tuszy\AppData\Local\Docker\wsl` do `D:\docker\DockerDesktopWSL`.
Kolejność, która zadziałała i obowiązuje przy kolejnym przeniesieniu:

1. Zatrzymanie producentów zapisów (tunel, Reviewer, Admin, API), potem
   workera; kontrola: brak jobów `created`/`processing`, brak żywych
   dzierżaw (`lease_expires_at > now()`), puste
   `remote_manual_selection_host_actions`, brak klientów w
   `pg_stat_activity`.
2. Raport odniesienia (tylko odczyt) wszystkich baz: rozmiary
   `pg_database_size`, role, rewizja Alembic, liczby tabel `game_data_v2` i
   `public`, joby według statusu, sesje zdalnej selekcji, gry, dokładne
   `count(*)` największych tabel (wzór:
   `D:\game_predictor_backup\db-state-before-move.txt`).
3. Czyste zatrzymanie bazy: `docker stop -t 600 game-predictor-postgres-1`
   (w logu „database system is shut down”), zamknięcie Docker Desktop
   (Quit albo `docker desktop stop`), `wsl --shutdown`, `wsl --list
   --verbose` = wszystkie `Stopped`.
4. Niezależna kopia obrazu: `robocopy <stary katalog>\disk <backup>\disk
   docker_data.vhdx /J` i `Get-FileHash -Algorithm SHA256` źródła i kopii
   (2026-10-10: 158 440 882 176 bajtów; kopie na tym samym NVMe 63 s i
   233 s, każdy hash ok. 145 s; log
   `D:\game_predictor_backup\b1-vhdx-copy.log`).
5. Docker Desktop → Settings → Resources → Advanced → **Disk image
   location** → katalog na docelowym dysku → **Apply & restart** (Docker
   dopisuje `DockerDesktopWSL` i sam kopiuje obraz). Wariant użyty
   2026-10-10, bo agent nie obsługuje UI: przy zatrzymanym Docker Desktop
   kopia `disk\` i `main\` do `D:\docker\DockerDesktopWSL` z równym
   SHA-256, kopia zapasowa `settings-store.json`, ustawienie
   `CustomWslDistroDir` na ten katalog, start Docker Desktop.
6. Start **samej** bazy, bez provisioningu ról:

   ```powershell
   docker compose -f infra/docker/compose.yaml up -d --wait postgres
   docker volume ls
   npm run db:current
   ```

7. Raport jak w kroku 2 i porównanie pole po polu z odniesieniem **przed
   jakimkolwiek zapisem**. Jedyna dopuszczalna różnica to rozmiar pliku
   `pg_internal.init` (160 944 bajtów na bazę), który PostgreSQL usuwa przy
   starcie i odbudowuje przy pierwszym połączeniu: połącz się z bazą i
   zmierz ponownie. Baza oznaczona jako nieprawidłowa (`datconnlimit = -2`,
   pozostałość przerwanego `DROP DATABASE`) nie przyjmuje połączeń i
   zostaje mniejsza o tę wartość.
8. Dopiero po równości: `npm run db:up` (provisioning ról i uprawnień,
   zapisy `ALTER ROLE`), potem start API, Admina, Reviewera i workera.

Stary obraz zostaje nieużywany do osobnej decyzji (TASK-0957). Procedura
awaryjna (powrót do starej lokalizacji, podstawienie kopii, odtworzenie ze
zrzutu) jest w `ai_docs/tasks/completed/0955-disk-d-database-cutover.md`,
„Technical notes”.

### 5.2. Artefakty (`GAME_PREDICTOR_ARTIFACT_ROOT`)

Ścieżki obrazów i manifestów w bazie są względne względem
`GAME_PREDICTOR_ARTIFACT_ROOT` (domyślnie `artifacts` w katalogu, z którego
uruchomiono API/worker). Kopiowanie:

```powershell
robocopy C:\Users\tuszy\Documents\game_predicotr\artifacts D:\game_predictor\artifacts /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /LOG:D:\game_predictor\robocopy-artifacts.log
(Get-ChildItem C:\Users\tuszy\Documents\game_predicotr\artifacts -Recurse -File | Measure-Object Length -Sum).Count
(Get-ChildItem D:\game_predictor\artifacts -Recurse -File | Measure-Object Length -Sum).Count
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_ARTIFACT_ROOT', 'D:\game_predictor\artifacts', 'User')
```

Kod wyjścia `robocopy` 0–7 oznacza sukces. Zmienna użytkownika działa w nowym
terminalu; API i worker czytają ją przez `ApiSettings`. Po uruchomieniu API
sprawdź w Adminie podgląd planszy i crop komórki. Tak samo przenosi się
`GAME_PREDICTOR_IMPORT_ROOT` (domyślnie `imports`), jeśli jest używany.

Przeniesienie całego checkoutu na inny dysk (plan
`delivery/DISK_D_MIGRATION_PLAN_20261009.md`, D-540) wykonuje skrypt
`scripts/sync_data_directories_to_d.ps1` (`npm run data:sync:d -- <parametry>`)
zamiast ręcznego `robocopy`. Zamiast przestawiać zmienne korzeni, uruchamia się
API i worker z nowego katalogu, a skrypt kopiuje wszystkie zachowywane wpisy
ignorowane przez git (`artifacts`, `imports`, `.runtime`, `.tooling`, `.tmp`,
`work`, luźne pliki), pomijając odtwarzalne (`node_modules`, `.venv*`, cache,
`dist`) i oba korzenie worktree'ów:

```powershell
# inwentarz i klasyfikacja wpisów ignorowanych (nic nie kopiuje)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Inventory
# kopia przyrostowa przy działających usługach; błędy plików w użyciu = INCOMPLETE, kod 0
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Initial
# po zatrzymaniu usług: kopia i porównanie manifestów SHA-256; każda różnica = kod 1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Final
# manifesty SHA-256 źródła bez kopiowania (wykrywanie późniejszych zmian na starym dysku)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -ManifestOnly
# później: tylko porównanie celu z zapisanym manifestem (nowe pliki celu ignorowane)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -VerifyOnly -Manifest <katalog przebiegu Final>
```

Logi i manifesty trafiają do `D:\game_predictor_backup\sync-logs\<czas>-<tryb>`,
poza kopiowanym drzewem; ścieżki pod `.tooling` są w manifestach zastąpione
skrótem SHA-256 (klucze podpisu). `-Mirror` usuwa w celu wyłącznie pliki z
zatwierdzonej listy (`-Confirm -MirrorApprovedList`). Po przełączeniu na nowy
dysk nie wolno już synchronizować starego katalogu do aktywnego.

### 5.3. Repozytorium

Wykonane 2026-10-10 (TASK-0954, TASK-0956): `D:\game_predicotr` to osobny
klon (`git clone`, `npm install`, `.venv` z `pip install -e ".[dev]"`),
zachowywane dane ignorowane skopiował `scripts/sync_data_directories_to_d.ps1`
(manifest `Final` z B1 w `D:\game_predictor_backup\sync-logs\20261010-163332-Final`
i `20261010-175735-Final`), zmienne użytkownika przepisał `npm run
windows:environment:setup` uruchomiony z D. Kompletność odwołań bazy do plików
sprawdza (tylko odczyt):

```powershell
.\.venv\Scripts\python.exe scripts/verify_artifact_references.py --output <raport.json>
```

Po przeniesieniu samego katalogu repozytorium (zamiast klonu):

```powershell
git worktree repair
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm run windows:environment:setup
npm run windows:environment:check
```

`git worktree repair` naprawia bezwzględne ścieżki worktree, `.venv` ma
bezwzględne ścieżki i trzeba go odtworzyć, a zmienne użytkownika
`GAME_PREDICTOR_NODE_HOME` i `GAME_PREDICTOR_GRADLE_USER_HOME` wskazują
`.tooling` w starej lokalizacji.
