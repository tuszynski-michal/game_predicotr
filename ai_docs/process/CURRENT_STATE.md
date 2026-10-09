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

Ograniczenia operacyjne nadal obowiązujące, wyniesione ze starszych wpisów
(przeszukanie słów kluczowych: migracja, zgoda, blokada, PID, job, „nie
uruchamiać”, potem ręczny dobór). Każdy punkt wskazuje sekcję-źródło. Stan z
daty wpisu może być nieaktualny, więc przed poleganiem na nim zweryfikuj go
(odczyt, bez zmian w systemie).

- **Stan migracji bazy operatora.** Ostatni zapis: 2026-10-08 operator wykonał migrację `0151_super_game_roles`, `npm install` i `worker:poll`. Kod tej gałęzi wymaga `0152_super_game_series` (strażnik schematu startowego). Wdrożenie `0152` nie jest nigdzie odnotowane jako wykonane: stop API/worker/Admin → `npm run db:migrate` → start → `POST …/derive` dla Mumii (komórki sprzed migracji nie podbiły licznika). Przed poleganiem na tym stanie sprawdź `alembic current` (odczyt, bez zmian). Źródło: sekcja „TASK-0933 — wyprowadzanie serii supergry i API serii (done)” w tym pliku; sekcja „TASK-0932 — ewaluator `payout-v4-wild-count` (done)” w tym pliku.
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

Kryterium: plan o statusie `proposed`/`accepted`/`active`/`deferred`, którego
taski mają aktywne pliki w `ai_docs/tasks/` albo który czeka na decyzję.
Statusy czytane z nagłówków `ai_docs/delivery/*.md` w dniu przeniesienia
(2026-10-09); pozostałe plany `accepted` bez aktywnych tasków są zamknięte w
praktyce (ich taski leżą w `ai_docs/tasks/completed/`).

| Plan (`ai_docs/delivery/…`) | Status planu | Pozostałe taski |
|---|---|---|
| `MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` (D-535) | accepted | TASK-0937 (pilot złotej ramki, etap S-D, `blocked` na etykietach operatora), TASK-0939 (narzędzia oszczędzania tokenów, etap T); TASK-0929–0936, 0938 i 0940 ukończone |
| `VISION_LAB_EXECUTION_PLAN.md` (D-447) | accepted | TASK-0668 (`in_progress`), TASK-0671 (`blocked`), TASK-0672–0678 (`todo`) |
| `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md` | active | TASK-0645, 0646, 0647 (`blocked`, D-445/D-447) |
| `V2_READINESS_REMEDIATION_PLAN.md` | accepted | TASK-0694 (`blocked`), TASK-0695 (`todo`), TASK-0698 (`blocked`, wymaga decyzji) |
| `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` | completed (w nagłówku) | TASK-0687 (`blocked`), TASK-0688–0691 (`todo`): rozbieżność z nagłówkiem do wyjaśnienia |
| `GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` | accepted | TASK-0802 (`in_progress`) |
| `MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md` | proposed | brak aktywnych plików; czeka na decyzje operatora (zakres częściowo przejęty przez plany Mumie z 2026-10-04..08) |
| `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` | proposed | TASK-0910 ukończony; TASK-0911–0918 nie mają plików w `ai_docs/tasks/` |
| `APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md` | deferred | wymaga nowej decyzji (D-463 nie przyjęta) |
| `MILESTONE_06_EXECUTION_PLAN.md` | in_progress (nagłówek z 2026-07-29) | brak aktywnych plików; status nagłówka przestarzały |
| bez planu w `delivery/` | n/a | TASK-0290, 0305, 0472, 0517, 0603, 0611, 0654, 0928 (sekcje w „Aktywne taski”) |

Sekcja planu Mumie poniżej jest bez zmian względem poprzedniej wersji tego
pliku; zdanie „Żaden etap nie jest jeszcze uruchomiony” jest historyczne
(ukończono S-0, S-A, S-B i S-C, patrz sekcje `done` na końcu pliku).

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

Sekcje tasków `in_progress`, `blocked` i `todo` (każdy plik w `ai_docs/tasks/`),
posortowane po numerze. Krótkie wpisy „TASK-… (status)” wskazują plik zadania i
historię w archiwum; po rozpoczęciu pracy agent zastępuje wpis pełną sekcją.

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

