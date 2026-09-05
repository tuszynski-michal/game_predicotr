---
title: TASK-0358 — Bezpieczny szeroki OCR zakresów v2
status: done
last_updated: 2026-08-31
---

# TASK-0358 — Bezpieczny szeroki OCR zakresów v2

## Goal

Naprawić odrzucanie małych, prawidłowych etykiet zakresu przez osobny,
wersjonowany adapter `semi-automatic-range-only-ocr-v2`, bez uruchamiania
geometrii plansz, croppera komórek ani klasyfikatora symboli.

## Context

Odbiór TASK-0357 potwierdził, że Paddle OCR potrafi odczytać cyfry, lecz
historyczny filtr v1 wymaga etykiety o szerokości co najmniej 5,5% obrazu i
aspect ratio co najmniej 2,4. Rzeczywiste etykiety mają zwykle 3–6% szerokości
i aspect ratio 1,3–1,9. Dodatkowo v1 sprawdza najwyżej 12 kandydatów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0357-semi-automatic-selection-rollout.md`

## Scope

- osobny adapter i proof policy v2;
- dedykowany filtr etykiet: X `0.20–0.82`, Y `0.24–0.48`, minimalna
  szerokość `0.025`, minimalny aspect ratio `1.20`;
- progresywne poziomy `12/24/36`, bez ponownego OCR wcześniejszych cropów;
- niezmieniona końcowa bramka minimum trzech zgodnych pozycji i pary
  sąsiadującej przy confidence co najmniej `0.90`;
- jawne wersjonowanie v1/v2 i wybór adaptera z fingerprintu runu;
- skoncentrowane testy i dokumentacja.

## Out of scope

- zmiana geometrii, croppera, symbol inference lub grupowania;
- oczekiwany zakres wywnioskowany z kursora albo sąsiednich zdjęć;
- migracja bazy lub zmiana OpenAPI;
- domyślne włączenie feature flagi;
- odbiór 100 zdjęć należący do TASK-0357.

## Acceptance criteria

- [x] Historyczny fingerprint i builder v1 pozostają niezmienne.
- [x] Nowe runy otrzymują fingerprint v2 obejmujący progi i poziomy.
- [x] Worker wznawia v1 przez v1, v2 przez v2, a nieznaną wersję odrzuca.
- [x] V2 OCR-uje progresywnie najwyżej 36 kandydatów, partiami do 9.
- [x] Jedna, dwie, sprzeczne lub słabe etykiety pozostają luką.
- [x] Testy potwierdzają brak zależności od geometrii, croppera i symboli.
- [x] Flaga rolloutowa pozostaje domyślnie wyłączona.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/range_only_ocr.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/job.py`
- `services/worker/tests/test_semi_automatic_selection_range_only_ocr.py`
- `services/worker/tests/test_semi_automatic_selection_job.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_semi_automatic_selection_range_only_ocr.py services/worker/tests/test_semi_automatic_selection_job.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_semi_automatic_selection_range_only_ocr.py services/worker/tests/test_semi_automatic_selection_job.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
```

## Outcome

### Changed

- Dodano niezmienny builder v1 i nowy v2 z dedykowanym filtrem oraz progresją
  `12/24/36`.
- Worker wybiera builder z fingerprintu utrwalonego runu; nieznany kontrakt
  kończy się stabilnym błędem.
- Narzędzie odbioru raportuje poziomy, liczbę cropów, batche, overlap i bramkę
  minimum 50% bez fałszywych przypisań.

### Verification results

- Skoncentrowany zestaw domeny, joba, acceptance i API: `54 passed`.
- Ruff: bez błędów.
- Mypy dla zmienionych modułów: bez błędów.
- Rzeczywista próba 10: `7/10` exact, `0` false assignments, `0`
  overlap, `2` nieczytelne i `1` bez wystarczającego proof; geometria,
  cropper i symbol inference: po `0` wywołań. Manifest źródeł:
  `299f79e584d301c0d0923281433e5fbb36e0cf6c935fa8dc2806a06dce3e8e27`.
- Feature flag pozostała domyślnie wyłączona.

### Remaining

- Odbiór 100 oraz końcowy raport należą do wznowionego TASK-0357.
