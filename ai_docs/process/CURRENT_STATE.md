---
title: Current project state
status: active
last_updated: 2026-11-18
---

# Current State

Obowiązkowy odczyt startowy to **okno kroczące ≤ 30 000 B**: ograniczenia operacyjne ≤ 8 000 B, tabela niezakończonych planów ≤ 5 000 B, otwarte pytania, wskaźniki aktywnych tasków (`in_progress`, `blocked`, `todo` w `ai_docs/tasks/`) ≤ 1 200 B każdy i 10 wierszy `done` ≤ 400 B każdy. Szczegóły aktywnego taska są w jego pliku. Pełna historia pozostaje bez zmian w [archiwum Q4](../archive/CURRENT_STATE_2026Q4.md) od 2026-10-01 i [archiwum Q3](../archive/CURRENT_STATE_2026Q3.md) dla wcześniejszych dat.

Zamykaj task przez `scripts/close_task.py` ([procedura](../../.agents/skills/task-close/SKILL.md)). Skrypt archiwizuje pełny wpis, usuwa wskaźnik i dopisuje najnowszy z 10 wierszy `done`. Wskaźnik podaje status, plik i następny krok lub bloker. Plany i ograniczenia aktualizuj osobno. Hash dopisz przez `record-hash` w kolejnym commicie. Format i budżety sprawdza `npm run docs:check`.

## Obowiązujące ograniczenia

- **777 a2:** model symboli5 `9afa868a` aktywny. Źródło: TASK-1179.

- **Audyt Claude (operator2026-11-08):** terminal/polecenia są wymaganym sposobem. Desktop wyłącznie na nowe, jawne polecenie dla danego audytu. Operator loguje CLI sam; nie sterujemy logowaniem ani nie kopiujemy tokenów. Limit Opus pozwala odłożyć audyty i kontynuować kod, bez PASS/commita oczekującego taska.

- **Mumie A2 / TASK-1176–1178:** kod v1.7.597 wdrożony; API/Admin/general po restarcie. bf601495:691 zdjęć/6219 plansz/0%. Ready276 TRAIN/75 nowych (~58s), canStart=true; bez nowego treningu. Źródło: `quality/REVIEW_LEARNING_RELIABILITY_DEPLOYMENT_20261110.md`.

- **Mumie A2 / TASK-1246:** gra=6cc10344 rev7, default=01767a49 rev5; 2 siatki ręcznie. Szczegóły w Outcome.

- **Uczenie siatek / TASK-1205–1206, 1212:** gate v6, trening bije bazę, bez progu zdjęć; `0189` (dev), `0190`. D-611, D-613.