### TASK-0938 — okno kroczące `CURRENT_STATE.md` i indeks `DECISION_LOG.md` (done)

- Commit v1.7.282 / 2361e6ed77a23f88930cdf372b96371cf24305d7
- `CURRENT_STATE.md`: 868 364 B / 13 375 linii → ok. 75 KB; sekcje spoza okna
  przeniesione bez zmian do `ai_docs/archive/CURRENT_STATE_2026Q4.md` (od
  2026-10-01) i `CURRENT_STATE_2026Q3.md` (wcześniejsze); dowód: równość
  multizbiorów bloków z HEAD. Nowa sekcja „Obowiązujące ograniczenia” (25
  punktów ze wskazaniem źródła).
- `DECISION_LOG.md`: 787 675 B → ok. 70 KB (nagłówek z regułami, indeks D-359..
  D-537, pięć najnowszych pełnych wpisów); pełne wpisy w
  `ai_docs/process/decisions/DECISION_LOG_2026.md` (kotwice bez zmian), starszy
  indeks w `decisions/DECISION_INDEX_ARCHIVE.md`.
- `scripts/check_decision_links.py` i `scripts/check_current_state_window.py`
  w `npm run docs:check` (część `quality`, ok. 2 s); testy
  `services/worker/tests/test_check_decision_links_script.py`.
- Audyt Codex gpt-6-astra / medium: REVISE (2 × P1, 1 × P2), jedna runda
  poprawek (`ai_docs/quality/TASK-0938_AUDIT_gpt-6-astra.md`).

### TASK-0936 — rozwinięcie super symbolu i koszt per pozycja (done)

- Commit v1.7.280 / 8629be40e01d49a230ec703d27b89057d37d6d73.
- `wild_super_spins.evaluate_series_board`: `k` kolumn z X na planszy
  oryginalnej; przekształcenie tylko przy `k ≥ minimum(X)` (kolumny
  wypełnione X, przykrycie usuwa symbole pod spodem); linie na planszy
  rozwiniętej, sztuki na oryginalnej, wygrane liniowe X zastąpione
  `payout_line(X, k) × liczba linii`; `payout_kind`: w serii `provisional`
  bez super symbolu, przy nieświeżym stanie (wtedy wszystkie plansze gry,
  także bazowe — decyzja leada wg planu) albo z jakąkolwiek nieznaną komórką;
  `exact` tylko dla pełnej planszy. Lustro TS `packages/shared-ts/src/super-game.ts`;
  16 złotych przypadków `wildSuperSpinsScenario` w Pythonie i TS. D-537.
- Projekcja per pozycja (`domain/sequence_mode_projection.py`) z zapytania
  znaczników (jeden snapshot): koszt 0 w serii, trigger z kosztem normalnym;
  §D sumuje koszt per pozycja, wyniki prowizoryczne poza bilansem z osobną
  sumą i licznikiem; `superSpinRanges`/`superSpinCost` w podsumowaniu (Admin,
  udostępnienie, panel, zapisane wyniki); wykres, piny i wkład liczone z tych
  zakresów; modal pokazuje planszę rozwiniętą i wiersz rozwinięcia.
  Kalkulator, szczegół planszy i panel czytają w jednym snapshocie
  `REPEATABLE READ` (dla wszystkich gier; 777 bajt w bajt bez zmian —
  test regresji ze skrótami z v1.7.279).
- Audyt Codex gpt-6-astra / high: runda 1 REVISE (3 × P0: koszt darmowych
  spinów w wykresie i pinach, wkład przy starcie w serii, wspólny snapshot),
  runda 2 PASS, P2 miniatury zaakceptowane (`ai_docs/quality/TASK-0936_AUDIT_gpt-6-astra*.md`).
  Worker 118, API 305 + PG 13, shared-ts 65, board-search-ui 94 + 62, Admin
  733 + 188, Reviewer 240 + 40, klient 105, `openapi:check`, typecheck
  (mypy 851), lint, format, fixture PASS.
- Etap S-C zamknięty. Następne: TASK-0938/0939 (etap T), TASK-0937 (pilot,
  wymaga etykiet operatora).

### TASK-0935 — oznaczenie supergry w wyszukiwaniu plansz (done)

