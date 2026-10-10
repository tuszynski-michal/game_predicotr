---
title: TASK-0956 — Pierwsze uruchomienie aplikacji z D i odbiór
status: blocked
last_updated: 2026-10-10
---

# TASK-0956 — Pierwsze uruchomienie aplikacji z D i odbiór

## Status

`blocked` (every agent-doable criterion passed; remaining: Windows
restart, phone and tunnel check, removal of the C entries from the user
`Path`, Mumie symbol-review backfill restart; see Outcome)

## Goal

API, Admin, Reviewer (produkcyjny), worker `general` i Quick Tunnel działają
wyłącznie z `D:\game_predicotr`; skrypt weryfikacji odwołań do plików
zgłasza 0 brakujących plików; odbiór z sekcji „Odbiór całego przepływu”
planu przechodzi także po restarcie Windows; przewodniki wskazują D.

## Context

Etap B2 planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`,
decyzje 9 i 10. Konfiguracja czyta korzenie danych względem katalogu
uruchomienia, więc start z D wystarcza, pod warunkiem skopiowanych
katalogów (TASK-0953, tryb `Final` w B1) i bazy na D (TASK-0955). Zmienne
użytkownika HKCU wskazują `.tooling` na C.

## Dependencies / entry conditions

- TASK-0955 `done`. Procesy z C zatrzymane; Docker Desktop wskazuje D.
- Fakt: `.runtime/` skopiowany z C zawiera nieaktualne
  `worker-lanes.json`, `remote-reviewer.json` i `*.pid.json`.
- Fakt: skrypt środowiska dodaje wpisy `Path` dla D przed istniejącymi i
  nie usuwa wpisów C; `GRADLE_USER_HOME` zostaje `C:\gpg`, jeśli istnieje.
- Operator uruchamia usługi w swoich terminalach (`AGENTS.md`); agent
  podaje komendy i weryfikuje.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Pierwszy start w nowej lokalizacji,
zmienne środowiskowe, nowy skrypt weryfikacji odwołań, odbiór po
restarcie i aktualizacja przewodników. Eskalacja do `claude-fable-5-1`,
`high`, jeśli weryfikacja odwołań zgłasza brakujące pliki mimo równych
manifestów z B1.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` („Najkrótsza procedura na
  kolejny dzień pracy”, „Uruchomienie aplikacji Reviewer”, „Udostępnienie
  wyszukiwarki plansz online”, „Zdalna ręczna selekcja”)
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (5.2, 5.3)
- `ai_docs/architecture/DATA_MODEL.md` (kolumny ścieżek)

## Scope

