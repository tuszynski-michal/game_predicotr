---
title: Przegląd ograniczeń i sekcji CURRENT_STATE.md (TASK-1021)
status: accepted
last_updated: 2026-10-16
---

# Przegląd ograniczeń i sekcji `CURRENT_STATE.md` — propozycja do decyzji operatora

Task: `ai_docs/tasks/1021-current-state-constraints-review.md`. Plan:
`ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md` (etap B,
decyzje D3, D6, D7). Raport jest wyłącznie propozycją: niczego nie zmieniono w
`CURRENT_STATE.md`, archiwach, plikach tasków, bazie ani usługach. Zastosowanie
zatwierdzonej klasyfikacji należy do TASK-1022.

## Metoda i stan wyjściowy

- Gałąź `feat/startup-read-diet`, czubek v1.7.367 / `d803c27c` (baza `main`
  v1.7.363 / `4e171b06`). Pomiar: `scripts/check_startup_read_budget.py
  --report`: `CURRENT_STATE.md` 90 959 B; „Obowiązujące ograniczenia”
  20 327 B; „Plany z niezakończonymi taskami” 8 180 B; „Otwarte decyzje i
  pytania” 1 015 B; „Aktywne taski” 49 045 B; „Ostatnie 10 ukończonych tasków”
  11 286 B. Bajty pojedynczych punktów policzono w UTF-8 razem ze znakiem nowej
  linii.
- Dowody zbierano wyłącznie odczytem: `git log --all --grep`, `git
  merge-base --is-ancestor`, łańcuch `down_revision` w
  `services/api/alembic/versions/`, linie `## Status` i `## Outcome` plików w
  `ai_docs/tasks/` i punktowo w `ai_docs/tasks/completed/`, `rg` w archiwach i
  `decisions/DECISION_LOG_2026.md`. Bazy nie odczytywano (bez uruchamiania
  usług); ostatni zapisany stan bazy operatora to `alembic current` =
  `0154_geometry_correction_revert` z 2026-10-10 (sekcja TASK-0956 i punkt
  „Migracja `0154`… wykonana”).
- Kluczowy fakt dla wielu punktów: łańcuch migracji jest liniowy
  `0124 → 0125 → … → 0147 → 0148 → 0149 → 0150 → 0151 → {0152_super_game_series,
  0152_management_compact_panel} → 0153_merge_compact_super_games → 0154`.
  Baza na `0154` ma więc zastosowane `0125`, `0130`, `0147`, `0148`–`0150`,
  `0151` i obie `0152`.
- Fakty z 2026-10-16: gałęzią integracyjną jest `main` (punkt „Gałąź
  integracyjna = `main`” jest nowy i zostaje); `v1.1-vision-lab-hybrid-geometry`
  (`c6510f19`) jest przodkiem `main`; lokalny `main` v1.7.363 wyprzedza
  `origin/main` v1.7.360. Checkout roboczy to `D:\game_predicotr`. Gałąź
  `codex/v3-grid-fine-tuning` ma 18 commitów ponad `main`, migracje
  `0155`–`0159` i plan V3 w rewizji 6 (`accepted`).

Klasy: `zostaje` (skrót ≤ 400 B, tekst w podsekcji „Proponowane teksty”),
`do task` (dotyczy jednego taska; przenieść do jego pliku albo wskaźnika),
`archiwum` (rozwiązane lub utrwalone gdzie indziej, z dowodem), `operator`
(nie da się rozstrzygnąć z repozytorium; do czasu decyzji zostaje skrót
„O-n”).

## 1. Obowiązujące ograniczenia

