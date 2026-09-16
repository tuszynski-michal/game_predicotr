---
title: TASK-0402 — Rzeczywisty korpus regresyjny OCR zakresów
status: done
created: 2026-09-02
---

# TASK-0402 — Rzeczywisty korpus regresyjny OCR zakresów

## Goal

Utrwalić checksum-bound korpus prawdziwych zdjęć oraz runner, który mierzy pełny łańcuch lokalizacji i Paddle OCR bez czerpania dowodu z nazw plików lub UI Admina.

## Context

Obecne testy wariantów v2–v5 w dużej części podstawiają cyfry do sztucznych cropów. Nie wykrywają więc błędu lokalizatora, preprocessingu lub Paddle OCR widocznego na rzeczywistych ekranach. Użytkownik dostarczył trzy czytelne przykłady oraz klatkę przejściową, która nigdy nie może zostać zaliczona jako poprawny zakres.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Dodać cztery zanonimizowane fixture’y JPEG bez dolnego panelu Admina i tekstu `seq_*`.
- Dodać manifest z checksumami, neutralnymi nazwami i etykietami człowieka: `28–36`, `55–63`, `64–72`, `transition`.
- Dodać testy integralności fixture’ów oraz ochronę przed ponownym użyciem nazwy pliku jako dowodu.
- Dodać read-only runner rzeczywistego łańcucha lokalizator → preprocessing → Paddle OCR dla historycznych wariantów v2, v3, v4.1 i v5.
- Zapisać raport diagnostyczny bazowego zachowania bez zmiany rolloutów ani progów.

## Out of scope

- Zmiana wariantów v1–v5, fingerprintów, progów lub produkcyjnego wyboru runtime'u.
- Zmiana API, OpenAPI, bazy, jobów, stagingu albo automatyczne uruchamianie OCR na danych użytkownika.
- Włączenie nowego wariantu v6.

## Acceptance criteria

- [x] Korpus jest checksum-bound i ma neutralne nazwy niekodujące zakresu.
- [x] Trzy czytelne zdjęcia mają jawne oczekiwane zakresy; klatka przejściowa ma status inny niż `exact`.
- [x] Test nie może przejść po zmianie JPEG-a lub użyciu nazwy pliku jako źródła zakresu.
- [x] Runner wywołuje rzeczywiste lokalizatory i Paddle OCR; nie uruchamia geometrii, croppera ani inferencji symboli.
- [x] Raport bazowy rozróżnia wynik każdego historycznego wariantu i reason codes.

## Technical notes

- Dolny panel oraz nazwa `seq_*` są redagowane przy przygotowaniu fixture’ów, z zachowaniem geometrii obrazu dla lokalizatorów.
- Zdjęcie przejściowe ma zostać opisane jako `transition`, nigdy jako poprawny zakres. Nie stanowi ono negatywnego przykładu pojedynczej liczby OCR, lecz kontrakt anty-false-positive.
- To zadanie nie zmienia modelu domenowego; następny task `TASK-0403` wprowadzi wspólny extractor v6.

## Expected files

- `services/worker/tests/fixtures/range_ocr_real_v6/*`
- `services/worker/tests/test_range_ocr_real_regression_corpus.py`
- `scripts/run_range_ocr_real_regression_corpus.py`
- `ai_docs/quality/RANGE_OCR_REAL_REGRESSION_CORPUS_V1.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_range_ocr_real_regression_corpus.py -q
.venv\Scripts\python.exe scripts/run_range_ocr_real_regression_corpus.py --report artifacts/quality/range-ocr-real-regression-v1.json
.venv\Scripts\python.exe -m ruff check services/worker/tests/test_range_ocr_real_regression_corpus.py scripts/run_range_ocr_real_regression_corpus.py
```

## Risks / open questions

- Korpus czterech zdjęć jest bramką regresji, nie miarą globalnego recall. Nie wystarcza do aktywacji nowego runtime'u.
- Runner wymaga lokalnego modelu Paddle OCR; jego brak jest kontrolowaną awarią narzędzia diagnostycznego, nie pominięciem testu jakości.

## Outcome

### Changed

- Dodano cztery redagowane, neutralnie nazwane fixture'y JPEG i manifest
  checksummowany SHA-256: trzy samodzielnie czytelne zakresy oraz klatkę
  przejściową.
- Dodano testy integralności, neutralności nazwy, etykiet człowieka i masek
  redakcyjnych.
- Dodano read-only runner faktycznej ścieżki lokalizator → preprocessing →
  Paddle OCR dla v2, v3, v4.1 i v5. Runner nie tworzy jobów, stagingu,
  outputów, geometrii, cropów ani inferencji symboli.
- Utrwalono wymaganie, architekturę, decyzję D-303 i raport jakości.

### Verification

- `pytest services/worker/tests/test_range_ocr_real_regression_corpus.py -q`:
  3 passed.
- Focused regression tests korpusu oraz v2/v3/v4.1/v5: 34 passed.
- Ruff dla nowego testu i runnera: passed.
- Realny, read-only audit z lokalnym Paddle:
  - v2/v3: `RANGE_LABEL_LATTICE_INCOMPLETE`;
  - v4.1: `UNKNOWN_LATTICE`;
  - v5: `COMPLETE_ROW_UNVERIFIED`;
  - żaden wariant nie zwrócił `exact` dla trzech czytelnych fixture'ów, a
    klatka przejściowa pozostała nieautomatyczna.

### Not changed

- Nie zmieniono v1–v5, ich fingerprintów, endpointów, jobów, stagingu,
  feature flag ani danych użytkownika.

### Next task

`TASK-0403` może dodać nowy, odrębnie fingerprintowany extractor i musi
zachować brak automatycznego wyniku dla klatki przejściowej.