0. Aktualizacja 2026-10-10 (sekcja „Aktualizacja 2026-10-10 po etapie A”
   planu): odtworzenie na D tylko worktree'ów wskazanych przez operatora
   (`git worktree add` z `refs/remotes/c/<gałąź>`, patch staged z
   `--index`, patch unstaged, kopia `untracked\` i `ignored\` z backupu,
   kontrola statusu i skrótu treści jak `-VerifyClone`); odbiór obejmuje
   każdą komendę dziennej procedury uruchomioną z `D:\game_predicotr`
   (`db:up`, `db:migrate`, `db:current`, `api:dev`, `admin:dev`,
   `reviewer:dev` albo `reviewer:build` + `reviewer:start`,
   `workers:start`/`workers:status`, `worker:poll`, `reviewer:remote:start`,
   `windows:environment:check`) oraz po restarcie Windows `db:up`,
   `api:dev`, `workers:start`; operator decyduje o kopii pamięci Claude Code
   do katalogu projektu D i o katalogach spoza repozytorium.
1. Z D: `npm run windows:environment:setup`, potem w nowym terminalu
   `npm run windows:environment:check`; zmienne HKCU wskazują
   `D:\game_predicotr\.tooling\…`. Po odbiorze (krok 8) usunąć z `Path`
   użytkownika wyłącznie wpisy `C:\Users\tuszy\Documents\game_predicotr\…`
   (zapisać przed/po w `Outcome`); `C:\gpg` zostaje, jeśli operator go
   używa.
2. `.runtime/` na D: usunąć wyłącznie pliki stanu procesów skopiowane z
   C: `worker-lanes.json`, `remote-reviewer.json`, `local-reviewer.json`,
   `*.pid.json` (lista z hashami w `Outcome`; ta lista jest wyłączeniem w
   bramce TASK-0957). Nie usuwać niczego innego: `v7-label-geometry/`
   (profile i sesje kalibracji V7), `v7-selection/`, `v7-model-download/`,
   `reviewer-ingress-controller-results/`, pliki JSON audytów i logi
   zostają.
3. `npm run db:up` z D (provisioning ról `ALTER ROLE`/uprawnienia; pierwszy
   zapis po bramce równości z TASK-0955), `npm run db:current`.
3. Nowy skrypt `scripts/verify_artifact_references.py` (proponowany,
   tylko odczyt, połączenie przez `GAME_PREDICTOR_DATABASE_URL` lub
   domyślny URL): dla każdej kolumny `*_path` w `game_data_v2` i `public`
   ustala korzeń według kodu (`artifact_root/data` dla kolumn
   rozwiązywanych przez `image_job_repository.py` i pokrewne;
   `artifact_root` dla ścieżek zaczynających się od `data/`;
   `source_directory` joba dla `image_import_job_files.source_relative_path`;
   `import_root` dla manifestów importu; kolumny nieznane raportuje jako
   „niezmapowane”), sprawdza istnienie pliku na dysku, raportuje liczby
   wierszy, brakujących i niezmapowanych per kolumna oraz próbkę
   brakujących ścieżek. Osobno liczy pliki rozwiązane przez korzeń
   wskazujący stary katalog C (`source_directory` jobów) jako
   „zależne od C” i czyta zawartość plików manifestów wskazanych przez
   kolumny `*manifest_relative_path`, raportując wpisy z prefiksem C.
   Parametr `--forbid-prefix <ścieżka>` zamienia obie liczby w błąd
   (kod 1); bez parametru są tylko raportowane. Test jednostkowy
   mapowania kolumn i bramki prefiksu.
4. `npm run reviewer:build` na D; `npm run reviewer:remote:setup` tylko
   gdy skrypt zgłosi brak konfiguracji.
5. Operator startuje z D: `npm run api:dev`, `npm run admin:dev`,
   `npm run workers:start`, `npm run reviewer:start`,
   `npm run reviewer:remote:start`.
6. Inwentaryzacja 13 bindingów zdalnej selekcji (tylko odczyt): per sesja
   status, `host_base_path`, liczby `batches`, `files`, `transfers`,
   `host_actions`, `operations`; wynik w `Outcome` i jako wejście
   TASK-0957. Nie unieważniać sesji w tym tasku.
7. Odbiór B2 (z tymczasowo dozwolonymi zależnościami od C) według
   „Odbiór całego przepływu” planu: `db:current`; niezmienniki względem
   raportu B1 (rewizja Alembic, liczba tabel, liczba jobów ≥ B1 z
   wyjaśnionymi różnicami: zakończony `super_game_series_derive`, nowe
   sesje; rozmiary baz w granicach ±2% albo różnica wyjaśniona), bez
   wymogu równości (równość sprawdził TASK-0955 przed startem usług);
   `verify_artifact_references.py` = 0 brakujących, liczba „zależnych od
   C” zapisana (rozlicza TASK-0957),
   zdjęcie planszy i crop w „Wyszukaj plansze” dla 777, „777 aktu 2” i
   Mumii, kropy ze statusami w weryfikacji symboli, `workers:status`, job
   `super_game_series_derive` w stanie końcowym (zakończony na C w B1,
   ścieżka podstawowa, albo anulowany i wznowiony na D według `Outcome`
   TASK-0955; nie uruchamiać go ponownie), brak procesów z C, nowy adres
   tunelu, nowa sesja udostępnienia z telefonu, otwarcie istniejącej
   aktywnej sesji zdalnej selekcji, obecność `.runtime/v7-label-geometry`
   na D z manifestem równym B1.
8. Restart Windows (operator), start usług z D, powtórzenie kroku 7
   w skróconej formie (`db:current`, health, `workers:status`,
   `verify_artifact_references.py`, jedna plansza z obrazem).
9. Dokumentacja: `LOCAL_OPERATION_GUIDE.md` i `DATABASE_MAINTENANCE.md`
   (ścieżki `C:\Users\tuszy\Documents\game_predicotr` → `D:\game_predicotr`
   tam, gdzie opisują bieżące środowisko, nie historię), `.wslconfig` bez
   zmian, `CURRENT_STATE.md` („Cykl życia usług”: stan z D; sesje agentów
   od tej pory w `D:\game_predicotr`).

## Out of scope

- Zmiany kodu API i workera. Build APK. Unieważnianie i przenoszenie
  bindingów zdalnej selekcji (TASK-0957). Usuwanie C.

## Acceptance criteria

- [ ] `npm run windows:environment:check` z nowego terminala: OK, ścieżki D;
      po kroku 1 `Path` użytkownika bez wpisów C repozytorium.
- [x] `verify_artifact_references.py`: 0 brakujących, 0 niezmapowanych
      kolumn (albo niezmapowane wymienione z uzasadnieniem); liczby wierszy
      i liczba „zależnych od C” w `Outcome`.
- [x] Niezmienniki względem raportu B1 spełnione; każda różnica liczników
      wyjaśniona w `Outcome`.
- [ ] Wszystkie punkty odbioru z planu zaliczone i zapisane w `Outcome`
      z wartościami; powtórzone po restarcie Windows.
- [x] Inwentaryzacja bindingów zapisana (14 sesji w bazie A′).
- [x] Przewodniki zaktualizowane; `npm run docs:check` zielony.

## Technical notes

`configure_windows_user_environment.ps1` wylicza ścieżki z
`$PSScriptRoot\..`, więc uruchomiony z D przepisuje zmienne na D; zmiana
jest trwała (HKCU). Hook `.claude/settings.json` używa
`${CLAUDE_PROJECT_DIR}`, więc działa z D. Reviewer produkcyjny wymaga
`reviewer:build`; `.next` nie jest kopiowane z C. Sesje udostępnienia
wyszukiwarki tracą ważność po restarcie API (capability procesu); trwałe
sesje zdalnej selekcji zostają w bazie.

Jeżeli Admin pokazuje planszę bez zdjęcia: sprawdzić `GAME_PREDICTOR_*ROOT`
w środowisku procesu API (muszą być nieustawione albo wskazywać D) i
istnienie pliku pod korzeniem właściwym dla tej kolumny (dla obrazów
operacyjnych `D:\game_predicotr\artifacts\data\<ścieżka względna>`,
dla referencji symboli `D:\game_predicotr\artifacts\<ścieżka z prefiksem data/>`).
Obejście w kodzie niedozwolone.

## Expected files

- Nowy: `scripts/verify_artifact_references.py`, test w `services/api/tests/`.
- Istniejące: `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`,
  `ai_docs/guides/DATABASE_MAINTENANCE.md`, `ai_docs/process/CURRENT_STATE.md`,
  ten plik.

## Test cases

- Zmienne nadal wskazują C po `setup` → błąd skryptu, nie kontynuować.
- Brakujący plik w próbce (test na kopii z usuniętym plikiem) → skrypt
  raportuje 1 brakujący z ścieżką.
- `workers:status` widzi lane z C (stary PID) → `.runtime` nie wyczyszczony;
  powtórzyć krok 2.
- Po restarcie Windows usługi startują z D bez ręcznych zmian środowiska.

## Verification

```powershell
# D:\game_predicotr, nowy terminal; każda komenda ≤ 120 s, weryfikacja odwołań w tle z limitem 60 min
npm run windows:environment:check
npm run db:current
npm run workers:status
.\.venv\Scripts\python.exe scripts/verify_artifact_references.py
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Documents\game_predicotr*' } | Select-Object ProcessId, Name
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## Risks / open questions

- Quick Tunnel zmienia adres; użytkownik końcowy dostaje nowy link.
- Mapowanie kolumn ścieżek na korzenie wymaga odczytu kodu; kolumny
  niezmapowane blokują kryterium do czasu wyjaśnienia.

## Outcome

Executed 2026-10-10 about 19:30–22:40 local time. The lead (Claude Code
session) started the services from D on the operator's instruction ("use
the app on D right now"); this agent (`claude-opus-5-5`, as assigned)
implemented the verification script, ran the read-only checks, updated the
guides and recorded the result. Codex audit: audyt Codex niedostępny
(limit), do wykonania później.

### Changed

- New `scripts/verify_artifact_references.py` (read-only): discovers every
  `*_path` / `relative_path` column of `game_data_v2` and `public` (parents
  only, partitions are covered by their parent), resolves each distinct path
  under the root the code uses (`data/...` under the artifact root, other
  managed paths under `<artifact_root>/data`, lab symbol candidates
  `models/lab-symbol-candidates/...` under the artifact root), checks the
  file, reads manifest columns as JSON and counts strings under the legacy
  prefix, and checks `jobs.input_payload.source_directory` and
  `remote_manual_selection_sessions.host_base_path` as directories (also
  whether the same path exists under the D repository). Connection: owner URL
  of `ApiSettings`, `default_transaction_read_only=on`. Missing files,
  invalid paths, unreadable manifests and unmapped columns with data fail
  (exit 1); `--forbid-prefix` additionally turns every legacy count into an
  error. Deviation from the task text, from code and data:
  `image_import_job_files.source_relative_path` holds managed
  `originals/...` paths (0 of 111 730 rows are anything else), so it is
  resolved under `<artifact_root>/data`; the job's `source_directory` is the
  separately checked directory.
- New `services/api/tests/test_verify_artifact_references_script.py`
  (23 tests: root mapping, invalid and escaping paths, prefix matching,
  manifest scan, column check counts, directory check, column
  classification, the gate with and without `--forbid-prefix`).
- `scripts/sync_data_directories_to_d.ps1`: `node_modules` is no longer
  excluded inside `.tooling` (durable fix, see below).
- `D:\game_predicotr\.tooling\node\node_modules` (npm and corepack of the
  isolated Node, 1 980 files, 12.5 MB) copied from C with `robocopy /E /XO`
  into the absent directory (nothing overwritten; log
  `D:\game_predictor_backup\tooling-node-modules-20261010.log`); SHA-256 of
  all 1 980 files equal on C and D. Cause: the sync script excluded every
  `node_modules`, also the one under `.tooling` that `npm install` cannot
  recreate, so `npm` from `D:\game_predicotr\.tooling\node` failed with
  "Cannot find module ...npm-cli.js" (and `windows:environment:check`
  printed an empty npm version).
- `.runtime` on D: the process-state files copied from C were moved (not
  deleted) by the lead to `D:\game_predictor_backup\runtime-state-from-c-20261010`
  (SHA-256): `admin-0886.pid.json` `7a9ae5b5…d50c`,
  `admin-deployment.pid.json` `344909df…afec`, `api-controlled.pid.json`
  `0cd684e8…116d`, `api-recovery.pid.json` `44d2a752…f21c`,
  `local-reviewer.json` `a68efcab…8981`, `reviewer-deployment.pid.json`
  `2de58fe7…bdbb`, `t0712-api.pid.json` `4f92f194…8c8c`, `worker-lanes.lock`
  (empty). `worker-lanes.json` and `remote-reviewer.json` were removed in B1
  (TASK-0955, `-Mirror` with an approved list). This list is the exclusion
  list for the TASK-0957 gate.
- Guides: `LOCAL_OPERATION_GUIDE.md` (the app runs from `D:\game_predicotr`,
  daily procedure, repository paths, npm 12 note and the direct check
  command, `.tooling\node\node_modules`), `DATABASE_MAINTENANCE.md`
  (repository path D, `diskpart` script path, section 5.3 with the clone,
  the B1 manifests and the verification script). `.wslconfig` unchanged.
- `CURRENT_STATE.md`: "Cykl życia usług" now names the D services; agent
  sessions work in `D:\game_predicotr` from now on.

### Verification results

- Startup from D (lead, 2026-10-10 evening; checked again 21:45–22:10):
  `npm run db:up` and `npm run db:current` from D (`0154_geometry_correction_revert
  (head)`, no migration needed); API 8000 `npm run api:dev` with `--reload`
  (`D:\game_predicotr\.venv`), health `http://127.0.0.1:8000/api/v1/health`
  = 200; Admin 3000 `next dev` from `D:\game_predicotr\node_modules`;
  Reviewer 3001 `next start` (built on D with `reviewer:build`); worker
  `general` from `npm run workers:start` (`D:\game_predicotr\.venv\Scripts\python.exe
  -m game_predictor_worker --poll --lane general`); listeners 8000, 3000,
  3001, 5432; 0 processes with `Documents\game_predicotr` in the command line.
- `npm run workers:status` from D: `General worker: running (launcher PID
  7212, worker PID 4108, since 2026-10-10T19:38:38Z)`, logs under
  `D:\game_predicotr\.runtime`; image-selection worker stopped (as before).
- Environment (HKCU): `GAME_PREDICTOR_NODE_HOME`, `JAVA_HOME`,
  `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `GAME_PREDICTOR_GRADLE_USER_HOME` point
  to `D:\game_predicotr\.tooling\…`; the user `Path` has the four D entries
  first and still the four old C `.tooling` entries (before:
  `D:\game_predictor_backup\user-path-before-b2.txt`).
  `scripts/configure_windows_user_environment.ps1 -CheckOnly` from D: exit 0,
  Node v24.21.0, npm 11.19.0, Java 17.0.20, ADB 1.0.41, all homes on D.
  `npm run windows:environment:check` started by the global npm 12.0.2
  (`C:\Program Files\nodejs` precedes the user `Path`; npm 12 installed in
  `%APPDATA%\npm` since 2026-09-14) fails with "npm 12.0.2 does not satisfy
  the repository range >=11 <12": the inner `.tooling` npm inherits the
  outer npm's prefix. The same command fails identically from the C
  checkout, so this is a pre-existing environment issue, not a migration
  regression; recorded in the guide.
- `verify_artifact_references.py` from D (`D:\game_predicotr\.venv`, cwd D,
  operator database, read-only), run 21:58, 26 s, report
  `D:\game_predictor_backup\verify-artifact-references-20261010-2158.json`
  and `.out`: `RESULT: OK`, exit 0.
  - 22 mapped columns, 258 212 distinct paths, 258 212 existing, 0 missing,
    0 invalid; 21 782 manifests read, 0 unreadable. Largest:
    `source_images.relative_path` 111 727 rows (110 300 distinct),
    `image_import_job_files.source_relative_path` 111 730 (110 303),
    `image_board_geometry_pending` 21 720 sources (15 557 distinct) and
    21 720 processing manifests, `image_board_geometry_revisions.board_relative_path`
    461 of 139 562 rows (242 distinct); `image_symbol_review_cells.crop_relative_path`
    (14 879 535 rows) and `recognized_boards.board_relative_path`
    (1 002 605 rows) are all NULL (virtual crops and boards).
  - 16 unmapped columns, all with 0 non-null rows (justification: empty,
    nothing to resolve): `image_selection_candidates.source_relative_path`,
    `image_selection_runs.output_manifest_relative_path`,
    `image_sequence_alternatives.source_relative_path`,
    `image_verified_cohort_exports.artifact_relative_path`,
    `layout_payouts.audit_path`, `representative_ranking_cohorts.artifact_relative_path`,
    `representative_ranking_iterations.model_artifact_relative_path`,
    `mobile_releases.apk_path`/`snapshot_path`, the five
    `remote_manual_selection_files/operations/transfers` path columns,
    `semi_automatic_image_selection_ranges.source_relative_path`,
    `semi_automatic_image_selection_runs.diagnostics_relative_path`.
    Excluded: `paylines.row_path` (integer array), `host_base_path` (checked
    as directory).
  - C-dependent (legacy prefix `C:\Users\tuszy\Documents\game_predicotr`,
    allowed in B2, settled in TASK-0957): resolved files 0; manifest entries
    53 (the 53 `browser_selection_retention_states` manifests under
    `data/originals/manifests/` hold their import's `source_directory`);
    job source directories 181 (completed 114, waiting_for_review 54,
    failed 8, cancelled 5; all 181 exist on C and under
    `D:\game_predicotr\imports\…`); remote sessions 14 (all exist on C and
    under D).
  - The first run (21:53) reported 2 missing files: a mapping error of the
    script, not missing data (the imported lab candidate's
    `candidate_manifest`/`gate_report` are relative to the artifact root;
    both files exist in `D:\game_predicotr\artifacts\models\lab-symbol-candidates\…`).
    Fixed in the script with a test before the reported run.
- Invariants against the B1 reference report (`db-state-before-move.txt`),
  22:11: alembic `0154` equal; 280/59 tables equal; jobs 845 with the same
  statuses (no new job since B1); 14 remote sessions (4 active, 10 revoked)
  equal; `game_predictor` 96 259 561 151 bytes vs 96 259 511 999 (+49 152
  bytes, 0.00005 %); `game_predictor_v7_pilot` +160 944 bytes
  (`pg_internal.init`, TASK-0955 P0-1); the newest
  `super_game_series_derive` job is `completed` (15:25 local, before B1,
  primary path), not rerun.
- `.runtime` on D against the B1 manifest
  (`sync_data_directories_to_d.ps1 -VerifyOnly -Manifest …\20261010-175735-Final
  -Directories .runtime`): 47 files, 0 different, 7 missing = exactly the
  seven process-state files moved above; `.runtime/v7-label-geometry`
  (profiles, sessions) equal.
- Function checks through the API from D (read-only GETs plus one preview
  render as the Admin does): board view
  (`/board-search/boards/{n}/view`) 200 `image/webp` for 777 (sequence
  198873) and Mumie (275833); symbol reference image 200 `image/png`; symbol
  crop atlas for 777 (`symbol-cell-preview-batches`) 200 `image/webp`.
  "777 aktu 2" (draft) has no source images or boards, so there is nothing
  to show. Mumie symbol verification answers
  `SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE` (`status: rebuilding`): its
  backfill job `9f8b1f8c-7719-4a45-b6ff-039a2bfdc851`
  (`image_symbol_review_backfill`) was cancelled at 15:25 local, before B1
  (queue drain), at 143 400 of 7 379 535 cells. Pre-existing, not caused by
  the move; restarting it is an operator decision (checklist).
- Remote manual-selection bindings (read-only inventory, 14 sessions, all
  with `host_base_path` `C:\Users\tuszy\Documents\game_predicotr\artifacts\remote-manual-selection-access`,
  directory empty on C and on D): 0 batches, 0 files, 0 transfers,
  0 host actions, 0 operations for every session. Active: `c5133c43…`
  ("bodzio 777", expired 2026-10-03), `ae422152…` ("bodzio", expired
  2026-10-06), `76fef4f1…` ("bodzio", expired 2026-10-07), `44ed9b0b…`
  ("s", expires 2026-10-11). Revoked: `7d9c0d7d…`, `37f79acf…`, `8b8edbe9…`,
  `90b64dbc…`, `01d82d20…`, `ebb9afe4…`, `74de232c…`, `2cac572d…`,
  `a2d819c8…`, `eca2d957…`. No session was invalidated. Input for
  TASK-0957: no binding holds data or pending actions.
- Worktrees to restore on D: none (every C worktree except
  `disk-migration` was merged and removed; TASK-0954).
- Script checks (C worktree, `.venv` of C): `pytest
  services/api/tests/test_verify_artifact_references_script.py` 23 passed;
  `ruff check` and `ruff format --check` clean; `mypy` (strict) clean on the
  script and test. Sync script fix: throwaway source with
  `.tooling/node/node_modules` and `work/node_modules`, `-Mode Final
  -Directories .tooling,work`: `.tooling` copied with `node_modules`
  (SHA-256 equal), `work/node_modules` still excluded, `RESULT: OK`;
  `-Inventory` unchanged.
- `npm run docs:check`: OK.

### Not completed (operator checklist)

Status `blocked` only on operator-only items:

1. Windows restart, then from `D:\game_predicotr` in a new terminal:
   `npm run db:up`, `npm run api:dev`, `npm run workers:start`, then
   `npm run db:current`, health, `npm run workers:status`,
   `.\.venv\Scripts\python.exe scripts/verify_artifact_references.py` and
   one board with its image in Admin (shortened step 7).
2. Phone and tunnel: `npm run reviewer:remote:start` from D (new Quick
   Tunnel address), a new board-search share session from the phone, and
   opening an existing active remote-selection session (only `44ed9b0b…`
   is still within its expiry).
3. Remove the four old `C:\Users\tuszy\Documents\game_predicotr\.tooling\…`
   entries from the user `Path` (before/after into this Outcome), then
   `scripts/configure_windows_user_environment.ps1 -CheckOnly` in a new
   terminal.
4. Mumie symbol verification: restart the Mumie symbol-review backfill in
   Admin (its job was cancelled before B1); 777 works.
5. Decisions still open from the plan: copy the Claude Code memory to the
   D project directory; whether to move the folders outside the repository
   (`game_predictor_vision_data` and others, about 14.9 GB); optionally
   align the global npm (12.0.2 in `%APPDATA%\npm`) with the repository's
   npm 11.

### Documentation updates

- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`,
  `ai_docs/guides/DATABASE_MAINTENANCE.md`,
  `ai_docs/process/CURRENT_STATE.md`, this Outcome.

### Commits

- v1.7.309 (this task; hash recorded with the merge in `CURRENT_STATE.md`).
- Previous in the series: v1.7.307 `4b96372c938a61f82c97a6398d13e0d63f787fb2`
  (TASK-0955), v1.7.308 `41aa80584cd8564d6b6d4955a3bf95e3fd053935`
  (TASK-0954).

### Recommended next task

- TASK-0957 (after the operator checklist and at least one working day on D)