| # | Punkt (pierwsze słowa) | B | Źródło cytowane | Co sprawdzono, wynik | Klasa |
|---:|---|---:|---|---|---|
| 1 | Claude Code CLI / TASK-1007 | 516 | AGENTS.md, TASK-1007 | Reguła jest w `AGENTS.md` (l. 338–343, „Dostęp do Claude Code CLI”); `885ba12f` (v1.7.362) jest przodkiem `main`; plik `tasks/completed/1007-claude-cli-discovery.md`. Brak push pokrywa punkt 3. | `archiwum` |
| 2 | TASK-0991 / 777 a2 | 452 | `quality/SYMBOL_REINFERENCE_777A2_20261014.md` | `17a1012e` (v1.7.358) i `efb4cdf5` w `main`, więc „akceptacja przed scaleniem” rozwiązana. Przeładowanie istniejącego poll workera: `completed/0991-…` l. 99, 115 mówi, że nie było wykonane; stanu procesu nie da się ustalić z repo. | `operator` (O1) |
| 3 | Gałąź integracyjna = `main` | 634 | decyzja operatora 2026-10-16, AGENTS.md | Nowy punkt; `v1.1-…` w `main` (merge-base), `main` v1.7.363 vs `origin/main` v1.7.360 zgodne z gitem. | `zostaje` (Z1) |
| 4 | Akceptacja przed integracją | 689 | AGENTS.md, TASK-0992 | Reguła w `AGENTS.md`, „Scalanie do gałęzi integracyjnej” (l. 198–230); reguła zgody. Hash scalenia `45923355` w `main` — historia do archiwum. | `zostaje` (Z2) |
| 5 | Selektor1.0.0 / D-547 | 748 | `quality/OFFLINE_PHOTO_SELECTOR_RELEASE_1_0_0_20261013.md` | D-547 w indeksie `DECISION_LOG.md`; `completed/0979-…`, `0988`–`0990` istnieją; `8ac68f5f` (v1.7.349) w `main`. Brak ograniczenia dla przyszłej pracy. | `archiwum` |
| 6 | TASK-0975: odrzuconych jobów treningu | 428 | TASK-0975 | Task `done` (`completed/0975-symbol-training-rejected-split-recovery.md`); plik wspomina „Ulepsz rozpoznawanie” (l. 87), ale nie zawiera ID jobów `79f2a5f6…`, `099ea091…`, `564fbff5…`. | `do task` (dopisać do `Outcome` `completed/0975-symbol-training-…`) |
| 7 | Historical numbering collision | 271 | brak (nota) | Dwa pliki `completed/0975-selector-desktop-foundation.md` i `completed/0975-symbol-training-…` potwierdzają kolizję. Treść jest szczególnym przypadkiem punktu 37. | `zostaje` (scalić z 37 → Z3) |
| 8 | Historia selektora | 346 | quality, completed | Jak punkt 5: D-547, rundy TASK-0975–0990 w `completed/`. | `archiwum` |
| 9 | TASK-0974 / D-544 | 500 | D-544, `completed/0974-…` | Kod v1.7.314 `4344510b` i v1.7.315 `55af1b63` scalone. Restart workera: `completed/0991-…` l. 19 opisuje grę `777a2` z 341 461 planszami i 35 122 komórkami z predykcją, czyli preflight V3 a2 przeszedł na nowym kodzie workera (stary proces odrzuciłby snapshot). Zakaz V1.1 i profilu Mumii jest treścią D-544 (wiersz w indeksie). | `archiwum` |
| 10 | Wymiana 275 zdjęć Mumii | 826 | `quality/MUMIE_SOURCE_REPLACEMENT_20261009.md`, Outcome TASK-0960 | Usunięcie zakończone (`completed/0960-…`). Otwarte zostaje „przygotować nową paczkę … jako nowy import”; sekcja TASK-0972 (pomiar N1) wspomina import `344ce332-…` z sekwencjami 69004–69012, co sugeruje nowy import, ale nie potwierdza całej paczki. | `operator` (O2) |
| 11 | Panel / D-539 | 318 | D-539 | D-539 w indeksie; zdanie o pinach wszystkich stawek dotyczy wyłącznie TASK-0947 (`selectedStake` jest w `tasks/0947-…`). | `do task` (`tasks/0947-management-point-workspace-layout.md`) |
| 12 | Kompaktowy panel / TASK-0945 | 366 | Outcome 0945 | `completed/0945-compact-panel-main-integration.md`; warunek „przed 0153 podgląd receipts i zgoda” nieaktualny, bo baza ma `0154` (⊃ `0153`). | `archiwum` |
| 13 | Lokalny Reviewer / D-541 | 371 | D-541 | D-541 w indeksie `DECISION_LOG.md`; TASK-0961–0965 w `completed/`; plan `REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md` ma `status: completed`. To decyzja produktowa, nie ograniczenie przekrojowe (D5). | `archiwum` |
| 14 | Stan migracji bazy operatora | 804 | „TASK-0933 … w tym pliku”, „TASK-0932 … w tym pliku” | Źródła nie ma już w oknie (są w archiwum Q4, l. 454 i 510). Część migracyjna rozwiązana: `0154` ⊃ `0151`, obie `0152`, `0153`. `POST …/derive` dla Mumii nie jest nigdzie odnotowany. | `operator` (O3; część migracyjna → `archiwum`) |
| 15 | Migracja `0154` … wykonana 2026-10-10 | 787 | sekcja TASK-0972 | Fakt wykonany; v1.7.308 `5621ed34`; gałąź usunięta. Uwaga o worktree na starym kodzie jest ogólną konsekwencją Z5. Odbiór i audyty są w pliku TASK-0972. | `archiwum` |
| 16 | Plan cofania korekt: odbiór i dług audytowy | 348 | sekcja TASK-0972 | Ta sama treść jest w `tasks/0972-…` (`SOURCE_ADVANCED`, `pipeline_store.py:353`). | `do task` (`tasks/0972-geometry-correction-revert-acceptance.md`; już tam jest) |
| 17 | Migracje panelu zarządzania `0148`–`0150` | 564 | archiwum Q4, TASK-0921–0927 | `0154` ⊃ `0150`: migracje zastosowane. Zdanie o kontrolach fizycznych (telefon, ingress, restart) jest w sekcjach-źródłach archiwum. | `archiwum` (pytanie R14 o kontrole fizyczne) |
| 18 | TASK-0928: wdrożenie na żywo zablokowane | 608 | sekcja TASK-0928 | Blokada `0146`/`0147` nieaktualna (`0154` ⊃ `0147`). Stan joba `092ff7a4…` nieznany; plik taska `in_progress`, `Outcome` czeka na wznowienie joba. | `do task` (`tasks/0928-image-import-storage-resume.md`) |
| 19 | Restart workera (zgoda TASK-0928) | 318 | sekcja TASK-0928 | Zgoda jednorazowa dla jednego taska; zasada ogólna jest w Z4. PID 6984/19496 sprzed przeniesienia na D (nieaktualne). | `do task` (0928) |
| 20 | Cykl życia usług | 1 014 | AGENTS.md, sekcja TASK-0956 | Reguła w `AGENTS.md`, „Kontrola lokalnych usług API i Admin” (l. 135). Stan z D potwierdza sekcja TASK-0956; TASK-0957 nadal `todo`, więc zakaz używania C obowiązuje. | `zostaje` (Z4) |
| 21 | Migracje bazy wymagają osobnej zgody | 528 | archiwum Q4, „Hybrydowy silnik siatek V3…” (l. 2467) | Reguła zgody; aktualna (na `codex/v3-grid-fine-tuning` czekają `0155`–`0159`). | `zostaje` (Z5) |
| 22 | Udostępnianie online (D-470/D-471) | 438 | archiwum Q3 | Migracja `0130` zastosowana (`0154` ⊃ `0130`); parametry bezpieczeństwa są w D-470/D-471 (`decisions/`). | `archiwum` |
| 23 | Masowe odświeżenie odczytów wyszukiwarki | 417 | archiwum Q3 | `completed/0773-board-lines-stale-document.md` dotyczy okna planszy; masowe odświeżenie nie jest odnotowane jako wykonane. Zgoda na mutację danych. | `zostaje` (Z7) |
| 24 | Kolejność dla `apply` manifestu Arbuz | 357 | archiwum Q3, D-464 | `1e4be8ce` występuje tylko w archiwum Q3 (l. 215) i w tym punkcie; brak śladu wykonania. Ograniczenie bezpieczeństwa danych. | `zostaje` (Z8; pytanie R13) |
| 25 | Operacje destrukcyjne na danych | 433 | sekcja TASK-0517 | Reguła zgody (`AGENTS.md`); TASK-0517 `in_progress`, receipt GC `executing`. | `zostaje` (Z6) |
| 26 | Rezerwa dysku (D-534, D-530) | 312 | sekcja TASK-0928 | D-534 w indeksie; implementacja v1.7.251 `9b88e244`. Zdanie „brak migracji ani czyszczenia w TASK-0928” jest zakresem taska. | `archiwum` |
| 27 | Gra Mumie jest w statusie `draft` | 563 | archiwum Q4, TASK-0843, TASK-0936 | Źródło TASK-0936 nie jest już w oknie (archiwum Q4 l. 358). Aktualnego statusu gry nie da się odczytać bez bazy. | `operator` (O4) |
| 28 | Modele symboli Mumii (V5 odrzucony) | 526 | archiwum Q4, TASK-0872, TASK-0843 | Brak późniejszego zapisu w oknie; mogło zostać zastąpione przebiegami RGB v2 (D-520 i nowsze). | `operator` (O5) |
| 29 | Plan symboli premium Mumii | 436 | archiwum Q4 | Duplikat: „Otwarte decyzje i pytania” wymienia status tego planu jako decyzję operatora. | `archiwum` |
| 30 | Plan Mumie (D-535) | 502 | sekcja planu w oknie | TASK-0929–0936 i 0938 w `completed/`; 0937 i 0939 `blocked`. Zastępstwo audytu Claude „do czasu CLI codex” nieaktualne: Codex audytował plan dysku D (5 rund) i TASK-0955. Reguła scalania pokrywa Z2. | `archiwum` |
| 31 | TASK-0937 (pilot złotej ramki) `blocked` | 476 | sekcja TASK-0936 „w tym pliku” | Źródło w archiwum Q4. Warunek `0152` spełniony; pozostałe warunki są w `tasks/0937-…` (`30 komórek`, `0152`). Zdanie o TASK-0939 dubluje Z12. | `do task` (0937) |
| 32 | Znane odłożone braki bramki jakości | 520 | „TASK-0940 … w tym pliku” | Źródło w archiwum Q4 l. 486 i `completed/0940-green-quality-gate.md`. Ograniczenie zakresu dla każdej pracy. | `zostaje` (Z9) |
| 33 | TASK-0645–0647 `blocked` | 307 | brak | Statusy w plikach zgodne; treść = wskaźnik grupowy. Decyzja jest też w „Otwartych decyzjach”. | `do task` (0645–0647) |
| 34 | Usunięcie legacy public store | 435 | sekcja TASK-0687 | `decisions/DECISION_LOG_2026.md` l. 2176 (D-467): „Migracja `0125` została już zastosowana na bazie operatora (`alembic_version` = `0128`); plan D-448 jest zamknięty”. Plan `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` ma `status: completed`. Zakaz DDL bez zgody jest więc rozwiązany; ogólna reguła pozostaje w Z5/Z6. | `archiwum` (pytanie R1 o statusy tasków) |
| 35 | Vision lab (D-456, T03k, porty) | 495 | archiwum Q4 | Statusy 0668/0671/0672–0678 zgodne z plikami; to treść wskaźników. Zdanie o portach 8103–8108 przenieść do wskaźnika 0668. | `do task` (wskaźniki 0668, 0671, 0672–0678) |
| 36 | TASK-0603 / 0654 / 0290 | 626 | sekcje w oknie | Duplikat wskaźników tych tasków. | `do task` |
| 37 | Kolizje numeracji | 641 | archiwum Q3, Q4 | Reguła ogólna, nadal aktualna (równoległe tory). | `zostaje` (Z3, z punktem 7) |
| 38 | Odroczony plan snapshotu mobilnego | 234 | plan `deferred` | `APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md` istnieje; D-463 nadal „proponowana” w „Otwartych decyzjach”. Chroni zasadę offline. | `zostaje` (scalić z 39 → Z11) |
| 39 | Aplikacja mobilna offline | 183 | CLAUDE.md | Reguła stała. | `zostaje` (Z11) |
| 40 | Narzędzia tokenowe (pilot TASK-0939) | 591 | TASK-0939 | Hook i `code-map:check` opisane w `AGENTS.md` (l. 26–32, 127); pilot nadal bez pomiaru. | `zostaje` (Z12) |
| – | Akapit wprowadzający „Ograniczenia operacyjne nadal obowiązujące…” | 470 | – | Opis metody z TASK-0938. | `zostaje` jako jedno zdanie (Z0) |

