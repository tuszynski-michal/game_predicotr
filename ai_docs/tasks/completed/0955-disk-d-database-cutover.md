---
title: TASK-0955 — Przeniesienie obrazu dysku Dockera z bazą na D
status: done
last_updated: 2026-10-10
---

# TASK-0955 — Przeniesienie obrazu dysku Dockera z bazą na D

## Status

`done`

## Goal

`docker_data.vhdx` z wolumenem `game-predictor_game_predictor_postgres_data`
leży na D, niezależna kopia tego pliku z równym SHA-256 leży w
`D:\game_predictor_backup`, kontener startuje z D-owego obrazu, a raport
stanu wszystkich zachowywanych baz po przeniesieniu jest równy raportowi
odniesienia wykonanemu po zatrzymaniu zapisów.

## Context

Etap B1 planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`, decyzje
1, 2(b) i 4. Procedura z `ai_docs/guides/DATABASE_MAINTENANCE.md`, sekcja
5.1. Jedyny etap z przestojem; kopia vhdx i przeniesienie są krokami,
których nie wolno przerywać.

## Dependencies / entry conditions

- TASK-0952 `done`, TASK-0953 z co najmniej jednym przebiegiem `Initial`,
  TASK-0954 `done`; checkout D na commicie ze skryptem synchronizacji
  (sprawdzić `git -C D:\game_predicotr log -1` i obecność skryptu).
- Fakt do sprawdzenia tuż przed startem: job `d9a49da0` w stanie końcowym
  (`completed`/`waiting_for_review`/`failed`).
- Aktualizacja 2026-10-10: start wyłącznie po sygnale operatora, że
  skończyły się wszystkie joby i zmiany równoległych sesji, oraz po etapie
  A′ planu (nowy zrzut bazy, przyrostowa kopia `Initial`, nowa
  inwentaryzacja worktree'ów z `-CreateRefs` i bundle, decyzje o push i
  merge). Sam pusty stan kolejki nie wystarcza.
- Operator przy komputerze: zatrzymuje usługi w swoich terminalach,
  zamyka Docker Desktop i obsługuje jego ustawienia. Agent nie zatrzymuje
  cudzych procesów ani nie steruje UI Docker Desktop.
- Wolne miejsce na D ≥ 300 GB (kopia vhdx 138 GB + przeniesiony vhdx
  138 GB + zapas); zgoda operatora na czas trwania (dwie kopie 138 GB).

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Granica przełączenia, kopia vhdx,
weryfikacja i procedura awaryjna przy ryzyku utraty danych operatora.
Eskalacja do `claude-fable-5-1`, `high`, jeśli po restarcie Docker nie
widzi wolumenu albo raport różni się od odniesienia.

## Relevant docs

- `AGENTS.md` („Kontrola lokalnych usług API i Admin”, „Operacje destrukcyjne”)
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcje 1, 3, 5.1)
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` („Zatrzymywanie usług”)

## Scope

Odpowiedzialności: operator wykonuje wszystko, co zatrzymuje lub uruchamia
procesy, kontenery i Docker Desktop (kroki 2, zatrzymanie workera w 3, 6,
8, start samego PostgreSQL w 9); agent wykonuje kontrole, kopie plików i
raporty (kroki 1, kontrole w 3, 4, 5, 7, odczyty w 9, 10). Każdy krok
kończy się zapisem w `Outcome`.

1. Kontrola wejścia: stan joba `d9a49da0`, brak jobów `processing`
   (`select status, count(*) from public.jobs group by 1`), wolne miejsce,
   HEAD na D.
2. Operator zatrzymuje producentów zapisów: `npm run reviewer:remote:stop`,
   Reviewer (`Ctrl+C`), Admin, API — na C. Od tej chwili nowe joby nie
   powstają.
