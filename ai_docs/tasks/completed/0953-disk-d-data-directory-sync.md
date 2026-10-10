---
title: TASK-0953 — Przyrostowa kopia katalogów danych na D
status: done
last_updated: 2026-10-10
---

# TASK-0953 — Przyrostowa kopia katalogów danych na D

## Status

`done`

## Goal

Skrypt `scripts/sync_data_directories_to_d.ps1` inwentaryzuje wpisy
ignorowane przez git w checkoucie C, klasyfikuje je jako zachowywane albo
odtwarzalne, kopiuje przyrostowo wszystkie zachowywane (domyślnie
`artifacts/`, `imports/`, `examples/imgs/`, `.tooling/`, `.runtime/`,
`work/`, `v7-output/`, `.tmp/`, `.claude/settings.local.json`,
`TEMP PLAN V2 GEOMETRY.md`, `tmp-*.out`, `tmp-*.err`) z C do
`D:\game_predicotr` w trybie `Initial` (usługi działają) albo `Final`
(usługi zatrzymane), a w trybie `Final` manifesty SHA-256 źródła i celu
są równe.

## Context

Etap A2 planu `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`, decyzja
3. Ścieżki w bazie są względne wobec katalogu uruchomienia API i workera,
więc te katalogi muszą istnieć na D w tej samej strukturze. 77 GB i prawie
400 000 plików kopiuje się w porcjach; `robocopy /E` jest przyrostowy, więc
każde uruchomienie dokopiowuje różnicę, także po restarcie.

## Dependencies / entry conditions

- Fakt: na D istnieje `artifacts/` z jednym podkatalogiem
  (`v7-main-panel-entry-20261007`) i `imports/README.md`; reszta pusta.
- Fakt (2026-10-09, `git ls-files --others --ignored --exclude-standard
  --directory` na C): poza katalogami danych ignorowane są
  `.claude/scheduled_tasks.lock`, `.claude/settings.local.json`,
  `.claude/worktrees/`, `.pnpm-store/`, `.tmp/`, `.venv-vision-lab/`,
  `TEMP PLAN V2 GEOMETRY.md`, `packages/*/dist/`, `tmp-symbol-audit*.out|err`,
  `node_modules/`, `.venv/`, `__pycache__`, `.next/`, cache narzędzi.
  `.runtime/` zawiera obok plików stanu (`worker-lanes.json`,
  `remote-reviewer.json`, `local-reviewer.json`, `*.pid.json`) i logów
  także dane trwałe: `v7-label-geometry/` (profile i sesje kalibracji
  V7), `v7-selection/`, `v7-model-download/`,
  `reviewer-ingress-controller-results/`, pliki JSON audytów pozycji
  plansz, `grid-v3-deployment-services.json`, oraz katalogi `pytest-*`,
  `task08xx/`, `t928*/` (tymczasowe wyniki testów).
- Fakt: worker na C dopisuje do `artifacts/` w trakcie joba `d9a49da0`;
  przebiegi `Initial` mogą pomijać pliki w użyciu.
- Fakt: `.tooling/` zawiera klucze podpisu wydania: nie wypisywać ich
  zawartości ani nazw w logach i `Outcome`.
- Wolne miejsce na D ≥ 100 GB (skrypt sprawdza przed startem).

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Skrypt PowerShell z `robocopy`,
kontraktem kodów wyjścia i manifestami; bez logiki domenowej. Eskalacja
do `claude-opus-5-5`, `high`, gdy manifesty w trybie `Final` różnią się
mimo zatrzymanych usług.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcja 5.2)

## Scope