Liczności (40 punktów): `zostaje` 13 (po scaleniu 7→37 i 38→39: 11
punktów Z1–Z12 bez Z10, plus Z0), `do task` 9, `archiwum` 13, `operator` 5.

### Proponowane teksty `zostaje` (każdy ≤ 400 B, zmierzone w UTF-8)

- Z0 (zamiast akapitu wprowadzającego): „Każdy punkt wskazuje źródło; stan
  z daty wpisu przed poleganiem na nim zweryfikuj odczytem, bez zmian w
  systemie.”
- Z1 (388 B): - **Gałąź integracyjna = `main`** (operator, 2026-10-16): nowe gałęzie od `main`, scalanie do `main`. `v1.1-vision-lab-hybrid-geometry` jest w `main`; usuwa ją operator albo agent za osobną zgodą (wskazuje ją worktree `multi-game-share`). Starsze wzmianki o „gałęzi integracyjnej” dotyczą tamtej gałęzi. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- Z2 (361 B): - **Akceptacja przed scaleniem** (operator, 2026-10-14, TASK-0992): wykonaj cały zlecony task, etap albo plan z kontrolami, dokumentacją i commitami, potem zapytaj o akceptację wyniku i zgodę na scalenie; scal po wyraźnym potwierdzeniu. Push, restart usług i migracje mają osobne bramki. Źródło: `AGENTS.md`, „Scalanie do gałęzi integracyjnej”.
- Z3 (334 B): - **Kolizje numeracji:** równoległe gałęzie kolidują w numerach TASK, D- i `vX.Y.N`; przed numerowaniem sprawdź czubek `main` i otwartych gałęzi. Istniejące kolizje (TASK-0603, 0649–0653, 0825, 0975) zostają: identyfikuj task pełną ścieżką pliku, bez przenumerowania commitów i raportów. Źródło: archiwum Q3/Q4.
- Z4 (386 B): - **Cykl życia usług:** API, Admin, Reviewer i workery uruchamia, zatrzymuje i restartuje wyłącznie operator; zgoda na restart dotyczy jednego zadania. Usługi działają z `D:\game_predicotr` (API z `--reload`). Z katalogu `C:\Users\tuszy\Documents\game_predicotr` nie uruchamiać usług do etapu C (TASK-0957). Źródło: `AGENTS.md`, „Kontrola lokalnych usług API i Admin”.
- Z5 (349 B): - **Migracje bazy operatora tylko za osobną zgodą**, w przejściu stop usług → scalenie → `db:migrate` → start; test na `*_test` nie jest zgodą. Nie scalaj do `main` kodu wymagającego niewykonanej migracji (API z `--reload` nie wystartuje). Ostatni zapis: `0154` (2026-10-10). Źródło: archiwum Q4, „Hybrydowy silnik siatek V3…”.
- Z6 (325 B): - **Operacje destrukcyjne** (GC, cleanup, usuwanie legacy, `db:reset:local`, DROP baz): implementacja nie jest zgodą na wykonanie; wymagany podgląd i jawne potwierdzenie. GC TASK-0517 zatrzymany; wznowienie tylko za nową zgodą dla istniejącego SHA. Źródło: `AGENTS.md`; `tasks/0517-confirmed-legacy-game-removal.md`.
- Z7 (247 B): - **Masowe odświeżenie odczytów wyszukiwarki** (TASK-0773, D-474, ok. 88 260 plansz gry 7) to osobne zadanie za zgodą operatora; okno planszy odświeża jedną planszę. Źródło: archiwum Q3, „D-470 / D-471 — Przybliżona wygrana…”.
- Z8 (232 B): - **`apply` manifestu Arbuz < 60 %** (sha256 `1e4be8ce…`, 2 703 plansze) nie biegnie równolegle z weryfikacją w Adminie ani z przeliczaniem predykcji. Źródło: archiwum Q3, „D-464 — biblioteka wzorców symboli, etap A”.
- Z9 (294 B): - **Odłożone braki `npm run quality`** (TASK-0940): 3 pomijane testy historycznych migracji, testy korpusów M5 bez korpusu, test junction tylko w worktree, 4 stare testy CLI (TASK-0928). Nie naprawiaj ich w innym zadaniu bez decyzji. Źródło: `tasks/completed/0940-green-quality-gate.md`.
- Z11 (343 B): - **Aplikacja mobilna offline:** jedynym źródłem jest wersjonowany snapshot SQLite w APK, bez `INTERNET` w wydaniu. Plan przybliżonego snapshotu mobilnego jest `deferred` do nowej decyzji (proponowana D-463); do tego czasu zmiany tylko w aplikacji webowej. Źródło: `CLAUDE.md`; `delivery/APPROXIMATE_MOBILE_SNAPSHOT_EXECUTION_PLAN.md`.
- Z12 (312 B): - **Narzędzia tokenowe (pilot TASK-0939):** hook blokuje `Read` pliku > 200 KB bez `offset`/`limit`; Serena i Graphify bez stałego wpisu do czasu pomiaru; task zmieniający moduły regeneruje mapę kodu (`scripts/generate_code_map.py`, kontrola `npm run code-map:check`). Źródło: `guides/TOKEN_TOOLING.md`.