- Commit v1.7.278 / bf0dd8617b449da7109b4b438f46b6ea7433bb3c.
- API: wyniki wyszukiwania i wiersze przybliżonej wygranej niosą opcjonalne
  `superGame` (`trigger` | `in_series`, `spinIndex`, `seriesLength`,
  `superSymbolCode`, `completeness`, `runVerification`, w Adminie `seriesId`),
  a każda odpowiedź `superGameState { fresh, inputVersion, generationInputVersion }`;
  jedno zapytanie SQL (LATERAL po serii pokrywającej pozycję) daje znacznik i
  świeżość z jednego snapshotu. Trasy publiczne (udostępnienie, panel) bez
  `seriesId` (osobny model / `response_model_exclude`, strażnik parametrów).
  Zamrożone wyniki panelu bez znaczników; skróty treści 777 bez zmian.
- UI (`board-search-ui`): złote wyróżnienie kart i wierszy, etykiety
  „Supergra: trigger / spin k/len, symbol X / super symbol do zdefiniowania”,
  dopiski o serii niekompletnej i triggerze z predykcji, baner dla całego
  wyniku (także pustego) przy `fresh = false`; link „Zdefiniuj super symbol”
  / „Pokaż serię” tylko gdy źródło danych deklaruje `superGameSeriesHref`
  (Admin), Reviewer i panel tylko etykieta. Cache wyszukiwania Reviewera
  pomijany dla odpowiedzi ze znacznikiem lub nieświeżych.
- Audyt Codex gpt-6-astra / medium: REVISE (P0 baner przy pustym wyniku,
  P1 brak akapitu w `ADMIN_APP.md`, P2 cache), wszystko naprawione w jednej
  rundzie (`ai_docs/quality/TASK-0935_AUDIT_gpt-6-astra.md`). API 281 PASS,
  PG 35 + 8 + 2, board-search-ui 85 + 60, Reviewer 240 + 40, Admin 733 + 188,
  klient 104, typecheck (mypy 850 plików), lint, format PASS.
- Etap S-B zamknięty (TASK-0933–0935). Następny: S-C / TASK-0936.

### TASK-0934 — sekcja „Supergry” w Adminie (done)

- Commit v1.7.277 / 9a2bbc685e2763553ce31b621c5e3c112e78e671.
- Nowa sekcja gry `super-games` (tylko dla gier z rodzajem supergry):
  lista serii z kursorem, filtrami (kompletność, weryfikacja przebiegu,
  symbol zdefiniowany) i licznikiem „do zdefiniowania”; „Przelicz serie” z
  baner „Serie w trakcie przeliczania” (polling stanu co 5 s); widok serii
  z karuzelą trigger + wszystkie pozycje (karty „brak planszy”, retriggery),
  komórki symbolu uruchamiającego podświetlone, modal linii; wybór super
  symbolu (tylko zwykłe symbole, cyfry `1`–`9`/`0`, `Enter`), zapis z
  `expectedRevision` (409 → odświeżenie bez nadpisania), „Wyczyść symbol”.
  Link z wyszukiwania: `?workspace=games&game=<id>&section=super-games&series=<id>`.
- Odpowiedzi zapisu związane z cyklem otwarcia serii (także nawigacja
  historią), strony listy z generacją ładowania, lista odświeżana po zmianie
  symbolu zgodnie z filtrem, obraz planszy związany z rewizją szczegółu.
- Audyt Codex gpt-6.1-sol (zamiast gpt-6-astra: „at capacity”): runda 1
  REVISE (3 × P0 opóźnione odpowiedzi/filtry/strony, P1 mapowanie cyfr —
  decyzja: cyfry = lista zwykłych symboli z selecta), runda 2 jeden P0
  (historia przeglądarki) naprawiony; `ai_docs/quality/TASK-0934_AUDIT_gpt-6.1-sol*.md`.
  Admin 733/733, interakcje jsdom 19/19 (`npm run test:geometry`), typecheck,
  lint, prettier PASS. Bez uruchomienia na żywym API.
- Otwarte drobne: polling także przy ukrytej karcie; kwoty w modalu linii
  jako „N kr.” (formatter złotówek nieeksportowany z `board-search-ui`).

