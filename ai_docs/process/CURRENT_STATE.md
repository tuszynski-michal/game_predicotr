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

- **Gałąź integracyjna = `main`** (operator, 2026-10-16): nowe gałęzie od `main`, scalanie do `main`. `v1.1-vision-lab-hybrid-geometry` jest w `main`; usuwa ją operator albo agent za osobną zgodą (wskazuje ją worktree `multi-game-share`). Starsze wzmianki o „gałęzi integracyjnej” dotyczą tamtej gałęzi. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Akceptacja przed scaleniem** (operator, 2026-10-14, TASK-0992): wykonaj cały zlecony task, etap albo plan z kontrolami, dokumentacją i commitami, potem zapytaj o akceptację wyniku i zgodę na scalenie; scal po wyraźnym potwierdzeniu. Push, restart usług i migracje mają osobne bramki. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. Źródło: archiwum Q3/Q4.
- **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`). Z katalogu `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług do etapu C (TASK-0957). Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- **Migracje bazy operatora tylko za osobną zgodą**, w przejściu stop usług → scalenie → `db:migrate` → start; test na `*_test` nie jest zgodą. Nie scalaj do `main` kodu wymagającego niewykonanej migracji (API z `--reload` nie wystartuje). Ostatni zapis: `0154` (2026-10-10). Źródło: archiwum Q4, „Hybrydowy silnik siatek V3…”.
- **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. GC TASK-0517 zatrzymany; wznowienie tylko za nową zgodą dla istniejącego SHA. Źródło: `AGENTS.md`; `tasks/0517-confirmed-legacy-game-removal.md`.
- **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- **`apply` manifestu Arbuz < 60 %** (sha256 `1e4be8ce…`, 2 703 plansze) nie biegnie równolegle z weryfikacją w Adminie ani z przeliczaniem predykcji. Źródło: archiwum Q3, „D-464 — biblioteka wzorców symboli, etap A”.
- **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- **Narzędzia tokenowe (pilot TASK-0939):** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; Serena i Graphify bez stałego wpisu do czasu pomiaru; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Źródło: `guides/TOKEN_TOOLING.md`.
- **Poll worker `general` po TASK-0991:** istniejący proces nie był przeładowany po naprawie v1.7.351; przeładowuje operator według instrukcji w `tasks/completed/0991-symbol-reinference-resume.md`.
- **Nowy import 275 zdjęć Mumii:** po wymianie źródeł 2026-10-09 przygotować paczkę z identycznymi nazwami i rangami jako nowy import; oryginały i staging zachowane. Źródło: `quality/MUMIE_SOURCE_REPLACEMENT_20261009.md`.
- **Seria supergry Mumii:** migracja `0152` jest zawarta w `0154`, ale `POST …/derive` dla Mumii nie jest odnotowany; to warunek pomiaru TASK-0937. Źródło: archiwum Q4, „TASK-0933 — wyprowadzanie serii supergry i API serii (done)”.
- **Gra Mumie `draft`** (`fea55cc1-…`, `grid_profile_mumie_v1`): wyniki serii są `provisional` do zdefiniowania super symbolu i świeżej generacji serii (D-537); nie wchodzą do bilansu ani rozpoznanych wypłat. Źródło: archiwum Q4, TASK-0843 i TASK-0936.
- **Modele symboli Mumii:** odrzuconego kandydata V5 nie używać (TASK-0872, obowiązuje baseline R2 RGB); historycznego CLI `verified_v19` nie uruchamiać, import przez `scripts/run_mumie_image_import.py`. Źródło: archiwum Q4, TASK-0872 i TASK-0843.
- **Nowy format okna (TASK-1022):** po scaleniu `feat/startup-read-diet` każda inna otwarta gałąź (np. `codex/v3-grid-fine-tuning`, `codex/photo-crop-p1`) przepisuje swoje hunki tego pliku na nowy format: wskaźnik aktywnego taska ≤ 1 200 B, wiersz `done` w oknie, pełna sekcja `done` na początku archiwum Q4. Źródło: `AGENTS.md`, „Po kodowaniu” 3.

