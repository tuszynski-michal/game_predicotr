---
title: Current project state
status: active
last_updated: 2026-11-02
---

# Current State

Ten plik jest obowiązkowym odczytem startowym i ma **okno kroczące z budżetami** (łącznie ≤ 30 000 B). Zawiera tylko (1) obowiązujące ograniczenia operacyjne (≤ 8 000 B), (2) plany z niezakończonymi taskami jako jedną tabelę (≤ 5 000 B), (3) otwarte decyzje i pytania, (4) po jednym wskaźniku ≤ 1 200 B na task aktywny (`in_progress`, `blocked`, `todo`: każdy task z plikiem w `ai_docs/tasks/`) oraz (5) 10 jednowierszowych wpisów `done` (≤ 400 B każdy). Pełna historia leży bez zmian w [archiwum Q4 2026](../archive/CURRENT_STATE_2026Q4.md) (od 2026-10-01) i [archiwum Q3 2026](../archive/CURRENT_STATE_2026Q3.md) (wcześniej); szczegóły taska aktywnego są w jego pliku.

Reguła utrzymania: przy zamykaniu taska agent (1) dopisuje pełną sekcję `done` na początku najnowszego pliku archiwum (tuż pod nagłówkiem, bez edycji tekstu), (2) dopisuje w oknie jeden wiersz `done` na początku sekcji „Ostatnie 10 ukończonych tasków” w formacie `- **TASK-NNNN** — tytuł — vX.Y.N / krótki hash — tasks/completed/<plik>.md`, (3) usuwa z okna najstarszy wiersz ponad 10 (jego pełna sekcja jest już w archiwum), (4) usuwa wskaźnik zamkniętego taska z „Aktywne taski” i (5) aktualizuje „Obowiązujące ograniczenia” oraz „Plany”. Wskaźnik aktywnego taska ma status, ścieżkę pliku, jedno zdanie blokera lub następnego kroku i ≤ 1 200 B; szczegóły idą do `Outcome` pliku taska. Lead dopisuje hashe commitów jak dotychczas. Spójność okna sprawdzają `scripts/check_current_state_window.py` i `scripts/check_startup_read_budget.py` (część `npm run docs:check`).

## Obowiązujące ograniczenia

- **TASK-1108 (2026-10-29):** Mumie v1 to opublikowany default nowych gier; GET eligible. Bez treningu i zmian przypisań. Źródło: `quality/MUMIE_DEFAULT_GEOMETRY_20261029.json`.


- **Selektor 1.0.4 / TASK-1104–1107 (2026-10-29):** finalny ZIP i sześć smoke PASS, warm p95 25,5 ms na lokalnej partii. Bez audytów (decyzja operatora), usług, migracji, merge/push. Reboot i komputer odbiorcy pending. Źródło, SHA i zakres testów: `quality/SELECTOR_FLUENCY_1_0_4_20261029.md`.

- **Odłączenie starego C / TASK-1085–1086 (2026-10-22):** backup i preview v2 179 ścieżek gotowe, audyt Claude PASS, zabezpieczenia P2 rozliczone. Zamiast pełnego skanu historii operator zatwierdził analizę konsumentów plików: 133 kolumny/108 tabel i operacyjne JSON bez dodatkowych zależności. Przed usunięciem C wymagane: zgoda na merge, wdrożenie i restart API/workerów przez operatora, świeży preview i zgoda na relokację, kontrolowane odcięcie i zgoda na usunięcie. Nic z tego nie wykonano. Źródło: [raport przygotowania](../quality/LEGACY_C_COPY_RETIREMENT_20261022.md).

Każdy punkt wskazuje źródło; stan z daty wpisu przed poleganiem na nim zweryfikuj odczytem, bez zmian w systemie. Pełne, niezmienione teksty dawnych punktów (także skróconych poniżej) są na początku archiwum Q4, sekcja „Przeniesione z okna 2026-10-16 (TASK-1022)”.