3. Opróżnienie kolejki i zatrzymanie workera. Warunek: `public.jobs` bez
   `processing` i bez `created` dla lane `general` (job
   `super_game_series_derive` kończy się jeszcze na C, co jest ścieżką
   podstawową i spełnia odbiór B2; jeśli kolejka nie pustoszeje, operator
   decyduje: poczekać albo anulować job w Adminie przed krokiem 2 i
   wznowić go na D; wybór zapisany w `Outcome`). Dopiero wtedy operator:
   `npm run workers:stop` (skrypt kończy proces przez `Kill()`). Po
   zatrzymaniu agent sprawdza ponownie joby, dzierżawy i
   `remote_manual_selection_host_actions` (puste) oraz listę procesów bez
   wpisów z C. Przypadek wyścigu (worker pobrał job między kontrolą a
   `Kill()`, job `processing` z żywą dzierżawą): nie kontynuować B1;
   odczekać do `lease_expires_at` i braku nowego `heartbeat_at`, zapisać
   id joba w `Outcome` (worker na D odzyska go przez `recover_expired_job`
   do `created` z checkpointem; jego `source_directory` wskazuje C, więc
   TASK-0957 rozlicza go jak joby ponawialne), ponownie wykonać kontrolę
   i dopiero wtedy przejść do kroku 4.
4. Agent: `scripts/sync_data_directories_to_d.ps1 -Mode Final` (SHA-256
   obu stron; `-Mirror` tylko po przedstawieniu listy plików istniejących
   wyłącznie na D i zgodzie operatora). Kod 0 wymagany.
5. Agent: raport odniesienia `D:\game_predictor_backup\db-state-before-move.md`:
   dla każdej bazy `pg_database_size`; dla `game_predictor` rewizja
   Alembic, liczba tabel `game_data_v2` i `public`, `count(*)` z
   `public.jobs` z rozkładem statusów, liczba sesji zdalnej selekcji,
   `count(*)` z pięciu największych tabel; dla `game_predictor_v7_pilot`
   rewizja Alembic i liczba tabel; lista ról.
6. Operator (po zgodzie): `docker compose -f infra/docker/compose.yaml stop
   postgres` z C; zamknięcie Docker Desktop (Quit); `wsl --shutdown`;
   `wsl --list --verbose` pokazuje wszystkie dystrybucje `Stopped`
   (agent sprawdza wynik).
7. Agent: kopia vhdx `robocopy C:\Users\tuszy\AppData\Local\Docker\wsl\disk
   D:\game_predictor_backup\docker-wsl-YYYYMMDD docker_data.vhdx /Z /J
   /R:3 /W:5` (wznawialna), potem `Get-FileHash` źródła i kopii; równe
   hashe zapisane w `Outcome`. Komputera nie usypiać.
8. Operator: start Docker Desktop → Settings → Resources → Advanced →
   Disk image location → `D:\docker` (lub wskazany katalog) → Apply &
   restart; czekać na zakończenie; nie restartować komputera.
9. Operator, z `D:\game_predicotr`: `docker compose -f
   infra/docker/compose.yaml up -d --wait postgres` (sam PostgreSQL;
   `npm run db:up` wykonuje dodatkowo provisioning ról, czyli zapisy
   `ALTER ROLE`, więc jest przesunięty do TASK-0956 za bramkę). Agent:
   `docker volume ls`, `npm run db:current` (odczyt), raport stanu jak w
   kroku 5 do `db-state-after-move.md` i porównanie pole po polu
   **przed jakimkolwiek zapisem** (provisioning, producent, worker);
   tylko wtedy równość jest wymagana, później zmiany są oczekiwane; plik
   vhdx na D o rozmiarze zbliżonym do 137,6 GB; ustawienie Docker Desktop
   wskazuje D.
10. Stary plik na C pozostaje do etapu C (jeśli Docker Desktop go nie
    usunął; zanotować, czy istnieje).

## Out of scope

- Uruchamianie API, Admina, Reviewera i workera z D (TASK-0956).
- Usuwanie starego vhdx, baz testowych, kompaktowanie (TASK-0957).

## Acceptance criteria

Bazą odniesienia jest stan po etapie A′ (2026-10-10), nie stan z
inwestygacji 2026-10-09: rewizja `0154_geometry_correction_revert`, 280
tabel `game_data_v2`, 59 tabel `public`, 845 jobów, 14 sesji zdalnej
selekcji. Liczby `0153`/272/13 z planu opisywały stan sprzed migracji
`0154` i nowych importów (aktualizacja kryteriów po audycie, P1-5).

- [x] Kroki 1–3: trzy kontrole jobów zapisane; przed `workers:stop` brak
      `processing` i `created`; po `workers:stop` brak `processing` z
      żywą dzierżawą (przypadek wyścigu rozliczony jak w kroku 3),
      `host_actions` puste, brak procesów z C.
