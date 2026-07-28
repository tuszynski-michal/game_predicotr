---
title: TASK-0055 Per-board perspective correction and cell crops
status: done
last_updated: 2026-07-28
---

# TASK-0055 — Per-board perspective correction and cell crops

## Status

`done`

## Goal

Indywidualnie wyprostować każdą z dziewięciu wykrytych plansz, usunąć
kontrolowany margines czerwonej ramki i zapisać deterministyczne wycinki
15 komórek planszy 3 × 5 bez wykonywania OCR ani klasyfikacji symboli.

## Context

TASK-0054 dostarcza quady dziewięciu plansz w kolejności row-major dla wariantu
D-053. Krzywizna ekranu i perspektywa zdjęcia wymagają osobnej transformacji
każdej planszy. Q-016 oraz pełne golden annotations pozostają otwarte, dlatego
wynik bieżącego korpusu jest prototypem dla potwierdzonego wariantu, a nie
uniwersalnym benchmarkiem accuracy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/quality/m5-quality-thresholds.json`
- `ai_docs/tasks/completed/0054-page-3x3-board-detection.md`
- D-006, D-010, D-014 i D-049–D-054 w
  `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- port `BoardCellCropper` niezależny od CLI i systemu plików,
- kontrakt `board-cell-crops-v1`,
- walidacja kompletnego wyniku TASK-0054 bez częściowego przesuwania indeksów,
- osobna transformacja perspektywy każdego quada do RGB 500 × 300,
- stały margines 5% od każdej krawędzi wyprostowanej planszy,
- podział wnętrza na 3 wiersze × 5 kolumn po 90 × 90,
- jawne indeksy planszy, wiersza i kolumny, wszystkie 0-based i row-major,
- zapis macierzy transformacji, źródłowego quada, geometrii siatki i checksum,
- niezmienne plansze, overlaye siatki i wycinki komórek poza wejściem,
- syntetyczne golden tests i raport działania na 12 aktualnych obrazach.

## Out of scope

- OCR numeru sekwencji — TASK-0056,
- klasyfikacja symboli, augmentacja i dane treningowe — M6,
- naprawianie brakującej planszy albo zmiana indeksów TASK-0054,
- obsługa innych wymiarów gry lub innego wariantu strony,
- zapis do PostgreSQL, jobs, panel i manual review UI,
- deklarowanie accuracy lub zaliczenia G5.3 bez niezależnych adnotacji.

## Assumptions

- Wariant D-053 ma planszę 3 × 5.
- Quad wejściowy ma kolejność top-left, top-right, bottom-right, bottom-left.
- Czerwony obrys nie jest treścią komórki; stały margines 5% daje wewnętrzny
  obszar 450 × 270 i komórki 90 × 90.
- Współrzędne i transformacja odnoszą się do znormalizowanego PNG z TASK-0053.

## Acceptance criteria

- [x] Syntetyczna plansza perspektywiczna zachowuje mapowanie 3 × 5 row-major.
- [x] Każda poprawna plansza daje RGB 500 × 300 i 15 RGB komórek 90 × 90.
- [x] Wynik zawiera źródłowy quad, macierz transformacji i geometrię siatki.
- [x] Brak kompletnego wyniku TASK-0054 daje jawne `needs_review`, bez wycinków.
- [x] Niepoprawny, zdegenerowany albo wychodzący poza obraz quad ma stabilny błąd.
- [x] Oryginał i znormalizowany obraz nie są modyfikowane.
- [x] Retry daje identyczny raport, checksumy i nie nadpisuje innej zawartości.
- [x] Wszystkie 12 aktualnych obrazów ma raport i komplet 108/1620 wycinków.
- [x] Brak twierdzenia o accuracy przed pełnymi golden annotations.
- [x] Przebieg jest lokalny i nie pobiera modeli ani danych.
- [x] Testy, formatowanie, Ruff, mypy i `pip check` przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/rectification.py`
- `services/worker/tests/test_board_cell_crops.py`
- `scripts/crop_m5_board_cells.py`
- `ai_docs/quality/m5-board-cell-crops-report.json`
- `package.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/crop_m5_board_cells.py `
  ai_docs\quality\m5-normalization-report.json `
  ai_docs\quality\m5-page-board-detection-report.json `
  --normalization-root artifacts\m5-normalization `
  --artifact-root artifacts\m5-board-crops `
  --output ai_docs\quality\m5-board-cell-crops-report.json
.venv\Scripts\python.exe -m pytest `
  services/worker/tests/test_board_cell_crops.py -q
.venv\Scripts\python.exe -m ruff check `
  services/worker/src/game_predictor_worker/images `
  services/worker/tests/test_board_cell_crops.py scripts/crop_m5_board_cells.py
.venv\Scripts\python.exe -m mypy `
  services/worker/src/game_predictor_worker/images scripts/crop_m5_board_cells.py
```

## Risks

- Quad oparty na czerwonej masce może zawierać błąd narożnika niewidoczny bez
  niezależnych golden annotations.
- Stały margines może wymagać konfiguracji dla innych obudów i gier po Q-016.
- JPEG źródłowy, moiré i refleksy ograniczają jakość pojedynczego wycinka mimo
  poprawnej geometrii.
- Duża liczba małych plików jest poprawna dla prototypu, ale M7 może wymagać
  innego cache/artifact store po pomiarach.

## Outcome

Zaimplementowano port `BoardCellCropper` i klasyczną implementację
`board-cell-crops-v1`. Każda kompletna plansza TASK-0054 jest niezależnie
mapowana przez `getPerspectiveTransform`/`warpPerspective` do RGB 500 × 300.
Po odcięciu jawnego marginesu 25 × 15 px wnętrze dzieli się bez resamplingu na
15 komórek RGB 90 × 90 w kolejności row-major.

Kontrakt zapisuje źródłowy quad, macierz transformacji, wymiary i margines
siatki, indeksy 0-based, ścieżki względne oraz SHA-256 każdej planszy, komórki
i overlayu. Niekompletny wynik upstream, zła kolejność, różne wymiary obrazu
oraz quad poza obrazem, niekonweksem lub zdegenerowany dają jawne
`needs_review` bez częściowych artefaktów.

Rzeczywisty przebieg na obecnym korpusie:

- 12/12 obrazów zakończyło się `cropped`, bez wyniku `needs_review`,
- zapisano 108 wyprostowanych plansz, 108 overlayów i 1620 komórek,
- 1836 niezmiennych plików zajmuje `56 325 183` bajty,
- raport ma `806 838` bajtów i SHA-256
  `01756c63ed3f8d6837193908cf0f03c8f4f243a2ead74fa2e9a3b3e5d7a55b4e`.

Ponowny przebieg `--check --require-cropped` odtworzył identyczny raport i
zweryfikował istniejące artefakty. Wizualnie sprawdzono overlaye z początku,
środka i końca korpusu; granice 3 × 5 odpowiadają widocznym symbolom.

Weryfikacja objęła 42 testy korpusu, discovery, normalizacji, detekcji i cropów,
Ruff, format Ruff, mypy oraz `pip check`. Nie zgłaszamy accuracy ani przejścia
G5.3: niezależne adnotacje narożników nadal nie są kompletne, a bieżący korpus
reprezentuje wyłącznie wariant D-053.