## Plany z niezakończonymi taskami

| Plan | Status | Pozostałe taski | Gałąź |
|---|---|---|---|
| `delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md` | accepted (2026-10-16) | TASK-1022, TASK-1023 (1019–1021 done) | `feat/startup-read-diet` |
| `delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md` | proposed, rev. 2 (na `codex/v3-grid-fine-tuning`: accepted, rev. 6; R8) | TASK-0993–1006 w planie; pliki tasków tylko na tamtej gałęzi | `codex/v3-grid-fine-tuning` |
| `delivery/DISK_D_MIGRATION_PLAN_20261009.md` | accepted (D-540) | TASK-0956 blocked, TASK-0957 todo | scalona (v1.7.312) |
| `delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md` | proposed (D-539) | TASK-0947–0949 todo | brak gałęzi |
| `delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md` | implemented, czeka na odbiór; migracja `0154` wykonana (R6) | TASK-0972 blocked | scalona (v1.7.306/308) |
| `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` | accepted (D-535; R2) | TASK-0937, TASK-0939 blocked | scalona |
| `delivery/VISION_LAB_EXECUTION_PLAN.md` | accepted (D-447) | TASK-0668, 0671, 0672–0678; 0649–0653 zastąpione | – |
| `delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md` | active | TASK-0645–0647 blocked | – |
| `delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` | `completed` w nagłówku (R1) | TASK-0687–0691, 0694, 0695, 0698 | – |
| `delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` | accepted | TASK-0802 in_progress | – |

Plan braków geometrii w lokalnym Reviewerze (`delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`, TASK-0961–0965 w `completed/`) przeniesiono do archiwum (odbiór wizualny: R7). Pełne dawne podsekcje planów są na początku archiwum Q4.

## Otwarte decyzje i pytania

- Pytania produktowe: `ai_docs/project/OPEN_QUESTIONS.md`; jedyne nierozstrzygnięte
  to Q-020 (zgoda właściciela na analizę aplikacji referencyjnej; nie blokuje
  bieżących prac).
- Decyzje czekające na operatora: status planu symboli premium Mumii
  (`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`), rozstrzygnięcie sprzecznych zasad
  transakcji routingu V2 (TASK-0698), osobna decyzja o wznowieniu reweryfikacji
  777 (TASK-0645–0647), decyzja D-463 dla odroczonego snapshotu mobilnego oraz
  status planu `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`).
- Decyzje architektoniczne: indeks 30 najnowszych w
  `ai_docs/process/DECISION_LOG.md` (starsze w archiwum indeksu); wszystkie wpisy mają status `accepted`
  albo `superseded`, brak wpisów `proposed`.
- Pozycje „Otwarte pytania” i „Blocked / deferred” z lipca 2026 (TASK-0076–0089,
  0143–0171, bramka `massImportAllowed`) są nieaktualne i leżą w
  `ai_docs/archive/CURRENT_STATE_2026Q3.md`.
