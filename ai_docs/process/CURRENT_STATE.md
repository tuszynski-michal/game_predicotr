---
title: Current project state
status: active
last_updated: 2026-10-09
---

# Current State

Ten plik jest obowiązkowym odczytem startowym i ma **okno kroczące**: zawiera
tylko (1) obowiązujące ograniczenia operacyjne, (2) plany z niezakończonymi
taskami, (3) otwarte decyzje i pytania, (4) sekcje tasków aktywnych
(`in_progress`, `blocked`, `todo`: każdy task z plikiem w `ai_docs/tasks/`) oraz
(5) 10 ostatnich sekcji `done`. Pełna historia leży bez zmian w
[archiwum Q4 2026](../archive/CURRENT_STATE_2026Q4.md) (od 2026-10-01) i
[archiwum Q3 2026](../archive/CURRENT_STATE_2026Q3.md) (wcześniej).

Reguła utrzymania: przy zamykaniu taska agent dopisuje jego sekcję `done` na
początku sekcji „Ostatnie 10 ukończonych tasków”, przenosi sekcje `done` ponad
limit 10 na początek najnowszego pliku archiwum (bez edycji tekstu), usuwa z
sekcji „Aktywne taski” sekcję zamkniętego taska i aktualizuje „Obowiązujące
ograniczenia”. Lead dopisuje hashe commitów jak dotychczas. Spójność okna
sprawdza `scripts/check_current_state_window.py` (część `npm run docs:check`).

## Obowiązujące ograniczenia

- **Wymiana 275 zdjęć Mumii (2026-10-09): zakończona.** Wszystkie zatwierdzone źródła usunięto przez pięć operacji API: 2198 plansz i 32970 komórek. [Manifest ze statusami i zakresami](../quality/MUMIE_SOURCE_REPLACEMENT_20261009.md) oraz CSV zachowują nazwy, ID i checksumy. TASK-0960 naprawił usuwanie licznika całego importu przy częściowym cleanupie; odtworzono siedem liczników z pozycji kolejki, zachowując 217 accepted reviews. Nowy odczyt: zero wskazanych źródeł, plansz, symboli i pending geometry; pięć receiptów, brak niespójnych liczników. Przygotować nową paczkę 275 zdjęć z identycznymi nazwami/rangami, jako nowy import. Oryginalne foldery i staging zachowano. Nie restartowano usług. Claude audit niedostępny (brak CLI), mypy timeout; ograniczenia zapisano w Outcome TASK-0960.

- **Panel / D-539:** tylko punkt jest poziomem nawigacji; maszyna i stawka to wybór na jego stronie. Zapisane piny każdej stawki mają być widoczne od razu, bez klikania stawki i także przy otwartym edytorze. Plan korekty jest proposed. Wcześniejszego patcha0947 nie traktować jako przetestowanej implementacji.

- **Kompaktowy panel / TASK-0945:** integracja D-538 (historyczny D-536 panelu) z D-536/D-537 Mumii w osobnym worktree. Baza operatora nie jest migrowana; przed0153 obowiązuje podgląd receipts i osobna zgoda/backup. Niezapisana praca main jest chroniona hashami. Kod i audyt zamknięte; lokalny main scalony, bez push/rollout. Pełne hashe zapisano w Outcome0945.

Ograniczenia operacyjne nadal obowiązujące, wyniesione ze starszych wpisów
(przeszukanie słów kluczowych: migracja, zgoda, blokada, PID, job, „nie
uruchamiać”, potem ręczny dobór). Każdy punkt wskazuje sekcję-źródło. Stan z
daty wpisu może być nieaktualny, więc przed poleganiem na nim zweryfikuj go
(odczyt, bez zmian w systemie).

- **Stan migracji bazy operatora.** Ostatni zapis: 2026-10-08 operator wykonał migrację `0151_super_game_roles`, `npm install` i `worker:poll`. Kod tej gałęzi wymaga `0153_merge_compact_super_games` (obie gałęzie0152: serie supergry i kompaktowy panel) (strażnik schematu startowego). Wdrożenie `0152` nie jest nigdzie odnotowane jako wykonane: stop API/worker/Admin → `npm run db:migrate` → start → `POST …/derive` dla Mumii (komórki sprzed migracji nie podbiły licznika). Przed poleganiem na tym stanie sprawdź `alembic current` (odczyt, bez zmian). Źródło: sekcja „TASK-0933 — wyprowadzanie serii supergry i API serii (done)” w tym pliku; sekcja „TASK-0932 — ewaluator `payout-v4-wild-count` (done)” w tym pliku.
- **Migracje panelu zarządzania `0148`–`0150`** (addytywne, strażnik wymaga `0150_management_sessions`) wdraża operator ręcznie; agenci nie wykonywali migracji produkcyjnej, wdrożenia ani zmian danych. Fizyczny telefon, publiczny ingress, restart komputera i czasy produkcyjne pozostają kontrolami operatora. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „TASK-0921–0927 — Management panel implementation (done)”; `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „TASK-0927 — Integrated acceptance and operator guide (done)”.
- **TASK-0928 (`in_progress`): wdrożenie na żywo zablokowane.** Job importu Mumii `092ff7a4-e652-4273-9c0a-a30e38ebd8cc` utknął na 535/2915 w `waiting_for_storage`; baza wtedy `0146_symbol_review_import_filter_index`, kod wymaga `0147_merge_v7_main`. Migracja V7 wymaga osobnej zgody lub serwisowego przejścia wykonanego przez użytkownika; nie włączać niezwiązanej migracji `0148`. Późniejsza migracja `0151` operatora sugeruje, że łańcuch jest już zastosowany: zweryfikować przed wznowieniem. Źródło: sekcja „TASK-0928 — image import storage resumption (in progress)” w tym pliku.
- **Restart workera.** Zgoda użytkownika na restart wyłącznie workera `general` dotyczyła TASK-0928 i po testach; nie przenosi się na inne taski. Istniejące procesy API/Admin (wtedy PID 6984/19496) nie są ruszane. Źródło: sekcja „TASK-0928 — image import storage resumption (in progress)” w tym pliku.
- **Cykl życia usług.** API, Admin (i Reviewer) uruchamia, zatrzymuje i restartuje wyłącznie użytkownik, w swoich terminalach; wcześniejsza zgoda na restart nie obowiązuje w kolejnych zadaniach (`AGENTS.md`, sekcja „Kontrola lokalnych usług API i Admin”). Stan z 2026-10-04: API 8000 (z `--reload` z głównego checkoutu), Admin 3000, Reviewer 3001 i worker `general`. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „Wdrożenie silnika siatek V3 — migracja 0140 i kolejka audytu działają (2026-10-04)”.
- **Migracje bazy deweloperskiej/operatora wymagają osobnej zgody** i skoordynowanego przejścia (stop usług → scalenie → `db:migrate` → start); migracja zweryfikowana na bazach `*_test` nie jest zgodą. Nie scalać do gałęzi integracyjnej kodu wymagającego nowej migracji przed jej wykonaniem: API 8000 z `--reload` w głównym checkoucie przestaje wtedy startować. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku (2026-10-01)”.
- **Udostępnianie online (D-470/D-471):** migracja `0130` i sesje udostępniania wymagały zgody operatora przed odbiorem etapu B; kody dostępu przechowywane z PBKDF2, blokada po 5 błędach, limit 5 aktywnych sesji, flaga `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED`. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q3.md`, sekcja „D-470 / D-471 — „Przybliżona wygrana”: linie, wykres, stawki; udostępnianie online (w toku)”.
- **Masowe odświeżenie nieaktualnych odczytów wyszukiwarki** (TASK-0773, D-474: ok. 88 260 plansz gry 7 sprzed późniejszej rewizji geometrii) jest osobnym zadaniem i wymaga zgody; okno planszy tylko pokazuje linie i odświeża jedną planszę. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q3.md`, sekcja „D-470 / D-471 — „Przybliżona wygrana”: linie, wykres, stawki; udostępnianie online (w toku)”.
- **Obowiązkowa kolejność dla `apply` manifestu Arbuz < 60%** (sha256 `1e4be8ce…`, 2 703 plansze): nie uruchamiać równolegle z weryfikacją w Adminie ani z jobem przeliczania predykcji. W chwili wpisu nic nie zapisano w bazie. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q3.md`, sekcja „D-464 — biblioteka wzorców symboli, etap A (w toku)”.
- **Operacje destrukcyjne na danych.** Implementacja mechanizmu destrukcyjnego (GC, cleanup, legacy deletion, `db:reset:local`) nie jest zgodą na jego wykonanie; wymaga osobnego preview i jawnego potwierdzenia. TASK-0517: baza starej gry usunięta, częściowy GC zatrzymany; dalsze usuwanie tylko za jawną zgodą. Źródło: sekcja „TASK-0517 — baza starej gry usunięta, częściowy GC bezpiecznie zatrzymany” w tym pliku.
- **Rezerwa dysku (D-534, D-530):** twarda rezerwa 5 GiB (domyślnie) dla kopiowania, normalnego pipeline i wznowienia; polityka GC i szacunki przyjęcia bez zmian. Brak migracji ani czyszczenia danych w TASK-0928. Źródło: sekcja „TASK-0928 — image import storage resumption (in progress)” w tym pliku.
- **Gra Mumie jest w statusie `draft`** (profil `grid_profile_mumie_v1`, gra `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`). Operator testuje Wild na drafcie; wyniki planszy w serii są `provisional`, dopóki super symbol nie jest zdefiniowany i generacja serii nie jest świeża (D-537): nie wchodzą do bilansu ani rozpoznanych wypłat. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „TASK-0843 — Mumie w głównej aplikacji (done: upload i preflight)”; sekcja „TASK-0936 — rozwinięcie super symbolu i koszt per pozycja (done)” w tym pliku.
- **Modele symboli Mumii:** kandydat V5 odrzucony (10/18 porównań nie przechodzi), etapu TASK-0873 nie uruchamiać z tym kandydatem; obowiązuje baseline R2 RGB. Historycznego CLI `verified_v19` nie uruchamiać (nowy CLI: `scripts/run_mumie_image_import.py`). Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „TASK-0872 — większy izolowany RGB Mumii (done; candidate rejected)”; `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „TASK-0843 — Mumie w głównej aplikacji (done: upload i preflight)”.
- **Plan symboli premium Mumii** (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`, `proposed`) czeka na decyzje operatora; od 2026-10-04 obowiązuje zakres `MUMIE_TRAINING_RESUME_20261004.md`. Zakres Super jest realizowany osobnym planem `MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` (D-535). Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku (2026-10-01)”.
- **Plan Mumie (D-535):** start każdego etapu na jawne polecenie operatora; 2026-10-08 operator zezwolił na przejście do etapu S-B bez pytań. Audyt krzyżowy wykonuje subagent Claude z innej rodziny modeli niż wykonawca do czasu zainstalowania i zalogowania CLI `codex`; zastępstwo odnotowuje `Outcome`. Merge i push tylko za zgodą operatora (merge do gałęzi integracyjnej obejmuje push). Źródło: sekcja „Plan Mumie: Wild, supergra, audyt krzyżowy (accepted, 2026-10-08)” w tym pliku.
- **TASK-0937 (pilot złotej ramki) jest `blocked`:** narzędzie gotowe (v1.7.281), odblokowanie wymaga migracji `0152` na bazie operatora, wyprowadzonej serii, co najmniej 5 zdefiniowanych super symboli i etykiet operatora (co najmniej 30 komórek na wariant wycinka); pomiar, bez zmiany produktu. TASK-0939 (narzędzia oszczędzania tokenów) jest zadaniem z pomiarem. Źródło: sekcja „TASK-0936 — rozwinięcie super symbolu i koszt per pozycja (done)” w tym pliku.
- **Znane odłożone braki bramki jakości (TASK-0940, zielona `npm run quality`):** 3 testy historycznych migracji pomijane z powodem, testy korpusów M5 bez korpusu, test junction tylko w worktree. Cztery stare testy CLI (fixture) padają także na niezmienionym HEAD (TASK-0928). Nie rozszerzać zakresu zadania o ich naprawę bez decyzji. Źródło: sekcja „TASK-0940 — zielona bramka `npm run quality` (done)” w tym pliku; sekcja „TASK-0928 — image import storage resumption (in progress)” w tym pliku.
- **TASK-0645–0647 (reweryfikacja siatek 777) są `blocked`:** D-445 wstrzymała stary weryfikator, D-447 nie upoważnia do uzupełniania slotów historycznego 777 siecią ani do zapisu na żywych danych; wznowienie wymaga osobnej decyzji i korekty planu `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`.
- **Usunięcie legacy public store (TASK-0687–0691):** DDL wymaga odrębnej zgody operacyjnej (`guides/LEGACY_PUBLIC_STORE_REMOVAL.md`); TASK-0694/0695/0698 zależą od rozstrzygnięcia sprzecznych zasad (TASK-0698). Plan ma w nagłówku `completed`, a pliki tasków są nadal aktywne: rozbieżność do wyjaśnienia. Źródło: sekcja „TASK-0687 — T08 readiness release V2-only: krytyczna bramka przed T09–T12” w tym pliku.
- **Vision lab:** D-456 zatwierdza T03k i pilota całymi grami bez pomiaru (TASK-0668); T06b (TASK-0671) czeka na rzeczywiste zatwierdzenia symboli operatora; T07–T13 (TASK-0672–0678) `todo`. Narzędzia przeglądowe/anotacyjne (porty 8103, 8105, 8107, 8108) startują ręcznie skryptami i nie mają autostartu; nie zakładaj, że działają. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku (2026-10-01)”.
- **TASK-0603** (kalibracja etykiet 777 w trybie V2) czeka na anotacje operatora; **TASK-0654** (dokumentacja „Przybliżonej wygranej”) ma ukończoną dokumentację, odbiór na żywych danych wstrzymany; **TASK-0290** (zdalna ręczna selekcja): benchmark i kontrolowany rollout `blocked`. Źródło: sekcja „TASK-0603 — ponowna kalibracja etykiet 777 w trybie V2 (w toku)” w tym pliku; sekcja „TASK-0654 — dokumentacja „Przybliżonej wygranej”; plan zaimplementowany, odbiór na żywo wstr…” w tym pliku; sekcja „Benchmark i kontrolowany rollout zdalnej ręcznej selekcji — TASK-0290” w tym pliku.
- **Kolizje numeracji.** Pliki TASK-0649–0653 (silnik V3 neural) kolidują z ukończoną serią „Przybliżona wygrana” (D-445), a TASK-0825 użyto w dwóch torach; identyfikuj plik pełną ścieżką. Równoległe sesje kolidują też w numerach TASK, D- i `vX.Y.N`: przed numerowaniem sprawdź czubek gałęzi integracyjnej. Źródło: `ai_docs/archive/CURRENT_STATE_2026Q3.md`, sekcja „TASK-0649 — „Liczba wyników” wyszukiwania plansz + kontrolowany wybór wyniku (1/6, plan D-445)”; `ai_docs/archive/CURRENT_STATE_2026Q4.md`, sekcja „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku (2026-10-01)”.
- **Odroczony plan przybliżonego snapshotu mobilnego** (`APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`, `deferred`) wymaga nowej decyzji (proponowane D-463; zmienia zasadę D-462/P4); do tego czasu zmiany tylko w aplikacji webowej.
- **Aplikacja mobilna** pozostaje w pełni offline: źródłem jest wyłącznie wersjonowany snapshot SQLite w APK, bez uprawnienia `INTERNET` w wydaniu (`CLAUDE.md`, `apps/mobile`).
- **Narzędzia tokenowe (pilot TASK-0939, obowiązują do czasu pomiaru; stałe włączenie zależy od wyniku):** hook w `.claude/settings.json` blokuje `Read` pliku > 200 KB bez `offset`/`limit` (mapa kodu: `ai_docs/architecture/CODE_MAP.md`; wyłączenie: `ai_docs/guides/TOKEN_TOOLING.md`). Serena MCP i Graphify to pilot bez stałego wpisu w `AGENTS.md` do czasu pomiaru; aktualność mapy kodu sprawdza osobno `npm run code-map:check` (poza `docs:check` i `quality`); zamykając task zmieniający moduły lub publiczne symbole, zregeneruj mapę (`python scripts/generate_code_map.py`).