- [x] Krok 4: `Final` kod 0, manifesty równe.
- [x] Krok 7: SHA-256 źródła = SHA-256 kopii; rozmiar i czas kopii w
      `Outcome`.
- [x] Krok 9: `docker volume ls` zawiera wolumen; `db:current` = `0154`
      (baza odniesienia A′); raport po przeniesieniu równy raportowi
      odniesienia dla wszystkich baz (jeden udokumentowany i
      zaakceptowany wyjątek bez różnicy danych, patrz `Outcome`, P0-1);
      vhdx na D; ustawienie Docker Desktop na D.
- [x] Stan trwały na granicy etapu zapisany: usługi zatrzymane, Docker
      wskazuje D, ścieżki kopii i raportów.

## Technical notes

`npm run db:up` z D używa tego samego projektu compose (`name:
game-predictor`) i identycznego hasha konfiguracji, więc nie odtwarza
kontenera; etykiety `config_files`/`working_dir` na kontenerze nadal
wskazują C (metadane, bez wpływu). Nie wymuszać `--force-recreate`.

Procedura awaryjna, w kolejności, tylko przy nieudanym kroku 8 lub
rozbieżnym raporcie w kroku 9:

1. Przywrócić w Docker Desktop starą lokalizację; sprawdzić, czy plik na C
   istnieje i czy `docker volume ls` widzi wolumen; raport jak w kroku 9.
2. Jeśli plik na C jest uszkodzony lub brak: Quit Docker Desktop,
   `wsl --shutdown`, podstawić kopię z `D:\game_predictor_backup\docker-wsl-…`
   pod ścieżkę wskazaną w ustawieniach (C lub D), sprawdzić SHA-256,
   uruchomić Docker Desktop, raport jak w kroku 9.
3. Dopiero gdy obie kopie vhdx zawodzą: nowy pusty obraz, `docker compose
   -f infra/docker/compose.yaml up -d --wait postgres` (sam PostgreSQL:
   pusty wolumen i tylko rola startowa `game_predictor` z compose; nie
   `npm run db:up`, bo jego provisioning utworzyłby `game_predictor_app`
   przed odtworzeniem globals i wywołał drugi duplikat), potem
   `docker run --rm --network game-predictor_default
   -e PGPASSWORD=<hasło z .env.example>
   -v "D:/game_predictor_backup:/backup:ro" postgres:18.4-alpine3.24
   psql -h postgres -U game_predictor -d postgres -v ON_ERROR_STOP=0
   -f /backup/globals-YYYYMMDD-HHMM.sql` (przy `ON_ERROR_STOP=0` kod
   wyjścia nie wystarcza: zapisać pełny stdout/stderr, przejrzeć każdy
   komunikat `ERROR`; dozwolony jest wyłącznie „role … already exists”
   dla roli startowej `game_predictor`; każdy inny błąd zatrzymuje
   procedurę), następnie tym samym wzorcem `docker run … pg_restore -h
   postgres -U game_predictor -d game_predictor -j 4 --exit-on-error
   /backup/game_predictor-YYYYMMDD-HHMM.dump` (plik z montowania, nie
   stdin), kod wyjścia 0 wymagany, dopiero potem `npm run db:up`
   (provisioning na odtworzonych rolach),
   `npm run db:roles:provision`, raport jak w kroku 9 porównany z
   raportem ze stanu A (zrzut jest starszy niż odniesienie: różnice po
   stronie jobów i importu opisać jako utracone). Godziny; zgłosić czas.
   Zrzutu i kopii nie usuwać w trakcie.

## Expected files

- Istniejące: ten plik, `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/guides/DATABASE_MAINTENANCE.md` (5.1: dopisać faktyczny czas,
  lokalizację i krok z kopią vhdx).

## Test cases

- Job `processing` w kroku 1 lub 3 → zatrzymanie, raport do operatora.
- Rozbieżny hash kopii vhdx → powtórzyć kopię; nie przechodzić do kroku 8.
- Po restarcie brak wolumenu → procedura awaryjna, krok 1.
- Raport po przeniesieniu różni się → wstrzymanie TASK-0956, procedura
  awaryjna, analiza.

## Verification

```powershell
# D:\game_predicotr; każda komenda ≤ 120 s, kopia vhdx w tle z limitem 180 min
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "select status, count(*) from public.jobs group by 1; select count(*) from public.remote_manual_selection_host_actions;"
docker volume ls
docker compose -f infra/docker/compose.yaml up -d --wait postgres
npm run db:current
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database order by 2 desc;"
Get-ChildItem D:\docker -Recurse -Filter *.vhdx | Select-Object FullName, @{n='GB';e={[math]::Round($_.Length/1GB,1)}}
```