### TASK-0933 — wyprowadzanie serii supergry i API serii (done)

- Commit v1.7.276 / 221e43ed0c645c218e84b2bee34785608ef04f1d.
- Migracja `0152_super_game_series` (manifest v6 = v5 + 4 tabele gry:
  `super_game_series`, tabela robocza generacji, stan wyprowadzania, audyt
  super symbolu; partycje i RLS dla istniejących gier; strażnik schematu
  wymaga `0152`). D-536.
- Licznik `input_version` per gra podbijany w tej samej transakcji w 10
  punktach zapisu (lista w kodzie, test statyczny w obie strony, test PG na
  12 realnych operacjach z rollbackiem); nieaktualność = porównanie z wersją
  generacji. Job `super_game_series_derive` (lane general, dedup na grę)
  buduje generację partiami (5000 pozycji / 500 serii), publikuje w jednej
  transakcji pod `FOR UPDATE`, odrzuca kandydata przy zmianie wersji.
  2000 pozycji / 30 serii: ~1 s, szczyt pamięci 0,27 MB.
- API `/api/v1/admin/games/{gameId}/super-game-series` (lista z kursorem i
  filtrami, `/derive`, `/{seriesId}/boards`, `PUT /{seriesId}/super-symbol`
  z CAS, `/state`); OpenAPI, klient i wrappery; etykieta joba w Adminie.
  Pole `superGameState` w odpowiedziach wyszukiwania przeniesione do
  TASK-0935 (decyzja leada po audycie).
- Audyt Codex gpt-6-astra / high (pierwszy audyt przez CLI): runda 1 REVISE
  (P0: brak podbicia przy zmianie `expected_layout_count`, kompletność na
  końcu sekwencji; P1: testy punktów zapisu, `superGameState`), poprawki w
  jednej rundzie, runda 2 w `ai_docs/quality/TASK-0933_AUDIT_gpt-6-astra.md`.
  Runda 2 i 3 (zawężone): cztery P0 współbieżności (odczyt parametrów pod
  blokadą stanu; wyścig blokady czyszczenia — wyłączenie usunięte, job
  blokuje jak każdy; odczyty w snapshocie RR), wszystkie naprawione i pokryte
  testami PG; commit po rundzie 3 bez kolejnej rundy (reguła szybkiego
  audytu, decyzja leada). Raporty rund w `ai_docs/quality/`.
- Wdrożenie u operatora: stop API/worker/Admin → `npm run db:migrate` (0152,
  manifest v5→v6) → start → `POST …/derive` dla Mumii (komórki sprzed
  migracji nie podbiły licznika).

### TASK-0940 — zielona bramka `npm run quality` (done)

- Commit v1.7.273 / 60ba1f74de09d82d159f42bf9706240dcb662123.
- Pełna bramka zielona: format (Prettier `endOfLine: auto` dla checkoutu
  autocrlf), openapi, lint, typecheck (mypy 836 plików po naprawie
  konfiguracji i 79 realnych błędów typów bez ogólnych ignore), testy JS,
  snapshot/fixture; API pytest z PostgreSQL 2725 PASS, worker 2781 PASS.
- Naprawy u źródła: współdzielony `services/test_support/` (helper V7,
  `require_local_corpus`), `services/api/tests/conftest.py` (loggery po
  Alembic), tabele `semi_automatic_selection_v7_*` jako `POST_V5_SHARED`
  w manifeście v5, `EXPECTED_PUBLIC_TABLES` i testy PG dostosowane do
  migracji bez downgrade (0148–0150), testy zaktualizowane do bieżących
  reguł z cytatem taska (TASK-0925, 0882, 0885, 0805, v0.10.298…).
- Łańcuch sum dowodów `ai_docs/quality/*.json` przepięty z CRLF na LF do
  punktu stałego (78 plików, tylko wartości sha256); nowy checker
  `scripts/check_quality_evidence_digests.py` + tabela
  `evidence-digest-references.json` + test workera pilnują dryfu.
- Audyt claude-opus-5-5 / high: runda 1 REVISE (P0: skip ukrywał błąd
  łańcucha), runda 2 jedna P1 (punkt stały), domknięta i zweryfikowana
  (`ai_docs/quality/TASK-0940_AUDIT_claude-opus-5-5.md`).