Z10 (legacy `public`) został przygotowany, ale punkt 34 przechodzi do
archiwum na podstawie D-467; jeśli operator zdecyduje inaczej (R1), tekst:
„**Usunięcie legacy `public` (TASK-0687–0691):** DDL wymaga odrębnej zgody
operacyjnej (`guides/LEGACY_PUBLIC_STORE_REMOVAL.md`); TASK-0694/0695/0698
czekają na rozstrzygnięcie sprzecznych zasad transakcji (TASK-0698).” (280 B).

TASK-1022 dopisze ponadto punkt zapowiedziany w planie: „po scaleniu każda
otwarta gałąź przepisuje swoje hunki stanu na nowy format” (ok. 250 B).

### Skróty dla klasy `operator` (zostają do decyzji, potem zostaje albo archiwum)

- O1 (203 B): - **Poll worker `general` po TASK-0991:** istniejący proces nie był przeładowany po naprawie v1.7.351; przeładowuje operator według instrukcji w `tasks/completed/0991-symbol-reinference-resume.md`.
- O2 (233 B): - **Nowy import 275 zdjęć Mumii:** po wymianie źródeł 2026-10-09 przygotować paczkę z identycznymi nazwami i rangami jako nowy import; oryginały i staging zachowane. Źródło: `quality/MUMIE_SOURCE_REPLACEMENT_20261009.md`.
- O3 (243 B): - **Seria supergry Mumii:** migracja `0152` jest zawarta w `0154`, ale `POST …/derive` dla Mumii nie jest odnotowany; to warunek pomiaru TASK-0937. Źródło: archiwum Q4, „TASK-0933 — wyprowadzanie serii supergry i API serii (done)”.
- O4 (263 B): - **Gra Mumie `draft`** (`fea55cc1-…`, `grid_profile_mumie_v1`): wyniki serii są `provisional` do zdefiniowania super symbolu i świeżej generacji serii (D-537); nie wchodzą do bilansu ani rozpoznanych wypłat. Źródło: archiwum Q4, TASK-0843 i TASK-0936.
- O5 (255 B): - **Modele symboli Mumii:** odrzuconego kandydata V5 nie używać (TASK-0872, obowiązuje baseline R2 RGB); historycznego CLI `verified_v19` nie uruchamiać, import przez `scripts/run_mumie_image_import.py`. Źródło: archiwum Q4, TASK-0872 i TASK-0843.

Pełne, niezmienione teksty punktów `archiwum`, `do task` i oryginały punktów
skracanych trafiają na początek `ai_docs/archive/CURRENT_STATE_2026Q4.md`
(D4); punkty `do task` dodatkowo do wskazanego pliku taska, gdy ich treści
tam jeszcze nie ma (dotyczy punktu 6; punkty 16, 18, 31 już są w plikach).

## 2. Plany z niezakończonymi taskami

