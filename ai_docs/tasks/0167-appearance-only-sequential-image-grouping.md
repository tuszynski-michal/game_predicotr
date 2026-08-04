---
title: TASK-0167 appearance-only sequential image grouping
status: todo
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0167 — Appearance-only sequential image grouping

## Status

`todo`

## Goal

Wprowadzić nową wersję selektora, która grupuje kolejne ujęcia wyłącznie na
podstawie lekkiego wyglądu ekranu, bez geometrii plansz i bez OCR.

## Context

Dokładna geometria i numery sekwencji są potrzebne dopiero w `Imporcie
layoutów`. Uruchamianie detektora plansz dla wszystkich 32 079 zdjęć fragmentuje
grupy przy zmianie kąta i zwiększa czas zamiast pomagać szybkiemu wyborowi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0166-reduced-jpeg-scan-and-bounded-cpu-budget.md`

## Scope

- dodać wersjonowany `fast-image-selector-v9` z lekkim deskryptorem wyglądu,
- zbudować deskryptor z niskoczęstotliwościowego perceptual hash, histogramu
  HSV i uproszczonego edge signature obszaru ekranu,
- porównywać obserwację z bezpośrednim poprzednikiem i bounded centroidem
  bieżącej grupy, aby tolerować płynną zmianę kąta i ekspozycji,
- otwierać granicę dopiero po dwóch kolejnych zgodnych obserwacjach zmiany,
- traktować pojedynczą różną klatkę jako przejście, refleks albo zasłonięcie,
- nie przewidywać następnego numeru ani długości serii,
- zachować deterministyczny naturalny `order_index` i bounded pamięć,
- zapisać deskryptor i progi w selector fingerprint.

## Out of scope

- OCR numerów, wykrywanie czerwonych ramek, homografia i cropy,
- identyfikowanie zakresu `1–9` lub późniejszych duplikatów po numerach,
- pełny ranking reprezentanta,
- adaptacyjne pomijanie plików skokami przed zaliczeniem liniowej wersji v9.

## Acceptance criteria

- [ ] Produkcyjny lekki skan wykonuje zero wywołań `PageBoardDetector` i zero
      wywołań `SequenceNumberRecognizer`.
- [ ] Stopniowa zmiana kąta tego samego ekranu nie tworzy krótkich grup.
- [ ] Nagła zmiana strony po potwierdzeniu tworzy nową grupę.
- [ ] Pojedyncza klatka przejściowa nie tworzy osobnej grupy.
- [ ] Golden ma zero fałszywych scaleń dwóch różnych kolejnych ekranów.
- [ ] Algorytm nie używa oczekiwanego numeru ani założenia 50–100 zdjęć.
- [ ] Stan checkpointu pozostaje bounded niezależnie od liczby wejść.

## Technical notes

Priorytetem jest recall różnych ekranów: dodatkowa fałszywa grupa zwiększa
wejście `Importu layoutów`, ale fałszywe scalenie może bezpowrotnie pominąć
unikalną stronę. Progi muszą być kalibrowane na realnych sekwencjach, nie na
pojedynczych wybranych zdjęciach.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_adapters.py`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_fast_image_selector.py services/worker/tests/test_image_selection_adapters.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/selection services/worker/tests/test_fast_image_selector.py
```

## Risks / open questions

- Stały crop ekranu może być zbyt wrażliwy na różne kadry. Deskryptor powinien
  składać się z kilku szerokich regionów i ignorować niewielki margines, bez
  wprowadzania pełnej detekcji geometrii.

## Outcome

Do uzupełnienia po realizacji.