- **Gałąź integracyjna = `main`** (operator, 2026-10-16): nowe gałęzie od `main`, scalanie do `main`. `v1.1-vision-lab-hybrid-geometry` jest w `main` i usunięta lokalnie oraz na `origin` (2026-10-16, polecenie operatora). Starsze wzmianki o „gałęzi integracyjnej” dotyczą tamtej gałęzi. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Panel wielu gier / TASK-0991 (2026-10-16):** migracja `0155`, scalenie do `main` (v1.7.364) i cleanup wykonane bez audytu (decyzja operatora); Reviewer 3001 wymaga ręcznego restartu. Numer TASK-0991 koliduje z naprawą symboli: identyfikuj pełną ścieżką. Źródło: archiwum Q4, „TASK-0991 — Panel udostępniania wielu gier”.
- **Akceptacja przed scaleniem** (operator, 2026-10-14, TASK-0992): wykonaj cały zlecony task, etap albo plan z kontrolami, dokumentacją i commitami, potem zapytaj o akceptację wyniku i zgodę na scalenie; scal po wyraźnym potwierdzeniu. Zgoda na scalenie obejmuje push `main` do origin (operator, 2026-10-16); restart usług i migracje mają osobne bramki. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975, 0991, D-548) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. TASK-1024 istnieje na `main` (zamknięcie tasków) i na `codex/v3-grid-fine-tuning`. TASK-1030–1033 (etap 2 odczytu startowego, `main`) zajął także tor V3 na `codex/v3-grid-fine-tuning`; kolejne numery bierz od TASK-1040 w górę po sprawdzeniu obu. Źródło: archiwum Q3/Q4.
- **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`); z `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług. Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- **Wyszukiwarka ciągów / migracja 0169 (2026-10-25):** po akceptacji integracji wykonano stop usług, fast-forward do main i migrację operatora do `0169_board_search_sequence_logs`; `ck_bss_query_request` = 32768, manifest v19. API, Admin, Reviewer i general worker (7 wątków) uruchomione ponownie. Live smoke 1/2/4 wzory i kotwica wygranych PASS. Gałąź selektora i lokalne zmiany zabezpieczone osobno; wersje v1.7.467–472 kolidują wyłącznie numerami z gałęzią selektora, bez przepisywania historii. Źródło: `tasks/completed/1097-board-search-schema-readiness.md`, raport odbioru wyszukiwarki.
- **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. Źródło: `AGENTS.md`, „Trwałe workflowy i operacje danych”.
- **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- **Przycinanie zdjęć P1 / TASK-1016 (2026-10-14, odbiór 2026-10-17):** galeria 40 zdjęć powstała wyłącznie na kopiach i została zaakceptowana. Pomiar nie jest zgodą na podmianę ani usunięcie oryginałów, nie jest też prognozą dla całej biblioteki. P2–P4 wymagają zaakceptowanego planu i zgody. Źródło: `tasks/completed/1016-photo-crop-preview.md`.
- **Przycinanie oryginałów, etap A (2026-10-17):** w `main` i na origin (`06657169`), baza operatora zmigrowana do `0167_source_image_crops` (manifest v18, 16 s); nie istnieje żaden crop i żaden oryginał nie został usunięty. Etap B (TASK-1047–1049) zaakceptowany i scalony do `main` 2026-10-17 z migracją `0168_source_crop_runs` (manifest v19); joby na danych operatora (TASK-1050) mają osobne zgody. Źródło: plan przycinania, rewizja 2, D-562.
- **Narzędzia tokenowe:** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Serena i Graphify nie są stałym narzędziem (pilot TASK-0939 zamknięty bez pomiaru). Źródło: `guides/TOKEN_TOOLING.md`.
- **Plan V3 rewizja 6** (`codex/v3-grid-fine-tuning`, accepted 2026-10-14): cały zakres i koszt zlecone; od TASK-1005 wykonuje Claude Code `claude-opus-5-5`/`high` (zamiennik `claude-fable-5-1` wybrany przez wykonawcę po sugestii operatora 2026-10-16; 0997 na `xhigh`), audytuje Codex `gpt-6-astra`. GPU smoke, trening, publikacja, aktywacja, migracje i operacje danych operatora oraz scalenie do `main` mają osobne zgody; kopia `D:\game_predictor_backup` wystarcza, bez nowego backupu. Źródło: plan sekcje 1, 3 i 8; D-552.
- **Integracja V3 (2026-10-16, zgoda operatora):** `codex/v3-grid-fine-tuning` w `main` i na origin (v1.7.396 `b263c738`); baza operatora zmigrowana `0155_board_search_panels` → `0166` przez `npm run db:migrate` (13 s), 4 lokalizacje gier na manifeście v17, przypisania Mumii, 777a2 i 777v2 zachowane, brak wersji domyślnej (wymaga jawnej publikacji). Usługi zrestartowane z `main`; lane `grid-training` używa `D:\game_predicotr\.venv-vision-lab` (torch cu130), które skrypt lane znajduje sam; środowisko na C nie jest już potrzebne. Źródło: [raport odbioru](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md), sekcja 6.
- **Regresje V3:** odbiór TASK-1001 w [raporcie](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md): Admin ma te same 10 porażek co [HEAD380](../quality/TASK-1003_BASELINE_HEAD380.md), worker 17 środowiskowych w worktree, PostgreSQL tylko znana usterka `reset_game` sprzed V3 (osobne zadanie). `scripts/run_python_tests.ps1 -Suite` dla jednej ścieżki psuje kolekcję: używać bezpośredniego `pytest`. Źródło: archiwum Q4, jak wyżej.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md` | T1/T2 Opus PASS; T2 v1.7.518; panel T3 gotowy w osobnym worktree do integracji i audytu | TASK-1122–1123 | `codex/grid-corrections-learning` |
| `delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` | poprawki TASK-1098–1100 zaakceptowane i scalone lokalnie 2026-10-27 (v1.7.484–488): wzory przed szukaniem, +10 zdjęć, 60 s i domyślne 40 wyników; push i cleanup objęte zgodą | odbiór działającego linku i fizycznego Androida; usługi bez restartu agenta | `main` |
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | accepted, rev. 6; 24/24 done, zintegrowany w `main` | rzeczywisty eksperyment TASK-1006 za osobną zgodą | `main` |
| `delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md` | accepted, rev. 2; etapy A i B w `main`; rewizja 3 (wariant B, D-563) w `main` | TASK-1050 (pilot) | `claude/photo-crop-pilot` |
| `delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md` | accepted 2026-10-19; 5/5 tasków done (v1.7.426–430, audyty Codex 1056/1057/1059 zamknięte); czeka na odbiór operatora (restart Reviewera i API, test linku Mumii) i zgodę na scalenie | brak (odbiór i scalenie) | `claude/share-super-series` |

Pozostałe plany z aktywnymi taskami zamknięto 2026-10-16 (TASK-1024): ich taski uznano za nieaktualne; dawne wiersze tabeli są na początku archiwum Q4.

## Otwarte decyzje i pytania

- Przycinanie oryginałów: zgody na kolejne kroki pilotażu TASK-1050.
- Decyzje czekające na operatora: status planu symboli premium Mumii (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`), decyzja D-463 dla odroczonego snapshotu mobilnego oraz status planu `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`). Pytania R1–R15 przeglądu TASK-1021 rozstrzygnięto zamknięciem tasków (TASK-1024).
- Pytania produktowe: `ai_docs/project/OPEN_QUESTIONS.md`; jedyne nierozstrzygnięte
  to Q-020 (zgoda właściciela na analizę aplikacji referencyjnej; nie blokuje
  bieżących prac).
