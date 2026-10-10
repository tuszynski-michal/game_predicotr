---
title: TASK-0955 — Przeniesienie obrazu dysku Dockera z bazą na D
status: todo
last_updated: 2026-10-09
---

# TASK-0955 — Przeniesienie obrazu dysku Dockera z bazą na D

## Status

`todo`

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

- [ ] Kroki 1–3: trzy kontrole jobów zapisane; przed `workers:stop` brak
      `processing` i `created`; po `workers:stop` brak `processing` z
      żywą dzierżawą (przypadek wyścigu rozliczony jak w kroku 3),
      `host_actions` puste, brak procesów z C.
- [ ] Krok 4: `Final` kod 0, manifesty równe.
- [ ] Krok 7: SHA-256 źródła = SHA-256 kopii; rozmiar i czas kopii w
      `Outcome`.
- [ ] Krok 9: `docker volume ls` zawiera wolumen; `db:current` = `0153`;
      raport po przeniesieniu równy raportowi odniesienia dla wszystkich
      baz; vhdx na D; ustawienie Docker Desktop na D.
- [ ] Stan trwały na granicy etapu zapisany: usługi zatrzymane, Docker
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

Wypełnia agent po pracy.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- TASK-0956