- Nowy skrypt `scripts/sync_data_directories_to_d.ps1` (proponowany):
  - tryb `-Inventory`: lista wpisów ignorowanych w `-Source`
    (`git ls-files --others --ignored --exclude-standard --directory`,
    rozmiary) z klasyfikacją: **odtwarzalne** = `node_modules`, `.next`,
    `.venv*`, `.pnpm-store`, `__pycache__`, `.pytest_cache`, `.mypy_cache`,
    `.ruff_cache`, `packages/*/dist`, `*.tsbuildinfo`, `*.egg-info`,
    `.claude/scheduled_tasks.lock`, `.runtime/pytest-*`, `.runtime/task0*`,
    `.runtime/t928*` i logi `.runtime/*.log`; **obsługiwane osobno, nigdy
    kopiowane jako katalogi** = oba korzenie worktree'ów `worktrees/` i
    `.claude/worktrees/` (ich pliki `.git` wskazują bezwzględnie
    repozytorium C; dane każdego worktree'a inwentaryzuje i zabezpiecza
    TASK-0954, a worktree'y na D odtwarza `git worktree add`); skrypt
    wyklucza oba korzenie zawsze, także gdy `-Directories` je wymienia;
    **zachowywane** = wszystko inne, w tym cały
    `.runtime/` poza wymienionymi (pliki stanu procesów są zachowywane w
    kopii, a czyszczone na D w TASK-0956), `.tmp/`,
    `.claude/settings.local.json`, `TEMP PLAN V2 GEOMETRY.md`, `tmp-*.out|err`;
    wynik `INVENTORY-<source>.md` w `-LogRoot`; nowy, niesklasyfikowany
    wpis jest zachowywany i raportowany jako „nowy”;
  - parametry `-Source` (domyślnie `C:\Users\tuszy\Documents\game_predicotr`),
    `-Destination` (domyślnie `D:\game_predicotr`), `-Mode Initial|Final`
    (wymagany poza `-Inventory`/`-VerifyOnly`), `-Directories` (domyślnie
    wszystkie zachowywane wpisy z inwentarza; przy wywołaniu przez
    `powershell -File` lista jako jeden ciąg rozdzielany przecinkami,
    dzielony i przycinany przez skrypt, jak w `audit_task.ps1 -Paths`),
    `-Manifest <plik>` (dla `-VerifyOnly`: porównanie celu z zapisanym
    manifestem, bez odczytu źródła, bez odrzucania plików nieobecnych w
    manifeście; raport: brakujące i o innym hashu), `-LogRoot`
    (domyślnie `D:\game_predictor_backup\sync-logs`, poza kopiowanym
    zbiorem), `-Mirror` (tylko w `Final`, wymaga `-Confirm:$true` i listy
    plików istniejących wyłącznie na D zatwierdzonej przez operatora),
    `-VerifyOnly` (samo porównanie manifestów bez kopiowania; używane też
    przez TASK-0957 do kontroli zachowanych plików względem manifestu B1);
  - `robocopy /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /MT:8 /NP /NFL /NDL
    /LOG+:<log>`; wykluczenia jawne i raportowane: `node_modules`, `.next`,
    `__pycache__`, `.pytest_cache`, `*pytest-run*` (nieczytelne korzenie
    pytest, np. `artifacts/vision-lab/t06b-pytest-run1`, ERROR 5) (nie są danymi trwałymi; skrypt wypisuje, ile plików
    pominął w każdym wykluczeniu);
  - kontrakt kodów `robocopy` (bity: 1 skopiowano, 2 dodatkowe w celu,
    4 niezgodne, 8 błąd plików, 16 błąd fatalny): `Initial` kończy się
    kodem 0 przy wyniku ≤ 7, przy bicie 8 kodem 0 z jawnym znacznikiem
    `INCOMPLETE` i liczbą plików z błędem, a przy bicie 16 kodem 1
    (fatalny, bez dalszych katalogów); `Final` kończy się kodem 1 przy
    każdym wyniku ≥ 8, przy bicie 4 i przy każdej rozbieżności manifestów;
  - manifest: dla każdego katalogu plik `<nazwa>.manifest.tsv` (ścieżka
    względna, rozmiar, SHA-256) dla źródła i celu, zapisany w `-LogRoot`;
    w `Initial` tylko ścieżka i rozmiar (szybki, informacyjny); w `Final`
    pełny SHA-256 obu stron i porównanie: brak, nadmiar, różny hash;
  - sprawdzenie wolnego miejsca przed startem; limit czasu per katalog
    jako parametr (`-TimeoutMinutes`, domyślnie 240) i przerwanie z kodem 2.
- Wpis npm `data:sync:d` (proponowany) w `package.json`, przekazujący
  parametry, i akapit w `ai_docs/guides/DATABASE_MAINTENANCE.md`, sekcja 5.2.
- Pierwszy pełny przebieg `Initial` i co najmniej jeden przebieg przyrostowy
  z zapisem kodów wyjścia i czasów w `Outcome`. Tryb `Final` wykonuje
  TASK-0955.

## Out of scope

- Usuwanie czegokolwiek na C. Kopiowanie `node_modules`, `.venv`,
  `worktrees/`, `.claude/worktrees/` (odtwarzane narzędziami).
  Synchronizacja po przełączeniu (zabroniona do aktywnych katalogów D).

## Acceptance criteria

- [ ] `-Inventory`: każdy wpis ignorowany na C sklasyfikowany; wpisy
      „nowe” wymienione w `Outcome`; domyślna lista `-Directories` równa
      zbiorowi zachowywanych; `worktrees/` i `.claude/worktrees/` nigdy w
      kopii (test: podanie ich w `-Directories` → pominięte z ostrzeżeniem).
- [ ] `Initial`: kod 0, podsumowanie z liczbą skopiowanych, pominiętych
      i błędnych plików per katalog, znacznik `INCOMPLETE` przy błędach.
- [ ] `-VerifyOnly -Manifest <B1>` na celu z jednym nowym plikiem D →
      kod 0 (nowe pliki poza porównaniem); z jednym zmienionym plikiem z
      manifestu → kod 1 z nazwą.
- [ ] Drugi przebieg `Initial` kopiuje tylko nowe/zmienione pliki.
- [ ] `Final` (test na małym katalogu przy zatrzymanych zapisach, np.
      `examples/imgs` i `work`): manifesty równe, kod 0. Test brakującego
      pliku wykonać na samym porównaniu manifestów (`-VerifyOnly`, bez
      kopiowania), bo pełny przebieg najpierw dokopiuje plik: po usunięciu
      jednego pliku z celu `-VerifyOnly` daje kod 1 z nazwą pliku.
- [ ] `-Mirror` bez `-Mode Final -Confirm:$true` → odmowa z kodem 1.
- [ ] `.tooling/` skopiowane; `npm run windows:environment:check` z D nie
      zgłasza brakujących plików toolchainu (zmienne mogą jeszcze
      wskazywać C; naprawia TASK-0956).
- [ ] Brak nazw ani zawartości kluczy podpisu w logach i `Outcome`.

## Technical notes

Plik zajęty daje `ERROR 32` i bit 8; `robocopy` kontynuuje. `Initial`
raportuje liczbę takich plików i nie przerywa. `/COPY:DAT` zachowuje czasy;
sam rozmiar i czas nie dowodzą równości zawartości, dlatego `Final` liczy
SHA-256 obu stron (ok. 77 GB; czas zmierzyć i zapisać; uruchamiać w tle z
limitem). `.runtime` skopiowany z C zawiera nieaktualne PID-y lane'ów i stan
tunelu; TASK-0956 czyści je przed pierwszym startem z D. Logi i manifesty
leżą poza kopiowanym zbiorem, więc nie tworzą różnicy.

## Expected files

- Nowy: `scripts/sync_data_directories_to_d.ps1`.
- Istniejące: `package.json` (skrypt `data:sync:d`),
  `ai_docs/guides/DATABASE_MAINTENANCE.md` (5.2).

## Test cases

- Pusty cel, `Initial` → pełna kopia, kod 0.
- Plik dopisany w źródle po pierwszym przebiegu → drugi przebieg kopiuje
  1 plik.
- Plik zajęty przez inny proces, `Initial` → `INCOMPLETE`, kod 0.
- Ten sam przypadek, `Final` → kod 1.
- Plik o tym samym rozmiarze i czasie, innej treści (test na kopii) →
  `Final` wykrywa różny hash.
- `-Mirror` bez potwierdzenia → odmowa.

## Verification

```powershell
# katalog repozytorium; Initial w tle (do kilku godzin), kolejne ≤ 10 min
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Inventory
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Initial
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Final -Directories "examples\imgs,work"
```

## Risks / open questions

- Czas pierwszej kopii i czas liczenia SHA-256 nieznane; mierzyć.
- `/MT:8` utrudnia czytanie logu; `/NFL /NDL` ograniczają log do
  podsumowania i błędów.

## Outcome

Executed 2026-10-10 01:44–02:20 local time by Claude Code (`claude-opus-5-5`;
the plan table assigns `claude-sonnet-5-5` high, recorded deviation to a
stronger model after the operator switched models). Services and the Mumie
`validate` job kept running; only `Initial` passes touched real data.

### Changed

- New `scripts/sync_data_directories_to_d.ps1` (ASCII, PowerShell 5.1):
  `-Inventory`, `-Mode Initial|Final`, `-VerifyOnly [-Manifest]`,
  `-Directories` (comma separated string accepted), `-AllowExtras`,
  `-Mirror -Confirm -MirrorApprovedList`, `-TimeoutMinutes`, `-Threads`,
  `-LogRoot`. Robocopy contract: Initial exits 0 for <= 7 and marks bit 8 as
  `INCOMPLETE`, bit 16 exits 1; Final exits 1 for >= 8, bit 4, any missing,
  different or extra file (`-AllowExtras` only for `-VerifyOnly`). SHA-256 manifests per
  entry, `.tooling` paths redacted to `redacted:<sha256>`, worktree roots
  `worktrees/` and `.claude/worktrees/` never copied, long paths via `\?\`.
- Exclusions inside entries: `node_modules`, `.next`, `__pycache__`,
  `.pytest_cache`, `*pytest-run*`; inside `.runtime` also `pytest-*`,
  `task0*`, `t928*`. `*pytest-run*` was added after the first run hit
  `ERROR 5` on the unreadable test leftover
  `artifacts/vision-lab/t06b-pytest-run1` (no readable content).
- `package.json`: `data:sync:d`. `ai_docs/guides/DATABASE_MAINTENANCE.md`,
  section 5.2: usage of the script for a whole-checkout move.
- Codex audit round 1 (REVISE, 4 P0, 6 P1, 1 P2) fixed in the same task:
  - `-Mirror` deletes only files that are both approved and currently extra,
    then re-lists the destination, recompares and writes the destination
    manifest after the deletion (P0-1);
  - `-Directories` is canonicalised (`./` stripped, `.`/`..`, absolute and
    empty paths rejected), worktree roots are matched case-insensitively and
    excluded at every level when a parent such as `.claude` is selected,
    including robocopy `/XD <full path>` (P0-2);
  - `.tooling` paths are redacted case-insensitively in manifests, summaries,
    error messages and robocopy logs (logs are rewritten after each run)
    (P0-3);
  - reproducible patterns narrowed to the task scope: `dist` only under
    `packages/*` or `apps/*`, `coverage` and `.expo` only at the root or under
    an app/package (P0-4);
  - inventory marks preserved entries outside the plan's known list as
    `new` (column and summary line; copy runs print a NOTICE) (P1-1);
  - every verify line reports `excluded=<rule>:<files>` (or `unreadable`);
    enumeration errors make Initial `INCOMPLETE` (P1-2);
  - needed space counts only source files missing or different in size on
    the destination (P1-3);
  - `-LogRoot` inside the source or destination is rejected (P1-4);
  - `.runtime/*.log` is excluded (`/XF *.log`) as the task requires (P2-1).
- Codex audit round 2 (REVISE, 3 P0, 2 P1) fixed in the same task:
  - `-Mirror` refuses to delete anything when the entry's robocopy status is
    not OK or any listing or hash error occurred, because an incomplete read
    can make a source file look extra (P0-1);
  - robocopy output is captured from stdout in memory (no `/LOG`) and only
    the redacted text is written; redaction covers everything after
    `.tooling\` up to the end of the line, so names with spaces are covered;
    entries below `.tooling` cannot be selected (P0-3);
  - `-AllowExtras` is refused except for `-VerifyOnly` without `-Manifest`;
    Final always requires equal manifests (P0-5);
  - `-VerifyOnly -Manifest` checks only the manifest's files (plain keys by
    direct path, redacted keys through a listing whose errors count only if
    a key stays unresolved), so unreadable new destination branches do not
    fail it (P1-7);
  - `-TimeoutMinutes` (and the new `-TimeoutSeconds` override) is a deadline
    for the whole entry: listing, robocopy and chunked SHA-256 hashing;
    exceeding it exits 2 (P1-8).
- Codex audit round 3 (REVISE, 2 P0, 1 P1) fixed in the same task:
  - redaction replaces everything after `.tooling\` up to the end of the
    line, so apostrophes and spaces in directory or file names no longer end
    the match (P0-3);
  - result file names get a 12-character hash of the relative path
    (`work/a_b` and `work/a/b` no longer collide) (P0-6);
  - the deadline is checked inside directory and file loops (every 2 000
    files), in the excluded-file counter (manual traversal) and in chunked
    hashing; one budget per entry is shared by the pre-copy listing, copy,
    listing and hashing (`Start-EntryBudget`/`Stop-EntryBudget`) (P1-8).
- Codex audit round 4 (REVISE, 1 P1) fixed: the deadline is also checked on
  entry to and after hashing (empty files), on every manifest item, on every
  subdirectory of the excluded-file counter and when an entry's budget is
  closed (`Stop-EntryBudget`), so an exhausted budget always ends with
  `TIMEOUT`/exit 2. Function-level test with a passed deadline: empty-file
  hash, manifest loop, excluded counter and budget close all throw
  `TimeoutException`; a regression Final run with an empty file passes.
- Codex audit round 5 (REVISE, 1 P1) fixed: an explicitly selected entry
  that is reproducible itself, lies inside a reproducible entry, has an
  excluded directory name in its path or is an excluded `.runtime` path is
  skipped with a warning (`Get-SelectionExclusion`). Test: `node_modules`,
  `.venv`, `artifacts/x/node_modules/c`, `.runtime/pytest-9`,
  `.runtime/r.log` and `packages/x/dist` skipped, `artifacts/ok` and
  `.runtime/keep` copied and verified, result `OK`.
- Codex audit round 6 (REVISE, 1 P0, 1 P1) fixed: manifest, comparison and
  mirror sets use `OrdinalIgnoreCase` like the file listings (NTFS is
  case-insensitive), so `a.txt` on one side and `A.txt` on the other are
  the same file and never an extra that `-Mirror` could delete (test:
  destination `A.txt` approved for deletion, source `a.txt`: no extra,
  nothing deleted, `OK`); `-VerifyOnly -Manifest` starts the deadline
  before reading the manifest, `Compare-Manifests` checks it on every key
  and a final check runs before the result (function test with a passed
  deadline: `TimeoutException`).
- Codex audit round 7 (REVISE, 1 P0) fixed: the default inventory also
  lists untracked, not ignored entries (`git ls-files --others
  --exclude-standard --directory`), marked `untracked`, so `v7-output/` is
  part of every default Initial/Final run and its B1 manifest. Test:
  untracked `v7-output/run1/r.json` and `stray.txt` (reported `new`)
  inventoried, copied and verified by a default Final, exit 0.
- Codex audit round 8: **PASS** (no P0/P1). Its P2 (validation errors
  printed by `Fail` without redaction) is applied: `Fail` passes the
  message through `Protect-Text`; `-Directories '.tooling/test-key.jks/..'`
  now prints only `redacted:<sha256>`.
- A bug found while testing the fixes: piping the wrapped exclusion arrays
  passed all `/XD` patterns as one quoted argument; the arrays are now
  assigned before use, and the test below proves `.runtime/pytest-*` stays
  out of the copy.
- Data on D: `D:\game_predicotr` now holds all 98 preserved ignored entries
  of the C checkout (about 80 GB, about 400 000 files) plus `v7-output/`
  (untracked, copied explicitly).

### Verification results

- Throwaway repository (scratchpad), all as expected: Final copy and equal
  SHA-256 manifests (exit 0); `-VerifyOnly -Manifest` ignores a new
  destination file (exit 0) and reports a changed file (exit 1); plain
  `-VerifyOnly` reports missing and extra (exit 1); `-Mirror` without
  confirmation refused (exit 1); listed `worktrees` skipped with a warning;
  Final with an extra file fails (the `-AllowExtras` pass of this first run
  is no longer possible after round 2); `-Mirror` with
  an approved list deletes exactly that file; `.tooling` paths redacted;
  `node_modules`, `.runtime/pytest-*` and nested `node_modules` excluded.
- `-Inventory` on C (20 s): 98 preserved, 59 reproducible, 2 worktree roots;
  largest entries `artifacts/data` 227 072 files / 40.5 GB and
  `imports/browser-selections` 118 529 files / 32.0 GB.
- Initial run 1 (`sync-logs\20261010-015242-Initial`): needed 84.9 GB,
  `artifacts/data` copied in 45 s, `imports/browser-selections` in 22 s,
  `.tooling` 12 181 files in 2 s; result `INCOMPLETE` only because of the
  unreadable `t06b-pytest-run1`; size manifests equal for every entry.
  `v7-output` run: `OK`.
- Initial run 2 (`sync-logs\20261010-020051-Initial`, after the exclusion):
  3 files copied (changed `.runtime` state), every other file skipped,
  result `OK`, exit 0.
- Final on real entries `work`, `TEMP PLAN V2 GEOMETRY.md`,
  `.claude/settings.local.json` (`sync-logs\20261010-020051-Final`): SHA-256
  manifests equal, exit 0.
- `configure_windows_user_environment.ps1 -CheckOnly` run from D passes the
  toolchain file checks and stops only at the user variable that still
  points to C (`GAME_PREDICTOR_NODE_HOME is not persisted`), which TASK-0956
  fixes by design.
- `prettier --check` on the changed Markdown and `package.json`: clean.
- After the audit fixes, second throwaway repository (scratchpad
  `synctest2`), all as expected:
  - inventory: `artifacts/dist` preserved, `packages/x/dist` reproducible,
    unknown entries reported as `new`;
  - Final: `.claude/worktrees` excluded (`excluded=worktree:.claude/worktrees:1`),
    `.runtime/pytest-1` and `.runtime/run.log` excluded, manifests equal;
  - `-Directories "./worktrees,.claude,.CLAUDE/worktrees"`: both worktree
    forms skipped with a warning, `.claude` copied without its worktrees;
  - `../x` rejected, `-LogRoot` inside the destination rejected (exit 1);
  - `-Mirror` with an approved list naming an extra file and a source file:
    only the extra file deleted, result OK;
  - same size and same timestamp, different content: robocopy skips the
    file, Final reports `different` and exits 1;
  - exclusively locked `.tooling` file: Initial `INCOMPLETE` (robocopy 9,
    exit 0), Final `FAIL` (robocopy 8, exit 1); robocopy logs and summaries
    show `redacted:<sha256>` instead of the path; no key file name in any log;
  - `-VerifyOnly -Manifest`: a new destination file is ignored, a changed
    file fails (exit 1).
- After the round 2 fixes, third throwaway repository (`synctest3`, removed
  afterwards), all as expected:
  - Final default: worktree roots, `.runtime/pytest-*` and `.runtime/*.log`
    excluded, manifests equal, exit 0;
  - `-Mode Final -AllowExtras` and `-Directories ".tooling/key dir"` refused
    (exit 1);
  - locked `.tooling/key dir/upload key.jks` (space in the name): Final
    `FAIL`, exit 1, no key file or directory name in any log;
  - `-Mirror` with an approved extra file while a source file is locked:
    `mirror refused`, nothing deleted, exit 1;
  - `-VerifyOnly -Manifest` with an unreadable new destination directory
    (deny ACL): `OK`, exit 0; the same tree with plain `-VerifyOnly`
    reports the access error;
  - 3 GiB file, Final with `-TimeoutSeconds 2`: robocopy skips the file,
    hashing is interrupted, `TIMEOUT`, exit 2.
- After the round 3 fixes (`synctest4`, removed afterwards):
  - locked `.tooling/operator's keys/upload.jks`: Final `FAIL`, no part of
    the directory or file name in any log;
  - `-Directories "work/a/b,work/a_b"`: two distinct manifests
    (`work_a_b-0387f9e589a9`, `work_a_b-cd0e6d1f8546`), both `OK`;
  - function-level test (functions loaded from the script AST, deadline
    already passed): `Get-FileCount` and `Get-EntryFiles -CountExcluded`
    over 30 000 excluded files throw `TimeoutException`; with 4.5 s of a 5 s
    budget used the next phase gets 0.5 s; an exhausted budget throws at
    phase start; `Protect-Text` redacts a path with an apostrophe.
- PowerShell parser: no errors; script is ASCII-only.
- `docs:check` scripts (main `.venv`): `check_decision_links: OK`,
  `check_current_state_window: OK`.
- `python scripts/generate_code_map.py` regenerated `CODE_MAP.md` (new
  script and `data:` prefix); `--check`: up to date.

### Not completed

- Final over all entries: belongs to TASK-0955 step 4 after the services stop.

### Documentation updates

- `ai_docs/guides/DATABASE_MAINTENANCE.md` 5.2, this Outcome,
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- TASK-0954.
