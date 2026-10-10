---
title: TASK-0957 — Sprzątanie po przeniesieniu i rozliczenie zależności od C
status: todo
last_updated: 2026-10-10
---

# TASK-0957 — Sprzątanie po przeniesieniu i rozliczenie zależności od C

## Status

`todo`

## Goal

Po odbiorze pracy z D: wszystkie operacyjne odwołania do C (joby,
bindingi zdalnej selekcji) są rozliczone, a za osobnymi zgodami wykonane są
usunięcie baz testowych, kompaktowanie vhdx oraz usunięcie starego
katalogu i starego vhdx na C, poprzedzone kontrolowanym odcięciem C.

## Context

Etap C planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`, decyzje
8 i 11. Każda operacja jest destrukcyjna lub zmienia dane operatora:
podgląd → jawna zgoda na tę jedną operację → wykonanie → raport.
Implementacja podglądu nie jest zgodą na wykonanie.

## Dependencies / entry conditions

- TASK-0956 `done`, odbiór powtórzony po restarcie Windows, co najmniej
  jeden pełny dzień pracy z D bez incydentu.
- Fakt: 173 jobów ma `source_directory` pod C; `requeue_job` dopuszcza
  ponowienie `waiting_for_review`, `failed` i `cancelled`, więc ponawialne
  są 49 + 8 + 5 (+ ewentualne `created`), historyczne 110 `completed`.
- Fakt: 13 bindingów zdalnej selekcji z `host_base_path` pod C (4 active);
  `host_actions` i `batches` puste w chwili inwestygacji; inwentaryzacja
  danych bindingów z TASK-0956.
- Fakt: w vhdx są `mumie_0884_restore_20261006_155101_test` (44 GB),
  `game_predictor_v7_pilot` (188 MB) i 14 baz testowych.
- Zasada: po przełączeniu nie synchronizować C→D do aktywnych katalogów
  (D ma już nowsze pliki); porównania tylko względem manifestu `Final` z B1.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Operacje destrukcyjne z podglądem, SQL
na danych operatora, blokady wierszy. Eskalacja do `claude-fable-5-1`,
`high`, gdy podgląd pokaże checkpointy z innymi ścieżkami bezwzględnymi
albo bindingi z danymi wymagającymi przeniesienia.

## Relevant docs

- `AGENTS.md` („Operacje destrukcyjne”)
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcje 1, 2, 3)

## Scope

Podzadania w tej kolejności; 4 i 5 są zablokowane do czasu zamknięcia 1 i 2.

1. **Ścieżki C w jobach.** Skrypt `scripts/preview_job_source_directory_rewrite.py`
   (proponowany; podgląd tylko odczyt): dla każdego joba z
   `input_payload->>'source_directory'` (zdekodowany JSON, nie
   `::text` z escapowanymi backslashami) zaczynającym się od prefiksu C,
   z porównaniem bez rozróżniania wielkości liter i jawnym raportem
   wariantów zapisu: id, status, czy katalog istnieje pod D po zamianie
   prefiksu, czy `checkpoint_payload` i `input_payload` zawierają inne
   ścieżki bezwzględne (dowolny klucz). Wykonanie (`--apply`, osobna
   zgoda): w jednej transakcji, `select … for update`, ponowne
   sprawdzenie statusu pod blokadą, `jsonb_set` prefiksu
   `C:\Users\tuszy\Documents\game_predicotr\imports` →
   `D:\game_predicotr\imports` wyłącznie w `input_payload.source_directory`
   dla jobów `waiting_for_review`, `created`, `failed`, `cancelled`;
   poprzednie wartości do `artifacts/maintenance/disk-d-migration/
   job-source-directory-before.json`. Joby `completed` zostają z
   udokumentowanym uzasadnieniem: wykonawca sprawdza w kodzie
   (`application/image_import*`, `requeue_job`,
   `requeue_job_with_fresh_progress`, raporty importu), czy jakikolwiek
   obsługiwany przepływ czyta `source_directory` joba `completed`; jeśli
   tak, mapowanie obejmuje też `completed`. Decyzja operatora: przepisać
   (zalecane) albo zostawić `imports/` na C jako archiwum; archiwum
   wyklucza usunięcie C w podzadaniu 5 (zamiast tego przeniesienie
   archiwum na D i przepisanie prefiksu na jego nową ścieżkę).
2. **Bindingi zdalnej selekcji.** Na podstawie inwentaryzacji z TASK-0956
   (13 sesji: dane, batche, pliki, transfery, akcje hosta): dla sesji bez
   danych i bez akcji — revoke (jeśli jeszcze active) i zapis; dla sesji z
   danymi — zakończenie operacji z D i weryfikacja zachowanych wyników,
   albo osobny task przeniesienia bindingu z zachowaniem tożsamości i
   markerów własności. Usunięcie C zablokowane, dopóki istnieje binding z
   danymi lub akcjami wskazujący C.
3. **Bazy testowe.** Podgląd: lista baz z rozmiarami i `pg_stat_database`
   (ostatnia aktywność). Wykonanie: `DROP DATABASE` każdej bazy wskazanej
   jawnie przez operatora (nigdy `game_predictor`; `game_predictor_v7_pilot`
   tylko po osobnej decyzji); potem `DROP ROLE` osieroconych
   `game_predictor_app_test_*`; testy integracyjne nie mogą działać
   równolegle.
4. **Kompaktowanie vhdx** według runbooka, sekcja 3 (fstrim,
   `wsl --shutdown`, `diskpart` z nową ścieżką na D); rozmiar przed i po.
5. **Odcięcie i usunięcie C.** Podgląd: ponowna inwentaryzacja
   `scripts/inventory_worktrees.ps1 -CompareWith` z `inventory.json` z A3 (brak
   nowych zmian; nowe zmiany → powrót do TASK-0954), ustawienie Docker
   Desktop wskazuje D, podzadania 1 i 2 zamknięte, kontrola zachowanych
   plików względem manifestu `Final` z B1 (`sync_data_directories_to_d.ps1
   -VerifyOnly -Manifest <B1>`): obejmuje wszystkie zachowywane wpisy z
   inwentarza TASK-0953, w tym `.runtime/` (profile i sesje
   `v7-label-geometry`, `v7-selection`, `v7-model-download`, wyniki
   kontrolera ingress, pliki JSON audytów); wyłączone z bramki są tylko
   pliki stanu procesów usunięte w TASK-0956 (lista z jego `Outcome`:
   `worker-lanes.json`, `remote-reviewer.json`, `local-reviewer.json`,
   `*.pid.json`) i logi `.runtime/*.log` oraz `reviewer-lifecycle-logs/`
   (zastępowane przez nowe procesy); nowe pliki D poza porównaniem; każdy
   inny plik z manifestu B1 brakujący albo o innym hashu musi mieć w
   `Outcome` dowód zastąpienia przez aplikację (np. przepisany manifest
   importu, zaktualizowany profil V7) albo świadomego usunięcia; bez
   dowodu bramka nie przechodzi. Starych plików nie przywracać do
   aktywnego D. Dodatkowo skan treści `.runtime/v7-label-geometry/**`,
   `.runtime/v7-selection/**` i `.runtime/*.json` na D pod kątem prefiksu
   C (lokalne manifesty i sesje poza bazą): każde trafienie rozliczone
   jak ścieżki jobów (przepisanie po podglądzie i zgodzie albo
   udokumentowany brak użycia).
   Odcięcie: zmiana nazwy `C:\Users\tuszy\Documents\game_predicotr` →
   `game_predicotr_old`; rejestracje worktree'ów należą do
   `game_predicotr_old\.git`, więc `git worktree repair <nowe ścieżki>`
   wykonuje się z `game_predicotr_old` (dla worktree'ów, które mają
   dalej istnieć), a worktree'y potrzebne do pracy na D odtwarza się w
   klonie D (`git -C D:\game_predicotr worktree add …` z gałęzi na
   `origin`); powtórzenie odbioru z TASK-0956 z
   `verify_artifact_references.py --forbid-prefix
   C:\Users\tuszy\Documents\game_predicotr` (0 rozwiązań do starego
   katalogu, także w treści manifestów) oraz wznowienie jednego joba
   `waiting_for_review` z przepisaną ścieżką; odbiór musi przejść bez
   dostępu do starej nazwy. Usunięcie (po zgodzie): `git -C
   "C:\Users\tuszy\Documents\game_predicotr_old" worktree remove
   <pełna ścieżka worktree'a>` dla wpisów wskazujących `_old` (przez
   repozytorium będące właścicielem; komendy uruchamiane z D muszą
   podawać pełną ścieżkę), usunięcie katalogu `_old`
   i starego
   `C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx`, jeśli
   istnieje. Kopie w `D:\game_predictor_backup` (zrzut, vhdx, repo)
   zostają do osobnej decyzji.

## Out of scope

- Zmiany schematu, GC obrazów (`storage_gc`), usuwanie gier, usuwanie
  kopii z `D:\game_predictor_backup`.

## Acceptance criteria

- [ ] Każde podzadanie ma w `Outcome` podgląd, cytat zgody operatora i
      wynik; podzadania bez zgody oznaczone „nie wykonano”.
- [ ] Po 1: podgląd zdekodowanych wartości pokazuje 0 jobów ponawialnych
      ze ścieżką C; plik z poprzednimi wartościami istnieje; wznowienie
      jednego joba `waiting_for_review` z D działa.
- [ ] Po 2: lista 13 bindingów ze stanem (revoked bez danych / zakończone /
      osobny task); żaden binding z danymi nie wskazuje C.
- [ ] Po 3: usunięte bazy nie występują w `\l`; `game_predictor` nietknięta
      (rozmiar jak w TASK-0955).
- [ ] Po 4: rozmiar vhdx przed/po w `Outcome`.
- [ ] Po 5: `--forbid-prefix` daje 0 rozwiązań do starego katalogu;
      odbiór po zmianie nazwy katalogu C przeszedł; odstępstwa od
      manifestu B1 udokumentowane; C nie zawiera katalogu repozytorium ani
      starego vhdx; `docker volume ls` i `db:current` z D bez zmian.

## Technical notes

Przepisanie: `update public.jobs set input_payload = jsonb_set(
input_payload::jsonb, '{source_directory}', to_jsonb(<nowa wartość>))
where id = :id and status = :expected_status` po `select … for update`;
`input_payload` jest typu JSON: zachować typ kolumny i pozostałe klucze.
Joby `processing` wykluczyć (dzierżawa). `DROP DATABASE` wymaga braku
połączeń. Kompaktowanie: Windows 11 Home bez `Optimize-VHD`; `diskpart`
jako administrator przy zamkniętym Docker Desktop.

## Expected files

- Nowy: `scripts/preview_job_source_directory_rewrite.py` (podgląd i
  `--apply`), test `services/api/tests/` dla funkcji zamiany prefiksu i
  bramki statusu.
- Istniejące: `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcje 3, 5: nowe
  ścieżki), ten plik, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Job z `source_directory` już pod D → pominięty w podglądzie.
- Job `processing` → wykluczony z `--apply`.
- Prefiks w innej wielkości liter → raportowany jako wariant, przepisany
  tylko po jawnym potwierdzeniu wariantu.
- Status zmieniony między podglądem a `--apply` → wiersz pominięty z
  raportem.
- Nowa zmiana w worktree po A3 → podzadanie 5 zablokowane.

## Verification

```powershell
# D:\game_predicotr; każda komenda ≤ 120 s
.\.venv\Scripts\python.exe scripts/preview_job_source_directory_rewrite.py
# compares HEADs, working-tree digests, preserved-data digests and refs.txt
# with the B1-time inventory; exit 3 = something changed on C after B1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/inventory_worktrees.ps1 -OutputRoot D:\game_predictor_backup\repo-recheck -CreateRefs -CompareWith D:\game_predictor_backup\repo-YYYYMMDD\inventory.json
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database order by 2 desc;"
```

## Risks / open questions

- Decyzja operatora: przepisanie ścieżek (zalecane) czy archiwum na D.
- Usunięcie C jest nieodwracalne; manifest `Final` z B1 i kopie na D są
  jedynym odniesieniem.

## Preview for the operator's consent (2026-10-10, read-only)

Prepared by Claude Code (`claude-opus-5-5`) after TASK-0956; nothing was
deleted, rewritten, dropped or compacted. This is input for the separate
consents of the subtasks below, not a consent. Measured 22:15–22:25 local
time (sizes in bytes, GB = 10^9 bytes).

### What becomes removable on C (after subtasks 1, 2 and the gate of 5)

| Item | Size | Files | State |
|---|---|---|---|
| `C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx` | 158 440 882 176 (158.4 GB) | 1 | not in use since 17:58 (Docker uses `D:\docker\DockerDesktopWSL`); SHA-256 equal to the D copy and the backup at B1 |
| `C:\Users\tuszy\Documents\game_predicotr` (whole checkout incl. `.git`, `worktrees\disk-migration`) | 103 091 163 946 (103.1 GB) | 846 806 | no service runs from it; main checkout clean at `f7048452` before the merge |
| total | about 261.5 GB | | C has 40.1 GB free now, about 300 GB after both |

Largest parts of the checkout: `artifacts` 54.1 GB (409 652 files),
`imports` 32.0 GB (118 530), `node_modules` 3.7 GB, `.venv-vision-lab`
3.3 GB, `apps` 2.9 GB (build output and workspace `node_modules`),
`.pnpm-store` 2.6 GB, `.venv` 1.9 GB, `.tooling` 1.2 GB, `.mypy_cache`
0.25 GB, `services` 0.24 GB, `worktrees` 0.21 GB, `work` 0.19 GB,
`.runtime` 0.19 GB, `.git` 0.10 GB, `.tmp` 0.04 GB. The preserved data
(`artifacts`, `imports`, `.tooling`, `.runtime`, `.tmp`, `work`, loose files)
has SHA-256 equal copies on D from the B1 `Final` run; `.tooling\node\node_modules`
was added to D in TASK-0956.

### What must be kept (or decided separately first)

- `C:\Users\tuszy\AppData\Local\Docker\wsl\main\ext4.vhdx` (100 663 296
  bytes): the Docker Desktop system distribution `docker-desktop` is still
  registered there (`HKCU\…\Lxss` BasePath) and in use. Remove only after
  Docker Desktop re-registers it on D (not needed for data).
- Folders outside the repository that were not copied to D (operator
  decision still open): `C:\Users\tuszy\Documents\game_predictor_vision_data`
  13.3 GB (22 815 files, default Vision Lab `-LabRoot`), `…\mumie` 2.2 GB
  (7 595), `…\new_traning_set` 0.26 GB (994), `…\game_predictor_traning_set`
  0.12 GB (474); together about 15.9 GB.
- Reproducible environments that exist only on C and would have to be
  recreated on D when needed: `.venv-vision-lab` (3.3 GB, Vision Lab
  tools) and `.pnpm-store`.
- Backups on D stay until a separate decision: `D:\game_predictor_backup`
  228.5 GB (vhdx copy 158.5 GB, two dumps 33.8 and 34.4 GB, repository
  backups 1.1 GB, sync logs and manifests 0.7 GB).

### Blockers before deleting C (from the plan, decision 8)

- Subtask 1: 181 jobs have `input_payload.source_directory` under the C
  checkout: 67 retryable (`waiting_for_review` 54, `failed` 8,
  `cancelled` 5, 0 `created`) and 114 `completed`; every one of the 181
  directories also exists under `D:\game_predicotr\imports\…`
  (`verify_artifact_references.py`, TASK-0956). The 53 browser-selection
  retention manifests under `data/originals/manifests/` contain the same C
  source directories (53 entries).
- Subtask 2: 14 remote manual-selection sessions with `host_base_path`
  under C (4 active, 3 of them past `expires_at`; 10 revoked), all with
  0 batches, files, transfers, host actions and operations.
- Subtask 5 gate: `inventory_worktrees.ps1 -CompareWith` against the A′
  inventory (`D:\game_predictor_backup\repo-20261010-a2\inventory.json`),
  `.runtime` against the B1 manifest (exclusion list: the seven
  process-state files in TASK-0956 plus `worker-lanes.json` and
  `remote-reviewer.json`, logs), and the run of
  `verify_artifact_references.py --forbid-prefix C:\Users\tuszy\Documents\game_predicotr`
  after renaming the C checkout. Seven local-only, unmerged C branches
  (TASK-0954 Outcome) exist on D only as `refs/remotes/c/*` and in
  `all-refs.bundle`; decide whether to push them or keep them only there.

### Subtask 3 input (test databases, inside the D disk image)

22 databases besides `game_predictor`, `postgres`, `template0/1`, together
47 664 379 562 bytes (47.7 GB): `mumie_0884_restore_20261006_155101_test`
46 970 946 063; `game_predictor_v7_pilot` 197 138 111 (separate decision);
20 test databases 15.6–44.8 MB each (about 0.5 GB), three of them invalid
(`datconnlimit = -2`: `game_predictor_t5management_af019d99177e_test`,
`game_predictor_task0760_e7d125df587d_test`,
`game_predictor_task0760_4fc4ef7df4ad_test`). Dropping them frees space only
inside the vhdx; the file shrinks only after subtask 4 (compaction).

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

- brak
