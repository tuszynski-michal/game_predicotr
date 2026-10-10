---
title: TASK-0952 — Kopia zapasowa bazy na D przed przeniesieniem
status: done
last_updated: 2026-10-10
---

# TASK-0952 — Kopia zapasowa bazy na D przed przeniesieniem

## Status

`done`

## Goal

Na D istnieje zrzut `pg_dump -Fc` bazy `game_predictor` zakończony kodem 0,
zrzut ról `pg_dumpall --globals-only`, zapisany SHA-256 i pełny wynik
`pg_restore --list` (kod 0), a raport stanu bazy z etapu A jest zapisany
jako wczesny punkt odniesienia.

## Context

Etap A1 planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`, decyzja
2(a). Podstawą odzyskania po nieudanym przeniesieniu jest kopia pliku
vhdx wykonana w B1 (TASK-0955); zrzut z tego taska jest zabezpieczeniem
dodatkowym (odzyskanie logiczne, odchudzenie) i powstaje przy działającym
imporcie, więc nie odzwierciedla stanu z chwili przełączenia. Procedura
zrzutu: `ai_docs/guides/DATABASE_MAINTENANCE.md`, sekcja 4.

## Dependencies / entry conditions

- Fakt: kontener `game-predictor-postgres-1` działa; baza 85 GB na
  `0153_merge_compact_super_games`; ostatnia pełna kopia miała 22 GB,
  ok. 25 min.
- Założenie do potwierdzenia przez operatora: katalog docelowy
  `D:\game_predictor_backup` i zgoda na czas trwania (zrzut w tle, limit
  90 min).
- Wolne miejsce na D ≥ 60 GB (skrypt sprawdza przed startem).

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium`. Komendy z runbooka, kontrola kodów
wyjścia. Eskalacja do `claude-opus-5-5`, `high`, jeśli `pg_dump` lub
`pg_restore --list` kończy się kodem ≠ 0.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcje 1 i 4)

## Scope

- Utworzyć katalog docelowy na D (jeśli nie istnieje).
- `pg_dumpall --globals-only` do pliku `.sql` (role i uprawnienia globalne).
- `pg_dump -Fc -Z 1` przez `docker exec` z przekierowaniem `cmd /c`
  (PowerShell 5.1 psuje strumień binarny przy `>`); zapisać kod wyjścia
  `cmd` (`$LASTEXITCODE`), czas trwania i rozmiar pliku.
- `pg_restore --list` do pliku `.toc.txt` z kodem wyjścia; zapisać liczbę
  wpisów; SHA-256 obu zrzutów.
- Pełny odczyt archiwum: `pg_restore --file=/dev/null` wewnątrz kontenera
  (stdin, bez `-j`), kod wyjścia 0 wymagany; to jedyny dowód, że wszystkie
  bloki danych archiwum są czytelne (`--list` czyta tylko spis). Czas
  zapisać; uruchamiać w tle z limitem 120 min.
- Raport stanu bazy `artifacts/maintenance/disk-d-migration/db-state-stage-a.md`
  (katalog ignorowany): `pg_database_size` wszystkich baz, rewizja Alembic,
  liczba tabel w `game_data_v2` i `public`, `count(*)` z `public.jobs`
  i rozkład statusów, liczba sesji zdalnej selekcji. Raport służy jako
  wczesne odniesienie; raport właściwy dla porównania po przeniesieniu
  powstaje w TASK-0955 po zatrzymaniu zapisów.

## Out of scope

- Odtworzenie próbne zrzutu (osobna decyzja operatora: ok. 85 GB i
  godziny). Usuwanie starszych kopii. Zmiany w bazie.

## Acceptance criteria

- [ ] Pliki `game_predictor-YYYYMMDD-HHMM.dump`, `globals-YYYYMMDD-HHMM.sql`
      i `game_predictor-YYYYMMDD-HHMM.toc.txt` istnieją na D; rozmiary,
      SHA-256 i kody wyjścia (`pg_dump` 0, `pg_restore --list` 0,
      `pg_dumpall` 0) zapisane w `Outcome`.
- [ ] `toc.txt` zawiera wpisy `TABLE DATA` dla schematów `public` i
      `game_data_v2`; liczba wpisów zapisana.
- [ ] `pg_restore --file=/dev/null` na całym archiwum zakończony kodem 0;
      czas w `Outcome`.
- [ ] Raport stanu zapisany; wartości zgodne z inwestygacją z planu
      (85 GB, `0153`, 272/59 tabel, ≥ 828 jobów) albo odchylenie wyjaśnione.
- [ ] `Outcome` zawiera czas trwania zrzutu i wolne miejsce na D po zrzucie.

## Technical notes

`pg_dump` działa równolegle z jobem importu; zrzut jest spójną migawką
transakcyjną. Nie uruchamiać `VACUUM FULL` ani kompaktowania. Sam SHA-256
identyfikuje plik, nie dowodzi kompletności: dowodem jest kod 0 `pg_dump`,
kod 0 `pg_restore --list` oraz kod 0 pełnego odczytu
`pg_restore --file=/dev/null`. Odtworzenie próbne do osobnej bazy pozostaje
poza zakresem, bo podstawą odzyskania jest kopia vhdx (TASK-0955). Jeżeli
`cmd /c` zwróci kod ≠ 0, plik usunąć i powtórzyć do nowej nazwy.

