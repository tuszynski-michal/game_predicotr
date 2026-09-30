---
title: Utrzymanie bazy danych — VACUUM, kompaktacja pipeline, VHDX i migracja dysku
status: active
last_updated: 2026-09-30
---

# Runbook: utrzymanie bazy danych

Dotyczy lokalnego PostgreSQL 18 w kontenerze Docker Desktop
`game-predictor-postgres-1` (baza i rola `game_predictor`, wolumen
`game-predictor_game_predictor_postgres_data`), którego dane leżą w pliku
`C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx`. Źródła:
D-467 (plan `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`,
S3), TASK-0756.

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
  `C:\Users\tuszy\Documents\game_predicotr` w PowerShell. Pliki SQL zapisuj
  wyłącznie znakami ASCII: PowerShell 5.1 przekazuje potok do `docker exec`
  w kodowaniu ASCII.
- `df` wewnątrz kontenera pokazuje rozmiar wirtualnego dysku (ok. 1 TB), nie
  realne wolne miejsce. Miarodajne jest wolne miejsce dysku Windows, na którym
  leży `docker_data.vhdx`:

```powershell
Get-PSDrive C | Select-Object Name, @{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}
Get-Item C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx |
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
   select vdisk file="C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
   attach vdisk readonly
   compact vdisk
   detach vdisk
   exit
   ```

4. W PowerShell uruchomionym jako administrator:

   ```powershell
   diskpart /s C:\Users\tuszy\Documents\game_predicotr\artifacts\maintenance\compact-vhdx.txt
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

Ścieżkę `D:\game_predictor_backup` zastąp istniejącym katalogiem.
`pg_restore --list` potwierdza czytelność spisu archiwum, nie pełne
odtworzenie.

## 5. Migracja danych na inny dysk

Przed każdym krokiem: kopia (sekcja 4), zatrzymane API, Admin, Reviewer,
workery i baza (`docker compose -f infra/docker/compose.yaml stop postgres`).
Stare lokalizacje usuwaj dopiero po weryfikacji i osobnej zgodzie.

### 5.1. Dysk Dockera (baza)

Docker Desktop → Settings → Resources → Advanced → **Disk image location** →
wybierz katalog na docelowym dysku → **Apply & restart**. Docker Desktop
przenosi `docker_data.vhdx` razem z wolumenem bazy. Po restarcie:

```powershell
docker volume ls
npm run db:up
npm run db:current
```

Wolumen `game-predictor_game_predictor_postgres_data` musi istnieć, Alembic
musi pokazywać bieżącą rewizję, a raport z sekcji 1 — te same rozmiary.

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

### 5.3. Repozytorium

Po przeniesieniu katalogu repozytorium:

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
