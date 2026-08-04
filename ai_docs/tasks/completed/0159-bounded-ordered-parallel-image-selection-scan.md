---
title: TASK-0159 bounded ordered parallel image selection scan
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0159 — Bounded ordered parallel image-selection scan

## Status

`done`

## Goal

Wykorzystać kilka rdzeni CPU do taniego skanu JPEG bez zmiany naturalnej
kolejności grup, wyniku selektora, fingerprintu manifestu ani granic retry.

## Context

Rzeczywisty run 32 079 uporządkowanych zdjęć używał praktycznie jednego rdzenia.
W 20-sekundowym pomiarze przetworzył 96 plików, czyli około 5,1 pliku/s, przy
stabilnej pamięci i zerze błędów. Upload nie jest już wąskim gardłem; koszt
stanowią odczyt JPEG, miniatura, OpenCV lattice/fingerprint i metryki jakości.
Zdjęcia tego samego ekranu będą dostarczane obok siebie, dlatego wyniki mogą być
liczone z wyprzedzeniem, ale muszą zostać skonsumowane dokładnie według
`order_index`.

Bieżący worker nie obserwuje zmian plików. Implementacja nie przerywa ani nie
modyfikuje działającego runu; zacznie obowiązywać dopiero po restarcie workera.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`

## Scope

- dodać bounded pulę dla wyłącznie taniego `CheapImageAnalyzer`,
- domyślnie użyć czterech wątków i najwyżej ośmiu zleconych obserwacji w
  produkcyjnym workerze,
- konsumować futures w naturalnej kolejności źródeł,
- zachować sekwencyjne grupowanie, top-k verification, OCR i zapis checkpointu,
- po cancel/crash dopuścić ponowną analizę wyłącznie bounded niezatwierdzonego
  prefetchu,
- zachować tryb jednowątkowy dla testów, diagnostyki i bezpiecznego fallbacku,
- opisać pomiar przed zmianą oraz wymagany benchmark kolejnego realnego runu.

## Out of scope

- wiele równoległych ciężkich jobów lub zmiana `execution_slot = 1`,
- równoległe wywołania PaddleOCR albo publikacji outputu,
- zmiana progów, rankingu, grupowania lub selector fingerprintu,
- restart albo ponowne uruchomienie obecnego joba 32 079 zdjęć,
- obietnica konkretnego przyspieszenia bez pomiaru po wdrożeniu.

## Acceptance criteria

- [x] Co najmniej dwa tanie skany mogą być aktywne równocześnie.
- [x] Audit sink zawsze otrzymuje obserwacje w rosnącym `order_index`.
- [x] Wynik równoległy jest bajtowo równoważny wynikowi jednowątkowemu.
- [x] Liczba zleconych, jeszcze nieskonsumowanych skanów jest bounded.
- [x] Checkpoint, cancel i retry nie pomijają żadnego źródła.
- [x] Produkcyjny worker używa `workers = 4`, `prefetch = 8`; testy mogą wymusić
  `workers = 1`.
- [x] V2, v3 i v4 pozostają wznawialne po dotychczasowych fingerprintach.
- [x] Krótkie testy nie zatrzymują ani znacząco nie obciążają bieżącego joba.

## Technical notes

Równoległość jest wyłącznie strategią wykonania. `Future` są pobierane w
kolejności źródeł, dlatego state machine nadal widzi identyczny strumień.
Prefetch nie jest częścią checkpointu; po awarii najwyżej osiem rozpoczętych,
ale niezatwierdzonych obserwacji może zostać policzonych ponownie.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_job.py`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/selection services/worker/tests/test_fast_image_selector.py services/worker/tests/test_image_selection_job.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/selection services/worker/src/game_predictor_worker/cli.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_fast_image_selector.py services/worker/tests/test_image_selection_job.py -q
```

## Risks / open questions

- OpenCV/Pillow muszą pozostać bezstanowe dla taniego skanu; OCR nie trafia do
  puli.
- Realny speedup zależy od dekodowania JPEG, dysku i throttlingu CPU; potwierdzi
  go dopiero kolejny run po restarcie workera.

## Outcome

### Changed

- `FastImageSelector` ma walidowany tryb `scan_workers`/`scan_prefetch` i
  konsumuje futures w kolejności wejścia.
- Produkcyjny CLI oraz standalone selector używają `4/8`; domyślny konstruktor
  pozostaje jednowątkowy dla testów i fallbacku.
- Worker został oznaczony `worker-v7`; selector manifest i fingerprint v4 nie
  zmieniły się, ponieważ wynik domenowy pozostaje identyczny.

### Verification results

- Ruff dla zmienionego workera i testów: pass.
- 50 skupionych testów selektora, trwałego joba i adapterów/standalone CLI:
  pass.
- MyPy dla zmienionego silnika i kontraktu: pass. Szerszy, skupiony odczyt
  `job.py`/CLI pozostaje ograniczony przez istniejące środowisko `.venv`, które
  nie ma `services/api/src` na `sys.path`; testy importujące oba pakiety
  przechodzą.
- Test wymusza faktyczną współbieżność, zakończenie poza kolejnością, ordered
  audit oraz identyczny wynik jak tryb sekwencyjny.
- Bieżący worker-v6 po testach nadal miał status `processing`, etap
  `image_selection:scanning`, postęp `15456/32079` i zero błędów.

### Not completed

- Nie restartowano bieżącego workera i nie uruchamiano długiego benchmarku na
  katalogu właściciela. Realny throughput worker-v7 zostanie zmierzony w
  kolejnym runie.

### Documentation updates

- Zaktualizowano wymagania, architekturę, Current State i D-139.

### Recommended next task

- Pozwolić bieżącemu worker-v6 zakończyć run, następnie zrestartować worker i
  porównać rolling throughput worker-v7 na kolejnym uporządkowanym katalogu.
