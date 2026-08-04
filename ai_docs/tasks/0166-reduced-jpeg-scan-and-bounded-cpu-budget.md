---
title: TASK-0166 reduced JPEG scan and bounded CPU budget
status: todo
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0166 — Reduced JPEG scan and bounded CPU budget

## Status

`todo`

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

- [ ] JPEG nie jest najpierw dekodowany w pełnej rozdzielczości tylko po to,
      aby utworzyć miniaturę.
- [ ] Orientacja, wymiary źródła i błędy uszkodzonego JPEG-a pozostają poprawne.
- [ ] OpenCV nie tworzy własnego wielordzeniowego poolu pod każdym zewnętrznym
      scan workerem.
- [ ] Wybrana liczba workerów wynika z pomiaru, a nie ze stałej bez dowodu.
- [ ] Golden ma zero nowych fałszywych scaleń i zero utraconych granic.
- [ ] Upload 1–100 000 JPEG-ów zachowuje dotychczasowy kontrakt i testy.

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

Do uzupełnienia po realizacji.