| Plan (podsekcja) | B | Status (nagłówek / plik planu) | Pozostałe taski (`tasks/` vs `completed/`) | Propozycja |
|---|---:|---|---|---|
| Odchudzenie obowiązkowego odczytu startowego | 662 | accepted / accepted | 1021, 1022, 1023 w `tasks/` | wiersz: `delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md` · accepted · TASK-1021–1023 · `feat/startup-read-diet` |
| Doszkalanie siatek V3 z korekt w aplikacji | 2 343 | proposed rev. 2 (na tej gałęzi); na `codex/v3-grid-fine-tuning` plik ma `accepted`, rewizja 6, v1.7.384 | na tej gałęzi brak plików; na `codex/v3-grid-fine-tuning` aktywne 0995, 0996, 0997, 1000, 1001, 1005, 1006 | wiersz po synchronizacji z tamtą gałęzią (stan z jej czubka); szczegóły audytu i kierunki operatora do archiwum |
| Plan przeniesienia aplikacji i bazy na dysk D | 1 711 | accepted / accepted | 0952–0955 w `completed/`; 0956 `blocked`, 0957 `todo` | wiersz: `delivery/DISK_D_MIGRATION_PLAN_20261009.md` · accepted (D-540) · 0956 blocked, 0957 todo · scalona (v1.7.312) |
| Plan braków geometrii zdjęć w lokalnym Reviewerze | 1 054 | „wykonany w kodzie” / `completed` | 0961–0965 wszystkie w `completed/` | archiwum (pytanie R7 o odbiór wizualny) |
| Plan korekty układu panelu | 737 | proposed / proposed | 0947, 0948, 0949 `todo` | wiersz: `delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md` · proposed (D-539) · 0947–0949 todo · brak gałęzi |
| Plan cofania korekty cięcia siatki… | 1 060 | „implemented, awaiting operator migration and acceptance” (także w pliku planu) | 0966–0971 w `completed/`; 0972 `blocked` | wiersz: `delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md` · migracja `0154` wykonana, czeka odbiór · 0972 blocked · scalona (v1.7.306/308); rozbieżność nagłówka R6 |
| Plan Mumie: Wild, supergra, audyt krzyżowy | 576 | accepted; tekst „taski 0929–0939 `todo`… żaden etap nie jest uruchomiony” | 0929–0936, 0938 w `completed/`; 0937, 0939 `blocked` | wiersz: `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` · accepted (D-535) · 0937, 0939 blocked · scalona; rozbieżność R2 |

