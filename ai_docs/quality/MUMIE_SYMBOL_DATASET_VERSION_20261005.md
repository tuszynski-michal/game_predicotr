---
title: Mumie — labels-only dataset version acceptance
status: accepted
last_updated: 2026-10-05
---

# TASK-0851 — odbiór wersji etykiet symboli

## Wynik

Istniejący panel `http://127.0.0.1:3102/symbols` działa dla gry `mumie`:
31 zatwierdzonych zdjęć, 279 plansz, 4185 aktualnych komórek. Pełna plansza
otwiera od razu 15 edytowalnych pól; symbol nie wymaga zmiany siatki.
Nie nadano żadnej etykiety obecnym zdjęciom. Następna interakcja to wybór klas
przez operatora. Główna gra Mumie pozostaje bez plansz i zdjęć.

Wersja create-only:
`dab77630f3518604add168c2baeed124dc9c5010d8ea483201a5be8cb77da1fc`,
`C:\Users\tuszy\Documents\game_predictor_vision_data\symbol-dataset-versions\dab77630f3518604add168c2baeed124dc9c5010d8ea483201a5be8cb77da1fc`.
Manifest 11 642 217 bajtów zachowuje pełne oryginalne payloady/historię/receipts,
SHA katalogu/źródeł i zgody, zatwierdzony słownik v1 oraz historyczne użycie
runu 3 (25 train / 6 holdout). Bez nowego splitu lub AnnotationStore.

## Integralność

- Payload geometrii: `9975d618c4440c8d68ba40260881f25ffe75ee8e041b01e8deb6cd36bb09897f`.
- Payload symboli: `ffb9545ffad3d9cbeb62227395ec54f7c8d814d32aca307bd033e2ea96b4c140`.
- Słownik v1: `590f5154b3b0563ec2b8def746d179206bf5c73d494c32405f10bf365866597a`.
  Te same 10 tożsamości: 10, J, Q, K, A, Ra, Sarkofag, Mumia, Faraon, Sfinks.
- Role zachowane: Reels final_test, Treasure unseen_game, Mumie validation.
  Przechodnia suma starych i aktualnych powiązań chroni 523 źródła przed pikselami.
- Dawny split nadal stale; rewizje 591 geometrii i 46 symboli. 706 dotychczasowych
  decyzji zachowanych; zero obecnych 31 zdjęć. Sumy plików anotacji, symboli,
  ledger i manifestu snapshotu identyczne przed/po publikacji, UI i restartach.
- Deklaracja dwóch różnych nagrań ma dokładne foldery i nie nadaje verified.
  Nowa wersja upoważnia tylko do etykietowania. Trainability, podział symboli,
  rodziny i Super nie są zatwierdzone. Sześć dawnych zdjęć to historyczny holdout
  geometrii, nie nowy niezależny test symboli.

## Weryfikacja

- 47 testów: nowa wersja i istniejący pion labels/board/store/API. Restart,
  utracona odpowiedź, retry także po późniejszej korekcie siatki, holdout całego
  komponentu, drift katalogu/słownika i uszkodzenie manifestu. PASS.
- 16 testów snapshotu i whole-game split PASS. Łącznie 63 odrębne testy.
- Po limicie publikacji zgodnym z czytnikiem 64 MiB ponownie 7 testów wersji PASS.
- Ruff format/check PASS. Scoped strict Mypy: 6 zmienionych modułów PASS.
- OpenAPI `export_vision_lab_openapi.py --check` PASS; schema przed/po identyczna.
  Konfiguracja nie zmienia pól HTTP. Klient generowany i wrapper bez zmian.
- Next build istniejącego UI wraz z TypeScript PASS (20,72 s).
  Ostrzeżenie o dwóch lockfile zastane i pozostaje poza zakresem.
- Start/Status/Stop oraz ponowny Start w nowym PowerShell PASS. Zapisane
  PID/czas utworzenia/command line, ukryte procesy, krótkie odczyty gotowości.
  Własny writer 8105 zatrzymany; inne galerie i produkcyjne usługi bez zmian.
- Finalne HTTP po restarcie: pierwsze/ostatnie 15 pól, 4185 total, pełna plansza
  15 pól, identyczne bindingi queue/board, zero etykiet i niezmienione sumy.
- Browser smoke: mumie, słownik v1, 500/4185 w poczekalni, `seq_10-18.jpg`,
  plansza 1, wszystkie 15 wyborów aktywne. Bez przypisania i zapisu.
- Produkcyjny odczyt 8000: 10 symboli, zero layouts/source_images/
  recognized_boards/dataset_versions/imports. Bez DB/migracji/materializacji/
  shadow/treningu/aktywacji/usuwania/push/merge.

Pierwszy test nowego procesu importował main; dodano jawny PYTHONPATH worktree.
Dwie adnotacje Mypy poprawione. Nieistniejącą nazwę szerszego testu zastąpiono
zweryfikowanymi istniejącymi plikami. Testów i asercji nie osłabiono.

## Audyt DoD i granice

Własny audyt pokrywa wszystkie kryteria taska i sześć kroków planu: preview,
create-only lineage, ochrona ról, istniejący pion, labels-only, trwały start.
Bez pozostałych P0–P2. Domyślny workflow nadal blokuje stale. Drift geometrii,
katalogu lub słownika blokuje referencję; stary receipt pozostaje odtwarzalny
bez nowych pikseli i z nieważną kwalifikacją. Bez pomiaru accuracy symboli.
Restart procesów potwierdzony; restart komputera niewykonany. Konfiguracja
i instrukcja są zapisane trwale. Kod na `feat/grid-engine-v3`, bez merge.

Artefakty:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005`.
`runtime.json` służy do repozytoryjnego launchera. `preview.json`, `applied.json`,
`baseline.json`, `fresh-process-verification.json`, `runtime-verification.json`,
`editor-ready.jpg` i logi dokumentują odbiór.