- Rozbieżności z przeglądu TASK-1021 (`quality/CURRENT_STATE_REVIEW_20261016.md`, sekcja 5; otwarte, bez napraw w TASK-1022):
  - R1 legacy `public`: D-467 odnotowuje `0125` jako zastosowaną, a TASK-0687–0691/0694/0695/0698 są aktywne; zamknąć te taski?
  - R2 plan Mumie: 0929–0936 i 0938 są w `completed/`; uznać plan za wykonany poza 0937/0939?
  - R3 TASK-0939: okno `in_progress`, plik taska i v1.7.285 `blocked`; który status obowiązuje?
  - R4 TASK-0603: potwierdzić archiwizację sekcji „eksperyment shape v2” i „przygotowanie realnej kalibracji”.
  - R5 migracja `0154` a warunki starsze (TASK-0928 `0147`, TASK-0937 `0152`): czy job `092ff7a4…` istnieje i czy `POST …/derive` dla Mumii wykonano?
  - R6 plan cofania korekt: nagłówek „awaiting operator migration”, choć `0154` wykonana 2026-10-10.
  - R7 plan braków geometrii w Reviewerze: czy wykonano odbiór wizualny?
  - R8 plan V3 fine-tuning: `proposed` rev. 2 tu, `accepted` rev. 6 na `codex/v3-grid-fine-tuning`; czy tamta gałąź scali się przed TASK-1022?
  - R9 martwe źródła „w tym pliku” (TASK-0932, 0933, 0936, 0940): są w archiwum Q4.
  - R10 TASK-0654: czy odbiór na żywych danych jest nadal wstrzymany, skoro usługi działają z D?
  - R11 TASK-0649–0653 zastąpione przez D-447; zamknąć jako superseded?
  - R12 TASK-0802, TASK-0675, TASK-0676: `neural_grid` działa produkcyjnie (D-544); czy te taski są aktualne?
  - R13 Arbuz `apply` (`1e4be8ce…`) i TASK-0305: czy manifest zastosowano, czy D-543 pokrywa zamiennik zdjęcia planszy?
  - R14 dysk C: czy lista kontrolna TASK-0956 i kontrole fizyczne panelu zarządzania wykonano; sesja Claude Code zarejestrowana pod C.
  - R15 TASK-0472: okno było nieaktualne (cztery bramki, plik: szósta); po zmianie zostaje wskaźnik, do potwierdzenia.

## Aktywne taski

### TASK-1023 — `CLAUDE.md` bez duplikatu i końcowy pomiar (todo)

- `ai_docs/tasks/1023-claude-md-dedupe-final-measurement.md`; etap C, zamyka plan.

### TASK-0956 — pierwsze uruchomienie aplikacji z D i odbiór (blocked)

- `ai_docs/tasks/0956-disk-d-application-startup.md`. Etap B2 wykonany 2026-10-10 (usługi z D, `0154`, 0 brakujących ścieżek). Czeka na listę kontrolną operatora: restart Windows, telefon i tunel, wpisy C w `Path`, ponowny backfill weryfikacji symboli Mumii. v1.7.309 / `ba3b36d1`, scalenie v1.7.312.

### TASK-0957 — sprzątanie po przeniesieniu i ścieżki C w jobach (todo)

- `ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md`. Podgląd gotowy (sekcja „Preview” w tasku): stary vhdx na C, checkout C, `source_directory` jobów, bazy testowe; każda operacja za osobną zgodą. v1.7.310 / `190d30cc`.

### TASK-0947, TASK-0948, TASK-0949 — korekta układu panelu (todo)

- Pliki: `ai_docs/tasks/0947-management-point-workspace-layout.md`, `0948-management-modal-recovery-and-legacy-access.md`, `0949-management-layout-visual-acceptance.md`. Plan `delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md` (proposed) czeka na akceptację operatora. D-539: piny wszystkich zapisanych stawek widoczne od razu (kod ogranicza podgląd przez `selectedStake && !editor`). Ograniczenie D-539: sekcja „Ograniczenia z CURRENT_STATE” w pliku TASK-0947.

### TASK-0290 — benchmark i kontrolowany rollout zdalnej ręcznej selekcji (blocked)

- `ai_docs/tasks/0290-remote-manual-selection-rollout-benchmark.md`. Operator-local workflow wdrożony; benchmark i publiczny rollout (LAN/Quick Tunnel) wstrzymane do decyzji właściciela; przed publicznym pilotem wymagany checkpoint polityki feature flag. Historia: archiwum Q4 (sekcja przeniesiona 2026-10-16).

### TASK-0305 — Zastępcze zdjęcie pojedynczej planszy 0.10 (todo)