Plany bez podsekcji, choć mają aktywne taski (propozycja: dodać wiersze, ok.
200 B każdy): `VISION_LAB_EXECUTION_PLAN.md` (0611?, 0649–0653 zastąpione,
0668, 0671–0678), `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`
(0645–0647), `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` (`completed`,
a 0687–0698 aktywne; R1), `GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (0802).
Taski 0290, 0305, 0472, 0517, 0603, 0654, 0928 nie mają wskazanego planu w
oknie; wystarczy wskaźnik taska.

Proponowany kształt sekcji: jedna tabela `Plan | Status | Pozostałe taski |
Gałąź` z 10 wierszami (6 obecnych bez planu Reviewera + 4 brakujące), pełne
podsekcje bez zmian na początek archiwum Q4.

## 3. Aktywne taski

Kolumna „W pliku?” mówi, czy fakty sekcji są już w pliku taska (sprawdzone
`grep -F` charakterystycznych wartości). „Do archiwum” oznacza przeniesienie
całej sekcji bez edycji na początek archiwum Q4. Grupowe nagłówki muszą
wymieniać każdy numer z prefiksem `TASK-`, bo `scripts/check_current_state_window.py`
szuka `\bTASK-NNNN\b` w nagłówku dla każdego pliku w `ai_docs/tasks/`.

| Sekcja(e) | B | Plik taska i status | W pliku? | Proponowany wskaźnik (≤ 1 200 B) | Do archiwum |
|---|---:|---|---|---|---|
| TASK-1021 | 179 | `tasks/1021-current-state-constraints-review.md`, `todo` | tak | bez zmian | – |
| TASK-1022 | 151 | `tasks/1022-current-state-budgets.md`, `todo` | tak | bez zmian | – |
| TASK-1023 | 154 | `tasks/1023-claude-md-dedupe-final-measurement.md`, `todo` | tak | bez zmian | – |
| TASK-0956 | 1 239 | `tasks/0956-disk-d-application-startup.md`, `blocked` (lista operatora) | tak (`258 212`, `Path`) | `blocked` — plik taska. Etap B2 wykonany 2026-10-10 (usługi z D, `0154`, 0 brakujących ścieżek). Czeka na listę kontrolną operatora: restart Windows, telefon i tunel, wpisy C w `Path`, ponowny backfill weryfikacji symboli Mumii. v1.7.309 / `ba3b36d1`, scalenie v1.7.312. | cała sekcja |
| TASK-0957 | 780 | `tasks/0957-disk-d-cleanup-and-job-paths.md`, `todo` | tak (Preview: 158.4 GB, 103.1 GB) | `todo` — plik taska. Podgląd gotowy (sekcja „Preview”): stary vhdx na C, checkout C, `source_directory` jobów, bazy testowe; każda operacja za osobną zgodą. v1.7.310 / `190d30cc`. | cała sekcja |
| TASK-0947, 0948, 0949 (3 sekcje) | 1 091 | `tasks/0947-…`, `0948-…`, `0949-…`, wszystkie `todo` | częściowo (`selectedStake` w 0947) | Nagłówek `### TASK-0947, TASK-0948, TASK-0949 — korekta układu panelu (todo)`: plan `ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md` (proposed) czeka na akceptację operatora; D-539: piny wszystkich zapisanych stawek widoczne od razu (kod ogranicza podgląd przez `selectedStake && !editor`). | trzy sekcje |
| TASK-0290 | 13 543 | `tasks/0290-remote-manual-selection-rollout-benchmark.md`, `blocked` | częściowo (`v0.8.18`, `v0.7.71` są; `REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY` i checkpoint feature flag nie) | `blocked` — plik taska. Operator-local workflow wdrożony; benchmark i publiczny rollout (LAN/Quick Tunnel) wstrzymane do decyzji właściciela; przed publicznym pilotem wymagany checkpoint polityki feature flag. Historia: archiwum Q4 (sekcja przeniesiona 2026-10-16). | cała sekcja 13,5 KB |
| TASK-0305 | 614 | `tasks/0305-v0-10-replacement-board-source.md`, odroczone (bez znacznika statusu) | tak | `todo` (odroczone poza 0.9) — plik taska; przed implementacją osobny breakdown API, transakcji i UX. Historia: archiwum Q3 „Odbiór wersji 0.9 — TASK-0304”. | – (sekcja prawie zgodna; skrót) |
| TASK-0472 (4 sekcje) | 2 749 | `tasks/0472-crop-v11-acceptance.md`, `blocked` — szósta bramka nie przeszła | częściowo (`960/1600`, `6/10`, raport; `5/10` nie) | Nagłówek `### TASK-0472 — akceptacja cropów v11 (blocked)`: szósta niezależna bramka jakości nie przeszła ścisłej precyzji; v11 nieaktywny, dane użytkownika bez zmian; dalsze prace tylko po osobnym poleceniu. Raport `quality/SELECTED_CROP_V11_REGRESSIONS.md`. | cztery sekcje |
| TASK-0517 | 1 635 | `tasks/0517-confirmed-legacy-game-removal.md`, `in_progress` | tak (`c4cce437`, `database_done`, `2258144`) | `in_progress` — plik taska. Baza starej gry `777 v0.1` usunięta (`database_done`); fizyczny GC zatrzymany przez operatora (receipt `executing`, 19,8 z 104,9 GiB). Wznowienie tylko za nową dokładną zgodą dla preview SHA `c4cce437…`. | cała sekcja |
| TASK-0603 (3 sekcje) | 3 322 | `tasks/0603-v7-real-777-calibration.md`, `in_progress`; ponadto `completed/0603-shape-geometry-v2-experiment-and-gates.md` | tak (`0,2255`, `0,0354`, `D-418`) | Nagłówek `### TASK-0603 — kalibracja etykiet 777 V7 w trybie V2 (in_progress)`: sesja V2 (manifest `.runtime/v7-label-geometry-calibration-t0603-v2.local.json`) czeka na anotacje operatora; potem profil, raport walidacji i adopcja; V7 zablokowane. Instrukcja: `LOCAL_OPERATION_GUIDE.md`. | trzy sekcje (sekcja „eksperyment… shape v2” opisuje ukończony plik kolizyjny) |
| TASK-0611 | 509 | `tasks/0611-shape-geometry-v2-board-frame-lattice.md`, `in_progress` | tak | bez zmian (zgodna z D7) | – |
| TASK-0645, 0646, 0647 (3 sekcje) | 1 700 | pliki `0645-…`, `0646-…`, `0647-…`, wszystkie `blocked` | tak | Nagłówek `### TASK-0645, TASK-0646, TASK-0647 — reweryfikacja siatek 777 (blocked)`: plan `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`; D-445 wstrzymała stary weryfikator, D-447 nie upoważnia do uzupełniania slotów historycznego 777 siecią ani zapisu na żywych danych; wznowienie wymaga osobnej decyzji. | trzy sekcje |
| TASK-0649–0653 (5 sekcji) | 3 560 | `0649-grid-nn-candidate-pool.md` … `0653-grid-nn-777-slot-fill.md`, `blocked` (zastąpione) | tak | Nagłówek `### TASK-0649, TASK-0650, TASK-0651, TASK-0652, TASK-0653 — dawny plan sieci siatek (blocked, zastąpiony)`: plan zastąpiony przez `VISION_LAB_EXECUTION_PLAN.md` (D-447), odpowiedniki TASK-0666/0668–0671/0674/0675/0678. Numery kolidują z ukończoną serią „Przybliżona wygrana” (`completed/0649-…`–`0653-…`); identyfikuj pełną ścieżką. | pięć sekcji |
| TASK-0654 | 2 071 | `tasks/0654-approximate-win-docs-and-acceptance.md`, `in_progress` | tak (`D-446`, `spinCount`) | `in_progress` — plik taska. Dokumentacja „Przybliżonej wygranej” (D-446) ukończona; odbiór na żywych danych gry 777 czeka na jawną zgodę operatora. Znane braki: fikstura `test_payout_store.py`, `prettier` klienta, limit `spinCount ≤ 10 000` bez pomiaru. | cała sekcja |
| TASK-0668 | 1 000 | `tasks/0668-vision-lab-geometry-annotations.md`, `in_progress` | tak | `in_progress` — plik taska. D-456 zatwierdza T03k i pilota całymi grami bez pomiaru; pozostaje mapowanie źródeł do rodzin, kontrola konfliktów i zamrożony podział. Narzędzia lab (porty 8103, 8105, 8107, 8108) startują ręcznie, bez autostartu. | cała sekcja |
| TASK-0671 | 497 | `tasks/0671-vision-lab-symbol-labels.md`, `blocked` | tak | bez zmian | – |
| TASK-0672–0678 (7 sekcji) | 1 665 | `0672-…` … `0678-…`, wszystkie `todo` | tak | Nagłówek z siedmioma numerami `TASK-0672, …, TASK-0678 — laboratorium wizji T07–T13 (todo)`: T07 modele symboli, T08 panel treningu, T09 walidacja, T10 neural_grid, T11 geometria w aplikacji, T12 symbole w workerze, T13 odbiór; plan `VISION_LAB_EXECUTION_PLAN.md`; czekają na T03 (0668) i T06b (0671). | siedem sekcji |
| TASK-0687 | 2 951 | `tasks/0687-v2-only-release-readiness.md`, `blocked` | tak (`67,56`, `D-038`, `0124`) | wchodzi do wskaźnika grupowego poniżej | cała sekcja |
| TASK-0688–0691, 0694, 0695, 0698 (7 sekcji) | 2 440 | 0688–0691 `todo`, 0694 `blocked`, 0695 `todo`, 0698 `blocked` | tak | Nagłówek `### TASK-0687, TASK-0688, TASK-0689, TASK-0690, TASK-0691, TASK-0694, TASK-0695, TASK-0698 — V2-only i usunięcie legacy public (blocked/todo)`: plan `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` (`completed`). T09 `no-go` wg 0687; D-467 odnotowuje jednak, że `0125` zastosowano na bazie operatora (R1). Otwarta decyzja: konflikt D-038 z transakcją jednej gry V2 (TASK-0698). Raport `quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`. | siedem sekcji |
| TASK-0802 | 653 | `tasks/0802-neural-grid-whole-screen-network.md`, `in_progress` | tak | `in_progress` — plik taska. Silnik `neural_grid` (wszystkie plansze, 24 węzły, ONNX, metryka D-483); historia: archiwum Q4 „Hybrydowy silnik siatek V3…”. | – (skrót „Cel”) |
| TASK-0928 | 1 373 | `tasks/0928-image-import-storage-resume.md`, `in_progress` | tak (`19:22:52`, `0147_merge_v7_main`) | `in_progress` — plik taska. Poprawka rezerwy (D-534) v1.7.251 / `9b88e244`; odbiór wymaga wznowienia joba Mumii `092ff7a4…` (535/2915) po restarcie workera `general` przez operatora. Blokada migracji `0147` nieaktualna (baza `0154`, 2026-10-10); stan joba po wymianie źródeł Mumii nieznany. | cała sekcja |
| TASK-0937 | 790 | `tasks/0937-gold-frame-detection-pilot.md`, `blocked` | tak | `blocked` — plik taska; narzędzie v1.7.281 / `7b7b0a7e`. Warunek `0152` spełniony (`0154`); pozostają wyprowadzona seria supergry Mumii, co najmniej 5 super symboli i etykiety operatora (≥ 30 komórek na wariant). | cała sekcja |
| TASK-0939 | 1 899 | `tasks/0939-token-tooling-pilot.md`, `blocked` (okno: `in_progress`) | tak (`36 sesji`, `uvx`) | `blocked` — plik taska; narzędzia v1.7.284 / `6f783932`, status v1.7.285 / `1b97ad65`. Pomiar 36 sesji wg `quality/TOKEN_TOOLING_PILOT_PROTOCOL.md` i raport „zostaje / wypada” wykonuje operator po zgodzie na koszt. | cała sekcja |
| TASK-0972 | 2 462 | `tasks/0972-geometry-correction-revert-acceptance.md`, `blocked` | tak (`SOURCE_ADVANCED`, `pipeline_store.py:353`, `task0760`) | `blocked` — plik taska; scalenie v1.7.306 / `853052a1`, dokumenty v1.7.307 / `f7f6d30e`, migracja `0154` 2026-10-10. Czeka na odbiór operatora (cofnięcie świeżej korekty, import zastępczy; slot 69004 nie istnieje). Dług audytowy 0966/0968/0970/0971 i baza testowa do usunięcia — w pliku taska. | cała sekcja |

