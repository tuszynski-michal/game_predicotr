---
title: TASK-0954 — Zabezpieczenie repozytorium przed porzuceniem C
status: todo
last_updated: 2026-10-09
---

# TASK-0954 — Zabezpieczenie repozytorium przed porzuceniem C

## Status

`todo`

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
- `git bundle create D:\game_predictor_backup\repo-YYYYMMDD\all-refs.bundle
  --all` z głównego checkoutu C; `git bundle verify` na D.
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
skrypt, porównanie z `INVENTORY.md`).

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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/inventory_worktrees.ps1 -OutputRoot D:\game_predictor_backup\repo-$(Get-Date -Format yyyyMMdd)
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

- TASK-0955 (po zakończeniu joba `d9a49da0`)