- Plik zadania: `ai_docs/tasks/0305-v0-10-replacement-board-source.md`.
- Status: Zadanie jest celowo odroczone poza wersję 0.9. Przed implementacją wymaga osobnego breakdownu API, transakcji i UX.
- Cel: Pozwolić operatorowi dodać nowe zdjęcie dla jednego numeru planszy, utworzyć z niego niezależne źródło i wynik rozpoznania oraz świadomie przełączyć kanonicznego właściciela sekwencji bez utraty historii poprzedniego źródła.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „Odbiór wersji 0.9 — TASK-0304”.

### TASK-0472 — akceptacja cropów v11 (blocked)

- `ai_docs/tasks/0472-crop-v11-acceptance.md`. Szósta niezależna bramka jakości nie przeszła ścisłej precyzji; v11 nieaktywny, dane użytkownika bez zmian; dalsze prace tylko po osobnym poleceniu. Raport `quality/SELECTED_CROP_V11_REGRESSIONS.md`. Historia czterech dawnych sekcji: archiwum Q4.

### TASK-0517 — baza starej gry usunięta, częściowy GC zatrzymany (in_progress)

- `ai_docs/tasks/0517-confirmed-legacy-game-removal.md`. Baza starej gry `777 v0.1` usunięta (`database_done`); fizyczny GC zatrzymany przez operatora (receipt `executing`, 19,8 z 104,9 GiB). Wznowienie tylko za nową dokładną zgodą dla preview SHA `c4cce437…`.

### TASK-0603 — kalibracja etykiet 777 V7 w trybie V2 (in_progress)

- `ai_docs/tasks/0603-v7-real-777-calibration.md`. Sesja V2 (manifest `.runtime/v7-label-geometry-calibration-t0603-v2.local.json`) czeka na anotacje operatora; potem profil, raport walidacji i adopcja; V7 zablokowane. Instrukcja: `LOCAL_OPERATION_GUIDE.md`. Dwie dawne sekcje (eksperyment shape v2, przygotowanie realnej kalibracji): archiwum Q4 (R4).

### TASK-0611 — Rdzeń V2.1 dla siatki osobnych ramek plansz (in_progress)

- Plik zadania: `ai_docs/tasks/0611-shape-geometry-v2-board-frame-lattice.md`.
- Status: `in_progress`
- Cel: Wykrywać na prawdziwych zdjęciach 777 i Mumii pełną siatkę 3 × 3 osobnych ramek plansz, bez zależności od koloru, jako deterministyczną propozycję testową bez importu ani zapisu danych gry.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „P00 / TASK-0665 — zapis planu laboratorium wizji (D-447)”.

### TASK-0645, TASK-0646, TASK-0647 — reweryfikacja siatek 777 (blocked)

- Pliki: `ai_docs/tasks/0645-777-grid-reverify-dry-run.md`, `0646-777-grid-reverify-execute.md`, `0647-777-grid-reverify-live-run.md`. Plan `delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`; D-445 wstrzymała stary weryfikator, D-447 nie upoważnia do uzupełniania slotów historycznego 777 siecią ani zapisu na żywych danych; wznowienie wymaga osobnej decyzji. Ograniczenie: sekcja „Ograniczenia z CURRENT_STATE” w plikach tasków.

### TASK-0649, TASK-0650, TASK-0651, TASK-0652, TASK-0653 — dawny plan sieci siatek (blocked, zastąpiony)

