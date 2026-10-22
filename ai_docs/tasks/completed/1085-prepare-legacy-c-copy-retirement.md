---
title: TASK-1085 — Przygotowanie bezpiecznego usunięcia starej kopii na C
status: done
last_updated: 2026-10-22
---

# TASK-1085 — Przygotowanie bezpiecznego usunięcia starej kopii na C

## Status

`done` — przygotowanie techniczne gotowe; audyt Claude PASS bez P0/P1.
Siedem P2 rozliczono jako ograniczenia przygotowania i warunki przed wykonaniem.

## Goal

Przygotować zweryfikowane zabezpieczenie starej kopii oraz konkretny podgląd
zmian pozwalających odłączyć `C:\Users\tuszy\Documents\game_predicotr`.

## Context

Operator zlecił ustalenie przydatności starych importów i pełne przygotowanie
usunięcia C. Zaakceptował zakres i koszt 30–60 minut w czacie 2026-10-22.
Usunięcie katalogu, operacje destrukcyjne, migracja danych operatora, restart
usług i scalenie pozostają osobnymi bramkami. W D przed zadaniem są dwa
usunięte pliki artifacts/v7-main-panel-entry-20261007 oraz obcy katalog roboczy;
nie należą do tego zadania. Praca: `codex/retire-c-copy` w osobnym worktree.

## Dependencies / entry conditions

- Odczyt tylko do odczytu: 179 jobów wskazuje C; wyłącznie
  `input_payload.source_directory`, bez ścieżek C w checkpointach.
- 113 completed oraz 7 failed/cancelled to preflighty validate. 53 importy
  waiting_for_review i 6 failed. Importy mają 108835 source_images oraz
  1792 kanoniczne pozycje; sześć failed nie ma source_images.
- Wszystkie 179 katalogów istnieje na D; zgodność treści nie była sprawdzona.
- 14 sesji selekcji jest bez kolekcji, batchy, plików, operacji, transferów
  i akcji hosta. Cztery ze statusem active są już po expires_at.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`: kontrola trwałości danych, manifestów,
kopii repozytorium i ograniczonego narzędzia operatorskiego. Niezależny
przegląd `claude-opus-5-5`, `medium`, przed commitem; brak odpowiedzi w
limicie skilla zostaje jawnie odnotowany. Nie rozszerzać na sprzątanie baz.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md`
- `ai_docs/tasks/completed/0957-disk-d-cleanup-and-job-paths.md`

## Scope

1. Utrwalić odczyt zależności jobów i pustych wygasłych sesji oraz ocenę
   przydatności importów. Nie usuwać importów ani plansz.
2. Zabezpieczyć aktualne referencje starego Git i zmiany jego worktree.
3. Porównać zachowywane pliki C z D przez SHA-256; brakujące i różniące się
   zachować w odrębnym archiwum. Praca wznawialna i ograniczona czasowo.
4. Przygotować podgląd zmian ścieżek z warunkami zapisu i odtworzenia.
   Sprawdzić zależności manifestów oraz możliwość działania z nowego procesu.
5. Testy narzędzia, lint, typecheck, raport i zamknięcie taska. Przed
   jakąkolwiek migracją danych operatora przedstawić konkretny podgląd.

## Out of scope

- Usunięcie C, zmiana nazwy C, kasowanie importów, wygaszanie sesji.
- Zmiany schematu, GC, stare vhdx, backupy i sąsiedni game_predictor_vision_data.
- Restart, aktywacja modeli, push i merge.

## Acceptance criteria

- [x] Raport rozróżnia historię preflightów, używane importy i puste sesje.
- [x] Git C i wszystkie jego zarejestrowane worktree mają zabezpieczenie.
- [x] Zachowywane pliki mają weryfikację SHA i bezpieczny odpowiednik na D
      albo jawny blocker; żaden aktualny plik D nie został nadpisany.
- [x] Podgląd zmian nie przedstawia historycznych ścieżek jako aktywnych
      zależności bez kontroli ich konsumentów.
- [x] Narzędzie odmawia zapisu po zmianie danych względem podglądu.
- [x] Wyniki, ograniczenia i kolejny krok są zapisane w raporcie.
- [x] Kontrole zmienionych części i docs:check zaliczone; audyt rozliczony.

## Technical notes