## Plany z niezakończonymi taskami

### Plan przeniesienia aplikacji i bazy na dysk D (accepted, 2026-10-10)

- `delivery/DISK_D_MIGRATION_PLAN_20261009.md`, TASK-0952–0957 (`todo`),
  gałąź `feat/disk-d-migration-plan`, worktree `worktrees/disk-migration`.
- Etapy: A (kopia `pg_dump`, przyrostowy `robocopy` katalogów danych,
  push gałęzi) bez przestoju; B1 (przeniesienie `docker_data.vhdx` przez
  Docker Desktop, jedyny niepodzielny krok) i B2 (pierwszy start z
  `D:\game_predicotr`) po zakończeniu joba `d9a49da0`; C (sprzątanie,
  osobne zgody). Baza nie jest kopiowana przez `pg_dump`/`pg_restore`;
  compose z D podłącza się do tego samego kontenera (identyczny hash).
- Inwestygacja 2026-10-09 (tylko odczyt): ścieżki w `game_data_v2`
  względne; ścieżki C tylko w `jobs.input_payload.source_directory`
  (173 jobów) i `remote_manual_selection_sessions.host_base_path` (13).
- Pięć rund przeglądu Codex (gpt-6.1-sol, high, tylko odczyt): rundy 1–4
  REVISE, runda 5 PASS; raporty
  `quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round1–5.md`.
  Zaakceptowany 2026-10-10 (D-540). Etap A wykonany (v1.7.302–304).
  B1 czeka na sygnał operatora (nowe joby i zmiany równoległych sesji
  trwają); po sygnale etap A′: nowy zrzut, kopia `Initial`, nowa
  inwentaryzacja worktree'ów, decyzje o push/merge i wyborze worktree'ów
  do odtworzenia na D. Kolizja numeracji z `feat/reviewer-geometry-gaps`
  (v1.7.300–304, D-540) do rozwiązania przy merge.

### Plan korekty układu panelu (proposed, 2026-10-09)

- `delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md`, TASK-0947–0949.
- D-539 zatwierdza model wyboru maszyny; pełny plan oczekuje akceptacji/uruchomienia.
- Claude Code opus5.5/medium: pierwszyREVISE, trzyP1 doprecyzowane; końcowy przegląd aktualnej wersji na prośbę operatora PASS bezP0/P1. DwieP2 doprecyzowano (waluta i stare piny). Raport `quality/ADMIN_PANEL_LAYOUT_PLAN_FINAL_REVIEW_CLAUDE_20261009.md`; bez implementacji.
- Niezweryfikowany patch formularza odłożono; kod pozostaje na poprawce paddingu0946.
- Odczyt operatora: API snapshot200, dwa archiwalne punkty, baza0153; zapis według operatora działa. Brak produkcyjnych zmian i lifecycle usług.

### Plan Mumie: Wild, supergra, audyt krzyżowy (accepted, 2026-10-08)

- `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` i taski
  TASK-0929–0939 (`todo`) na gałęzi `feat/mumie-super-game-plan`,
  worktree `worktrees/mumie-super-game`. Cztery przeglądy Codex, ostatni
  PASS (v1.7.264). Zaakceptowany; D-535. Wszystkie taski wykonuje ta sesja
  przez subagentów; audyt Codex zastąpiony subagentem Claude do czasu CLI.
  Etapy: P, S-0, S-A, (T: 0938) S-B, S-C, S-D; start każdego etapu na
  jawne polecenie operatora. Żaden etap nie jest jeszcze uruchomiony.

## Otwarte decyzje i pytania

- Pytania produktowe: `ai_docs/project/OPEN_QUESTIONS.md`; jedyne nierozstrzygnięte
  to Q-020 (zgoda właściciela na analizę aplikacji referencyjnej; nie blokuje
  bieżących prac).
