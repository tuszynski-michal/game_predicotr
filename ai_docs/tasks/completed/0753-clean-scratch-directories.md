---
title: TASK-0753 — S1 — sprzątanie ignorowanych katalogów scratch w root repozytorium
status: done
last_updated: 2026-09-30
---

# TASK-0753 — S1 — sprzątanie ignorowanych katalogów scratch w root repozytorium

## Status

`done`

## Goal

Skrypt z podglądem i potwierdzeniem usuwa ignorowane katalogi scratch
(`.codex-task-*`, `test-temp-*`, `t07-pytest-*`, `t6?`, `.codex-tmp`,
`.test-tmp`, `.pytest-tmp`, `.pytest_cache`, `.test-artifacts`,
`.codex-remote-attachments`) z root checkoutu, nigdy z katalogów
chronionych ani z katalogów w użyciu.

## Context

D-467, S1. W głównym checkoucie jest 65 takich katalogów (54 czytelne, 252 MB); zaśmiecają
wyszukiwanie i listowanie plików (`CLAUDE.md` każe je ignorować).

## Dependencies / entry conditions

- Wzorce zgodne z `.gitignore` (root); `.codex-tmp` i `.test-artifacts`
  nie są w nim ignorowane, więc skrypt je pomija (oba puste).
- `.tmp` jest poza zakresem: trzymają w nim logi i pliki PID serwerów
  deweloperskich innych checkoutów oraz wyniki `scripts/*_crop_v11_*.mjs`.

## Recommended execution

`claude-opus-5-5`, reasoning `low` (warunkowo). Audyt: `claude-opus-5-5`,
`medium`, osobny agent.

## Relevant docs

- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`

## Scope

- `scripts/clean_scratch_dirs.ps1` (`-Root`, `-Execute`, `-ConfirmPhrase`,
  `-RecentHours`): kandydaci tylko jeden poziom pod root, ignorowane przez
  Git i bez plików śledzonych; pomijane i tylko raportowane: reparse pointy
  (także zagnieżdżone), katalogi nieczytelne, z plikiem zapisanym w
  ostatnich 24 h albo otwartym przez inny proces; lista chroniona (`.git`,
  `.tooling`, `.venv*`, `node_modules`, `artifacts`, `worktrees`, `work`,
  `.runtime`, `.tmp`, katalogi kodu); fraza potwierdzenia związana z listą
  usuwalnych i rozmiarami; usuwanie przez `[IO.Directory]::Delete` z
  prefiksem długiej ścieżki Windows (bez podążania za reparse pointami),
  każdy katalog osobno, porażki zebrane na końcu (kod 1).

## Out of scope

- Katalogi `worktrees/*`, `artifacts`, cache Pythona w podkatalogach.

## Acceptance criteria

- [x] Podgląd w głównym checkoucie: 54 katalogi usuwalne (251,8 MiB),
  11 nieczytelnych (`t07-pytest-*`, `t6?`) do usunięcia ręcznie z
  uprawnieniami administratora, bez katalogów chronionych i bez `.tmp`.
- [x] Warunek wykonania: serwery innych checkoutów działały, ale ich katalog
  `.tmp` jest poza zakresem; pozostałe kandydaty bez zablokowanych plików
  (skrypt i tak pomija katalogi z zablokowanym, tylko do odczytu lub
  świeżym plikiem).
- [x] Wykonanie za zgodą operatora (fraza z podglądu).
- [x] Audyt bez P0–P2.

## Technical notes

- Rozmiar w podglądzie liczy tylko katalogi czytelne; nieczytelne są
  raportowane bez rozmiaru.

## Test cases

- Podgląd bez `-Execute` → 0 zmian; zła fraza → kod 2, 0 zmian.
- Katalog chroniony, reparse point, nieczytelny, z zablokowanym plikiem →
  nigdy w liście usuwalnych.
- Porażka usunięcia jednego katalogu nie przerywa pozostałych; kod 1 z listą.

## Verification

```powershell
powershell -File scripts/clean_scratch_dirs.ps1 -Root C:\Users\tuszy\Documents\game_predicotr
```

## Outcome

### Changed

- `scripts/clean_scratch_dirs.ps1`: klasyfikacja kandydatów (ignorowane,
  bez plików śledzonych, bez reparse pointów, czytelne, bez plików świeżych,
  tylko do odczytu lub otwartych), fraza potwierdzenia z listy usuwalnych,
  usuwanie każdego katalogu osobno z raportem porażek; `.tmp` chroniony.

### Verification results

- Podgląd na głównym checkoucie: 54 usuwalne (251,8 MiB), 11 nieczytelnych
  pominiętych, `.codex-tmp` i `.test-artifacts` nieignorowane (puste).
- Audyt `claude-opus-5-5`: FAIL (P1: `.tmp` w użyciu przez serwer innego
  checkoutu; P2: brak obsługi katalogów nieczytelnych i reparse pointów) →
  przepisanie → PASS; P3 wdrożone (komunikaty dla plików tylko do odczytu i
  długich ścieżek, odmowa UNC).

### Executed (2026-09-30, za zgodą operatora)

- `-Execute -ConfirmPhrase "CLEAN-SCRATCH bba515c056119eac"`: 54 katalogi
  usunięte (251,8 MiB), 0 porażek.

- 11 katalogów nieczytelnych (`t6a`–`t6i`, 2× `t07-pytest-*`) usunięto na
  polecenie operatora osobnym procesem z podniesieniem UAC (`takeown` +
  `icacls` + `Directory.Delete`, nazwy ograniczone wyrażeniem regularnym);
  root repozytorium nie ma już katalogów scratch.