- **Selektor1.0.5:** zaakceptowany; reboot/odbiorca pending. Źródło: `quality/SELECTOR_SMOOTH_1_0_5_20261103.md`.

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
- **Plan V3 rewizja6:** zlecony zakres/model/koszt w `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`, sekcje1/3/8 i D-552. Operacje GPU/trening/publikacja/aktywacja/migracje/operator/merge wymagają osobnych zgód; zaakceptowana kopia `D:\game_predictor_backup` wystarcza.
- **Integracja V3 (2026-10-16):** main/origin v1.7.396, operator0166/manifestv17; historyczny brak defaultu nie opisuje obecnego stanu MumieA2 powyżej. Lane grid-training wykrywa `D:\game_predicotr\.venv-vision-lab` (torchcu130), bez środowiskaC. Źródło: [odbiór](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md), sekcja6.
- **Regresje V3:** odbiór TASK-1001 w [raporcie](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md): Admin ma te same 10 porażek co [HEAD380](../quality/TASK-1003_BASELINE_HEAD380.md), worker 17 środowiskowych w worktree, PostgreSQL tylko znana usterka `reset_game` sprzed V3 (osobne zadanie). `scripts/run_python_tests.ps1 -Suite` dla jednej ścieżki psuje kolekcję: używać bezpośredniego `pytest`. Źródło: archiwum Q4, jak wyżej.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md` | TASK-1253–1257: prywatna rodzina i niezależny pierwszy trening | migracje 0193–0194, włączenie dla Mumii, świeże nagranie do pilota i osobne polecenie treningu | `codex/private-grid-models` |
| `delivery/PARTIAL_SLOT_BINDING_PLAN_20261115.md` | 1208–1209 done (v1.7.640–641), audyt Codex P0 zamknięty | scalenie i ponowny import 8 zdjęć za zgodą | `claude/partial-slot-binding` |
| `delivery/GRID_COHORT_NOTICE_PERFORMANCE_PLAN_20261112.md` | accepted 2026-11-12; TASK-1195 done (v1.7.617, migracja 0186 nie wykonana na bazie operatora) | TASK-1196–1197 (osobne polecenie); scalenie i migracja za zgodą | `claude/grid-cohort-refs` |
| `delivery/EFFECTIVE_GRID_LEARNING_PLAN_20261111.md` | accepted; T1–T4 lokalnie v1.7.602–605; audyty Codex T2–T4 niewykonane (operator) | brak tasków; odbiór i zgoda na scalenie, potem osobno migracja0184 i dane A | `codex/effective-grid-delivery` |
| `delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md` | T0–T5 i poprawka startu Opus PASS; main/origin, baza0183, usługi działają lokalnie | obrysy z siatek w oknie TASK-1201 (Mumie A2: 210 zatwierdzonych), ślepy pomiar, świeże kontrole i dowód rodowodu; trening nieuruchomiony | `main` |
| `delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` | poprawki TASK-1098–1100 zaakceptowane i scalone lokalnie 2026-10-27 (v1.7.484–488): wzory przed szukaniem, +10 zdjęć, 60 s i domyślne 40 wyników; push i cleanup objęte zgodą | odbiór działającego linku i fizycznego Androida; usługi bez restartu agenta | `main` |
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | accepted, rev. 6; 24/24 done, zintegrowany w `main` | rzeczywisty eksperyment TASK-1006 za osobną zgodą | `main` |
| `delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md` | accepted, rev. 2; etapy A i B w `main`; rewizja 3 (wariant B, D-563) w `main` | TASK-1050 (pilot) | `claude/photo-crop-pilot` |
| `delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md` | accepted 2026-10-19; 5/5 tasków done (v1.7.426–430, audyty Codex 1056/1057/1059 zamknięte); czeka na odbiór operatora (restart Reviewera i API, test linku Mumii) i zgodę na scalenie | brak (odbiór i scalenie) | `claude/share-super-series` |

Pozostałe plany z aktywnymi taskami zamknięto 2026-10-16 (TASK-1024): ich taski uznano za nieaktualne; dawne wiersze tabeli są na początku archiwum Q4.

## Otwarte decyzje i pytania

- **TASK-1245/P2:** Outcome.

- **Bramka v4 / TASK-1188:** baza na 0185; `bf327cfa` zastosowany poleceniami rejestru, bo panel uczenia `63767b36` przypina starą ocenę REVISE.

- **Mumie A2 / TASK-1152:** naprawa licznika wdrożona po Opus PASS i zgodzie; ten sam apply zakończony, default i MumieA2 revision2. Porównanie151plansz w root artifacts/grid-applied-comparison-20261103/comparison.html.


- **TASK-1147 / P2:** 2 zastane FAIL retencji także na `60f50c64`; produkt fail-closed, naprawa osobno. Źródło: `quality/TASK-1147_VERIFICATION.md`.

- **Wdrożenie 777A2 / 2026-11-03:** zatwierdzony delete pustej 777v2 i migracja 0177 zakończone; usługi zdrowe. Pozostałe gry i aktywacje zachowane, bez pilota 777A2. TASK-1148 buildy i Opus PASS. [Odbiór](../quality/777A2_DEPLOYMENT_BLOCKER_20261103.md).

- **TASK-1137 / P2 Opus:** dwa zastane FAIL w test_grid_training_run_preview.py (lista presetów i stara blokada korekt), potwierdzone baseline main. Nie maskują wyniku nowego testu limitów; naprawa osobno.

- **Mumie A2 / TASK-1136–1137:** poprzedni trening PASS, default v1 zachowany. Szczegóły i HTML: [odbiór](../quality/GRID_LEARNING_DEPLOYMENT_20261103.md).

- **TASK-1134 / P2 Opus:** domyślne repo CUDA jest pokryte naprawą CLI; niestandardowy `-GridTrainingPython` i User-only/invalid env w launcherze lane mają nadal odrębną politykę. Ujednolicenie poza zakresem; szczegóły w Outcome TASK-1134.

- **TASK-1120–1123:** main/origin,4×OpusPASS, migracja0171 za zgodą. Historyczny odbiór bez treningu/aktywacji; pełny mypy nie ma PASS (scoped tak). Źródło: [odbiór2026-11-02](../quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md).

- Przycinanie oryginałów: zgody na kolejne kroki pilotażu TASK-1050.
- Decyzje czekające na operatora: status planu symboli premium Mumii (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`), decyzja D-463 dla odroczonego snapshotu mobilnego oraz status planu `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`). Pytania R1–R15 przeglądu TASK-1021 rozstrzygnięto zamknięciem tasków (TASK-1024).
- Pytania produktowe: `ai_docs/project/OPEN_QUESTIONS.md`; jedyne nierozstrzygnięte
  to Q-020 (zgoda właściciela na analizę aplikacji referencyjnej; nie blokuje
  bieżących prac).