- Decyzje architektoniczne: indeks 30 najnowszych w
  `ai_docs/process/DECISION_LOG.md` (starsze w archiwum indeksu); wszystkie wpisy mają status `accepted`
  albo `superseded`, brak wpisów `proposed`.
- TASK-1102: zaakceptowany, scalony i wypchnięty razem z działającą nawigacją ±15 (TASK-1101); API zrestartowane za zgodą operatora. Ostatni zgłoszony wzór 777a2: POST HTTP 200, 40 wyników w 8,219 s zamiast timeoutu po 66,109 s. Admin, Reviewer i istniejący publiczny adres HTTP 200, bez ich restartu i bez migracji. Źródło: `tasks/completed/1102-board-search-query-timeout.md`, sekcja odbioru wdrożenia. Inne wzory i uwierzytelniony link odbiorcy nie były sprawdzane operacyjnie.
- Pozycje „Otwarte pytania” i „Blocked / deferred” z lipca 2026 (TASK-0076–0089,
  0143–0171, bramka `massImportAllowed`) są nieaktualne i leżą w
  `ai_docs/archive/CURRENT_STATE_2026Q3.md`.

## Aktywne taski

### TASK-1122 — Uproszczony panel i zastosowanie modelu (in_progress)

- Plik: `tasks/1122-grid-correction-learning-panel.md`. Operator polecił kontynuację przed audytem T2; T3 w odizolowanym worktree grid-corrections-panel na kopii stabilnego T2. Audyty i commity nadal osobno, bez pomijania Opus.