## Expected files

- Nowy (ignorowany): `artifacts/maintenance/disk-d-migration/db-state-stage-a.md`.
- Istniejące: ten plik (`Outcome`), `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Przerwany `docker exec` → kod ≠ 0, `pg_restore --list` błąd → task
  niezaliczony, powtórzyć zrzut do nowego pliku.

## Verification

```powershell
# katalog repozytorium; pg_dump w tle, limit 90 min; pozostałe ≤ 120 s
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$dir = 'D:\game_predictor_backup'
cmd /c "docker exec game-predictor-postgres-1 pg_dumpall -U game_predictor --globals-only > `"$dir\globals-$stamp.sql`""; $LASTEXITCODE
cmd /c "docker exec game-predictor-postgres-1 pg_dump -U game_predictor -d game_predictor -Fc -Z 1 > `"$dir\game_predictor-$stamp.dump`""; $LASTEXITCODE
cmd /c "docker exec -i game-predictor-postgres-1 pg_restore --list < `"$dir\game_predictor-$stamp.dump`" > `"$dir\game_predictor-$stamp.toc.txt`""; $LASTEXITCODE
cmd /c "docker exec -i game-predictor-postgres-1 pg_restore --file=/dev/null < `"$dir\game_predictor-$stamp.dump`""; $LASTEXITCODE
Get-FileHash "$dir\game_predictor-$stamp.dump", "$dir\globals-$stamp.sql" -Algorithm SHA256
(Get-Content "$dir\game_predictor-$stamp.toc.txt" | Select-String 'TABLE DATA').Count
```

## Risks / open questions

- Katalog docelowy na D do potwierdzenia przez operatora.
- Zrzut 85 GB bazy może trwać dłużej niż 25 min; limit 90 min, raport czasu.

## Outcome

Executed 2026-10-10 01:00–01:43 local time by Claude Code (`claude-opus-5-5`,
model switched by the operator; the plan table assigns `claude-sonnet-5-5`
medium, so this is a recorded deviation to a stronger model). The dump ran
while the Mumie `validate` job was processing, as the task allows.

### Changed

- New directory `D:\game_predictor_backup` (outside the repository) with:
  - `game_predictor-20261010-0100.dump`: 33 815 750 791 bytes,
    SHA-256 `94E5DB9B064CF80B96F72426B58357472C327B42F8A40BA9438DB478B73D6053`;
  - `globals-20261010-0100.sql`: 4 743 bytes, 26 `CREATE/ALTER ROLE` lines,
    SHA-256 `6629ED0E66258EE4F62EF959BBC3CDE12F55EA215988F934A852E3EF02DB5C4C`;
  - `game_predictor-20261010-0100.toc.txt`: 481 073 bytes (archive list);
  - `task0952-20261010-0100.log`: 797 bytes (exit codes, durations, hashes).
- Stage-A database report: `artifacts/maintenance/disk-d-migration/db-state-stage-a.md`
  (ignored directory of the plan worktree, as the task requires).
- No change to the database, services or repository code.

### Verification results

- `pg_dumpall --globals-only`: exit 0.
- `pg_dump -Fc -Z 1`: exit 0, 1 594 s (26.5 min).
- `pg_restore --list`: exit 0, 4 727 entries, 263 `TABLE DATA` entries
  counted with `^\d+; \d+ \d+ TABLE DATA ` (59 in `public`, 204 in
  `game_data_v2`; partitioned parents carry no data). The first log line said
  264 because the plain substring also matched an ACL on `dataset_versions`.
- `pg_restore --file=/dev/null` (full read of every data block): exit 0, 943 s.
- Free space on D: 1 834.2 GB before, 1 802.7 GB after.
- `docs:check` (both scripts, run with the main checkout's `.venv` because
  the worktree has none): `check_decision_links: OK (537 …)`,
  `check_current_state_window: OK (44 active tasks, 10 done sections)`.
- Codex audit round 1 (gpt-6.1-sol, medium): REVISE, documentation only
  (toc size, report location, docs:check evidence, TABLE DATA count);
  report `ai_docs/quality/TASK-0952_AUDIT_gpt-6.1-sol.md`. All fixed here.
- Stage-A report: `game_predictor` 88 GB, Alembic
  `0153_merge_compact_super_games`, 272 tables in `game_data_v2`, 59 in
  `public`, 839 jobs (770 completed, 51 waiting_for_review, 10 failed,
  5 cancelled, 2 created, 1 processing), 13 remote selection sessions,
  `mumie_0884_restore_20261006_155101_test` 44 GB, `game_predictor_v7_pilot`
  188 MB and 19 small test databases. The database grew from 85 GB
  (2026-10-09) to 88 GB because of the running Mumie pipelines.

### Not completed

- Trial restore into a separate database: out of scope by design (the B1
  disk-image copy is the recovery basis).

### Documentation updates

- This Outcome and `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- TASK-0953 (first `Initial` copy is already running).
