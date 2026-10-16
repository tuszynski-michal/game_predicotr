---
title: Current project state
status: active
last_updated: 2026-10-16
---

# Current State

Ten plik jest obowiązkowym odczytem startowym i ma **okno kroczące z budżetami** (łącznie ≤ 30 000 B). Zawiera tylko (1) obowiązujące ograniczenia operacyjne (≤ 8 000 B), (2) plany z niezakończonymi taskami jako jedną tabelę (≤ 5 000 B), (3) otwarte decyzje i pytania, (4) po jednym wskaźniku ≤ 1 200 B na task aktywny (`in_progress`, `blocked`, `todo`: każdy task z plikiem w `ai_docs/tasks/`) oraz (5) 10 jednowierszowych wpisów `done` (≤ 400 B każdy). Pełna historia leży bez zmian w [archiwum Q4 2026](../archive/CURRENT_STATE_2026Q4.md) (od 2026-10-01) i [archiwum Q3 2026](../archive/CURRENT_STATE_2026Q3.md) (wcześniej); szczegóły taska aktywnego są w jego pliku.

Reguła utrzymania: przy zamykaniu taska agent (1) dopisuje pełną sekcję `done` na początku najnowszego pliku archiwum (tuż pod nagłówkiem, bez edycji tekstu), (2) dopisuje w oknie jeden wiersz `done` na początku sekcji „Ostatnie 10 ukończonych tasków” w formacie `- **TASK-NNNN** — tytuł — vX.Y.N / krótki hash — tasks/completed/<plik>.md`, (3) usuwa z okna najstarszy wiersz ponad 10 (jego pełna sekcja jest już w archiwum), (4) usuwa wskaźnik zamkniętego taska z „Aktywne taski” i (5) aktualizuje „Obowiązujące ograniczenia” oraz „Plany”. Wskaźnik aktywnego taska ma status, ścieżkę pliku, jedno zdanie blokera lub następnego kroku i ≤ 1 200 B; szczegóły idą do `Outcome` pliku taska. Lead dopisuje hashe commitów jak dotychczas. Spójność okna sprawdzają `scripts/check_current_state_window.py` i `scripts/check_startup_read_budget.py` (część `npm run docs:check`).

## Obowiązujące ograniczenia

Każdy punkt wskazuje źródło; stan z daty wpisu przed poleganiem na nim zweryfikuj odczytem, bez zmian w systemie. Pełne, niezmienione teksty dawnych punktów (także skróconych poniżej) są na początku archiwum Q4, sekcja „Przeniesione z okna 2026-10-16 (TASK-1022)”.

- **Gałąź integracyjna = `main`** (operator, 2026-10-16): nowe gałęzie od `main`, scalanie do `main`. `v1.1-vision-lab-hybrid-geometry` jest w `main` i usunięta lokalnie; na `origin` zostaje do decyzji operatora. Starsze wzmianki o „gałęzi integracyjnej” dotyczą tamtej gałęzi. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Panel wielu gier / TASK-0991 (2026-10-16):** migracja `0155`, scalenie do `main` (v1.7.364) i cleanup wykonane bez audytu (decyzja operatora); Reviewer 3001 wymaga ręcznego restartu. Numer TASK-0991 koliduje z naprawą symboli: identyfikuj pełną ścieżką. Źródło: archiwum Q4, „TASK-0991 — Panel udostępniania wielu gier”.
- **Akceptacja przed scaleniem** (operator, 2026-10-14, TASK-0992): wykonaj cały zlecony task, etap albo plan z kontrolami, dokumentacją i commitami, potem zapytaj o akceptację wyniku i zgodę na scalenie; scal po wyraźnym potwierdzeniu. Push, restart usług i migracje mają osobne bramki. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. TASK-1024 istnieje na `main` (zamknięcie tasków) i na `codex/v3-grid-fine-tuning`. Zakres TASK-1030–1033 zarezerwowany dla etapu 2 odczytu startowego. Źródło: archiwum Q3/Q4.
- **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`); z `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług. Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- **Migracje bazy operatora tylko za osobną zgodą**, w przejściu stop usług → scalenie → `db:migrate` → start; test na `*_test` nie jest zgodą. Nie scalaj do `main` kodu wymagającego niewykonanej migracji (API z `--reload` nie wystartuje). Ostatni zapis: `0155` (2026-10-16, panel wielu gier). Źródło: archiwum Q4, „Hybrydowy silnik siatek V3…”.
- **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. Źródło: `AGENTS.md`, „Trwałe workflowy i operacje danych”.
- **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- **Narzędzia tokenowe:** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Serena i Graphify nie są stałym narzędziem (pilot TASK-0939 zamknięty bez pomiaru). Źródło: `guides/TOKEN_TOOLING.md`.
- **Nowy format okna (TASK-1022):** po scaleniu `feat/startup-read-diet` każda inna otwarta gałąź (np. `codex/v3-grid-fine-tuning`, `codex/photo-crop-p1`) przepisuje swoje hunki tego pliku na nowy format: wskaźnik aktywnego taska ≤ 1 200 B, wiersz `done` w oknie, pełna sekcja `done` na początku archiwum Q4. Źródło: `AGENTS.md`, „Po kodowaniu” 3.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md` | accepted (2026-10-16), etap A w toku | TASK-1031–1033 todo (1030 done) | `feat/stage2-plan` |
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | proposed, rev. 2 (na `codex/v3-grid-fine-tuning`: accepted, rev. 6) | TASK-0993–1006 w planie; pliki tasków tylko na tamtej gałęzi | `codex/v3-grid-fine-tuning` |

Pozostałe plany z aktywnymi taskami zamknięto 2026-10-16 (TASK-1024): ich taski uznano za nieaktualne; dawne wiersze tabeli są na początku archiwum Q4.

## Otwarte decyzje i pytania

- Decyzje czekające na operatora: status planu symboli premium Mumii (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`), decyzja D-463 dla odroczonego snapshotu mobilnego oraz status planu `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`). Pytania R1–R15 przeglądu TASK-1021 rozstrzygnięto zamknięciem tasków (TASK-1024).
- Pytania produktowe: `ai_docs/project/OPEN_QUESTIONS.md`; jedyne nierozstrzygnięte
  to Q-020 (zgoda właściciela na analizę aplikacji referencyjnej; nie blokuje
  bieżących prac).