## Risks / open questions

- Dwie kopie 138 GB wydłużają przestój; alternatywa (tylko kopia Docker
  Desktop) odrzucona przez przegląd Codex jako brak niezależnego
  zabezpieczenia.
- Katalog docelowy (`D:\docker`) do potwierdzenia przez operatora.
- Docker Desktop może usunąć stary plik po udanym przeniesieniu; kopia z
  kroku 7 pokrywa ten przypadek.

## Outcome

Executed 2026-10-10 16:20–18:15 local time by Claude Code
(`claude-opus-5-5`, as assigned). The operator signalled that all jobs had
finished, ran steps 1–2 (tunnel stopped, `workers:stop`) and then
delegated every remaining step to the agent ("resztę wykonuj już sam,
czyli WSL shutdown i reszta"), including Docker Desktop and the disk
location change. Stage A′ preceded B1 (plan section "Aktualizacja
2026-10-10 po etapie A").

### Changed

- Stage A′: new dump `D:\game_predictor_backup\game_predictor-20261010-1527.dump`
  (34 387 279 308 bytes, SHA-256 `25EECFEC…`, all exit codes 0, full
  `pg_restore --file=/dev/null` read 1 044 s); Initial copy (2 672 new
  files in `artifacts/data`); worktree inventory, bundle and `-VerifyClone`
  in `D:\game_predictor_backup\repo-20261010-a2` (`RESULT: OK`, 16 branches
  of C on D, 0 mismatches); D checkout fast-forwarded to `3fb9a0a5`
  (v1.7.310, migrations head `0154`, same as the database; no dependency
  file changes).
- Step 2–3 deviation: after the operator's steps the API (8000), Admin
  (3000), Reviewer (3001) and a worker started with `npm run worker:poll`
  (not managed by `workers:stop`) were still running on C. With the queue
  empty and no live lease the agent stopped them (`taskkill /T`), Reviewer,
  Admin and API first, the worker last; afterwards no app process, no
  listener on 8000/3000/3001 and 0 database clients.
- Step 4: `-Mode Final` over all 102 entries (83 min; 101 equal SHA-256
  manifests, run `sync-logs\20261010-163332-Final`); the only difference was
  two process-state files on D (`.runtime/remote-reviewer.json`,
  `.runtime/worker-lanes.json`) that stopping the tunnel and workers had
  removed on C; they were deleted on D with `-Mirror -Confirm
  -MirrorApprovedList` and `.runtime` re-verified equal (run
  `sync-logs\20261010-175735-Final`). These two runs are the B1 manifest.
- Step 5: reference report `D:\game_predictor_backup\db-state-before-move.txt`
  (script in the session scratchpad, read-only).
- Step 6: `docker stop -t 600` (clean shutdown checkpoint, "database system
  is shut down", exit 0), `docker desktop stop`, `wsl --shutdown`; all WSL
  distributions stopped; `docker_data.vhdx` not locked.
- Step 7: `docker_data.vhdx` (158 440 882 176 bytes) and `main\ext4.vhdx`
  copied with `robocopy /J` to `D:\game_predictor_backup\docker-wsl-20261010`
  and to `D:\docker\DockerDesktopWSL`; SHA-256 of source, backup and target
  equal. Log `D:\game_predictor_backup\b1-vhdx-copy.log` (17:59–18:11):
  - `docker_data.vhdx`: copy to the backup 63 s, copy to
    `D:\docker\DockerDesktopWSL\disk` 233 s (robocopy exit 1 = copied);
    SHA-256 of all three files
    `23E3543C24B6755CAB26FC5AEA3A065406A7F8606CCE9DB18DAAD52C927C354E`,
    158 440 882 176 bytes each (hashing 161 s, 144 s, 143 s);
  - `main\ext4.vhdx`: copies 0 s and 1 s, SHA-256 of all three files
    `77A797DF9FF415667E04F396592E5B1B8D019D67BA469EB881D8BEA76C247932`,
    100 663 296 bytes each;
  - `RESULT data_equal=True main_equal=True`.
- Step 8 deviation: Docker Desktop 4.90 has no CLI for the disk location,
  and the agent cannot click the UI. The UI field "Disk image location"
  (`vm.resources.wslDataFolder`, appends `DockerDesktopWSL`) is stored as
  `CustomWslDistroDir` in `%APPDATA%\Docker\settings-store.json` (both names
  confirmed in the installed binaries). With Docker stopped the agent backed
  up the settings file (`D:\game_predictor_backup\docker-settings-store.before-b1.json`
  and `settings-store.json.before-disk-d`), set `CustomWslDistroDir` to
  `D:\docker\DockerDesktopWSL` (same `disk\`/`main\` layout as the default
  `%LOCALAPPDATA%\Docker\wsl`) with the pre-copied disk in place, and
  started Docker Desktop. Docker kept the setting; the D data disk is in
  use and the C file is not. The small system distribution
  `docker-desktop` (`main\ext4.vhdx`, 100 MB, no data) is still registered
  at `%LOCALAPPDATA%\Docker\wsl\main`.
- Step 9: PostgreSQL started from `D:\game_predicotr` with `docker compose
  … up -d --wait postgres` only (no provisioning).

### Verification results

- `docker volume ls`: `game-predictor_game_predictor_postgres_data`;
  container healthy; `alembic current` from the D `.venv`:
  `0154_geometry_correction_revert (head)`.
- Report after the move (`db-state-after-move-2.txt`) equals the reference
  report except one byte count: `game_predictor` 96 259 511 999 bytes in
  both, 280/59 tables, 845 jobs with the same statuses, 14 remote sessions,
  games, roles and exact row counts of the 8 largest tables identical. Three
  small databases first differed by exactly 160 944 bytes each, the size of
  `pg_internal.init`, which PostgreSQL removes at restart and rebuilds on
  first connection; after connecting, two match exactly; the third
  (`game_predictor_task0760_e7d125df587d_test`) is marked invalid
  (`datconnlimit = -2`, a leftover of an interrupted test `DROP`, as are two
  other test databases) and cannot be connected, so its init file stays
  absent. No data difference.
- Recovery assets kept: the original disk on C (not in use), the SHA-256
  verified copy on D, both dumps and both settings backups.

### Audit resolution (Codex round 1, 2026-10-10 evening)

Codex audit `ai_docs/quality/TASK-0955_AUDIT_gpt-6.1-sol.md` (gpt-6.1-sol,
high): `REVISE`, one P0, five P1, one P2. Fixes are documentation only, done
2026-10-10 about 21:45–22:30 by Claude Code (`claude-opus-5-5`) on the lead's
instruction. Second audit round: Codex audit unavailable (quota limit), to be
run later ("audyt Codex niedostępny (limit), do wykonania później").

- **P0-1 (report equality, one test database).** Accepted exception,
  recorded on the lead's explicit acceptance; the operator ordered the
  migration finished ("close this topic to the end"). The only difference
  between `db-state-before-move.txt` and `db-state-after-move-2.txt` (both in
  `D:\game_predictor_backup`) is line 20: `game_predictor_task0760_e7d125df587d_test`
  26 531 519 → 26 370 575 bytes, a difference of exactly 160 944 bytes. That
  is the size of `pg_internal.init` (relation cache file that PostgreSQL
  deletes at startup and rebuilds on the first connection). Evidence: in the
  first after-move report (`db-state-after-move.txt`) three databases were
  smaller by exactly 160 944 bytes (`game_predictor_task0760_4c4e1a3f5239_test`,
  `game_predictor_task0760_e7d125df587d_test`, `template1`); after one
  connection the first and `template1` returned to their exact reference size
  (`db-state-after-move-2.txt`). Independently, `game_predictor_v7_pilot`
  measured now, after this evening's first connection to it, is 197 138 111
  bytes = its reference size 196 977 167 + 160 944 (cache file created by
  that connection). The test database is invalid (`datconnlimit = -2`, a
  leftover of an interrupted test `DROP DATABASE`) and refuses connections,
  so its cache file cannot be rebuilt. This is not a data difference. The
  database is not repaired, dropped or restored to equalize the size; it is a
  TASK-0957 drop candidate.
- **P1-1 (D checkout lacks the scripts).** Resolved by the merge of
  `feat/disk-d-migration-plan` into `v1.1-vision-lab-hybrid-geometry` and the
  fast-forward of `D:\game_predicotr` (TASK-0956 / merge commit): D then has
  `scripts/sync_data_directories_to_d.ps1`, `scripts/inventory_worktrees.ps1`,
  the `data:sync:d` npm entry and this plan. TASK-0954 is closed in the same
  series.
- **P1-2 (job, lease and host action checks).** Evidence from the B1 session
  transcript (`~\.claude\projects\C--Users-tuszy-Documents-game-predicotr\0a0c6dac-…jsonl`,
  tool outputs with timestamps) and the reference report; local time
  (UTC+2):
  - 16:30:42, before stopping anything (after the A′ inventory):
    `select count(*) from public.jobs where status in ('created','processing')`
    = 0;
  - 16:32:55, services still running (API, Admin, Reviewer, `worker:poll`):
    no `created`/`processing` rows, `leases_alive=0` (`lease_expires_at >
    now()`), `host_actions=0` (`remote_manual_selection_host_actions`), five
    idle `game_predictor_app` connections;
  - 16:33:21, after stopping Reviewer, Admin, API and then the worker:
    `created_processing=0`, `leases_alive=0`, no app process, no listener
    on 8000/3000/3001, `db_clients=0`;
  - 17:57, reference report `db-state-before-move.txt`: jobs
    `cancelled 6, completed 775, failed 10, waiting_for_review 54` (845, no
    `created`/`processing`).
  - Job `d9a49da0-94bd-451d-93d1-ce04c8130158` (import): final state
    `waiting_for_review`, 5 784/5 784, last update 2026-10-09 20:03:13 local,
    no lease (read now; the row has not changed since, so it was final before
    B1). The newest `super_game_series_derive` job
    (`bb87976c-7c17-45ca-9695-19de449f65b6`) finished `completed` at
    2026-10-10 15:25:57 local, before B1 (primary path: finished on C).
  - No evidence exists in `D:\game_predictor_backup` itself for the three
    checks (only the 17:57 report); there is no separate check of
    `host_actions` after the worker stop (the last one is 16:32:55, 26 s
    before the stop). Read now (21:47): `host_actions` 0,
    `remote_manual_selection_batches` 0, jobs unchanged (845, same
    statuses), so no host action appeared in between.
  - The race case of step 3 did not occur (no live lease at 16:32:55 or
    16:33:21).
- **P1-3 (pilot database).** No pre-move measurement of the alembic revision
  and table count of `game_predictor_v7_pilot` exists; both reports hold only
  its size and role. Measured now, read-only (21:47): alembic
  `0146_v7_operator_sources`, 64 tables in `game_data_v2`, 48 in `public`,
  197 138 111 bytes. Its size before and after the move was equal
  (196 977 167 bytes in both reports; the later +160 944 bytes is the
  cache file created by the measuring connection, see P0-1).
- **P1-4 (`DATABASE_MAINTENANCE.md`).** Updated: the Docker disk image lives
  in `D:\docker\DockerDesktopWSL` (`CustomWslDistroDir`), backups in
  `D:\game_predictor_backup`, section 5.1 describes the real procedure with
  the vhdx copy, its duration and the corrected start order (PostgreSQL only
  with `docker compose … up -d --wait postgres`, compare the reports, only
  then `npm run db:up`). `npm run docs:check` (both scripts): OK.
- **P1-5 (criteria and state).** Acceptance criteria now name the A′
  baseline (`0154`, 280/59 tables, 845 jobs, 14 sessions);
  `CURRENT_STATE.md` no longer says B1 waits for a signal; the plan's
  acceptance section points at the A′ baseline. No downgrade.
- **P2-1.** Full SHA-256 values, copy times and the log path are in step 7
  above.

### Not completed

- Re-registration of the 100 MB `docker-desktop` system distribution on D
  (not needed for data; can be done through the Docker Desktop UI later).
- Removing the old disk image on C: stage C, separate consent.

### Documentation updates

- This Outcome, `ai_docs/process/CURRENT_STATE.md`.
- After the audit: `ai_docs/guides/DATABASE_MAINTENANCE.md` (disk image on
  D, backups, section 5.1 with the real procedure and start order), the
  acceptance criteria above and the plan's acceptance section (A′
  baseline).

### Commits

- v1.7.307 `4b96372c938a61f82c97a6398d13e0d63f787fb2` (close the task and
  resolve the Codex audit).

### Recommended next task

- TASK-0956