### TASK-1123 — Odbiór i dokumentacja uczenia z korekt (todo)

- Plik: `tasks/1123-grid-correction-learning-acceptance.md`. Oczekuje na TASK-1120–1122 i audyty.

### TASK-1050 — Pilotaż przycinania na danych operatora (todo)

- Plik: `tasks/1050-photo-crop-pilot.md`. Wariant B; TASK-1051 i TASK-1052 zaakceptowane i scalone do `main` 2026-10-18 (bez migracji). Pilot czeka na osobne zgody na każdy krok.

## Ostatnie 10 ukończonych tasków

- **TASK-1121** — Trening i ocena częściowych zdjęć — v1.7.518 — tasks/completed/1121-grid-correction-training-evaluation.md
- **TASK-1120** — Dane z korekt i trwały podział — v1.7.517 / `e1fcae27` — tasks/completed/1120-grid-correction-training-data.md
- **TASK-1116** — Przyciąganie kliknięcia wykresu — v1.7.513 / `781650dc` — tasks/completed/1116-board-search-chart-peak-snap.md
- **TASK-1115** — Uproszczenie ekranu wyszukiwania i modal supergry w Adminie — v1.7.511 / `3ad50668` — tasks/completed/1115-board-search-screen-simplification.md
- **TASK-1114** — Usunięcie wyszukiwania wielu układów — v1.7.508 / `969c341c` — tasks/completed/1114-remove-multi-board-search.md
- **TASK-1113** — Odblokowanie zapisu super symbolu — v1.7.514 / `923dd029` — tasks/completed/1113-super-symbol-save-lock.md
- **TASK-1112** — Plan usunięcia wyszukiwania wielu układów — v1.7.506 / `6ec12eab` — tasks/completed/1112-single-board-removal-plan.md
- **TASK-1111** — Rozszerzenie setu 2 do 1000 zdjęć — v1.7.512 / `a8727323` — tasks/completed/1111-expand-mumie-training-set-2.md
- **TASK-1110** — Drugi losowy set 60 zdjęć — v1.7.510 / `c4afc20a` — tasks/completed/1110-mumie-random-training-set-2.md
- **TASK-1109** — Kopia reguł i wypłat Mumii — v1.7.508 / `0754a77a` — tasks/completed/1109-copy-mumie-rules-payout.md