- Decyzje architektoniczne: indeks 30 najnowszych w
  `ai_docs/process/DECISION_LOG.md` (starsze w archiwum indeksu); wszystkie wpisy mają status `accepted`
  albo `superseded`, brak wpisów `proposed`.
- Pozycje „Otwarte pytania” i „Blocked / deferred” z lipca 2026 (TASK-0076–0089,
  0143–0171, bramka `massImportAllowed`) są nieaktualne i leżą w
  `ai_docs/archive/CURRENT_STATE_2026Q3.md`.

## Aktywne taski

TASK-1024 zamknął 2026-10-16 wszystkie 42 dawne taski jako nieaktualne. Taski toru V3 (TASK-0993–1024) są na gałęzi `codex/v3-grid-fine-tuning`.

### TASK-1031 — skill `merge-to-main` z preflightem (todo)

- `ai_docs/tasks/1031-merge-to-main-skill.md`; etap A, po TASK-1030.

### TASK-1032 — `AGENTS.md` ≤ 14 000 B (todo)

- `ai_docs/tasks/1032-agents-md-slimming.md`; etap B, po skillach z etapu A.

### TASK-1033 — `README.md` ≤ 5 000 B i `DOC_INDEX.md` (todo)

- `ai_docs/tasks/1033-readme-doc-index.md`; etap B, zamyka plan.

## Ostatnie 10 ukończonych tasków

- **TASK-1030** — Skill `task-close` ze skryptem zamykania — v1.7.378 — tasks/completed/1030-task-close-skill.md
- **TASK-1024** — Zamknięcie nieaktualnych tasków na `main` — v1.7.375 / `5fa317c4` — tasks/completed/1024-close-stale-tasks.md
- **TASK-0991** — Panel udostępniania wielu gier — v1.7.364 / `cb87d269` — tasks/completed/0991-multi-game-board-search-share.md
- **TASK-1023** — `CLAUDE.md` bez duplikatu `AGENTS.md` i końcowy pomiar — v1.7.372 / `e342fdb6` — tasks/completed/1023-claude-md-dedupe-final-measurement.md
- **TASK-1022** — Zastosowanie budżetów `CURRENT_STATE.md` — v1.7.370 / `13800534` — tasks/completed/1022-current-state-budgets.md
- **TASK-1021** — Przegląd ograniczeń i sekcji `CURRENT_STATE.md` — v1.7.368 / `a8ed5dcc` (decyzja v1.7.369 / `13cb5022`) — tasks/completed/1021-current-state-constraints-review.md
- **TASK-1020** — `DECISION_LOG.md` jako lekki indeks — v1.7.367 / `d803c27c` — tasks/completed/1020-decision-log-light-index.md
- **TASK-1019** — Skrypt pomiaru i budżetów odczytu startowego — v1.7.366 / `d1174304` — tasks/completed/1019-startup-read-budget-script.md
- **TASK-1007** — Trwałe wykrywanie Claude Code CLI — v1.7.361 / `baf67dbd` (scalenie v1.7.362 / `885ba12f`) — tasks/completed/1007-claude-cli-discovery.md
- **TASK-0991** — Wznowienie symboli i pełny przebieg 777 a2 <80% — v1.7.358 / `17a1012e` (naprawa v1.7.351 / `6e84a1b1`) — tasks/completed/0991-symbol-reinference-resume.md
