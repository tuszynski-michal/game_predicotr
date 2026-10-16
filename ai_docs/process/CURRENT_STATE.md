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

- **Gałąź integracyjna = `main`** (operator, 2026-10-16): nowe gałęzie od `main`, scalanie do `main`. `v1.1-vision-lab-hybrid-geometry` jest w `main` i usunięta lokalnie oraz na `origin` (2026-10-16, polecenie operatora). Starsze wzmianki o „gałęzi integracyjnej” dotyczą tamtej gałęzi. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Panel wielu gier / TASK-0991 (2026-10-16):** migracja `0155`, scalenie do `main` (v1.7.364) i cleanup wykonane bez audytu (decyzja operatora); Reviewer 3001 wymaga ręcznego restartu. Numer TASK-0991 koliduje z naprawą symboli: identyfikuj pełną ścieżką. Źródło: archiwum Q4, „TASK-0991 — Panel udostępniania wielu gier”.
- **Akceptacja przed scaleniem** (operator, 2026-10-14, TASK-0992): wykonaj cały zlecony task, etap albo plan z kontrolami, dokumentacją i commitami, potem zapytaj o akceptację wyniku i zgodę na scalenie; scal po wyraźnym potwierdzeniu. Zgoda na scalenie obejmuje push `main` do origin (operator, 2026-10-16); restart usług i migracje mają osobne bramki. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975, 0991, D-548) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. TASK-1024 istnieje na `main` (zamknięcie tasków) i na `codex/v3-grid-fine-tuning`. Zakres TASK-1030–1033 zarezerwowany dla etapu 2 odczytu startowego. Źródło: archiwum Q3/Q4.
- **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`); z `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług. Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- **Migracje bazy operatora tylko za osobną zgodą**, w przejściu stop usług → scalenie → `db:migrate` → start; test na `*_test` nie jest zgodą. Nie scalaj do `main` kodu wymagającego niewykonanej migracji (API z `--reload` nie wystartuje). Ostatni zapis: `0155` (2026-10-16, panel wielu gier). Źródło: archiwum Q4, „Hybrydowy silnik siatek V3…”.
- **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. Źródło: `AGENTS.md`, „Trwałe workflowy i operacje danych”.
- **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- **Narzędzia tokenowe:** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Serena i Graphify nie są stałym narzędziem (pilot TASK-0939 zamknięty bez pomiaru). Źródło: `guides/TOKEN_TOOLING.md`.
- **Plan V3 rewizja 6** (`codex/v3-grid-fine-tuning`, accepted 2026-10-14): cały zakres i koszt zlecone; od TASK-1005 wykonuje Claude Code `claude-opus-5-5`/`high` (zamiennik `claude-fable-5-1` wybrany przez wykonawcę po sugestii operatora 2026-10-16; 0997 na `xhigh`), audytuje Codex `gpt-6-astra`. GPU smoke, trening, publikacja, aktywacja, migracje i operacje danych operatora oraz scalenie do `main` mają osobne zgody; kopia `D:\game_predictor_backup` wystarcza, bez nowego backupu. Źródło: plan sekcje 1, 3 i 8; D-552.
- **Migracje gałęzi V3:** `0155_historical_grid_acceptance`–`0163`, scalająca `0164_merge_main_board_search_panels`, `0165_grid_training_lane` (TASK-0996, lane `grid_training`) i `0166_grid_model_evaluation` (TASK-0997, manifest v17) sprawdzane tylko na bazach `*_test`; baza operatora jest na `0155_board_search_panels`. Integracja wymaga przejścia operatora i provisioningu capability przed `0161` (D-554). Źródło: archiwum Q4, „Przeniesione z okna gałęzi `codex/v3-grid-fine-tuning`…”.
- **Regresje V3:** odbiór TASK-1001 w [raporcie](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md): Admin ma te same 10 porażek co [HEAD380](../quality/TASK-1003_BASELINE_HEAD380.md), worker 17 środowiskowych w worktree, PostgreSQL tylko znana usterka `reset_game` sprzed V3 (osobne zadanie). `scripts/run_python_tests.ps1 -Suite` dla jednej ścieżki psuje kolekcję: używać bezpośredniego `pytest`. Źródło: archiwum Q4, jak wyżej.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | accepted, rev. 6; 24/24 done, czeka na integrację | — | `codex/v3-grid-fine-tuning` |

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

## Ostatnie 10 ukończonych tasków

- **TASK-1001** — Odbiór procesu i instrukcja operatora — v1.7.393 — tasks/completed/1001-v3-grid-fine-tuning-acceptance.md
- **TASK-1000** — Pełna sekcja „Geometria V3” — v1.7.392 / `eb212629` — tasks/completed/1000-v3-grid-model-workspace.md
- **TASK-1006** — Kandydat wspólnej geometrii Mumii i 777a2 — v1.7.390 / `9bf3a4b9` — tasks/completed/1006-shared-grid-model-candidate.md
- **TASK-0997** — Ocena per gra i bramka kandydata — v1.7.389 / 88b2ab82 — tasks/completed/0997-grid-model-evaluation.md
- **TASK-0996** — Trwały trening V3 w aplikacji — v1.7.388 / 6397bc51 — tasks/completed/0996-durable-v3-grid-training.md
- **TASK-1033** — `README.md` ≤ 5 000 B i `DOC_INDEX.md` — v1.7.382 / `ed25cd1c` — tasks/completed/1033-readme-doc-index.md
- **TASK-1032** — `AGENTS.md` ≤ 14 000 B — v1.7.381 / `676f22f4` — tasks/completed/1032-agents-md-slimming.md
- **TASK-1031** — Skill `merge-to-main` z preflightem — v1.7.379 / `bf0ad43b` — tasks/completed/1031-merge-to-main-skill.md
- **TASK-1030** — Skill `task-close` ze skryptem zamykania — v1.7.378 / `54e01133` — tasks/completed/1030-task-close-skill.md
- **TASK-1005** — Preset i dopuszczenie zasobów — v1.7.386 / `0862fbec` — tasks/completed/1005-grid-training-resource-admission.md