- Decyzje czekające na operatora: status planu symboli premium Mumii
  (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`), rozstrzygnięcie sprzecznych zasad
  transakcji routingu V2 (TASK-0698), osobna decyzja o wznowieniu reweryfikacji
  777 (TASK-0645–0647), decyzja D-463 dla odroczonego snapshotu mobilnego oraz
  status planu `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`).
- Decyzje architektoniczne: indeks i najnowsze pełne wpisy w
  `ai_docs/process/DECISION_LOG.md`; wszystkie wpisy mają status `accepted`
  albo `superseded`, brak wpisów `proposed`.
- Pozycje „Otwarte pytania” i „Blocked / deferred” z lipca 2026 (TASK-0076–0089,
  0143–0171, bramka `massImportAllowed`) są nieaktualne i leżą w
  `ai_docs/archive/CURRENT_STATE_2026Q3.md`.

## Aktywne taski

### TASK-0954 — zabezpieczenie repozytorium przed porzuceniem C (in_progress)

- Zabezpieczenie gotowe: `scripts/inventory_worktrees.ps1`, kopia 9 worktree'ów
  C w `D:\game_predictor_backup\repo-20261010` (patche, nieśledzone, dane
  ignorowane), `all-refs.bundle` (wszystkie 56 referencji C), weryfikacja
  odtworzenia w klonie D: OK. Klon D ma 22 gałęzie C jako `refs/remotes/c/*`.
- Czeka na operatora przy B1: push gałęzi (17 lokalnych, integracyjna +3),
  merge planu do gałęzi integracyjnej i `git pull` na D; tuż przed B1
  ponowna inwentaryzacja z `-CompareWith`.
- Task: `ai_docs/tasks/0954-disk-d-repository-handover.md`.

### TASK-0955 — przeniesienie obrazu dysku Dockera na D (todo)

- Etap B1: po zakończeniu joba `d9a49da0` i zatrzymaniu usług przez
  operatora: ostatni przebieg kopii, Docker Desktop → Disk image location
  → D (operator w UI), weryfikacja wolumenu, `db:current` = `0153`, raport
  stanu równy raportowi odniesienia z B1 (po zatrzymaniu zapisów, przed
  provisioningiem). Jedyny niepodzielny krok planu.
- Task: `ai_docs/tasks/0955-disk-d-database-cutover.md`.

### TASK-0956 — pierwsze uruchomienie aplikacji z D i odbiór (todo)

- Etap B2: `windows:environment:setup` z D, czyszczenie stanu `.runtime`
  z C, `reviewer:build`, start usług przez operatora, odbiór (zdjęcia
  plansz, kropy ze statusami, nowy tunel i sesja udostępnienia),
  aktualizacja przewodników.
- Task: `ai_docs/tasks/0956-disk-d-application-startup.md`.

### TASK-0957 — sprzątanie po przeniesieniu i ścieżki C w jobach (todo)

- Etap C, osobne zgody: podgląd i przepisanie `source_directory` w
  `jobs.input_payload`, usunięcie baz testowych (44 GB + 15 małych),
  kompaktowanie vhdx, usunięcie katalogu i starego vhdx na C.
- Task: `ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md`.

### TASK-0947 — czytelny widok punktu (todo)

- D-539: tylko punkt otwiera widok; maszyna podświetla się i pozostawia listę.
- Doprecyzowanie operatora: wszystkie zapisane piny przy wszystkich zapisanych stawkach od razu. Kod nadal ogranicza podgląd przez selectedStake && !editor; do poprawy w0947, bez zmiany API.
- Plan korekty gotowy do implementacji po końcowymClaudePASS obejmującym piny; statusproposed/todo, wykonanie jeszcze nie uruchomione.
- Task: `ai_docs/tasks/0947-management-point-workspace-layout.md`.

### TASK-0948 — formularz i historyczne kafelki (todo)

- Zapis działa według operatora; plan zabezpiecza widoczność błędu i retry w modalu.
- Przywracanie historycznych danych jest propozycją, nie nowym zaakceptowanym kontraktem.
- Task: `ai_docs/tasks/0948-management-modal-recovery-and-legacy-access.md`.

### TASK-0949 — wizualny odbiór układu (todo)

- Odrębne fixture Admin/Reviewer, utrzymanie listy maszyn i widoczne podsumowania pinów bez wyboru stawki, po Save/reload.
- Task: `ai_docs/tasks/0949-management-layout-visual-acceptance.md`.

### Benchmark i kontrolowany rollout zdalnej ręcznej selekcji — TASK-0290

- Od `v0.8.18` `Ekran startowy` otwiera zawsze wizualnie czysty konfigurator:
  oba pickery są niewybrane, nie jest pokazywany skrót powrotu do bieżącego
  workspace'u, a operator wskazuje ponownie katalog zdjęć oraz katalog zapisu.
  Jest to nadal nawigacja niedestrukcyjna — zgodna para folderów odtwarza
  zachowany manifest, decyzje, kursor i następny zakres.

- Od `v0.7.76` aktywny workspace eksponuje niedestrukcyjny `Ekran startowy`
  jako główną akcję po lewej stronie. `Restart selekcji` pozostaje po prawej
  jako akcja wtórna, która dopiero otwiera bezpieczny modal potwierdzenia.

- Od `v0.7.75` panel `Zdalna ręczna selekcja` trwale pokazuje przy wybranej
  aktywnej sesji link i kod wraz z niezależnymi przyciskami kopiowania. Kod z
  odpowiedzi create pozostaje wyłącznie w `localStorage` komputera Admina do
  TTL albo revoke; API, baza i lista sesji nadal nie zwracają surowego kodu.
  Nie ma już osobnej, znikającej sekcji „Kod jednorazowy”.

- Od `v0.7.74` ekran startowy rozróżnia relink aktywnego źródła od świadomego
  przełączenia folderu. Lokalne batch'e pozostają oddzielne i są odnajdywane po
  nazwie oraz checksummie manifestu; ponowne wskazanie zgodnej pary folderów
  wznawia postęp zamiast zgłaszać `REMOTE_SELECTION_SOURCE_CHANGED`.

- Od `v0.7.72` aktywny workspace otrzymał przycisk `Ekran startowy` obok
  restartu. Historyczny skrót `Wróć do selekcji` został zastąpiony w `v0.8.18`
  ponownym, jawnym wyborem obu katalogów.

- Od `v0.7.71` operator-local Reviewer pokazuje od razu dwa niezależne
  pickery: katalog zdjęć i katalog zapisu. Katalog nadrzędny można zapamiętać
  przed źródłem; po indeksowaniu powstaje `<źródło> wybrane`. Poprawny wynik
  wznawia zapisany kursor i zakres, a nowy modal resetu jawnie ostrzega przed
  usunięciem i blokuje skróty oraz nawigację do czasu decyzji.

- Wspólny dla lokalnej i zdalnej ręcznej selekcji wybór skoku strzałek obejmuje
  teraz również `8` oraz `9`; kolejność klawiaturowa `↑/↓` pozostaje ciągła.

- Lokalna ręczna selekcja synchronizuje przy wznowieniu należący do sesji
  manifest wynikowy z rekordem IndexedDB. Bezpieczna korekta ciągłej numeracji
  aktualizuje pierwszy i następny zakres bez ponownego kopiowania JPEG-ów;
  niezgodny manifest blokuje wznowienie.

- Od `v0.8.31` lokalny i operator-local workspace pozwalają kliknąć bieżący
  zakres i zapisać wyłącznie dodatni przedział `start–start+8`. Po decyzji
  kolejny zakres jest wyliczany względem ręcznie podanej wartości zgodnie z
  kierunkiem sesji. Manifest odtwarza takie świadome luki dokładnie, bez
  cichego wypełniania lub przenumerowywania historii.

- Historia importów plansz pokazuje przy każdym jobie przypięty silnik cięcia:
  historyczny `v18` albo pełny import `v20` korzystający z geometrii i cropów
  `v19`; źródłem etykiety jest niezmienny snapshot joba.

- Od `v0.7.70` każdy nowy staging i ponowne przetworzenie importu przypinają
  `v20 — geometria i cropy v19`. API przy braku pola także wybiera
  `verified_v19`; historyczny v18 pozostaje wyłącznie odtwarzalnym artefaktem
  już utworzonych jobów i nie jest fallbackiem.

- Monitor jobów pokazuje pod importem katalogowym i preflightem geometrii
  zakres z nazwy stagingu, np. `Zakres 19810–45162`. Nazwa stagingu jest
  metadataną prezentacyjną i nie zmienia idempotencji preflightu.

- Zamiast technicznych etykiet `Import` i `Walidacja` monitor jobów pokazuje
  opis aktualnej pracy: ładowanie zdjęć, wyznaczanie siatki i cięcie plansz,
  rozpoznawanie symboli albo tworzenie geometrii siatek.

- Po kolejnych rzeczywistych rozjazdach transferu właściciel zmienił model
  wyniku na operator-local. Od v0.7.51 link i kod wyłącznie odblokowują stronę;
  źródło, decyzje, kursor, zoom, obie osie scrolla, manifest oraz wybrane JPEG-i
  pozostają na urządzeniu operatora. Reviewer tworzy w wybranym katalogu
  nadrzędnym folder `<źródło> wybrane`; nie wysyła decyzji ani obrazów na host.
- Zdalny viewport otrzymał brakujące bazowe reguły CSS lokalnego selektora.
  Wcześniej komponent używał tych samych nazw klas i obliczał nowy rozmiar, ale
  Reviewer nie definiował wysokości viewportu, flex layoutu ani canvasu, dlatego
  wartość zoomu zmieniała się bez widocznego efektu. Scroll i zoom są utrwalane
  per sesja/partia w storage przeglądarki operatora.
- Mobilny test operator-local wykrył drugi niezależny przypadek niewidocznego
  zoomu: naturalne wymiary JPEG-a nie zawsze trafiały do stanu przez
  `onLoadCapture`. Reviewer używa zwykłego `onLoad` zgodnego z lokalnym
  selektorem i ma fallback dla obrazu już zdekodowanego z cache.
- Panel hosta nie pokazuje już pustej tabeli serwerowych partii, limitu 100 ani
  historycznych akcji recovery/reopen. Aktywny operator-local workflow utrzymuje
  wyniki wyłącznie na urządzeniu operatora, więc host zarządza tylko sesją
  dostępu i stanem połączenia.
- Lista hosta jest ograniczona do dziesięciu najnowszych sesji w porządku
  malejącym. Starsze wpisy pozostają audytowalne, ale nie rosną bez końca w
  codziennym widoku Admina. Operator może filtrować tę listę na aktywne
  (`draft/active`) i zakończone (`completed/expired/revoked`); panel pobiera
  ograniczone 100 metadanych, aby dziesięć nowych terminalnych wpisów nie
  ukrywało starszej aktywnej sesji.
- Zdalny podgląd nie resetuje już wymiarów tego samego JPEG-a po drugim refreshu
  następującym po zatwierdzeniu. Scroll poziomy i pionowy pozostają zachowane po
  `Enter`, `F` i przycisku zapisu, nie tylko po nawigacji strzałkami.
- Folder operator-local jest teraz przyjmowany tylko jako pusty albo jako
  kompletny wynik do wznowienia. Manifest przechowuje checksumę źródła, liczbę
  JPEG-ów, pierwszy zakres i kierunek; przy nowym linku odtwarza zdjęcie,
  następny zakres i decyzje, mapując je na świeże identyfikatory IndexedDB.
  Obce pliki, brak manifestu, brak wskazanego `seq_*` lub inne źródło blokują
  start przed zapisem.
- Odtworzenie scrolla po zatwierdzeniu jest przypięte do ordinalu następnego
  JPEG-a. Wcześniejsza flaga boolean mogła zostać skonsumowana przez render
  `busy` jeszcze na starym zdjęciu; teraz dopiero załadowany docelowy podgląd
  może odtworzyć i wyczyścić oczekiwanie.
- Dodatkowa regresja ujawniła różnicę względem lokalnego selektora: pozycja była
  przechwytywana przed asynchronicznym zapisem JPEG-a. Zdalny ekran przechwytuje
  ją teraz dokładnie jak lokalny — po trwałym zapisie, bezpośrednio przed
  zmianą stanu React. Test rzeczywistego komponentu przy viewportcie 390×844
  zachował `scrollTop=388,8` po zatwierdzeniu i przejściu na kolejny JPEG.
- Próba operatorska w Chrome na macOS nadal wykazała reset wewnętrznego scrolla
  wyłącznie po zatwierdzeniu; zwykła nawigacja zachowywała pozycję. Ścieżka
  zapisu przechwytuje więc `scrollLeft/scrollTop` synchronicznie przy komendzie
  Enter/F/klik, zanim rozpocznie zapis pliku i zmieni stan `busy`.
  Dodatkowym źródłem resetu był stan przejściowy: canvas znikał i `scrollHeight`
  chwilowo malał, więc Chrome mógł wymusić `scrollTop=0` po wcześniejszym
  odtworzeniu.
  Reviewer utrzymuje teraz stary canvas i jego wymiary do `decode` następnego
  JPEG-a; odtwarzanie czeka jawnie na `decoded` docelowego ordinalu.
- Kolejna próba ujawniła, że publiczny link nadal serwował proces Reviewera
  uruchomiony o 17:05, podczas gdy aktualny build powstał o 17:40. Kod poprawek
  nie był więc obecny w testowanej stronie. Po kontrolowanym restarcie aktualny
  proces wystartował o 17:56, a ten sam Quick Tunnel pozostał aktywny.
- Kontrolery lokalnego i zdalnego Reviewera wiążą teraz readiness z aktualnym
  `.next/BUILD_ID`, który produkcyjny HTML zawiera jako identyfikator builda.
  Stary produkcyjny Node na porcie 3001 jest bezpiecznie zastępowany przed
  ponownym użyciem ingressu, a stan procesu zapisuje tożsamość rzeczywistego
  listenera zamiast krótkotrwałego wrappera `npm.cmd`.
- Operator-local przechowuje teraz również uchwyt katalogu nadrzędnego wyniku.
  Usunięcie `<źródło> wybrane` albo błąd niedostępnego źródła powoduje atomowy
  reset od pierwszego zdjęcia i odłączenie obu uchwytów. Reviewer wymaga
  ponownego wskazania zgodnego folderu zdjęć i katalogu zapisu; pusty manifest
  powstaje dopiero przy jawnym uruchomieniu. Jawny `Restart selekcji` czyści
  tylko zweryfikowany folder tej selekcji; obce lub zmienione pliki blokują
  operację.
- Bieżącym aktywnym modelem symboli gry `777` jest iteracja `#3`
  `47b6aa0d-2cea-4765-97f0-ee1f86cfc056`. Weryfikacja bazy 2026-08-24
  potwierdziła status `candidate_ready` oraz aktywację z 2026-08-19; ponowna
  aktywacja zwraca poprawnie `SYMBOL_MODEL_ALREADY_ACTIVE`. Historyczna
  iteracja v19 z błędem `lemon → orange` pozostaje odrzuconym artefaktem i nie
  jest tym aktywnym modelem.
- Historyczny control outbox, transfer i materializacja pozostają w repozytorium
  do audytu, lecz nowy workspace ich nie uruchamia. Etapy rolloutowe mierzące
  transfer do hosta wymagają ponownej decyzji przed kontynuacją.

- Rozpoczęto TASK 18 po zamknięciu bramki bezpieczeństwa v0.7.41. Pierwszy pion
  tworzy deterministyczny etap 1, wersjonowany raport content-addressed oraz
  runbook kolejnych checkpointów 10/500/1000/8000/15000.
- Etap 1 przeszedł lokalnie przez `npm run remote-selection:rollout:stage1` i
  `npm run remote-selection:rollout:check`; obejmuje także stale-generation
  i exact retry przez właściwą maszynę domenową. Nie uruchomiono jeszcze
  etapów 2–5 ani środowiska LAN/publicznego.
- Lokalna podbramka etapu 2 przeszła 100 JPEG-ów przez rzeczywisty tymczasowy
  filesystem, produkcyjny streaming, materializację i finalizację. Wykryła i
  zamknęła regresję: udane ponowienie transferu anuluje starszą próbę `failed`
  tego samego pliku/generacji, zachowując audyt i twardą bramkę finalizacji.
  Raport pozostaje świadomie `blocked`, dopóki nie przejdą wymagane próby dwóch
  profili/UI, LAN, offline host/operator, restart API, revoke i nowy URL tunelu.
- Etapy 4 i 5, prawdziwy Quick Tunnel oraz testy na zewnętrznej sieci wymagają
  osobnej zgody właściciela i nie zostaną uruchomione przez implementację.
- TASK 19 pozostaje warunkowy: decyzja o chunkowanym uploadzie może powstać
  wyłącznie na podstawie raportów TASK-0290.
- Próba UI etapu 2 wykryła blokujący błąd File System Access API: identyfikator
  pickera folderu źródłowego przekraczał limit 32 znaków Chromium. Reviewer używa
  teraz stabilnego `gp-remote-source-v1`, a test regresyjny pilnuje limitu i
  dozwolonego alfabetu identyfikatora.
- Kolejna próba UI wykryła, że natywny `window.fetch` był wywoływany z obiektem
  transportu jako odbiorcą i Chromium zwracał `Illegal invocation`. Transport
  control plane oraz transfer JPEG wywołują teraz fetch z `globalThis`; dwa
  testy regresyjne chronią oba miejsca przed powrotem błędu.
- Zdalny workspace ponownie używa klas wizualnych lokalnej selekcji zamiast
  natywnie wyglądających kontrolek. Poziomy scroll podglądu jest ukryty, obraz
  pozostaje wycentrowany, a pionowy scroll jest przywracany po gotowym layoucie
  kolejnego zdjęcia. Dwa testy kontraktu pilnują parytetu UI i scrolla.
- Próba operatorska wykryła utratę szybkich decyzji oraz możliwość finalizacji
  po cyklu synchronizacji, który nie obejmował operacji dopisanych w jego
  trakcie. Interakcje są teraz szeregowane, koordynator synchronizacji wykonuje
  zaległy kolejny przebieg, a finalizacja wymaga pustego lokalnego outboxu.
  Cofnięcie przywraca również indeks zdjęcia usuwanej decyzji.
- Mobilna próba Quick Tunnel wykryła możliwość pozostania na statycznym ekranie
  `Sprawdzanie sesji…`, gdy przeglądarka odrzuca dostęp do `sessionStorage` albo
  zapytanie przez ingress nie kończy się. Id klienta ma teraz bezpieczny
  fallback pamięciowy i UUID v4 bez `randomUUID`, a context, unlock i lease mają
  wspólny limit 12 sekund zamiast bezterminowego oczekiwania.
- Kolejna próba wykryła `selected > 0` przy `transfer = synced = 0`: aktywny
  skan mógł nadpisać przewinięcie kursora transferów wykonane przez nową decyzję
  `F`. Aktualizacja kursora jest teraz warunkowa, więc starszy skan nie pomija
  świeżych wyborów. Zdalny viewport przywraca też poziomy scroll i zachowuje
  obie osie przy przejściu strzałką, decyzji, pominięciu oraz cofnięciu.
- Mobilna próba wykryła `REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY` po otwarciu
  kolejnej karty. Klient uzgadnia teraz globalny zegar sekwencji z odpowiedzią
  hosta i jednokrotnie, atomowo przenumerowuje wyłącznie niepotwierdzony outbox,
  zachowując `operationId` oraz decyzje. Koordynacja kart rozróżnia instancję
  karty od kopiowanego `clientInstanceId`, więc duplikat karty jest read-only.
  Podgląd ma pełną szerokość, techniczne liczniki usunięto z bocznego panelu,
  a zoom i przywracanie obu osi są wymuszane po ustabilizowaniu layoutu.
- Przed publicznym pilotem TASK-0290 wymaga checkpointu polityki feature flag:
  plan architektury opisuje nieaktywny kod do odbioru, natomiast obecna
  konfiguracja/instrukcja opisują wartość domyślnie włączoną. Nie zmieniono
  tej wcześniejszej polityki w ramach benchmarku.

### TASK-0305 — Zastępcze zdjęcie pojedynczej planszy 0.10 (todo)

- Plik zadania: `ai_docs/tasks/0305-v0-10-replacement-board-source.md`.
- Status: Zadanie jest celowo odroczone poza wersję 0.9. Przed implementacją wymaga osobnego breakdownu API, transakcji i UX.
- Cel: Pozwolić operatorowi dodać nowe zdjęcie dla jednego numeru planszy, utworzyć z niego niezależne źródło i wynik rozpoznania oraz świadomie przełączyć kanonicznego właściciela sekwencji bez utraty historii poprzedniego źródła.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „Odbiór wersji 0.9 — TASK-0304”.

### TASK-0472 — bezpieczeństwo v11 poprawione, precyzja nadal nie przechodzi

- Wielorozdzielcze potwierdzenie numerów, ostrożna deduplikacja wariantów bbox,
  fallback perspektywy i odzyskanie górnej granicy usunęły wykryte odcięcie.
- Ujawnione korpusy rozwojowe: 9/10, 7/7 i 10/10. Najnowsza niezależna próba:
  9 automatów, 1 manual, zero odcięć plansz/numerów, lecz tylko 6/10 cropów w
  ścisłych przedziałach obu linii z powodu nadmiaru tła.
- Bramka TASK-0472 nadal nie przeszła. V11 pozostaje nieaktywny; nie zmieniono
  danych użytkownika. Następna praca dotyczy odróżnienia dolnych numerów od
  elementów obudowy bez osłabiania obowiązkowej korekty.

### TASK-0472 — trzecia iteracja: 90% regresji, nieprzejściowy nowy odbiór

- Poziome łączenie krawędzi i analiza pochylonych etykiet dały 9/10 poprawnych
  automatów w znanej próbie, bez błędnych cięć. Bufor v11 wynosi teraz 20%.
- Niezależne 7 nowych katalogów: 5 poprawnych, 1 granica ponad referencją dolną,
  1 manual. Nie spełnia bramki. V11 nieaktywny, task pozostaje blocked.
- 101 testów i typecheck core/Admin OK. Bez zmian źródeł, cut, importów i jobów.
  Szczegóły i zamrożone referencje opisuje raport SELECTED_CROP_V11_REGRESSIONS.

### TASK-0472 — poprawka detektora, druga bramka nadal nieprzejściowa

- Poprawiono halo dylatacji, scalanie kandydatów i ranking etykiet w v11;
  stara para regresyjna daje 2/2 poprawnych automatów.
- Nowy niezależny zbiór: 5/10 poprawnych automatów, 1 z nadmiarem dolnego tła,
  4 ręczne korekty. Nie osiągnięto >=90%; v11 nadal nieaktywny, task blocked.
- 100 testów core/runner/Admin contract i oba typechecki OK. Bez zmian źródeł,
  katalogów cut, geometrii v0.10 i aktywnych jobów. Szczegóły w raporcie jakości.
- Odbiór dziesięciu zdjęć jest od teraz ujawniony; dalsze strojenie wymaga
  kolejnego niezależnego materiału. Oryginałów gry literowej nadal brak.

### TASK-0472 — bramka jakości v11 nie przeszła; rollout zatrzymany

- Holdout: 0/2 poprawnych automatów, 0 błędnych automatów, 2 incomplete_layout
  po analizach 960/1600. Nie osiągnięto wymaganych 90%; nie kontynuujemy strojenia.
- V11 pozostaje nieaktywny. Katalogi, importy, OCR i aktywne joby bez zmian.
- 72 core, 18 Admin contract, 7 Node recovery/EXIF, typecheck, scoped lint,
  scoped format oraz produkcyjny build Admina OK. Pełny lint nadal ma dwa
  wcześniejsze błędy w geometry-guard-resolution-panel.tsx, poza zakresem.
- Task pozostaje blocked; raport w SELECTED_CROP_V11_REGRESSIONS.md.
  Brak oryginałów gry literowej i live QA ogranicza odbiór. Dalsze prace tylko
  po osobnym poleceniu, bez obniżania ochrony ani automatycznego przeliczenia danych.

### TASK-0517 — baza starej gry usunięta, częściowy GC bezpiecznie zatrzymany

- `777 v0.1` (`80f3c7ec-6110-4e20-a263-2675ee5b15d6`) osiągnęła terminalny
  receipt `database_done`: 81 etapów i 10549 zatwierdzonych porcji.
- `new-siedem` pozostaje obecne, brak aktywnych jobów starej gry, a zachowane
  archiwum 414705 układów ma niezmieniony SHA-256
  `0e1d18a6f9ffe22860c6956f8f5761909df45021465643817c8cbf2426314c5e`.
- Read-only reference-aware GC preview chroni 80640 żywych ścieżek i wskazuje
  9599508 osieroconych plików (104,888 GiB). Preview SHA-256:
  `c4cce437b5f84df95f0ea07e6b68d4f8dffe2696e495c82badeb92946d2b2b2b`.
- Fizyczny GC przetworzył 15700 rekordów JSONL: 2258144 plików i
  21271550497 bajtów (19,811 GiB). Receipt ma status `executing`, bez pending.
  Operacja została zatrzymana przez operatora i nie jest obecnie uruchomiona.
- Pozostałe managed assets znajdują się w odłączonym katalogu
  `artifacts/data.detached-20260908-legacy-reset`; aktywny `artifacts/data` jest
  pusty. Katalog `C:\Users\user\Documents\777` i archiwum czatowe są poza
  zakresem.
- Executor GC jest gotowy jako ograniczona do 120 s, wznawialna operacja z
  atomowym przenoszeniem do kwarantanny, trwałym kursorem i blokadą zapisów do
  tabel ścieżek. Obsługuje jawnie przypięty katalog `data.detached-*`, blokuje
  wznowienie przy niepustym aktywnym `data`, wiąże katalog z receiptem i
  odzyskuje przerwany zapis intention/rename. Wznowienie wymaga nowej dokładnej
  zgody dla istniejącego SHA; dryf referencji, plików, tożsamości gry lub
  aktywny job zatrzymuje porcję przed usunięciem.

### TASK-0603 — ponowna kalibracja etykiet 777 w trybie V2 (w toku)

- Operator polecił wycofać poprzednią konfigurację. Pomiar tylko do odczytu
  wykazał dokładne kliknięcia; p95 `0,2255` wynikał z połączenia dwóch
  kadrowań w statycznym V1 oraz niespójnych grup. Stara sesja `482cbe56…`
  (V1, `blocked_source_drift` po zmianie `reels_test`) zostaje do audytu.
- D-463: nowy ignorowany manifest
  `.runtime/v7-label-geometry-calibration-t0603-v2.local.json` przypina oba
  katalogi 777 do V2. Admin tworzy sesje V2 domyślnie z obu katalogów, ma
  `Zacznij nową sesję` i ostrzega o zdjęciach bez lokalnej siatki (min. 5
  pełnych numerów w 2 wierszach i 2 kolumnach). Grupa `A` = `small_777`,
  `B` = `occluded_777`.
- Próba na tymczasowym runtime: sesja V2 z 374 źródeł (131 + 243), odmowy
  dla V1, `rells_big` i `reels_test`. Mutacja trwa ok. 7 s (pełna kontrola
  inwentarza). Stare punkty w V2 dają diagnostycznie p95 `0,0354`; to nie jest
  profil.
- Admin: 16 testów V7, 7 testów interakcji ekranu, `tsc` i ESLint PASS.
  Instrukcja operatora: `LOCAL_OPERATION_GUIDE.md`. Następny krok: anotacje
  operatora w nowej sesji V2, potem profil, raport walidacji i adopcja. V7
  pozostaje zablokowane.

### TASK-0603 — eksperyment i kontrakt wejścia geometrii shape v2

- Ukończono G01: schema v1 zachowuje pięć początkowych gier, a jawny schema v2
  pozwala później dodać zgodną grę z pełną ramką i topologią bez forka silnika.
  Read-only runner wiąże manifest, inventory, anotacje, wariant i profil
  transferowy checksumami, odrzuca wkład badanej gry oraz zwraca
  `not_evaluable` dla niepełnych dowodów.
- Brak atestowanego corpusów, anotacji i profili dla danych produkcyjnych nadal
  ogranicza tylko rzeczywisty pomiar i przyszły pilot. Nie powstały fikcyjne
  bramki liczbowe; G02 może zbudować niezależny rdzeń geometrii.
- 17 testów, Ruff i ograniczony mypy przeszły. Audyt Astra Medium wykrył trzy
  P2, wszystkie naprawiono; re-audyt nie ma P0–P2 ani P3. Karta zadania została
  przeniesiona do `ai_docs/tasks/completed/`.

### TASK-0603 — przygotowanie realnej kalibracji geometrii etykiet 777 V7

- Przygotowano realną kalibrację `standard_3x3_numeric_labels_v1`.
  Ekran z TASK-0602 oferował `small_777`, lecz aktywny manifest V1 oznaczał go
  jako `development`, przez co API słusznie nie pozwalało wykorzystać obu
  wskazanych katalogów 777 w jednej sesji kalibracyjnej.
- Zgodnie z D-415 powstał osobny, ignorowany manifest T0603 w `.runtime/`:
  oba case'y 777 są w nim `calibration`, należą do jednej rodziny i nie
  zmieniają istniejącego manifestu V1, danych wejściowych ani holdoutu.
  Operator oznaczył po sześć–siedem pełnych cropów każdej pozycji, w więcej
  niż dwóch grupach ujęć. Poprawka D-418 sprawia, że pojedyncze zapisane
  diagnostyki `clipped`/`uncertain` nie blokują już tych pełnych punktów;
  serwer do profilu bierze wyłącznie `contained` z zapisaną grupą ujęć.
  Rzeczywisty dry-run nie przeszedł p95, ponieważ pełne źródło ma poprawną,
  ale przesuniętą geometrię względem pięciu częściowo zasłoniętych źródeł.
  TASK-0603 pozostaje `blocked` na decyzji: osobne profile framingów albo
  dynamiczna normalizacja viewportu; V7 pozostaje zablokowane.

### TASK-0611 — Rdzeń V2.1 dla siatki osobnych ramek plansz (in_progress)

- Plik zadania: `ai_docs/tasks/0611-shape-geometry-v2-board-frame-lattice.md`.
- Status: `in_progress`
- Cel: Wykrywać na prawdziwych zdjęciach 777 i Mumii pełną siatkę 3 × 3 osobnych ramek plansz, bez zależności od koloru, jako deterministyczną propozycję testową bez importu ani zapisu danych gry.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „P00 / TASK-0665 — zapis planu laboratorium wizji (D-447)”.

### TASK-0645 — Reguła decyzji i dry-run (read-only) (blocked)

- Plik zadania: `ai_docs/tasks/0645-777-grid-reverify-dry-run.md`.
- Status: `blocked` — D-445 wstrzymała stary weryfikator; D-447 i `VISION_LAB_EXECUTION_PLAN.md` nie dostarczają uzupełniania slotów historycznego 777 siecią. Wznowienie wymaga osobnej decyzji i korekty tego planu.
- Cel: Dla każdej planszy „Do walidacji” i każdego slotu „Do poprawy” gry 777 wyznaczyć decyzję (pewny / niepewny / pominięty + powód) bez żadnego zapisu i zaraportować liczności.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „P00 / TASK-0665 — zapis planu laboratorium wizji (D-447)”; `CURRENT_STATE_2026Q3.md` → „TASK-0644 — kalibracja weryfikatora siatek 777: weryfikator…”.

### TASK-0646 — Ścieżka `execute` (bez uruchomienia na żywych danych) (blocked)

- Plik zadania: `ai_docs/tasks/0646-777-grid-reverify-execute.md`.
- Status: `blocked` — zależy od przepisania TASK-0645 po osobnej decyzji. D-447 nie upoważnia do uzupełniania slotów historycznego 777 siecią.
- Cel: Zapisywać decyzje „pewne” z TASK-0645 wyłącznie przez istniejące serwisy Reviewera, idempotentnie i z izolacją błędów per zdjęcie, pokryte testami.

### TASK-0647 — Przebieg na żywych danych i odbiór (blocked)

- Plik zadania: `ai_docs/tasks/0647-777-grid-reverify-live-run.md`.
- Status: `blocked` — zależy od osobnej decyzji i TASK-0645/0646; D-447 nie upoważnia do uzupełniania slotów historycznego 777 siecią ani do zapisu na żywych danych.
- Cel: Za osobną, jawną zgodą użytkownika wykonać `execute` dla gry 777 i potwierdzić wynik licznikami Reviewera oraz próbką wizualną.

### TASK-0649 — Pula kandydatów i kontrakt datasetu (tylko odczyt) (blocked)

- Plik zadania: `ai_docs/tasks/0649-grid-nn-candidate-pool.md`.
- Status: `blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); odpowiednik zakresu danych to TASK-0666/TASK-0668. Numer TASK-0649 koliduje z ukończonym zadaniem „Przybliżona wygrana”; identyfikuj ten plik pełną ścieżką.
- Cel: Wersjonowany manifest kandydatów do kuracji (plansze 777 z quadem, źródłem i metrykami trudności) z warstwowym losowaniem i splitem według rodziny źródła, bez zapisu do bazy.
- Uwaga: numer koliduje z ukończoną serią „Przybliżona wygrana” (D-445); sekcje archiwum o tym numerze dotyczą tamtej serii, nie tego pliku.

### TASK-0650 — Narzędzie kuracji danych uczących (blocked)

- Plik zadania: `ai_docs/tasks/0650-grid-nn-curation-tool.md`.
- Status: `blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); nowa kuracja to TASK-0668/TASK-0671. Numer koliduje z ukończoną serią „Przybliżona wygrana”; identyfikuj plik pełną ścieżką.
- Cel: Użytkownik szybko akceptuje/odrzuca kandydatów (klawisze A/R/S), a jego decyzje trwale trafiają do manifestu datasetu bez utraty i bez ponownego liczenia.
- Uwaga: numer koliduje z ukończoną serią „Przybliżona wygrana” (D-445); sekcje archiwum o tym numerze dotyczą tamtej serii, nie tego pliku.

### TASK-0651 — Model (etap A + B), trening i wydanie (blocked)

- Plik zadania: `ai_docs/tasks/0651-grid-nn-training.md`.
- Status: `blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); trening to TASK-0669/TASK-0670 i warunkowo TASK-0675. Numer koliduje z ukończoną serią „Przybliżona wygrana”; identyfikuj plik pełną ścieżką.
- Cel: Wytrenowane na zaakceptowanych danych modele etapu A (lokalizacja 9 plansz) i B (24 punkty siatki na wycinku) z eksportem ONNX, parytetem i manifestem wydania `shadowOnly=true`.
- Uwaga: numer koliduje z ukończoną serią „Przybliżona wygrana” (D-445); sekcje archiwum o tym numerze dotyczą tamtej serii, nie tego pliku.

### TASK-0652 — Ocena shadow na zbiorze złotym (blocked)

- Plik zadania: `ai_docs/tasks/0652-grid-nn-shadow-evaluation.md`.
- Status: `blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); ocena to TASK-0674/TASK-0678. Numer koliduje z ukończoną serią „Przybliżona wygrana”; identyfikuj plik pełną ścieżką.
- Cel: Liczbowe porównanie sieci z hybrydą na zbiorze złotym i ustalenie reguły pewności z zerem fałszywie zielonych siatek.
- Uwaga: numer koliduje z ukończoną serią „Przybliżona wygrana” (D-445); sekcje archiwum o tym numerze dotyczą tamtej serii, nie tego pliku.

### TASK-0653 — Użycie sieci w reweryfikacji 777 (blocked)

- Plik zadania: `ai_docs/tasks/0653-grid-nn-777-slot-fill.md`.
- Status: `blocked` — propozycję uzupełniania slotów historycznego 777 siecią wycofano. Obowiązuje `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); TASK-0645–0647 nie otrzymują takiej integracji. D-446 dotyczy „Przybliżonej wygranej”. Numer koliduje z ukończoną serią o tej nazwie; identyfikuj plik pełną ścieżką.
- Cel: Historyczna, niewykonywana propozycja zastąpienia kroku „dorysowania” w hybrydzie 777. D-446 nie jest jej decyzją.
- Uwaga: numer koliduje z ukończoną serią „Przybliżona wygrana” (D-445); sekcje archiwum o tym numerze dotyczą tamtej serii, nie tego pliku.

### TASK-0654 — dokumentacja „Przybliżonej wygranej”; plan zaimplementowany, odbiór na żywo wstrzymany (6/6)

- Ostatni task planu sesji `2026-09-24`/`2026-09-25`. Wyłącznie
  dokumentacyjny, bez zmiany kodu.
- Zaktualizowano `ai_docs/requirements/ADMIN_APP.md` (akapit „Liczba
  wyników” + nowa sekcja „Przybliżona wygrana”),
  `ai_docs/architecture/API_CONTRACT.md` (pełny kontrakt endpointu
  `GET .../board-search/approximate-win`) i
  `ai_docs/requirements/ALGORITHMS.md` (nowe `## D. Przybliżona wygrana w
Adminie` z dowodem, że naliczenie z widocznego prefiksu jest bezpiecznym
  dolnym ograniczeniem — właściwość istniejącego `payout-v3-unknown-prefix-stop`,
  nie nowy algorytm).
- Nowy wpis **D-446** w `DECISION_LOG.md`, zbierający całą serię
  TASK-0649–0653 w jedną decyzję referencyjną. **Kolizja numeracji:** plan i
  pliki tasków 0649–0653 odwoływały się do tego pakietu decyzji jako
  „D-445”; ten numer zajęła w międzyczasie inna, równoległa sesja (siatki
  777). D-446 jest właściwym, ostatecznym numerem.
- **Plan „Przybliżona wygrana” (D-446) jest w pełni zaimplementowany i
  przetestowany** (TASK-0649 „Liczba wyników”; TASK-0650
  `PreparedPayoutEvaluator`; TASK-0651 czysty kalkulator zakresu; TASK-0652
  pion API; TASK-0653 UI Admina). **Odbiór na żywych danych gry 777 nie
  został wykonany** — wymaga osobnej, jawnej zgody użytkownika na
  uruchomienie lokalnego API i Admina (zasady bezpieczeństwa tej sesji).
  TASK-0654 pozostaje `in_progress` do czasu tego odbioru;
  `ai_docs/tasks/0654-approximate-win-docs-and-acceptance.md` nie jest
  jeszcze przeniesiony do `completed/`.
- Znane, zgłoszone wcześniej i celowo nienaprawione w tym planie: pre-existing
  błąd fikstury `test_payout_store.py` (TASK-0650, chip `task_4008a087`) i
  pre-existing `prettier --check` na `packages/admin-api-client/src/index.ts`/
  `test/client.test.mjs` (TASK-0652). Limit `spinCount ≤ 10 000` jest
  oszacowaniem bez pomiaru (do weryfikacji przy pierwszym realnym użyciu).

### TASK-0668 — T03 — edytor i zbiór geometrii (in_progress)

- Plik zadania: `ai_docs/tasks/0668-vision-lab-geometry-annotations.md`.
- Status: `in_progress` — D-456 zatwierdza T03k i pilota całymi grami bez pomiaru. Pełny protokół rodzin/pomiaru pozostaje odroczony. Historycznie: anotacje i przegląd operatora wykonane; D-453 rozstrzyga użycie historycznych zdjęć 777 w modelu geometrii. Pozostają techniczne mapowanie źródeł do rodzin, kontrola konfliktów oraz zamrożony podział. Mechanizmy T03e/T03f są wdrożone i odebrane; T03g zachował zapisy w…
- Cel: Zatwierdzać warstwowe anotacje geometrii z trwałymi rewizjami i zamrożonymi podziałami.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „T03 — dopuszczenie historycznych zdjęć 777 do geometrii”; `CURRENT_STATE_2026Q3.md` → „Niepełne plansze — realizacja zaakceptowanego planu T1–T4”; `CURRENT_STATE_2026Q3.md` → „Etap B laboratorium — narzędzia T03 odebrane, bramka danych”.

### TASK-0671 — T06 — etykiety symboli (blocked)

- Plik zadania: `ai_docs/tasks/0671-vision-lab-symbol-labels.md`.
- Status: `blocked` — T06a odebrane; T06b wymaga rzeczywistych zatwierdzeń symboli i kwalifikacji zbioru. Nadrzędne T06 pozostaje aktywne, dlatego ten plik nie trafia do `completed/`.
- Cel: Zbudować zbiór symboli z weryfikowalnym pochodzeniem DB lub lab.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „Etap C — T06a odebrane; T06b blokuje dalszy trening”.

### TASK-0672 — T07 — RGB, szarość i fuzja (todo)

- Plik zadania: `ai_docs/tasks/0672-vision-lab-symbol-models.md`.
- Status: `todo`
- Cel: Porównać modele symboli i skalibrowaną fuzję na wspólnych podziałach per gra.

### TASK-0673 — T08 — panel treningu (todo)

- Plik zadania: `ai_docs/tasks/0673-vision-lab-training-panel.md`.
- Status: `todo`
- Cel: Udostępnić panel treningu korzystający z trwałego kontraktu runów T04 i odtwarzający widok po restarcie.

### TASK-0674 — T09 — walidacja i wybór (todo)

- Plik zadania: `ai_docs/tasks/0674-vision-lab-validation.md`.
- Status: `todo`
- Cel: Wybrać i zamrozić kandydata lub uzasadnić potrzebę pełnej sieci.

### TASK-0675 — T10 — pełna sieć węzłów (todo)

- Plik zadania: `ai_docs/tasks/0675-vision-lab-neural-grid.md`.
- Status: `todo`
- Cel: Warunkowo dodać neural_grid przewidujący pełną siatkę obu topologii.

### TASK-0676 — T11 — geometria w aplikacji (todo)

- Plik zadania: `ai_docs/tasks/0676-vision-lab-geometry-integration.md`.
- Status: `todo`
- Cel: Wprowadzić kandydata geometrii do review/shadow tylko dla 5 × 3, także równolegle do starego silnika na zdjęciu istniejącej gry `777 v1.1`.

### TASK-0677 — T12 — symbole i wspólny trening (todo)

- Plik zadania: `ai_docs/tasks/0677-vision-lab-symbol-integration.md`.
- Status: `todo`
- Cel: Podłączyć model symboli i neutralny rdzeń do workera bez regresji.

### TASK-0678 — T13 — test końcowy i raport (todo)

- Plik zadania: `ai_docs/tasks/0678-vision-lab-final-acceptance.md`.
- Status: `todo`
- Cel: Ocenić zamrożonego kandydata end-to-end i opublikować ograniczenia.

### TASK-0687 — T08 readiness release V2-only: krytyczna bramka przed T09–T12

- Użytkownik polecił dokończyć T08 i samodzielnie rozstrzygać zwykłe kwestie
  techniczne. Baza użytkownika została tylko odczytana i nadal ma Alembic
  `0124`; migracji 0125 nie zastosowano. Kod bazowy to commit `v0.10.451` z
  niezatwierdzonymi zmianami fixture. Release jest source-run; smoke zapisuje
  revision i hash źródeł/config, osobna binarka nie jest wymagana.
- Na izolowanym head 0125 po naprawie części fixture przeszły browser
  retention 1/1, katalog 1/1 i worker job store 1/1. Raport importu po
  usunięciu błędu routingu nadal ma wcześniejszy dryf kodu błędu, a test
  HTTP M2 kończy się 422 na tworzeniu symbolu. Poprzednia sesja zgłosiła
  49 failed / 64 passed w pełnych 28 plikach integracyjnych; tego przebiegu
  nie powtórzono. Szczegóły i granice dowodu:
  `quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`.
- Użytkownik doprecyzował zlecenie całego pozostałego planu do T12 i auditów;
  T08 wznowiono. TASK-0694 grupuje naprawy fixture/asercji po 0125,
  TASK-0695 niezwiązane rozjazdy kontraktu, TASK-0697 trzy rzeczywiste klucze
  konfliktu upsertów workera bez `game_id`.
- Sprostowanie środowiska: `.venv` działa z Pythonem 3.12.10 poza sandboxem.
  Brak startu w sandboxie nie dowodził brakującej instalacji; błędnie utworzone
  TASK-0696 wycofano. Mypy ma dodatkowo niepoprawny separator `;` w wartości
  config `mypy_path`; sam Python nie wymaga reinstalacji.
- Nowy smoke ujawnił rzeczywiste nieobsłużone globalne wejścia V2: odczyt
  layoutów przez `datasetId` oraz wielogrowe release bez bind. T09 pozostaje
  `no-go` do rozstrzygnięcia tych problemów; nie wolno ukrywać ich dodatkowym
  scope w fixture. Przygotowawczy read-only preflight z 07:16:30 CEST jest
  `ready` (65 pustych tabel, 3 active V2), ale nie jest zgodą na apply.
- Końcowy smoke rzeczywistych procesów trwał67,56s: trwały worker completed,
  restart API i drugi worker no_job,65 public absent, missing location409.
  Pozostały HTTP500 dataset layouts/review-batches i422 geometry schema3.
  Test oraz wynik zachowane; procesy/bazy izolowane posprzątane.
- Naprawione fixture: imagebatch15/16, catalog2/2, image selection4/4.
  Pozostały duplicate pending oraz wcześniejsze błędy typów zgrupowano z
  dryfem kontraktów i schema3 w TASK-0695. Pełnej suite nie powtórzono;
  TASK-0694 nie jest done. Audit fixture/smoke: brak nowych P0–P2.
- Krytyczny audit potwierdził konflikt accepted D-038 (źródła i rodzic
  release w jednej transakcji) z pojedynczą grą per transakcja V2.
  TASK-0698 zapisuje pytanie i rekomendację jawnego koordynatora atomowej
  operacji wielu gier. Nie podjęto ukrytej zmiany D-038/RLS. To warunek
  wymagający decyzji użytkownika; T09–T12 nie wykonano. Samo polecenie całego
  planu nie zastępuje wymaganej później zgody na exact path/hash preflightu.

### TASK-0688 — T09 — zastosowanie usunięcia legacy `public` (todo)

- Plik zadania: `ai_docs/tasks/0688-apply-legacy-public-store-removal.md`.
- Status: `todo`
- Cel: Po osobnym, dokładnym potwierdzeniu operatora zastosować 0125 raz i utrwalić dowód przed/po bez naruszenia catalog/control/shared lub V2.

### TASK-0689 — T10 — odbiór operacyjny po usunięciu legacy `public` (todo)

- Plik zadania: `ai_docs/tasks/0689-post-removal-operational-acceptance.md`.
- Status: `todo`
- Cel: Niezależnie potwierdzić, że aktywne gry, API, worker i trwały routing działają po 0125 wyłącznie na V2.

### TASK-0690 — T11 — usunięcie nieosiągalnych ścieżek legacy `public` (todo)

- Plik zadania: `ai_docs/tasks/0690-remove-legacy-public-code-paths.md`.
- Status: `todo`
- Cel: Usunąć lub jednoznacznie odseparować pozostałe nieprodukcyjne symbole legacy po udowodnieniu operacyjnego V2-only.

### TASK-0691 — T12 — końcowy odbiór V2-only (todo)

- Plik zadania: `ai_docs/tasks/0691-legacy-public-store-final-acceptance.md`.
- Status: `todo`
- Cel: Zamknąć plan dowodem, że V2 jest jedynym game data plane oraz że dokumentacja i ryzyka odzwierciedlają stan rzeczywisty.

### TASK-0694 — wiarygodny zestaw integracyjny po 0125 (blocked)

- Plik zadania: `ai_docs/tasks/0694-v2-0125-integration-suite.md`.
- Status: `blocked` — częściowe naprawy gotowe; zależny runtime wymaga TASK-0698.
- Cel: Przywrócić testy integracyjne zależne od 65 relacji game-owned tak, aby sprawdzały `game_data_v2` na świeżym head 0125 i stanowiły wiarygodną bramkę przed ponownym T08.

### TASK-0695 — dryf kontraktów testów integracyjnych (todo)

- Plik zadania: `ai_docs/tasks/0695-unrelated-integration-contract-drift.md`.
- Status: `todo`
- Cel: Rozstrzygnąć niezwiązane z usunięciem legacy rozjazdy między testami a bieżącym zachowaniem API i domeny, bez automatycznego osłabienia asercji.

### TASK-0698 — globalny routing V2 i granica transakcji release (blocked)

- Plik zadania: `ai_docs/tasks/0698-global-v2-routing-transaction-decision.md`.
- Status: `blocked` — wymaga jawnego rozstrzygnięcia sprzecznych zaakceptowanych zasad.
- Cel: Przywrócić globalne odczyty i atomowe wydania 1–15 gier bez legacy public, bez utraty fail-closed i bez niejawnego obejścia izolacji V2.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „TASK-0697 — ukończona naprawa upsertów V2”.

### TASK-0802 — neural_grid: sieć widząca cały ekran (in_progress)

- Plik zadania: `ai_docs/tasks/0802-neural-grid-whole-screen-network.md`.
- Status: `in_progress`
- Cel: Silnik `neural_grid` pod kontraktem `GeometryEngine` wykrywa na całym zdjęciu wszystkie plansze i wyznacza dla każdej 24 węzły siatki 5 × 3; jest wytrenowany na snapshocie produkcyjnym v2 w ramach budżetu D-481, wyeksportowany do ONNX z potwierdzoną zgodnością PyTorch–ONNX i opisany raportem per run z metryką nadrzędną D-483.
- Historia w archiwum: `CURRENT_STATE_2026Q4.md` → „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku…”.

### TASK-0928 — image import storage resumption (in progress)

- Mumie job 092ff7a4-e652-4273-9c0a-a30e38ebd8cc stalls at 535/2915 sources
  with `waiting_for_storage`, despite 50.23 GiB free. Attempts increase;
  the worker wrongly uses the 80 GiB GC target to resume instead of reserve.
- D-534: same configured hard reserve for copying, normal pipeline and resume,
  default 5 GiB. Keep GC policy and admission estimates unchanged; add the
  existing polling delay after storage deferral instead of immediate reclaims.
- The user separately authorized restarting only worker general after tests.
  No API/Admin lifecycle, data cleanup, new import or manual state mutation.
- Implementation verified: 119 worker tests (including 24 new regressions),
  71 API capacity/config/retention tests, scoped strict mypy and Ruff pass.
  Four old CLI fixture failures reproduce on unchanged HEAD; left outside
  this fix. No API schema change or GC-policy change.
- Live rollout blocked before stopping general: DB is
  `0146_symbol_review_import_filter_index`, current code requires
  `0147_merge_v7_main`. At 19:22:52 UTC, 50.14 GiB free and the same job still
  at 535/2915. Existing PID 6984/19496 and API/Admin remain untouched.
  V7 migration needs separate authorization/user-run service maintenance;
  do not include the unrelated in-progress management migration 0148.

### TASK-0937 — Pilot wykrywania złotej ramki super symbolu (pomiar) (blocked)

- Plik zadania: `ai_docs/tasks/0937-gold-frame-detection-pilot.md`.
- Stan: `blocked`. Narzędzie gotowe i zacommitowane (v1.7.281 /
  7b7b0a7e4b1b63fbde4518ccdabe336443ef1728): dwufazowy skrypt
  `scripts/m8_gold_frame_pilot.py`, arkusz kontaktowy i 8 testów
  (`services/worker/tests/test_m8_gold_frame_pilot.py`); raport
  `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md`.
- Warunki odblokowania: migracja `0152` zastosowana na bazie operatora, seria
  supergry wyprowadzona, zdefiniowanych co najmniej 5 super symboli oraz
  etykiety operatora (co najmniej 30 komórek na wariant wycinka). Dopiero
  wtedy można wykonać pomiar i sformułować wniosek o automatycznej propozycji
  super symbolu.

### TASK-0939 — Narzędzia oszczędzania tokenów z pomiarem (mapa kodu, Serena, Graphify, hook) (in_progress)

- Commit v1.7.284 / 6f783932b05f0c11d0579086e9d464756304f046.
- Plik zadania: `ai_docs/tasks/0939-token-tooling-pilot.md`.
- Status: `in_progress` (dostarczono narzędzia i protokół; brak przebiegów pomiaru).
- Cel: Zestaw narzędzi nawigacji po repozytorium i reguł pracy, który mierzalnie obniża tokeny wejścia typowych zadań bez spadku jakości wyniku; do stałego użytku wchodzi tylko to, co pomiar potwierdził.
- Gotowe (commit dostarczający narzędzia: `v1.7.284`, hash do dopisania po commicie): mapa kodu `ai_docs/architecture/CODE_MAP.md` i `CODE_MAP_SYMBOLS.md` generowane `scripts/generate_code_map.py` (`npm run code-map:check`, ok. 3 s, poza `docs:check`); hook `PreToolUse` w `.claude/settings.json` blokujący `Read` pliku > 200 KB bez zakresu (`scripts/hooks/block_large_read.py`); reguły „Oszczędzanie kontekstu” w `AGENTS.md`; Serena MCP i Graphify zainstalowane w izolowanym venv `.tooling/venv-tokens` (test dymny i pomiary czasu w `ai_docs/guides/TOKEN_TOOLING.md`), rejestracja MCP wyłącznie decyzją operatora (`claude mcp add`).
- Audyt Codex gpt-6-astra / medium, runda 1: REVISE (`ai_docs/quality/TASK-0939_AUDIT_gpt-6-astra.md`); poprawki wykonane w jednej rundzie (patrz Outcome).
- Pozostało (pomiar należy do operatora; task zostaje otwarty): przebiegi pomiaru wg `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md` (36 sesji operatora, najpierw kalibracja i zgoda na koszt; zbieranie zużycia `scripts/token_pilot_collect.py`), raport `TOKEN_TOOLING_PILOT_<data>.md` z decyzjami „zostaje / wypada”, audyt drugiej rodziny.
- Poza repozytorium po nieudanej próbie `uvx`: katalogi `uv` w `%APPDATA%` (ok. 67 MB) i `%LOCALAPPDATA%`, do ręcznego usunięcia przez operatora (usunięte przez leada 2026-10-09; katalogi nie istnieją).

## Ostatnie 10 ukończonych tasków

### TASK-0953 — przyrostowa kopia katalogów danych na D (done)

- Etap A (D-540). Nowy `scripts/sync_data_directories_to_d.ps1`
  (`npm run data:sync:d`): inwentarz wpisów ignorowanych (98 zachowywanych,
  59 odtwarzalnych, 2 korzenie worktree'ów), tryby `Initial`/`Final`,
  `-VerifyOnly -Manifest`, `-Mirror` z zatwierdzoną listą, manifesty SHA-256,
  redakcja ścieżek `.tooling`.
- `D:\game_predicotr` zawiera ok. 80 GB danych ignorowanych z C i
  `v7-output/`. Drugi przebieg `Initial`: 3 pliki, `OK`. Test `Final` na
  prawdziwych wpisach: manifesty równe. Pełny `Final` w TASK-0955.
- Wykluczono nieczytelną pozostałość testu `*pytest-run*` (ERROR 5).
  Wykonawca opus-5-5 zamiast sonnet-5-5.
- Task: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md`.

### TASK-0952 — kopia zapasowa bazy na D (done)

- Etap A planu przeniesienia na D (D-540). `D:\game_predictor_backup`:
  zrzut `game_predictor-20261010-0100.dump` (33,8 GB, SHA-256 `94E5DB9B…`),
  role `globals-20261010-0100.sql`, spis i log. Kody wyjścia 0 dla
  `pg_dumpall`, `pg_dump` (26,5 min), `pg_restore --list` (263 `TABLE DATA`)
  i pełnego odczytu `pg_restore --file=/dev/null` (15,7 min).
- Raport etapu A: baza 88 GB, `0153`, 272/59 tabel, 839 jobów, 13 sesji
  zdalnej selekcji. Bez zmian w bazie i usługach. Wykonawca opus-5-5 zamiast
  sonnet-5-5 (zmiana modelu przez operatora).
- Task: `ai_docs/tasks/completed/0952-disk-d-database-backup.md`.

### TASK-0960 — kolejka po częściowym usuwaniu źródeł (done)

- Commit: `v1.7.298` — `91ecf6a04a017a5723ea9f8336957221766cf043` (lokalnie, bez push).
- Przyczyna HTTP500: kasowanie image_review_queue_states całego importu przy pozostających review items. Licznik utrzymuje teraz istniejący trigger, który usuwa go dopiero po ostatniej pozycji.
- Odtworzono siedem liczników z poprawnych projekcji; nowe wersje unieważniają stare kursory. Zachowano 217 accepted reviews.
- Usunięto 275 zatwierdzonych źródeł (2198 plansz, 32970 komórek) przez pięć potwierdzonych API batches. Nowy odczyt: zero rekordów celu, brak niespójnych liczników, pięć receiptów.
- Test PostgreSQL dwóch partii w nowych sesjach: 1 passed; domain/API: 10 passed; Ruff PASS. Mypy dwukrotnie timeout, Claude CLI niedostępny — brief i ograniczenia zapisane, brak deklaracji PASS audytu.
- Manifest i CSV: `ai_docs/quality/MUMIE_SOURCE_REPLACEMENT_20261009.*`. Task: `ai_docs/tasks/completed/0960-board-source-cleanup-queue-state.md`. Bez restartów, migracji, push i nowego importu.

### TASK-0950 — Management pending modal recovery (done)

- Visible edit/delete dialogs now contain errors and exact retry; failed writes can be closed without losing pending identity. Fields remain locked during active/uncertain writes.
- Admin13/13, Reviewer23/23 (nine new cases), proxy11/11; scoped lint/shared typecheck PASS. One Claude medium static audit PASS, both P2 closed.
- Operator shared edit/delete complaint remains unconfirmed. Read-only API: active session, one active and two archived points. No public live write, data deletion, service lifecycle or deployment.
- See [task](../tasks/completed/0950-management-pending-modal-recovery.md) and [audit](../quality/TASK-0950_AUDIT_claude-opus-5-5.md). Commit `v1.7.295` / `25f91c842fbdad8c35e7c2622fe697fe04f65dd1`.


### TASK-0946 — odstępy kafelków panelu (done)

- Spójne16px dla ikon, stawek i archiwalnych kafelków; miejsce na dwa przyciski44px.
- Browser10/10 PASS; nowa asercja odtwarza błąd4px, sprawdza odstępy i brak kolizji. Prettier i składnia PASS; bez ponownego pełnego builda/audytu.
- Outcome: `ai_docs/tasks/completed/0946-management-tile-padding.md`; commit v1.7.291 / 1332c91013855f9d519cd0075a94eb8d3d69fe96.
- Bez zmian danych, uruchamiania usług i push. Kontrola na stronie operatora pozostaje do odbioru.

### TASK-0945 — Integracja kompaktowego panelu z main (done)

- Merge commit: v1.7.288 / 9cea1a8a363aa2efad6d012889a86aced34d613a; plan `ai_docs/delivery/ADMIN_COMPACT_PANEL_INTEGRATION_PLAN.md`, Outcome `ai_docs/tasks/completed/0945-compact-panel-main-integration.md`.
- Zachowano D-536/D-537 Mumii i geometrię0944; historyczny D-536 panelu mapuje się na D-538. Oba historyczne TASK-0940 zachowują osobne pliki i oryginalne commity.
- Jedna głowa0153, oba rodzice0152; frozen i compact piny używają free-spin/provisional kosztów. Digest oraz dawny kontrakt777 bez zmian, nowe metryki sprawdzone osobno.
- Claude opus5.5/high PASS,0 P0/P1; pięć P2 poprawiono i zweryfikowano w jednej rundzie. API client107/107, TS helpers34/34, scoped interactions17/17, Admin39/39, Reviewer proxy/geometry31/31, Python focused31/31, API supergame35 plus7772/2; final backend20/20 i saved-selection15/15. PG trzy ścieżki merge, dwa krytyczne scenariusze oraz wzmocniona macierz3/3 PASS. Buildy, Chromium10/10, OpenAPI/docs/maps, lint/types PASS.
- Jeden szerszy moduł PG osiągnął limit120s; nie deklarujemy pełnego PASS. Własną pozostałość testową usunięto, starsze bazy pozostawiono. Zawężone wymagane kontrole PASS.
- Main fast-forward zweryfikowany,25 niezapisanych ścieżek i v7-output zachowane. Bez push, migracji operatora ani API/Admin lifecycle. Do odbioru na żywo wymagana osobna procedura0153 i backup/preview.

### TASK-0943 — Minimalistyczny panel (done)

- Version: v1.7.276; commit: d7b37368646a5c9b8a039505646a5fc6f4c55518.
- Outcome: ai_docs/tasks/completed/0943-management-compact-acceptance.md; independent Claude review without open P0/P1.
- Final browser10/10 and host production builds PASS; no operator-data/service action.

### TASK-0942 — Minimalistyczny panel (done)

- Version: v1.7.275; commit: af1218b0685b5d472f2e7eb4842934b205f2ec26.
- Outcome: ai_docs/tasks/completed/0942-management-compact-stakes.md; independent Claude review without open P0/P1.
- Final browser10/10 and host production builds PASS; no operator-data/service action.

### TASK-0941 — Minimalistyczny panel (done)

- Version: v1.7.274; commit: 993ddc763f3946453ea391c1a82ba6288052f866.
- Outcome: ai_docs/tasks/completed/0941-management-compact-navigation.md; independent Claude review without open P0/P1.
- Final browser10/10 and host production builds PASS; no operator-data/service action.

### TASK-0940 — Atomic management edit and explicit scope deletion (done)

- Version v1.7.273; commit0625512d4a37072f1d6d44f3f85ef225e7db1835.
- Outcome: `ai_docs/tasks/completed/0940-management-atomic-edit-and-delete.md`; separate panel-branch task, independent of main's historical TASK-0940 quality task.
- Atomic final name/game edits, bound preview/confirmed scope purge, preserved independent security audit and redacted retry receipts. Original Claude report retained, required regression tests added before the task commit.