- Odłożone jawnie: 3 testy historycznych migracji (skip z powodem), testy
  korpusów M5 bez korpusu, test junction tylko w worktree.
- Następny etap: S-B (TASK-0933 → 0934/0935), zgodnie z poleceniem operatora.

### TASK-0932 — ewaluator `payout-v4-wild-count` (done)

- Commit v1.7.270 / 123953086aa11ba8454489298b1b4f1015128d4c.
- `services/worker/.../domain/payout.py`: symbole z rolą uruchamiającą poza
  liniami; Wild bez zmian (ta sama komórka jako różne symbole na różnych
  liniach, same Wildy nie wygrywają); nowe `count_matches` (największa
  reguła ≤ liczbie sztuk, komórki `0` nie liczone); suma linie + sztuki.
  Wersja per gra: bez triggera wyniki i wersja identyczne z v3 (777 bez
  zmian), z triggerem `payout-v4-wild-count`. Lustrzany ewaluator TS
  `packages/shared-ts/src/payout.ts`; 10 złotych przypadków v4 w
  `domain-fixtures` wykonywanych w Pythonie i TS.
- API: `countMatches[]` w szczególe planszy i wierszach przybliżonej wygranej;
  `rulesVersionId` (draft/published tej samej gry) w modalu linii i
  przybliżonej wygranej Adminu; udostępnienie i panel publiczny odrzucają
  parametr (422), proxy Reviewera 403. UI: select „Wersja reguł” tylko w
  Adminie, sekcja „Sztuki na planszy”, „w tym sztuki” w wierszach.
- Nieobjęte (jawny follow-up): prekomputacja v4 (job wypłat, `layout_payouts`,
  snapshot mobilny) — strażnik `PAYOUT_ALGORITHM_GAME_MISMATCH` odrzuca job
  v3 dla gry z triggerem; `create_payout_job` nadal tylko v3. Panel
  zarządzania (format v1) nie pokazuje rozbicia na sztuki, wypłata wiersza
  je zawiera.
- Audyt claude-fable-5-1 / high: PASS, 4 × P2 naprawione, 4 odstępstwa
  zaakceptowane (`ai_docs/quality/TASK-0932_AUDIT_claude-fable-5-1.md`).
  Worker 88, API 101, shared-ts 46, board-search-ui 80+51, Admin 679/679,
  `openapi:check` aktualne. Istniejące wcześniej: 2 testy kontraktowe
  Reviewera, `main.py:2005` mypy.
- Etap S-A zamknięty. Operator może testować Wild na drafcie Mumii
  (instrukcja w Outcome TASK-0931 i TASK-0932) po wdrożeniu migracji 0151.
  Operator 2026-10-08: migracja 0151, `npm install` i `worker:poll` wykonane;
  zaakceptował TASK-0940 (zielona bramka) i polecił przejść od razu do etapu
  S-B bez pytań o zgodę; TASK-0938/0939 po S-B.

### TASK-0931 — Wild, „Uruchamia supergrę” i rodzaj supergry (done)

- Commit v1.7.268 / 1aef5870ee22287b0e17f1278276cddf7793a9b5.
- Migracja `0151_super_game_roles` (addytywna): `symbols.super_game_trigger_count`
  (null/3/4/5) i `games.super_game_kind` (domyślnie `none`); strażnik
  schematu startowego wymaga teraz `0151`. Rejestr rodzajów supergry w
  `services/worker/.../domain/super_games/` (`none`, `wild_super_spins`:
  10 spinów, +10 przy retriggerze, koszt 0).
- Domena: zmiana ról Wild/trigger dozwolona tylko bez opublikowanej lub
  zarchiwizowanej wersji reguł; rola trigger wymaga rodzaju gry ≠ `none`
  (`SUPER_GAME_KIND_REQUIRED`, `SUPER_GAME_KIND_IN_USE`); symbol trigger ma
  `minimum_match_length = null`, a jego wypłaty znaczą liczbę sztuk
  2…rows×columns (rosnące); przy zyskaniu roli minimum w draftach jest
  czyszczone w tej samej transakcji. 777 bez zmian zachowania.
