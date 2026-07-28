---
title: TASK-0054 Page and 3x3 board detection
status: done
last_updated: 2026-07-28
---

# TASK-0054 — Page and 3x3 board detection

## Status

`done`

## Goal

Zbudować wymienny, deterministyczny prototyp klasycznej geometrii, który na
znormalizowanym obrazie wykrywa obszar strony oraz dokładnie dziewięć plansz
w kolejności row-major albo zwraca jawny wynik wymagający review.

## Context

TASK-0052/TASK-0053 dostarczają zweryfikowane źródła i RGB PNG bez EXIF.
Obecny korpus obejmuje jeden potwierdzony wariant ekranu: 9 plansz 3 × 5
w siatce 3 × 3, czerwone ramki i niebieskie tło. Q-016 nie potwierdza jeszcze
innych gier i wariantów. Na jawne polecenie właściciela D-053 dopuszcza
TASK-0054 wyłącznie dla obecnego wariantu; inne układy muszą zostać odrzucone,
a nie dopasowane na siłę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/quality/m5-quality-thresholds.json`
- D-006, D-010, D-014 i D-049–D-053 w
  `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- przypięcie dojrzałej linii OpenCV 4.13 i NumPy 2.4 zamiast świeżego major 5,
- port `PageBoardDetector` niezależny od CLI i systemu plików,
- kontrakt `page-board-detector-v1`,
- detekcja czerwonych ramek w HSV z operacjami morfologicznymi,
- filtrowanie kandydatów według pola, proporcji i położenia,
- wybór dziewięciu plansz oraz walidacja regularności siatki 3 × 3,
- stabilna kolejność row-major i indeksy 0–8,
- narożniki plansz i strony w pikselach znormalizowanego obrazu,
- confidence o jawnych składnikach, bez progu uczonego na tym samym wyniku,
- wynik `detected` albo `needs_review` ze stabilnymi powodami,
- wersjonowane overlaye diagnostyczne poza katalogiem źródłowym,
- syntetyczne golden tests i raport działania na 12 aktualnych obrazach.

## Out of scope

- obsługa innej liczby plansz lub innego układu strony,
- indywidualne prostowanie plansz i podział na komórki — TASK-0055,
- OCR numerów — TASK-0056,
- automatyczne poprawianie brakującej planszy z oczekiwanej pozycji,
- ciężki detektor obiektów, trening, YOLO albo VLM,
- zapis do PostgreSQL, jobs, panel i manual review UI,
- deklarowanie przejścia progów z M5.1 bez niezależnych golden annotations.

## Assumptions

- Jedynym wspieranym wariantem v1 jest dokładnie 3 × 3 plansz.
- Kolor czerwonej ramki jest cechą kandydującą, nie gwarancją wyniku.
- Strona jest wyprowadzana z obwiedni dziewięciu zaakceptowanych plansz
  z kontrolowanym marginesem; brak dziewięciu wiarygodnych plansz oznacza
  `needs_review`.
- Współrzędne dotyczą znormalizowanego PNG z TASK-0053.

## Acceptance criteria

- [x] Syntetyczna siatka perspektywiczna daje dziewięć plansz row-major.
- [x] Brak, nadmiar i nieregularna siatka dają `needs_review`, nie ciche indeksy.
- [x] Wynik każdej planszy zawiera indeks 0–8 i cztery narożniki w obrazie.
- [x] Confidence oraz powody review są deterministyczne i jawne.
- [x] Overlay nie modyfikuje znormalizowanego obrazu.
- [x] Ponowny przebieg daje ten sam raport i checksumy diagnostyki.
- [x] Wszystkie 12 aktualnych obrazów ma raport; przypadki niepewne są jawne.
- [x] Brak twierdzenia o accuracy przed pełnymi golden annotations.
- [x] Przebieg jest lokalny i nie pobiera modeli ani danych.
- [x] Testy, formatowanie, Ruff, mypy i `pip check` przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/geometry.py`
- `services/worker/tests/test_page_board_detection.py`
- `scripts/detect_m5_boards.py`
- `ai_docs/quality/m5-page-board-detection-report.json`
- `pyproject.toml`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/detect_m5_boards.py `
  ai_docs\quality\m5-normalization-report.json `
  --normalization-root artifacts\m5-normalization `
  --artifact-root artifacts\m5-page-detection `
  --output ai_docs\quality\m5-page-board-detection-report.json
.venv\Scripts\python.exe -m pytest `
  services/worker/tests/test_page_board_detection.py -q
.venv\Scripts\python.exe -m ruff check `
  services/worker/src/game_predictor_worker/images `
  services/worker/tests/test_page_board_detection.py scripts/detect_m5_boards.py
.venv\Scripts\python.exe -m mypy `
  services/worker/src/game_predictor_worker/images scripts/detect_m5_boards.py
```

## Risks

- Czerwone symbole wewnątrz plansz i czerwone elementy obudowy mogą tworzyć
  fałszywe kontury.
- Perspektywa, krzywizna ekranu i zasłonięcie dłoni zmieniają proporcje ramek.
- Brak niezależnych narożników golden blokuje uczciwe policzenie accuracy i
  przejście progu geometrii; raport bieżący jest diagnostyką, nie benchmarkiem.
- Inna gra może wymagać wariantu konfiguracji lub innego detektora po Q-016.

## Outcome

Zaimplementowano wymienny port `PageBoardDetector` i klasyczną implementację
`page-board-detector-v1`. Detektor pracuje na znormalizowanym RGB, buduje maskę
czerwieni w HSV, filtruje kontury, ustala siatkę 3 × 3, waliduje jej geometrię
i zwraca dokładnie dziewięć plansz row-major albo jawne `needs_review`.
Kontrolowana korekta pojedynczego kandydata względem median wiersza i kolumny
jest zapisywana w wyniku jako `refinedFromGrid`; nie tworzy brakującej planszy.

Rzeczywisty przebieg na obecnym korpusie:

- 12/12 obrazów zakończyło się `detected`, bez wyniku `needs_review`,
- zapisano 108 plansz, z czego 9 kandydatów miało jawną korektę siatki,
- confidence obrazu: minimum `0.597210`, średnia `0.682863`, maksimum `0.747265`,
- powstało 12 niezmiennych overlayów o łącznym rozmiarze `15 711 444` bajtów,
- SHA-256 raportu:
  `2e12e180a8d0f27704e1973f04632937c7a71b113185fa161e2a47b0d22741ca`.

Overlaye całego korpusu i przypadek o najniższym confidence sprawdzono wizualnie;
ramki odpowiadają dziewięciu widocznym planszom. Ponowny przebieg w trybie
`--check --require-detected` odtworzył identyczny raport.

Weryfikacja objęła 32 testy discovery, normalizacji i geometrii, Ruff, format
Ruff, mypy oraz `pip check`. Nie zgłaszamy accuracy ani przejścia G5.3:
adnotacje narożników niezależne od algorytmu nadal nie są kompletne, a obecny
korpus reprezentuje tylko wariant objęty D-053.
