---
title: TASK-0952 — Kopia zapasowa bazy na D przed przeniesieniem
status: todo
last_updated: 2026-10-09
---

# TASK-0952 — Kopia zapasowa bazy na D przed przeniesieniem

## Status

`todo`

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

- TASK-0953