Po zastosowaniu: 50 sekcji `###` → 24 wskaźniki (18 pojedynczych, w tym
1021–1023, 0611 i 0671 bez zmian, oraz 6 grupowych). Każdy wskaźnik ma
≤ 650 B.

## 4. Ostatnie 10 ukończonych tasków (format D6)

Hashe z sekcji okna; dla TASK-1020 sekcja odsyła do kolejnego commita, więc
skrót wzięto z `git log` (`d803c27c`).

- **TASK-1020** — `DECISION_LOG.md` jako lekki indeks — v1.7.367 / `d803c27c` — `tasks/completed/1020-decision-log-light-index.md`
- **TASK-1019** — Skrypt pomiaru i budżetów odczytu startowego — v1.7.366 / `d1174304` — `tasks/completed/1019-startup-read-budget-script.md`
- **TASK-1007** — Trwałe wykrywanie Claude Code CLI — v1.7.361 / `baf67dbd` (scalenie v1.7.362 / `885ba12f`) — `tasks/completed/1007-claude-cli-discovery.md`
- **TASK-0991** — Wznowienie symboli i pełny przebieg 777 a2 <80% — v1.7.358 / `17a1012e` (naprawa v1.7.351 / `6e84a1b1`) — `tasks/completed/0991-symbol-reinference-resume.md`
- **TASK-0992** — Scalenie naprawy i obowiązek integracji — v1.7.353 / `14aeb0c0` (korekta v1.7.355 / `be7ecff1`) — `tasks/completed/0992-integration-branch-merge-policy.md`
- **TASK-0979** — Wydanie 1.0.0 i odbiór operatora — v1.7.349 / `8ac68f5f` — `tasks/completed/0979-selector-desktop-release-acceptance.md`
- **TASK-0990** — Zakres pośrodku nad zdjęciem i końcowy zapis widoku — v1.7.343 / `8a3249fd` — `tasks/completed/0990-selector-desktop-centered-range.md`
- **TASK-0989** — Stabilny układ, minimalny fullscreen i centrowanie zdjęcia — v1.7.341 / `a9cb2fed` — `tasks/completed/0989-selector-desktop-stable-layout-and-fullscreen.md`
- **TASK-0988** — Brak limitu liczby zdjęć — v1.7.340 / `ccb9526e` — `tasks/completed/0988-selector-desktop-no-count-limit.md`
- **TASK-0975** — Odzyskiwanie treningu symboli po odrzuceniu podziału — v1.7.317 / `28d48445` — `tasks/completed/0975-symbol-training-rejected-split-recovery.md`

Każdy wiersz ma 150–230 B (≤ 400 B). Pełne sekcje `done` (11 286 B) idą bez
edycji na początek archiwum Q4. Uwaga dla TASK-1022: obecny
`check_current_state_window.py` liczy `### TASK-… (done` — po zmianie na
wiersze trzeba zmienić tę regułę (limit 10 wierszy).

## 5. Rozbieżności (pytania do operatora, bez napraw)

- **R1. Legacy `public`.** `decisions/DECISION_LOG_2026.md` (D-467, l. 2176):
  „Migracja `0125` została już zastosowana na bazie operatora
  (`alembic_version` = `0128`); plan D-448 jest zamknięty”, plan ma `completed`,
  a TASK-0687–0691/0694/0695/0698 są nadal `blocked`/`todo`, a punkt 34 mówi o
  wymaganej zgodzie na DDL. Czy zamknąć te taski (done/superseded), a TASK-0698
  (D-038) zostawić jako otwartą decyzję?