Manifest zarządzanych oryginałów jest niezmiennym dowodem. Jego sourceDirectory
może nadal wskazywać C mimo poprawnego input_payload joba. Nie przepisywać
manifestów ani ich checksum bez analizy konsumentów. Archiwum nie jest
zamiennikiem operacyjnego źródła importu. Porównania plików nigdy nie
synchronizują C do aktywnego D. Nowe procesy nie mogą korzystać z ukrytej
instancji API/workera. Istniejące serwisy pozostają po stronie operatora.

Potwierdzona poprawka: job importu dostaje jawny receipt
`source_directory_relocation` (previous/current, contract_version=1). Loader
zmienia wyłącznie operacyjny katalog pasującego manifestu; nie preferuje
bezwarunkowo katalogu joba, bo managed reprocess może mieć inną bazę źródła.
Pozostałe joby zachowują domyślne zachowanie. Narzędzie zapisu sprawdza nowy
loader przed jakąkolwiek zmianą bazy, blokuje wszystkie wiersze i porównuje
je z podglądem. Tej operacji jeszcze nie uruchomiono.

## Expected files

- Nowe proponowane: `scripts/prepare_legacy_copy_retirement.py`, test skryptu
  w `services/api/tests/`, `ai_docs/quality/LEGACY_C_COPY_RETIREMENT_20261022.md`.