- Pliki: `ai_docs/tasks/0649-grid-nn-candidate-pool.md` … `0653-grid-nn-777-slot-fill.md`. Plan zastąpiony przez `delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447), odpowiedniki TASK-0666/0668–0671/0674/0675/0678. Numery kolidują z ukończoną serią „Przybliżona wygrana” (`completed/0649-…`–`0653-…`); identyfikuj pełną ścieżką.

### TASK-0654 — dokumentacja „Przybliżonej wygranej”, odbiór na żywo wstrzymany (in_progress)

- `ai_docs/tasks/0654-approximate-win-docs-and-acceptance.md`. Dokumentacja „Przybliżonej wygranej” (D-446) ukończona; odbiór na żywych danych gry 777 czeka na jawną zgodę operatora. Znane braki: fikstura `test_payout_store.py`, `prettier` klienta, limit `spinCount ≤ 10 000` bez pomiaru.

### TASK-0668 — T03 — edytor i zbiór geometrii (in_progress)

- `ai_docs/tasks/0668-vision-lab-geometry-annotations.md`. D-456 zatwierdza T03k i pilota całymi grami bez pomiaru; pozostaje mapowanie źródeł do rodzin, kontrola konfliktów i zamrożony podział. Narzędzia lab (porty 8103, 8105, 8107, 8108) startują ręcznie, bez autostartu (sekcja „Ograniczenia z CURRENT_STATE” w pliku taska).

### TASK-0671 — T06 — etykiety symboli (blocked)

- Plik zadania: `ai_docs/tasks/0671-vision-lab-symbol-labels.md`.
- Status: `blocked` — T06a odebrane; T06b wymaga rzeczywistych zatwierdzeń symboli i kwalifikacji zbioru. Nadrzędne T06 pozostaje aktywne, dlatego ten plik nie trafia do `completed/`.
- Cel: Zbudować zbiór symboli z weryfikowalnym pochodzeniem DB lub lab.
- Historia w archiwum: `CURRENT_STATE_2026Q3.md` → „Etap C — T06a odebrane; T06b blokuje dalszy trening”.

### TASK-0672, TASK-0673, TASK-0674, TASK-0675, TASK-0676, TASK-0677, TASK-0678 — laboratorium wizji T07–T13 (todo)

- Pliki: `ai_docs/tasks/0672-vision-lab-symbol-models.md` … `0678-vision-lab-final-acceptance.md`. T07 modele symboli, T08 panel treningu, T09 walidacja, T10 neural_grid, T11 geometria w aplikacji, T12 symbole w workerze, T13 odbiór; plan `delivery/VISION_LAB_EXECUTION_PLAN.md`; czekają na T03 (TASK-0668) i T06b (TASK-0671).

### TASK-0687, TASK-0688, TASK-0689, TASK-0690, TASK-0691, TASK-0694, TASK-0695, TASK-0698 — V2-only i usunięcie legacy public (blocked/todo)

- Pliki: `ai_docs/tasks/0687-v2-only-release-readiness.md` (blocked), `0688`–`0691` (todo), `0694` (blocked), `0695` (todo), `0698-global-v2-routing-transaction-decision.md` (blocked). Plan `delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` (`completed`). T09 `no-go` wg 0687; D-467 odnotowuje jednak, że `0125` zastosowano na bazie operatora (R1). Otwarta decyzja: konflikt D-038 z transakcją jednej gry V2 (TASK-0698). Raport `quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`.

### TASK-0802 — neural_grid: sieć widząca cały ekran (in_progress)

- Plik zadania: `ai_docs/tasks/0802-neural-grid-whole-screen-network.md`.
- Status: `in_progress`
- Cel: Silnik `neural_grid` pod kontraktem `GeometryEngine` wykrywa na całym zdjęciu wszystkie plansze i wyznacza dla każdej 24 węzły siatki 5 × 3; jest wytrenowany na snapshocie produkcyjnym v2 w ramach budżetu D-481, wyeksportowany do ONNX z potwierdzoną zgodnością PyTorch–ONNX i opisany raportem per run z metryką nadrzędną D-483.
- Historia w archiwum: `CURRENT_STATE_2026Q4.md` → „Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku…”.

### TASK-0928 — wznowienie importu po rezerwie dysku (in_progress)

- `ai_docs/tasks/0928-image-import-storage-resume.md`. Poprawka rezerwy (D-534) v1.7.251 / `9b88e244`; odbiór wymaga wznowienia joba Mumii `092ff7a4…` (535/2915) po restarcie workera `general` przez operatora. Blokada migracji `0147` nieaktualna (baza `0154`, 2026-10-10); stan joba po wymianie źródeł Mumii nieznany. Ograniczenia: sekcja „Ograniczenia z CURRENT_STATE” w pliku taska.

### TASK-0937 — pilot wykrywania złotej ramki super symbolu (blocked)

- `ai_docs/tasks/0937-gold-frame-detection-pilot.md`; narzędzie v1.7.281 / `7b7b0a7e`. Warunek `0152` spełniony (`0154`); pozostają wyprowadzona seria supergry Mumii, co najmniej 5 super symboli i etykiety operatora (≥ 30 komórek na wariant).

### TASK-0939 — narzędzia oszczędzania tokenów z pomiarem (blocked)

- `ai_docs/tasks/0939-token-tooling-pilot.md`; narzędzia v1.7.284 / `6f783932`, status v1.7.285 / `1b97ad65` (R3). Pomiar 36 sesji wg `quality/TOKEN_TOOLING_PILOT_PROTOCOL.md` i raport „zostaje / wypada” wykonuje operator po zgodzie na koszt.

### TASK-0972 — odbiór cofania korekt i zamiennika, D-542 i D-543 (blocked)

- `ai_docs/tasks/0972-geometry-correction-revert-acceptance.md`; scalenie v1.7.306 / `853052a1`, dokumenty v1.7.307 / `f7f6d30e`, migracja `0154` 2026-10-10. Czeka na odbiór operatora (cofnięcie świeżej korekty, import zastępczy; slot 69004 nie istnieje). Dług audytowy 0966/0968/0970/0971 i baza testowa do usunięcia: w pliku taska.

## Ostatnie 10 ukończonych tasków

- **TASK-1022** — Zastosowanie budżetów `CURRENT_STATE.md` — v1.7.370 — tasks/completed/1022-current-state-budgets.md
- **TASK-1021** — Przegląd ograniczeń i sekcji `CURRENT_STATE.md` — v1.7.368 / `a8ed5dcc` (decyzja v1.7.369 / `13cb5022`) — tasks/completed/1021-current-state-constraints-review.md
- **TASK-1020** — `DECISION_LOG.md` jako lekki indeks — v1.7.367 / `d803c27c` — tasks/completed/1020-decision-log-light-index.md
- **TASK-1019** — Skrypt pomiaru i budżetów odczytu startowego — v1.7.366 / `d1174304` — tasks/completed/1019-startup-read-budget-script.md
- **TASK-1007** — Trwałe wykrywanie Claude Code CLI — v1.7.361 / `baf67dbd` (scalenie v1.7.362 / `885ba12f`) — tasks/completed/1007-claude-cli-discovery.md
- **TASK-0991** — Wznowienie symboli i pełny przebieg 777 a2 <80% — v1.7.358 / `17a1012e` (naprawa v1.7.351 / `6e84a1b1`) — tasks/completed/0991-symbol-reinference-resume.md
- **TASK-0992** — Scalenie naprawy i obowiązek integracji — v1.7.353 / `14aeb0c0` (korekta v1.7.355 / `be7ecff1`) — tasks/completed/0992-integration-branch-merge-policy.md
- **TASK-0979** — Wydanie 1.0.0 i odbiór operatora — v1.7.349 / `8ac68f5f` — tasks/completed/0979-selector-desktop-release-acceptance.md
- **TASK-0990** — Zakres pośrodku nad zdjęciem i końcowy zapis widoku — v1.7.343 / `8a3249fd` — tasks/completed/0990-selector-desktop-centered-range.md
- **TASK-0989** — Stabilny układ, minimalny fullscreen i centrowanie zdjęcia — v1.7.341 / `a9cb2fed` — tasks/completed/0989-selector-desktop-stable-layout-and-fullscreen.md
