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
- **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975, 0991, D-548) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. Źródło: archiwum Q3/Q4.
- **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`); z `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług. Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- **Migracje bazy operatora tylko za osobną zgodą**, w przejściu stop usług → scalenie → `db:migrate` → start; test na `*_test` nie jest zgodą. Nie scalaj do `main` kodu wymagającego niewykonanej migracji (API z `--reload` nie wystartuje). Ostatni zapis: `0155` (2026-10-16, panel wielu gier). Źródło: archiwum Q4, „Hybrydowy silnik siatek V3…”.
- **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. Źródło: `AGENTS.md`, „Trwałe workflowy i operacje danych”.
- **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- **Narzędzia tokenowe:** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Serena i Graphify nie są stałym narzędziem (pilot TASK-0939 zamknięty bez pomiaru). Źródło: `guides/TOKEN_TOOLING.md`.
- **Plan V3 rewizja 6** (`codex/v3-grid-fine-tuning`, accepted 2026-10-14): cały zakres i koszt zlecone; od TASK-1005 wykonuje Claude Code `claude-opus-5-5`/`high` (zamiennik `claude-fable-5-1` wybrany przez wykonawcę po sugestii operatora 2026-10-16; 0997 na `xhigh`), audytuje Codex `gpt-6-astra`. GPU smoke, trening, publikacja, aktywacja, migracje i operacje danych operatora oraz scalenie do `main` mają osobne zgody; kopia `D:\game_predictor_backup` wystarcza, bez nowego backupu. Źródło: plan sekcje 1, 3 i 8; D-552.
- **Migracje gałęzi V3:** `0155_historical_grid_acceptance`–`0163`, scalająca `0164_merge_main_board_search_panels`, `0165_grid_training_lane` (TASK-0996, lane `grid_training`) i `0166_grid_model_evaluation` (TASK-0997, manifest v17) sprawdzane tylko na bazach `*_test`; baza operatora jest na `0155_board_search_panels`. Integracja wymaga przejścia operatora i provisioningu capability przed `0161` (D-554). Źródło: archiwum Q4, „Przeniesione z okna gałęzi `codex/v3-grid-fine-tuning`…”.
- **Regresje V3:** [rejestr obowiązków](../quality/V3_BACKEND_REGRESSION_OBLIGATIONS_20261015.md) i [baseline HEAD380](../quality/TASK-1003_BASELINE_HEAD380.md) (215 PASS/10 FAIL) zachowują jawne FAIL; TASK-1001 porównuje wynik końcowy. `scripts/run_python_tests.ps1 -Suite` dla jednej ścieżki psuje kolekcję: używać bezpośredniego `pytest`. Źródło: archiwum Q4, jak wyżej.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | accepted, rev. 6; 21/24 done | TASK-1006, 1000, 1001 | `codex/v3-grid-fine-tuning` |

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

### TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2 (todo)

- [1006-shared-grid-model-candidate.md](../tasks/1006-shared-grid-model-candidate.md) na `codex/v3-grid-fine-tuning`; następny po TASK-0997 (ocena D-559 gotowa); rzeczywisty run tylko po osobnej zgodzie.

### TASK-1000 — Pełna sekcja „Geometria V3” (todo)

- [1000-v3-grid-model-workspace.md](../tasks/1000-v3-grid-model-workspace.md) na `codex/v3-grid-fine-tuning`; po TASK-0997/1006; wybór po nazwach zamiast UUID.

### TASK-1001 — Odbiór procesu i instrukcja operatora (todo)

- [1001-v3-grid-fine-tuning-acceptance.md](../tasks/1001-v3-grid-fine-tuning-acceptance.md) na `codex/v3-grid-fine-tuning`; ostatni; zawiera przyjęte P2-5 z TASK-0995 i porównanie z baseline HEAD380.

## Ostatnie 10 ukończonych tasków

- **TASK-0997** — Ocena per gra i bramka kandydata — v1.7.389 / hash w następnym commicie — tasks/completed/0997-grid-model-evaluation.md
- **TASK-0996** — Trwały trening V3 w aplikacji — v1.7.388 / 6397bc51 — tasks/completed/0996-durable-v3-grid-training.md
- **TASK-1005** — Preset i dopuszczenie zasobów — v1.7.386 / `0862fbec` — tasks/completed/1005-grid-training-resource-admission.md
- **TASK-0995** — Kwalifikacja korekt i niezmienny snapshot — v1.7.385 / `f0cfa9bd` — tasks/completed/0995-grid-training-cohort-snapshot.md
- **TASK-1009** — Losowa kontrola geometrii Mumii i 777a2 — v1.7.384 / `d2b692db` — tasks/completed/1009-grid-quality-measurement.md
- **TASK-1018** — Zgodność narzędzi i regresji po zmianach V3 — v1.7.383 / `ea9a27b2` — tasks/completed/1018-v3-head-compatibility-regressions.md
- **TASK-1024** — Zamknięcie nieaktualnych tasków na `main` — v1.7.375 / `5fa317c4` — tasks/completed/1024-close-stale-tasks.md
- **TASK-0991** — Panel udostępniania wielu gier — v1.7.364 / `cb87d269` — tasks/completed/0991-multi-game-board-search-share.md
- **TASK-1023** — `CLAUDE.md` bez duplikatu `AGENTS.md` i końcowy pomiar — v1.7.372 / `e342fdb6` — tasks/completed/1023-claude-md-dedupe-final-measurement.md
- **TASK-1022** — Zastosowanie budżetów `CURRENT_STATE.md` — v1.7.370 / `13800534` — tasks/completed/1022-current-state-budgets.md