- Decyzje architektoniczne: indeks 30 najnowszych w
  `ai_docs/process/DECISION_LOG.md` (starsze w archiwum indeksu); wszystkie wpisy mają status `accepted`
  albo `superseded`, brak wpisów `proposed`.
- TASK-1102: wcześniejszy odbiór777a2=40wyników/8,219s; inne wzory/link odbiorcy niesprawdzone. Źródło: `tasks/completed/1102-board-search-query-timeout.md`; pełny dawny wpis w archiwumQ4/TASK1151.
- Pozycje „Otwarte pytania” i „Blocked / deferred” z lipca 2026 (TASK-0076–0089,
  0143–0171, bramka `massImportAllowed`) są nieaktualne i leżą w
  `ai_docs/archive/CURRENT_STATE_2026Q3.md`.

## Aktywne taski

### TASK-1233 — Plan wydajnego uczenia i audyt (blocked)

- `tasks/1233-grid-learning-efficiency-plan-review.md`: plan przyjęty; worktree blokuje zapis .git, świeży audyt CLI kończy się 401 OAuth.

### TASK-1231 — Podgląd i napis zakresu Selektora (blocked)

- `tasks/1231-selector-preview-range-overlay.md`: nakładka tylko podglądu, zapis per projekt; blokady w tasku.

### TASK-1230 — Uczenie w tle (in_progress)

- `tasks/1230-grid-learning-background-preparation.md`: PASS; kod do integracji.

### TASK-1050 — Pilotaż przycinania na danych operatora (todo)

- Plik: `tasks/1050-photo-crop-pilot.md`. Wariant B; TASK-1051 i TASK-1052 zaakceptowane i scalone do `main` 2026-10-18 (bez migracji). Pilot czeka na osobne zgody na każdy krok.

## Ostatnie 10 ukończonych tasków

- **TASK-1265** — Partie podejrzanych siatek Mumii A2 — v1.7.697 / `315d0e97` — tasks/completed/1265-mumie-suspicious-batches.md
- **TASK-1264** — Stałe dane prywatnego treningu siatek — v1.7.696 / `c4b78912` — tasks/completed/1264-grid-training-metadata-reads.md
- **TASK-1263** — Zamknięcie zestawu prywatnego treningu — v1.7.695 / `9ca7cd80` — tasks/completed/1263-private-cohort-freeze.md
- **TASK-1262** — Wersja odniesienia po korektach — v1.7.694 / `343ece9a` — tasks/completed/1262-assigned-grid-comparison.md
- **TASK-1261** — Trening z wgranych plansz — v1.7.693 / `7b85d745` — tasks/completed/1261-training-with-imported-boards.md
- **TASK-1259** — Seria zdjęć w Reviewerze — v1.7.691 / `644d2416` — tasks/completed/1259-reviewer-photo-series.md
- **TASK-1258** — Korekta jednego zdjęcia — v1.7.690 / `a631dcea` — tasks/completed/1258-reviewer-single-photo.md
- **TASK-1257** — Niezależny pierwszy trening geometrii gry — v1.7.686 / `7c71402d` — tasks/completed/1257-independent-game-grid-training.md
- **TASK-1256** — Ślepy pilot cięcia siatek Mumii A2 — v1.7.684 / `fda9ecc0` — tasks/completed/1256-mumie-private-grid-pilot.md
- **TASK-1255** — Zastosowanie i cofnięcie prywatnego modelu — v1.7.682 / `dbd0d686` — tasks/completed/1255-private-grid-model-apply.md