- Ewentualna poprawka ładowania źródła manifestu tylko po potwierdzeniu
  potrzeby; osobny test regresji, zachowane bajty niezmiennych dowodów.
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`, `CURRENT_STATE.md`.
- Zmienione: oba walidatory preflightu i ich testy (opcjonalny receipt),
  `ai_docs/DOC_INDEX.md` (raport operatora).
- `scripts/audit_task.ps1` i `scripts/tests/test_auditor_cli.ps1`: usunięcie
  blokera audytu — wykrywanie aplikacji w `AppData/Local/Claude-Data/*/claude-code`
  bez utrwalania wersji, builda ani nazwy pakietu. Skrypt przekazuje jawny
  effort Claude według planu; starszy CLI bez opcji jest odrzucany kodem 3.

## Verification

Polecenia z `D:\game_predicotr\worktrees\retire-c-copy`, Python z
`D:\game_predicotr\.venv\Scripts\python.exe`. Każdy proces skończony ma
timeout ≤120 s; porównanie plików jest dzielone na wznawialne odcinki.
Testy: małe katalogi z kopią zgodną, różniącą się, brakującą, dowiązaniem,
zmianą po podglądzie i wznowieniem; wyłącznie odizolowane fixture'y.

## Outcome

Commit: v1.7.460 (hash dopisuje kolejny commit).

### Changed

- Narzędzie wznawialnego porównania SHA i archiwizacji różnic, bez zapisu do
  aktywnego D. Checkpointy, kontrola dowiązań, publikacja atomowa archiwum.
- Narzędzie preview/apply z SHA podglądu, kontrolą plików, weryfikacją wersji
  loadera, blokadami wierszy i odmową zapisu po zmianie stanu.
- Loader respektuje jawne potwierdzenie relokacji. Bajty manifestów bez zmian;
  domyślne zachowanie managed reprocess chronione testem regresji.
- Bundle Git zweryfikowany; wszystkie referencje C i oba worktree zabezpieczone.

### Verification results

- Końcowy komplet 78 testów: narzędzia, source ingestion, oba preflighty
  i wznowienie po przycięciu oryginału — PASS, 11.97 s. Po usprawnieniu
  paczek/wznowienia 16 testów narzędzi — PASS, 2.27 s. Nowy proces korzysta
  z kodu worktree, nie z
  editable install głównego checkoutu. Odtworzenie z nowego folderu bez C.
- Ruff zmienionych plików — PASS. Mypy dwóch nowych skryptów z
  `--follow-imports=skip` — PASS.
- Mypy workera w tym samym trybie ma istniejący błąd no-any-return (487 w
  main, przesunięty po zmianie); potwierdzony również na niezmienionym main.
  Pełny mypy zależności przekroczył 110 s i ujawnił wcześniejsze błędy
  source_lattice_geometry.py:36,38. Końcowa kontrola procesów potwierdziła
  brak osieroconego typechecku; brak zmian poza taskiem.
- Odczyt bazy: 179 starych ścieżek, 55 różnych folderów, 14 pustych wygasłych
  sesji. 59/59 manifestów ma ten sam dawny katalog co input joba; wszystkie
  112423 wskazane zarządzane oryginały istnieją na D.
- Świeży końcowy odczyt 434131 plików — PASS, zero błędów. 311795 zgodnych
  plików na D (76020477970 B), 122336 starszych/brakujących wersji w osobnym
  archiwum (9822323477 B). 10 dowiązań, żadne do D. Obsługa długich ścieżek
  Win32 potwierdzona testem i ponownym rzeczywistym skanem bez błędów.
- Świeży podgląd bazy i ponowny SHA 55 folderów wejściowych — PASS,
  blockers=[], 179 jobów. SHA podglądu:
  `e8b592828aea9e4f33dc701ec85ec95089b84a9a820734b549e3f6835345efe2`.
- Nowy proces rozwiązał do D wszystkie 176 istniejących manifestów jobów
  z podglądu; żadnych zmian w bajtach tych manifestów.
- Bundle ponownie porównany z aktualnymi referencjami C: 39/39 obecnych.
- docs:check i code-map:check — PASS. Końcowe docs:check po oznaczeniu
  blokera również PASS: 2 aktywne taski, 12562 B okna stanu, 11/11 budżetów.
- Pierwotne wykrywanie CLI obejmowało starsze lokalizacje; po uwadze operatora
  potwierdzono nowy katalog aplikacji `AppData/Local/Claude-Data/*/claude-code`.
  `--version`: 2.1.304 (Claude Code), kod 0. Dodano trwałe wykrywanie z testem.
  Test wykrywania 10/10 PASS z nowego procesu. Operator nie zrezygnował
  z audytu i jawnie zatwierdził przekazanie briefu do Claude (Anthropic).
- [Audyt Claude](../../quality/TASK-1085_AUDIT_claude-opus-5-5.md) — PASS,
  runda 1, claude-opus-5-5/medium, bez P0/P1. Siedem P2 pozostaje jawnie
  przyjętych dla zakresu przygotowania; bez kolejnej rundy audytu.
  P2-1/2: sprawdzenie 176 manifestów i restart operatora są ręcznymi
  warunkami, nie gwarancją wersji działających workerów. P2-3: bez edycji
  zatwierdzonego pliku, pełny przegląd before/after. P2-4: brak propagacji
  relokacji do reprocessu wymaga poprawki/testu przed odcięciem C. P2-5:
  pełny odczyt kolumn tekstowych/JSON bazy przed odcięciem. P2-6: effort
  sprawdzony rzeczywistym audytem, brak automatycznego testu składania
  argumentów. P2-7: test pełnej transakcji na izolowanej bazie przed apply.
  Szczegóły i uzasadnienia: raport przygotowania, tabela ograniczeń.
- Format zmienionych plików Python: 10/10 bez zmian, PASS.

### Not completed

- Żadnych UPDATE, restartów, odcięcia ani usunięcia C; te operacje wymagają
  osobnej zgody po konkretnym podglądzie. Scalenie i push niewykonane.
- Migracja i odcięcie C nie są odebrane. Warunki P2-1–7 pozostają jawnie
  opisane; w szczególności fallback reprocessu, pełny skan bazy i test
  transakcji muszą być rozliczone przed wykonaniem. Worktree ma junction .venv do D.

### Documentation updates

- Model danych opisuje jawny receipt relokacji i zachowanie niezmiennych
  manifestów. Raport: `ai_docs/quality/LEGACY_C_COPY_RETIREMENT_20261022.md`;
  prywatne dane/receipty: `D:\game_predicotr\artifacts\maintenance\legacy-c-20261022`.

### Recommended next task

- Najpierw warunki wykonania z raportu (reprocess, pełny skan bazy,
  izolowany test PostgreSQL i kontrola manifestów). Po akceptacji wyniku:
  scalenie, jawnie zatwierdzona migracja ścieżek,
  restart workerów przez operatora i kontrolowany odbiór bez starej nazwy C.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1085 | gpt-6.1-sol | high | Przygotowanie trwałego zabezpieczenia danych i kontrolowanego podglądu migracji. | claude-opus-5-5, medium; przegląd statyczny przed commitem. |