- **R2. Plan Mumie.** Podsekcja mówi „taski 0929–0939 `todo`… żaden etap nie
  jest uruchomiony”, a 0929–0936 i 0938 są w `completed/`; 0937 i 0939
  `blocked`. Czy plan uznać za wykonany poza 0937/0939?
- **R3. TASK-0939.** Okno: `in_progress`; plik i commit v1.7.285 (`1b97ad65`):
  `blocked`. Który status obowiązuje?
- **R4. TASK-0603.** Sekcja „eksperyment i kontrakt shape v2” opisuje ukończony
  plik `completed/0603-shape-geometry-v2-experiment-and-gates.md` (kolizja
  numerów), a sekcja „przygotowanie realnej kalibracji” mówi `blocked`, gdy
  plik aktywny ma `in_progress` (V2). Potwierdzić archiwizację obu sekcji.
- **R5. Migracja `0154` a warunki starsze.** Warunki TASK-0928 (`0147`),
  TASK-0937 (`0152`) i punkt 14 opisują migracje już zawarte w `0154`. Czy job
  `092ff7a4…` jeszcze istnieje i czy `POST …/derive` dla Mumii został wykonany?
- **R6. Plan cofania korekt.** Nagłówek okna i `status:` pliku planu: „awaiting
  operator migration”; migracja `0154` wykonana 2026-10-10. Zdanie „kod
  wymagający `0154` nie trafia do gałęzi integracyjnej przed migracją” jest
  nieaktualne.
- **R7. Plan braków geometrii w Reviewerze.** Plan `completed`, wszystkie
  taski w `completed/`, a podsekcja czeka na „odbiór wizualny po restarcie
  operatora”. Czy odbiór wykonano (usługi startowały z D po v1.7.312)?
- **R8. Plan V3 fine-tuning.** Tu `proposed` rev. 2, na
  `codex/v3-grid-fine-tuning` `accepted` rev. 6 z 7 aktywnymi plikami i
  migracjami `0155`–`0159`; tamta gałąź ma `CURRENT_STATE.md` 97 148 B i 17
  sekcji TASK-0993–1018. TASK-1022 musi działać po synchronizacji (plan, „Warunki
  wejścia”). Czy scalenie tamtej gałęzi nastąpi przed TASK-1022?
- **R9. Martwe źródła.** Punkty 14, 27, 31, 32 cytują sekcje „w tym pliku”
  (TASK-0932, 0933, 0936, 0940), których nie ma już w oknie (są w archiwum Q4,
  l. 510, 454, 358, 486). Propozycja: w skrótach podać „archiwum Q4”.
- **R10. TASK-0654.** Blokada „zgoda na uruchomienie lokalnego API i Admina”;
  usługi działają teraz stale z D. Czy odbiór na żywych danych jest nadal
  wstrzymany, czy może zostać wykonany na działających usługach?
- **R11. TASK-0649–0653 (grid-nn).** Zastąpione przez D-447, ale trzymane jako
  `blocked`. Zamknąć jako superseded?
- **R12. TASK-0802 i T10/T11 (0675, 0676).** `neural_grid` działa produkcyjnie
  (D-544, import `777a2`). Czy te taski są nadal aktualne, czy częściowo
  wykonane?
- **R13. Arbuz `apply` i TASK-0305.** Czy manifest `1e4be8ce…` został
  zastosowany (wtedy punkt 24 do archiwum)? Czy TASK-0305 (zastępcze zdjęcie
  planszy) nie jest pokryty przez D-543 / `completed/0971-replacement-photo-sequence-takeover.md`?
- **R14. Dysk C i kontrole fizyczne.** Czy lista kontrolna TASK-0956 (restart,
  telefon, tunel, `Path`) i kontrole fizyczne panelu zarządzania (punkt 17)
  zostały wykonane? Sesja Claude Code tego przeglądu ma katalog projektu i
  pamięć zarejestrowane pod `C:\Users\tuszy\Documents\game_predicotr`, choć punkt
  20 każe nie używać C.
- **R15. TASK-0472.** Okno ma cztery sekcje kolejnych bramek, a plik mówi o
  szóstej nieudanej bramce: okno było nieaktualne; po zmianie zostaje
  wskaźnik.

## 6. Prognoza

| Sekcja | Teraz (B) | Po propozycji (B, szacunek) | Budżet D3 |
|---|---:|---:|---:|
| Nagłówek i reguła utrzymania (TASK-1022 przepisuje regułę) | ok. 1 450 | ok. 1 600 | – |
| Obowiązujące ograniczenia (Z0–Z12 bez Z10 ok. 3 900, O1–O5 1 200, punkt o hunkach 250, nagłówek) | 20 327 | ok. 5 500 | 8 000 |
| Plany z niezakończonymi taskami (tabela 10 wierszy) | 8 180 | ok. 2 300 | 5 000 |
| Otwarte decyzje i pytania (bez zmian; ewentualnie R1/R11) | 1 015 | ok. 1 100 | – |
| Aktywne taski (24 wskaźniki, każdy ≤ 650 B) | 49 045 | ok. 10 000 | 1 200 na sekcję |
| Ostatnie 10 ukończonych (wiersze D6) | 11 286 | ok. 2 000 | 400 na wpis |
| **Razem** | **90 959** | **ok. 22 500** | **30 000** |

Po synchronizacji z `codex/v3-grid-fine-tuning` dojdzie 7 aktywnych tasków
(ok. 7 × 450 B) i wiersz planu, czyli ok. 25 800 B. Jeśli operator zamknie
taski z R1, R2, R11, wynik spada o ok. 1 500 B. Budżety D3 są osiągalne bez
usuwania żadnego ograniczenia, które musi zostać, więc nie proponuję zmiany
budżetów. Margines ok. 4 000 B pokrywa kolejne równoległe tory, o ile nowe
sekcje od razu trzymają D6/D7.

## 7. Decyzja operatora

2026-10-16: operator zatwierdził propozycję w całości (sekcje 1–4 i 6).
Pytania z sekcji 5 „Rozbieżności” pozostają otwarte, bez napraw w TASK-1022;
trafiają do „Otwartych decyzji i pytań” w `CURRENT_STATE.md`.
