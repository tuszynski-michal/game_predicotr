---
title: TASK-0166 reduced JPEG scan and bounded CPU budget
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0166 — Reduced JPEG scan and bounded CPU budget

## Status

`done`

## Goal

Dekodować roboczy obraz bezpośrednio w małej rozdzielczości i usunąć
zagnieżdżoną nadsubskrypcję CPU, zachowując kolejność, EXIF i wynik goldenów.

## Context

Obecny loader wykonuje pełne `image.load()` przed skalowaniem do 960 px, a
cztery zewnętrzne zadania konkurują z ośmioma wewnętrznymi wątkami OpenCV na
ośmiu logicznych procesorach. Jest to koszt infrastrukturalny niezależny od
algorytmu grupowania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0165-image-selection-stage-timing-and-real-corpus-baseline.md`

## Scope

- zastosować decoder-side JPEG reduction przed pełnym odczytem pikseli,
- porównać wersjonowane warianty dłuższego boku 384 i 480 px i wybrać
  najmniejszy przechodzący golden granic oraz jakości,
- zachować EXIF transpose i deterministyczną konwersję RGB,
- ustawić jeden wewnętrzny wątek OpenCV przy bounded zewnętrznym poolu,
- zmierzyć konfiguracje 1, 2 i 4 scan workers na tym samym profilu,
- zachować source-order consumption, checkpointy i retry bez zmian,
- potwierdzić, że kod uploadu oraz schema v2 stagingu nie zostały zmienione.

## Out of scope

- usunięcie geometrii lub OCR ze selektora,
- zmiana granic grup albo rankingu,
- GPU, nowa biblioteka CV lub nowy proces workera,
- pełny profil 32 079 zdjęć przed krótkim benchmarkiem.

## Acceptance criteria

- [x] JPEG nie jest najpierw dekodowany w pełnej rozdzielczości tylko po to,
      aby utworzyć miniaturę.
- [x] Orientacja, wymiary źródła i błędy uszkodzonego JPEG-a pozostają poprawne.
- [x] OpenCV nie tworzy własnego wielordzeniowego poolu pod każdym zewnętrznym
      scan workerem.
- [x] Runner obsługuje pomiar 1/2/4; końcowy wybór workerów na podstawie pomiaru
      jest jawnie przeniesiony do wspólnej bramki TASK-0171.
- [x] Golden ma zero nowych fałszywych scaleń i zero utraconych granic dla
      aktywowanego wariantu 960 px; warianty 384/480 zostały odrzucone.
- [x] Upload 1–100 000 JPEG-ów zachowuje dotychczasowy kontrakt i nie został
      zmieniony przez zadanie.

## Technical notes

Preferowane jest wykorzystanie obecnego Pillow/libjpeg-turbo (`draft()` przed
`load()`) albo równoważnego reduced decode OpenCV. Zmiana biblioteki jest
dopuszczalna dopiero, gdy oba warianty nie spełnią budżetu TASK-0165.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_image_selection_adapters.py`
- `services/worker/tests/test_image_selection_job.py`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_selection_adapters.py services/worker/tests/test_image_selection_job.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/selection services/worker/tests/test_image_selection_adapters.py
```

## Risks / open questions

- Zbyt mała miniatura może zacierać realną zmianę strony; rozmiar jest częścią
  wersjonowanego manifestu i musi przejść realny golden.

## Outcome

- Dodano adapter `pillow-jpeg-draft-thumbnail-v2`, który wywołuje JPEG
  decoder-side `draft()` przed `load()`, a następnie zachowuje EXIF transpose,
  wymiary źródła i deterministyczne RGB.
- Warianty 384 i 480 px porównano na prywatnym realnym goldenie. Oba pogorszyły
  granice, dlatego aktywny wariant zachowuje 960 px i korzysta wyłącznie z
  wcześniejszej redukcji dekodera.
- Historyczny fingerprint v8 `9dc754cca7e…` nadal rozwiązuje stary adapter;
  nowy manifest ma fingerprint `284eb7f842b6…`.
- Worker ustawia jeden wewnętrzny wątek OpenCV przed utworzeniem zewnętrznego
  poolu. Pomiar 1/2/4 i wybór produkcyjny odbędą się razem z profilami
  500–1000, 3000 i 40 000 zdjęć w TASK-0171, zgodnie z decyzją właściciela.
- Testy: `25 passed` dla adapterów i joba, `2 passed` dla CLI workera oraz
  `1 passed` dla kontraktu limitu uploadu 100 000 JPEG-ów; Ruff zakończony bez
  błędów. Kontrola
  mypy całego dużego modułu została przerwana po 60 sekundach bez wyniku zgodnie
  z regułą timeoutów; testy wykonawcze i lint pokrywają zmieniony pion.
- Kod uploadu oraz staging schema v2 nie zostały zmienione.
