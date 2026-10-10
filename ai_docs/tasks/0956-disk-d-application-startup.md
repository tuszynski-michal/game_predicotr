---
title: TASK-0956 — Pierwsze uruchomienie aplikacji z D i odbiór
status: todo
last_updated: 2026-10-09
---

# TASK-0956 — Pierwsze uruchomienie aplikacji z D i odbiór

## Status

`todo`

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
- [ ] `verify_artifact_references.py`: 0 brakujących, 0 niezmapowanych
      kolumn (albo niezmapowane wymienione z uzasadnieniem); liczby wierszy
      i liczba „zależnych od C” w `Outcome`.
- [ ] Niezmienniki względem raportu B1 spełnione; każda różnica liczników
      wyjaśniona w `Outcome`.
- [ ] Wszystkie punkty odbioru z planu zaliczone i zapisane w `Outcome`
      z wartościami; powtórzone po restarcie Windows.
- [ ] Inwentaryzacja 13 bindingów zapisana.
- [ ] Przewodniki zaktualizowane; `npm run docs:check` zielony.

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

- TASK-0957 (po co najmniej jednym dniu pracy z D)
