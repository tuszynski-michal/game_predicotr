---
title: TASK-0954 — Zabezpieczenie repozytorium przed porzuceniem C
status: in_progress
last_updated: 2026-10-10
---

# TASK-0954 — Zabezpieczenie repozytorium przed porzuceniem C

## Status

`in_progress` (securing done; push, merge and D checkout wait for the
operator at the B1 boundary)

## Goal

Każdy commit, każda referencja i każda niezapisana zmiana z głównego
checkoutu i wszystkich worktree'ów na C są odtwarzalne z D: referencje w
zweryfikowanym bundle i na `origin`, zmiany śledzone w patchach `--binary`,
pliki nieśledzone w kopii, a checkout D jest na commicie z planem i
skryptami.

## Context

Etap A3 planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`, decyzje
6 i 7. Inwestygacja 2026-10-09: na C 27 niecommitowanych zmian w głównym
checkoucie oraz gałęzie tylko lokalne: `feat/grid-engine-v3`,
`feat/mumie-super-game-plan` (zaakceptowany plan Mumii, D-535),
`feat/super-game-series-count`, `task-0860`. Worktree'y: `worktrees/*`,
`.claude/worktrees/agent-…`, jeden detached w katalogu tymczasowym sesji.
Ich stan plików nie był sprawdzany. Usunięcie C bez tego kroku traci pracę.

## Dependencies / entry conditions

- Fakt: D jest na `c504fe70`, czysty, z tym samym `origin`.
- Niewiadoma: pochodzenie zmian w `ai_docs/tasks/**` (prawdopodobnie hashe
  `Outcome` dopisane przez wcześniejsze sesje) i w `package-lock.json`.
  Zmiany obecne przed taskiem należą do operatora: nie usuwać, nie
  formatować, nie commitować bez decyzji.
- Zgoda operatora na push gałęzi roboczych i na merge gałęzi
  `feat/disk-d-migration-plan` do gałęzi integracyjnej (merge obejmuje push).

## Recommended execution

`claude-opus-5-5`, reasoning `medium`. Inwentaryzacja wielu worktree'ów,
bundle, patche binarne i weryfikacja; ryzyko utraty pracy operatora przy
pominięciu. Eskalacja do `claude-fable-5-1`, `medium`, jeśli bundle lub
patche nie weryfikują się na D.

## Relevant docs

- `AGENTS.md` („Brudny worktree i zakres commita”, „Wersjonowanie commitów”)
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`

## Scope

- Nowy skrypt `scripts/inventory_worktrees.ps1` (proponowany, tylko
  odczyt + zapis do katalogu wyjściowego): dla każdego wpisu `git worktree
  list --porcelain` (także detached): HEAD, gałąź, `git status --porcelain
  --untracked-files=all`, liczby zmian staged/unstaged/nieśledzonych;
  zapis `git diff --binary --cached --output=<dir>\<wt>-staged.patch`,
  `git diff --binary --output=<dir>\<wt>-unstaged.patch` (bez przekierowań
  PowerShell, kodowanie zachowane przez git), kopia plików nieśledzonych
  (`robocopy` listą) do `<dir>\<wt>-untracked\`; dodatkowo inwentarz
  plików ignorowanych każdego worktree'a (`git ls-files --others
  --ignored --exclude-standard --directory`, z rozmiarami katalogów)
  sklasyfikowany jako **odtwarzalne** (`node_modules`, `.next`, `.venv`,
  `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `*.log`)
  albo **zachowywane** (wszystko inne, np. `artifacts/`, `.runtime/`,
  `imports/`, `work/`, `.tmp/` w worktree'ach); zachowywane katalogi
  kopiowane przez `scripts/sync_data_directories_to_d.ps1 -Inventory
  -Source <worktree>` (klasyfikacja), a potem `-Mode Final -Source
  <worktree> -Destination D:\game_predictor_backup\repo-YYYYMMDD\<wt>-ignored
  -Directories "<zachowywane wpisy z inwentarza, także luźne pliki>"`
  z manifestem SHA-256; ignorowane dane głównego checkoutu obejmuje
  inwentarz i kopia z TASK-0953 (ten sam skrypt, wszystkie zachowywane
  wpisy, nie tylko katalogi danych); wynik w
  `D:\game_predictor_backup\repo-YYYYMMDD\INVENTORY.md`.
- Skrypt zapisuje `refs/c-migration/<nazwa>` dla HEAD każdego worktree'a
  (`-CreateRefs`), bo `git bundle --all` nie obejmuje odłączonych HEAD
  (np. `wt0858`). `StatusDigest` obejmuje listę statusu, oba diffy i treść
  plików nieśledzonych, więc `-CompareWith` wykrywa także edycję pliku już
  zmienionego lub nieśledzonego.
- `git bundle create D:\game_predictor_backup\repo-YYYYMMDD\all-refs.bundle
  --all` z głównego checkoutu C; `git bundle verify` na D; weryfikacja
  odtworzenia `inventory_worktrees.ps1 -VerifyClone D:\game_predicotr
  -Bundle <plik>` (pobiera `refs/c-migration/*` do klonu D, tworzy
  tymczasowy worktree, nakłada patche i pliki nieśledzone, porównuje status
  i usuwa worktree).
- Push na `origin` czterech gałęzi lokalnych (po zgodzie); `git fetch
  --all --prune` na D; `git branch -r` zawiera je z tymi samymi hashami.
- Główny checkout C: zmiany `Outcome`/hashe zaklasyfikować i, po zgodzie
  operatora, zapisać commitem `vX.Y.N - record outcome hashes` na gałęzi
  integracyjnej albo zostawić w patchu (decyzja zapisana w `Outcome`).
- Po akceptacji planu: push `feat/disk-d-migration-plan`, merge do gałęzi
  integracyjnej za zgodą operatora; na D `git pull --ff-only`; sprawdzić,
  że D zawiera `scripts/sync_data_directories_to_d.ps1` i wpis npm
  `data:sync:d` (po TASK-0953) oraz ten plan.
- Weryfikacja odtwarzalności na D: tymczasowy worktree na D na commicie
  HEAD danego worktree'a C, potem w tej kolejności `git apply --index
  <wt>-staged.patch` i `git apply <wt>-unstaged.patch` (unstaged nakłada
  się na odtworzony indeks, nie na czysty HEAD), `git status --porcelain`
  równy inwentarzowi; tymczasowy worktree usunięty po teście. Dla bundle
  `git bundle verify` i `git ls-remote <bundle>`; dla zachowywanych
  katalogów ignorowanych `-VerifyOnly` manifestu.
- `Outcome`: tabela worktree → HEAD → liczby zmian → pliki patch/kopii →
  wynik `apply --check`.

## Out of scope

- Merge gałęzi roboczych (innych niż plan) do gałęzi integracyjnej.
  Usuwanie worktree'ów i gałęzi (etap C). Rozstrzyganie, czy zmiany w
  worktree'ach są warte commitowania.

## Acceptance criteria

- [ ] `INVENTORY.md` obejmuje wszystkie wpisy `git worktree list`, również
      detached i `.claude/worktrees`.
- [ ] Każdy worktree z niezerowym `status --porcelain` ma patche
      (`--binary`) lub kopię nieśledzonych; odtworzenie na D (staged z
      `--index`, potem unstaged) daje `status --porcelain` równy
      inwentarzowi.
- [ ] Każdy katalog ignorowany każdego worktree'a jest w `INVENTORY.md`
      jako odtwarzalny albo zachowywany; zachowywane mają kopię na D z
      równym manifestem SHA-256.
- [ ] `all-refs.bundle` weryfikuje się na D (`git bundle verify`), zawiera
      wszystkie gałęzie i tagi z C.
- [ ] Cztery gałęzie: `git rev-list --count origin/<b>..<b>` = 0; na D
      `git branch -r` pokazuje je z tymi samymi hashami.
- [ ] D na commicie zawierającym plan i skrypty (hash w `Outcome`).
- [ ] Hash ewentualnego commita zapisów `Outcome` w `Outcome` tego taska i
      w `CURRENT_STATE.md`.

## Technical notes

Nie używać `git stash` (wspólny stos między worktree'ami i sesjami).
`git diff --output=` zapisuje bajty bez udziału PowerShell. Pliki
nieśledzone kopiować po liście z `git ls-files --others --exclude-standard`;
ignorowane wpisy głównego checkoutu (wszystkie zachowywane z inwentarza
`-Inventory`, w tym `.tmp/`, `.claude/settings.local.json`, luźne pliki)
obsługuje TASK-0953; ignorowane wpisy pozostałych worktree'ów ten task
(inwentarz i kopia zachowywanych). Skrypt synchronizacji przyjmuje dowolne
`-Source`/`-Destination` i listę wpisów (TASK-0953).
Przed pushem gałęzi integracyjnej sprawdzić, czy czubek zawiera tylko
commity znane operatorowi (`git log origin/v1.1-vision-lab-hybrid-geometry..`).
Zmiany powstałe po A3 wykrywa ponowna inwentaryzacja w TASK-0957 (ten sam
skrypt, `-CompareWith` z `inventory.json` tego przebiegu).

## Expected files

- Nowy: `scripts/inventory_worktrees.ps1`.
- Istniejące: ten plik, `ai_docs/process/CURRENT_STATE.md`.
- Nowe (poza repo): `D:\game_predictor_backup\repo-YYYYMMDD\` (bundle,
  patche, kopie, `INVENTORY.md`).

## Test cases

- Worktree ze zmianą staged i nieśledzonym plikiem → oba patche/kopie
  istnieją, `apply --check` OK.
- Worktree detached HEAD → ujęty w inwentarzu z hashem.
- Gałąź z commitami lokalnymi → po push `rev-list --count` = 0.
- Bundle bez jednej gałęzi (test negatywny na kopii) → `ls-remote` ujawnia brak.

## Verification

```powershell
# katalog C (inwentarz, bundle, push) i katalog D (fetch, verify); każda komenda ≤ 120 s
# -CreateRefs is mandatory before every bundle (fresh or refreshed backup):
# it writes refs/c-migration/<name> so detached HEADs enter the bundle.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/inventory_worktrees.ps1 -OutputRoot D:\game_predictor_backup\repo-$(Get-Date -Format yyyyMMdd) -CreateRefs
git bundle create D:\game_predictor_backup\repo-$(Get-Date -Format yyyyMMdd)\all-refs.bundle --all
git push origin feat/grid-engine-v3 feat/mumie-super-game-plan feat/super-game-series-count task-0860
git -C D:\game_predicotr fetch --all --prune
git -C D:\game_predicotr bundle verify D:\game_predictor_backup\repo-$(Get-Date -Format yyyyMMdd)\all-refs.bundle
```

## Risks / open questions

- `package-lock.json` zmieniony przez `npm install` w innym worktree:
  commit tylko, jeśli diff jest wynikiem taska; inaczej patch.
- Worktree w katalogu tymczasowym sesji może zniknąć przed A3; inwentarz
  zapisuje, czy istniał.

## Outcome

Executed 2026-10-10 01:55–02:40 local time by Claude Code (`claude-opus-5-5`;
the plan table assigns `claude-opus-5-5` medium, used as assigned). Two
parallel Claude Code sessions ("Interfejs korekcji siatek plansz",
"Cofnięcie zatwierdzenia siatki") were active, so this is a snapshot; the
TASK-0957 gate repeats the inventory with `-CompareWith`.

### Changed

- New `scripts/inventory_worktrees.ps1` (ASCII, PowerShell 5.1): per
  worktree `status-raw.txt`, `status.txt` (content changes only), binary
  `staged.patch`/`unstaged.patch` written by `git diff --output`, copies of
  untracked files, ignored-data inventory and copy through
  `sync_data_directories_to_d.ps1`, `inventory.json`/`INVENTORY.md`,
  `-CreateRefs` (`refs/c-migration/<name>` for every HEAD so detached heads
  enter the bundle), `-CompareWith` (content digest over status, both diffs
  and untracked file contents; exit 3 on change), `-VerifyClone -Bundle`
  (restore every worktree in a temporary detached worktree of a clone and
  compare the status).
- `D:\game_predictor_backup\repo-20261010\`: `INVENTORY.md`,
  `inventory.json`, `all-refs.bundle` (49 905 245 bytes, every ref of C
  including `refs/c-migration/*`), one directory per worktree with patches,
  untracked copies and preserved ignored data (main checkout: ignored data
  is the TASK-0953 copy in `D:\game_predicotr`, not duplicated here).
- C repository: only new refs `refs/c-migration/*` (9 refs). No commit,
  stash, checkout or file change in any C worktree.
- D clone `D:\game_predicotr`: all 22 local branches of C fetched from the
  bundle as `refs/remotes/c/<branch>` and `refs/c-migration/*`; working tree
  unchanged (still `c504fe70`, untracked `v7-output/` from TASK-0953).
- Deviation from Scope: C has 17 local-only branches (the plan listed 4) and
  the integration branch is 3 commits ahead of `origin` (v1.7.297–299 from
  another session). Pushing 18 refs to GitHub is an outward action that the
  plan reserved for operator consent, and the bundle already makes every
  commit available on D, so nothing was pushed. Main checkout changes were
  not committed either: they belong to other sessions; they are secured as
  patches.

### Verification results

- Throwaway repository: inventory with staged, unstaged, untracked and
  ignored data; `-VerifyClone` restored the worktree status exactly;
  `-CompareWith` unchanged = exit 0, after editing an untracked file =
  `CHANGED`, exit 3.
- Real C inventory (9 worktrees: main, `wt0858` detached, `.claude` agent
  worktree `task-0860`, `disk-migration`, `geometry-correction-revert`,
  `grid-engine-v3`, `mumie-super-game`, `reviewer-geometry-gaps`,
  `super-game-series-count`): exit 0. `stat_only` lines (marked modified only
  by line endings, empty `git diff`): main 3, `task-0860` 15; they carry no
  content and are listed in `status-raw.txt`.
- `-VerifyClone D:\game_predicotr -Bundle all-refs.bundle`: bundle valid,
  every HEAD present, restored status equal to the inventory for all 7
  worktrees with changes (main 30 lines, `wt0858` 3, `task-0860` 10,
  `disk-migration` 8, `geometry-correction-revert` 52, `grid-engine-v3` 36,
  `reviewer-geometry-gaps` 14), 2 clean; `RESULT: OK`; temporary worktrees
  removed.
- Bundle completeness: `ls-remote` lists 65 refs = all 56 refs of C
  (`refs/heads` 22, `refs/codex` 17, `refs/c-migration` 9, `refs/remotes` 6,
  `refs/original` 1, `refs/stash` 1) plus `HEAD` and the 8 per-worktree
  `HEAD`s. All 22 `refs/heads/*` of C equal `refs/remotes/c/*` on D
  (0 mismatches).
- Final re-run at 03:10–03:19 with the committed sync script (v1.7.303)
  and the final inventory script (INVENTORY.md column index updated for the
  new `New` column): `-CreateRefs`, new `all-refs.bundle`,
  `-VerifyClone`: all 9 worktrees `OK` (main 30 lines, `wt0858` 3,
  `task-0860` 10, `disk-migration` 3, `geometry-correction-revert` 52,
  `grid-engine-v3` 36, `reviewer-geometry-gaps` 14, two clean),
  `RESULT: OK`; refetched `refs/remotes/c/*` on D: 0 mismatches. The main
  checkout now lists 102 preserved entries (98 ignored plus untracked ones
  such as `v7-output/`, added by TASK-0953 round 7).
- Codex audit round 1 (REVISE, 3 P0, 1 P1, 1 P2) fixed by rewriting
  `scripts/inventory_worktrees.ps1`:
  - a non-zero exit code of the ignored-data copy is collected and makes the
    run end with exit 1 after the inventory is written (P0-1);
  - `-IgnoredMode` defaults to `Final` (SHA-256 manifests), and
    `-VerifyClone` re-checks every Final copy with
    `sync_data_directories_to_d.ps1 -VerifyOnly -Manifest` (P0-1, P0-2);
  - `-CompareWith` is read before anything is written and may not point at
    the run's own `inventory.json` (P0-3);
  - every git call goes through `Invoke-GitRaw` with `-GitTimeoutSeconds`
    (default 600; timeout = exit 2); the sync script gets
    `-SyncTimeoutMinutes` (P1-1);
  - `-VerifyClone` compares the content digest (status, both diffs,
    untracked contents) of the restored worktree as well as the status
    (P2-1).
- Tests of the rewrite (throwaway repository, removed afterwards): default
  Final copy and `-VerifyClone` `OK`; `-CompareWith` at the output's own
  `inventory.json` refused (exit 1); a corrupted untracked copy in the backup
  fails `-VerifyClone` by digest (exit 1); `-CompareWith` from a separate
  output: unchanged = exit 0, after editing an untracked file = exit 3; an
  exclusively locked ignored file makes the copy fail and the run exit 1;
  a git alias sleeping 30 s with `-GitTimeoutSeconds 10` ends with exit 2
  after 10 s.
- Real run with the rewritten script (03:36–03:47): all 8 linked worktrees
  copied in Final mode (`exit 0 (Final)`), main inventoried (102 preserved
  entries, copy owned by TASK-0953); new `all-refs.bundle`; `-VerifyClone`:
  status and content digest equal for all 7 worktrees with changes, the 2
  clean ones have their HEAD, every Final ignored copy equals its manifest,
  `RESULT: OK`; `refs/remotes/c/*` refetched on D, 0 mismatches.
- Codex audit round 2 (REVISE, 1 P0, 1 P1, 2 P2) fixed:
  - `-VerifyClone` requires, for every linked worktree with preserved
    entries, a successful Final copy (`skipped` or a failed copy fails) and
    manifests whose `entry=` headers cover every preserved entry; only the
    main checkout is exempt and reported as covered by TASK-0953 (P0-4);
  - the `-CompareWith` instructions in this task and in TASK-0957 point at
    `inventory.json` (P1-2);
  - `inventory.json` and the ignored-data `INVENTORY.md` are read with
    `-Encoding UTF8` (P2-2);
  - a failed removal of a temporary verification worktree is reported and
    fails the verification (P2-3).
- Tests (throwaway repository with a Polish directory name `work/ąę`,
  removed afterwards): complete Final copy verifies `OK` (2 entries);
  deleting one manifest and its copy fails with "1 preserved entries without
  a manifest: work"; a `-SkipIgnoredCopy` inventory fails verification
  ("needs a successful Final copy").
- The stricter verification on the real backup: every linked worktree's
  ignored copy covers all its preserved entries (3, 4, 4, 19, 5, 12, 7, 2)
  and equals its manifests; restored status and digest equal for all 7
  worktrees with changes; `RESULT: OK`.
- Codex audit round 3 (REVISE, 2 P0, 1 P1) fixed:
  - `refs.txt` lists every local ref with its hash (remote-tracking refs and
    `refs/c-migration/*` excluded); `-CompareWith` compares it with the
    baseline's `refs.txt` and treats a baseline without it as changed (P0-5);
  - every record carries `IgnoredDigest`, a digest over the SHA-256
    manifests of the worktree's preserved ignored/untracked data (from the
    Final copy, or from the new `-ManifestOnly` mode of
    `sync_data_directories_to_d.ps1` for the main checkout and skipped or
    failed copies); `-CompareWith` reports a changed or missing digest
    (P0-6);
  - the documented inventory commands in this task and in TASK-0957 include
    `-CreateRefs`, mandatory before every bundle (P1-3).
  - Tests (throwaway repository): baseline vs. unchanged = exit 0; a new
    branch = `CHANGED refs`, exit 3; a changed ignored file in a linked
    worktree and a new ignored file in the main checkout = `CHANGED ...
    (preserved ignored/untracked data)`, exit 3.
- Incident while testing round 3 (fixed, no data lost): the sync script's
  internal variable `$manifestOnly` (verify against saved manifests) and the
  new switch `-ManifestOnly` are the same name in PowerShell, which ignores
  case. The test's manifest-only call therefore ran as a copy to the default
  destination and put the 2-byte test file `main.txt` into
  `D:\game_predicotr\artifacts`; nothing was deleted (no `/MIR`). The test
  was stopped, the file was compared byte by byte with the test file and
  removed, and the variable was renamed to `$verifyAgainstManifest`; the
  repeated test left `D:\game_predicotr\artifacts` unchanged.
- Performance fix in `sync_data_directories_to_d.ps1`, found because the
  real inventory took 114 min (almost all of it the manifest-only pass over
  about 80 GB of the main checkout): hashing allocated a 4 MB buffer and a
  SHA object per file (75 files/s). A compiled helper (`Add-Type`, loaded on
  first use) now reuses one buffer, reads sequentially and checks the
  deadline per 1 MB chunk (returns `$null` on timeout, turned into
  `TimeoutException`); `Assert-Deadline` uses `[datetime]::Now`. Measured:
  2 187 files/s (620 MB/s) on C. Files on D read cold at about 140-190
  files/s even with plain `ReadAllBytes` (Windows Defender real-time
  protection is on and scans each new file on first open; warm reads 3 277
  files/s), so a full `-VerifyOnly` run was started to pre-scan D before the
  B1 downtime. Hashes of the helper equal `Get-FileHash`; a passed deadline
  still throws `TimeoutException`.
- Real run with digests and refs (04:12–06:06, before the performance fix):
  all 8 linked worktrees `exit 0 (Final)`, main digest from a manifest-only
  pass, `refs.txt` 41 refs, new `all-refs.bundle`, `-VerifyClone`
  `RESULT: OK`, `refs/remotes/c/*` on D 0 mismatches.
- Codex audit round 4 (REVISE, 2 P0, 1 P2) fixed:
  - `-VerifyClone` requires the digest of the newest Final manifest
    directory to equal the inventory's `IgnoredDigest` before checking the
    copy, so a truncated, missing or replaced manifest fails (P0-7);
  - every linked worktree's backup name is its leaf name plus 10 hex digits
    of the SHA-256 of its full path; a duplicate name stops the run before
    anything is written for it (P0-8);
  - `-ManifestOnly` reports a selected entry that does not exist as an error
    (P2-4).
  - Tests (throwaway repository): three detached worktrees all named `task`
    get three backup directories (`task-f91cd048a9`, `task-cfd11648a7`,
    `task-d63fd0fe5f`) and verify `OK`; a manifest truncated to its header
    plus the matching copy removed fails with "do not match the inventory's
    IgnoredDigest"; `-ManifestOnly -Directories artifacts/nope` exits 1.
- Final real run with the final scripts (07:42–08:31, 49 min, mostly the
  manifest-only hash of the main checkout): 9 worktrees under their new
  names (`wt0858-cd3401a99e`, `agent-ad9ceefe41647c77c-1ed7c2e547`,
  `disk-migration-9ab82ef89a`, `geometry-correction-revert-5062cfa0f3`,
  `grid-engine-v3-5ee9faf8f3`, `mumie-super-game-ea45255693`,
  `reviewer-geometry-gaps-8ef03f1d83`, `super-game-series-count-0b6610dc84`,
  `main`), all 8 linked worktrees `exit 0 (Final)`, `RESULT: OK`; new
  `all-refs.bundle`; `-VerifyClone`: status and content digest equal for all
  7 worktrees with changes, every Final ignored copy matches its
  `IgnoredDigest` and manifests, `RESULT: OK`; `refs/remotes/c/*` on D:
  0 mismatches. The 8 `refs/c-migration/<old name>` refs from earlier runs
  were deleted from C after checking that each equals its new-name ref.
- Pre-scan of D (TASK-0953 data, 06:12–07:40, 88 min): `-VerifyOnly` over
  all 102 entries of the main checkout, SHA-256 of both sides equal for
  every entry, `RESULT: OK`. This is the first full hash proof that the
  copy in `D:\game_predicotr` equals C at that time; B1 still runs Final
  after the services stop.
- Bugs found and fixed during the run: Windows PowerShell 5.1 unwrapping of
  `ConvertFrom-Json` arrays, a corrupted `\?\` prefix, a loop variable that
  shadowed `$name` (the main checkout's ignored data was copied a second
  time into the repo backup; that duplicate, about 80 GB in a directory
  created by this task, was removed with `robocopy /MIR` from an empty
  folder; D free space back to 1 720.7 GB).

### Not completed

- Push of local-only branches and of the integration branch to `origin`,
  merge of `feat/disk-d-migration-plan` into the integration branch and
  `git pull` on D: operator decision at the B1 boundary (merge includes
  push). Until then D has every commit through `refs/remotes/c/*`.
- Commit of the main checkout's uncommitted changes: they belong to other
  sessions; secured as patches.

### Documentation updates

- This Outcome and `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- TASK-0955 after the job queue drains, the two parallel sessions publish
  their work and the operator decides the pushes; re-run this inventory
  with `-CompareWith` right before B1.
