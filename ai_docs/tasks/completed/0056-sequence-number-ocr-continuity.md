---
title: TASK-0056 Sequence number OCR and continuity validation
status: done
last_updated: 2026-07-28
---

# TASK-0056 — Sequence number OCR and continuity validation

## Status

`done`

## Goal

Zbudować wymienny, całkowicie lokalny adapter OCR cyfr, wyciąć numer pod każdą
z dziewięciu plansz i zapisać surowy wynik, wartość znormalizowaną, confidence
oraz niezależną walidację ciągłości bez cichego poprawiania OCR.

## Context

TASK-0054 dostarcza quady plansz, a `m5-golden-annotations.json` zawiera
niezależne etykiety numerów 1–108. Obecne 12 zdjęć reprezentuje jedną grę,
sesję i rozdzielczość. Progi w `m5-quality-thresholds.json` nadal mają status
`proposed`, dlatego zadanie tworzy i mierzy bazowy prototyp, ale nie optymalizuje
go pod ten sam korpus ani nie zalicza G5.4.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/quality/m5-corpus-manifest.json`
- `ai_docs/quality/m5-golden-annotations.json`
- `ai_docs/quality/m5-quality-thresholds.json`
- D-006, D-010, D-014 i D-049–D-055 w
  `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- port `SequenceNumberRecognizer` niezależny od runnera i systemu plików,
- kontrakt `sequence-number-ocr-v1`,
- crop numeru wyprowadzony z dolnej krawędzi każdego quada TASK-0054,
- wersjonowany preprocessing dla jasnych cyfr na ciemnym/niebieskim tle,
- oficjalny model `en_PP-OCRv5_mobile_rec` uruchamiany recognition-only przez
  PaddlePaddle CPU, bez pakietu PaddleOCR/PaddleX kolidującego z OpenCV/NumPy,
- jawny lokalny katalog modelu; brak pobierania wag przy przetwarzaniu,
- surowy tekst i confidence bez usuwania śladu odpowiedzi modelu,
- znormalizowana liczba tylko dla pełnego wyniku złożonego z cyfr,
- walidacja dziewięciu pozycji na zdjęciu i ciągłości między zdjęciami,
- konflikt, luka, duplikat i nierozpoznany numer jako jawne powody review,
- raport exact accuracy względem istniejących adnotacji, bez ukrywania błędów,
- content-addressed cropy i diagnostyka poza katalogiem źródłowym.

## Out of scope

- ciche zastępowanie OCR wartością wynikającą z sąsiednich pozycji,
- trening/fine-tuning OCR na obecnych 12 zdjęciach,
- uznanie proponowanego progu 98% za zaakceptowany,
- klasyfikacja symboli i dataset treningowy — M6,
- zapis do PostgreSQL, jobs, panel i manual review UI,
- obsługa innych wariantów strony przed Q-016.

## Assumptions

- Numery znajdują się bezpośrednio pod odpowiadającą planszą.
- Numer jest pojedynczym wierszem cyfr 1–108.
- Model i runtime są instalowane/przygotowywane wcześniej; właściwy przebieg
  korpusu nie wykonuje żadnego żądania sieciowego.
- Etykiety sekwencji są ground truth dla metryki OCR, ale nie dla geometrii.

## Acceptance criteria

- [x] Każda plansza ma deterministyczny crop numeru i diagnostyczny obraz.
- [x] Adapter przechowuje raw text, normalized number i confidence.
- [x] Wynik niebędący pełnym ciągiem cyfr pozostaje nierozpoznany.
- [x] Ciągłość flaguje konflikt/lukę/duplikat, ale nie zmienia raw ani normalized.
- [x] Brak lokalnego modelu ma stabilny błąd i nie uruchamia pobierania.
- [x] Retry daje identyczny raport, checksumy i artefakty.
- [x] Raport obejmuje wszystkie 108 pozycji i osobną exact accuracy.
- [x] Przebieg jest lokalny; model i jego checksum są jawne.
- [x] Brak deklaracji przejścia G5.4 przy progu `proposed`.
- [x] Testy, formatowanie, Ruff, mypy i `pip check` przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/sequence_ocr.py`
- `services/worker/tests/test_sequence_number_ocr.py`
- `scripts/run_m5_sequence_ocr.py`
- `ai_docs/quality/m5-sequence-ocr-report.json`
- `package.json`
- `pyproject.toml`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/run_m5_sequence_ocr.py `
  ai_docs\quality\m5-corpus-manifest.json `
  ai_docs\quality\m5-golden-annotations.json `
  ai_docs\quality\m5-normalization-report.json `
  ai_docs\quality\m5-page-board-detection-report.json `
  --normalization-root artifacts\m5-normalization `
  --model-root artifacts\m5-models\sequence-number-ocr-v1 `
  --artifact-root artifacts\m5-sequence-ocr `
  --output ai_docs\quality\m5-sequence-ocr-report.json
.venv\Scripts\python.exe -m pytest `
  services/worker/tests/test_sequence_number_ocr.py -q
```

## Risks

- Numery są małe, rozmyte i objęte moiré; baseline może nie osiągnąć
  proponowanego progu.
- Crop oparty na quadzie planszy może wymagać wariantu dla innych ekranów.
- PaddlePaddle jest dużą zależnością; benchmark M5.5 musi uwzględnić czas
  startu i rozmiar lokalnego modelu.
- Strojenie geometrii lub preprocessingu na tych samych 12 zdjęciach
  zawyżyłoby wynik.

## Outcome

Dodano kontrakt `sequence-number-ocr-v1`, port `SequenceNumberRecognizer`,
deterministyczne cropy 192 × 64, preprocessing
`bright-component-tight-v1`, bezpośredni lokalny adapter PaddlePaddle CPU oraz
niekorygującą walidację ciągłości. Model `en_PP-OCRv5_mobile_rec` jest
identyfikowany checksumami trzech plików i nie jest pobierany podczas przebiegu.

Pełny korpus objął 108 pozycji: exact `68/108 = 62.9630%`, `58` wyników
wymaga review, a `51` ma konflikt ciągłości. Raport
`m5-sequence-ocr-report.json` ma SHA-256
`bae6f8129115e45d4085ac75d8990d6ef06691db8847153e71afee69e7247d0b`;
retry `--check --require-complete` był identyczny. Baseline nie osiąga
proponowanego progu 98%, więc G5.4 pozostaje otwarta i przechodzi do analizy w
TASK-0057, bez strojenia na tym samym 12-zdjęciowym korpusie.

Weryfikacja: 10 testów TASK-0056, 47 testów całego pionu obrazów, Ruff, mypy,
`pip check`, deterministyczny CLI check i wizualna kontrola reprezentatywnych
cropów.