- API: pola w schematach gry i symbolu (`superGameTriggerCount` wymagane,
  `superGameKind`), `GET /api/v1/admin/super-game-kinds`, OpenAPI i klient
  zregenerowane, wrapper `listSuperGameKinds`, request testy. Admin: etykieta
  „Wild”, checkbox „Uruchamia supergrę” + select 3/4/5, select „Supergra”
  w tworzeniu i edycji gry, pola „sztuk na planszy” w regułach.
- Audyt claude-fable-5-1 / high: PASS, 4 × P2 naprawione, 8 odstępstw
  zaakceptowanych (`ai_docs/quality/TASK-0931_AUDIT_claude-fable-5-1.md`).
  Pytest skupiony 72 PASS, PG katalog 4 PASS, cykl migracji na bazie
  jednorazowej OK, `openapi:check` aktualne, Admin 679/679, Reviewer
  typecheck PASS.
- Wdrożenie u operatora (po merge): zatrzymać API/Admin, `npm run db:migrate`
  (0147→0151 na bazie operatora wymaga osobnej zgody, patrz TASK-0928),
  restart. Nie publikować reguł Mumii przed TASK-0932 (stary ewaluator liczy
  Mumię jako symbol liniowy). Instrukcja operatora w Outcome taska.

### TASK-0929 — skill audytu krzyżowego i sekcja „Audyt krzyżowy” (done)

- Commit v1.7.267 / 6323939f41d93501a537463eb82ce127ab1f04b3.
- `scripts/audit_task.ps1` (PowerShell 5.1, ASCII, limity czasu, UTF-8)
  składa brief taska (plik taska, fragment planu, `Verification results`,
  diffy ograniczone `-Paths`, pliki nieśledzone) do ignorowanego
  `artifacts/audits/` i uruchamia audytora tylko do odczytu (`codex exec
  --sandbox read-only` lub `claude -p --permission-mode plan`); raport trafia
  do `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` tylko z wierszem werdyktu.
  Bez CLI na PATH tryb „tylko brief” (kod 0). Skille `.claude/skills/audit-task`
  i `.codex/skills/claude-audit`; szablon `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.
- `AGENTS.md`: sekcja „Audyt krzyżowy” (rodziny modeli, zastępstwo subagentem
  Claude do czasu CLI, jedna runda audytu + jedna poprawek, otwarte P0/P1
  blokują commit, wyjątek czasowy 600 s dla przebiegu audytu); punkt 8
  „Po kodowaniu” ujednolicony.
- Audyt claude-opus-5-5 / high: runda 1 REVISE (2 × P1: `-Paths` z przecinkami,
  wstrzyknięcie przez `-Model` na shimach `.cmd`; 5 × P2), po poprawkach
  runda 2 PASS; 3 × P2 naprawione przez leada. Prawdziwe CLI `codex`/`claude`
  nie są zainstalowane: operator instaluje i loguje je sam, potem jeden
  przebieg bez `-DryRun` z zapisem wersji.
- Etap P zamknięty. Trwa TASK-0931 (etap S-A).

### TASK-0930 — klawisz `0` dla dziesiątego symbolu w weryfikacji symboli (done)

- Commit v1.7.266 / ad058e23a487a70f543636c6b024d779006c9bdb.
- W weryfikacji symboli `0` wybiera dziesiąty aktywny symbol (Mumia) jako
  `Symbol do zatwierdzenia`; etykiety w selekcie i pasku skrótów pokazują `0`.
  Nowe helpery `extendedDigitShortcutIndex/Label` w `apps/admin/src/lib`;
  wyszukiwanie plansz bez zmian (`0` = nieznany).
- Admin: testy 668 PASS, typecheck i lint PASS. Audyt niezależny
  claude-opus-5-5 / medium: PASS, 4 × P2 naprawione przed commitem
  (`ai_docs/quality/TASK-0930_AUDIT_claude-opus-5-5.md`); uwaga o opisie w
  `symbol-catalog.tsx` przekazana do TASK-0931.
- Etap S-0 zamknięty. Równolegle trwają TASK-0929 (etap P) i TASK-0931 (S-A).

## Archiwum

- Q4 2026 (od 2026-10-01): `ai_docs/archive/CURRENT_STATE_2026Q4.md`.
- Q3 2026 i starsze tory: `ai_docs/archive/CURRENT_STATE_2026Q3.md`.
