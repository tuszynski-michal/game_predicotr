---
title: TASK-0953 — Przyrostowa kopia katalogów danych na D
status: todo
last_updated: 2026-10-09
---

# TASK-0953 — Przyrostowa kopia katalogów danych na D

## Status

`todo`

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
    `__pycache__` (nie są danymi trwałymi; skrypt wypisuje, ile plików
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

- TASK-0954
