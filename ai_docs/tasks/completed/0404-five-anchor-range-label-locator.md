---
title: TASK-0404 — Lokalizator pięciu etykiet zakresu
status: done
created: 2026-09-02
---

# TASK-0404 — Lokalizator pięciu etykiet zakresu

## Goal

Zbudować odrębny, czysty lokalizator v6 pięciu widocznych etykiet numerów
plansz: lewy górny róg, prawy górny róg, środek, lewy dolny róg i prawy dolny
róg. Komponent ma dostarczyć pełne, source-direct cropy do późniejszego OCR
zarówno półautomatu, jak i weryfikacji nazw plików.

## Context

Rzeczywisty korpus TASK-0402 pokazał, że historyczne lokalizatory v2–v5
odrzucają czytelne ekrany przed albo po rozpoznaniu etykiet. V4.1 zakłada jeden
środkowy wiersz, a v5 wymaga dwóch kompletnych wierszy; oba założenia nie
odpowiadają operatorowi, który odczytuje pięć rozproszonych numerów bez
trudności.

Numeracja taska 0403 została wykorzystana przez pilną, niezależną naprawę
lokalnego recovery. Ten pion kontynuuje plan OCR jako TASK-0404.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0402-real-range-ocr-regression-corpus.md`

## Scope

- Dodać wersjonowany, deterministyczny komponent
  `five-anchor-range-label-locator-v6`.
- Po jednokrotnej kanonizacji EXIF znajdować wyłącznie położenia pięciu cropów
  etykiet: `top_left`, `top_right`, `center`, `bottom_left`, `bottom_right`.
- Stosować lekką detekcję lokalnych komponentów tekstu i dopuszczać szeroki,
  geometryczny fallback viewportu; oba tryby muszą być jawne w diagnostyce i
  fingerprintcie.
- Cropy mają pochodzić bezpośrednio z kanonizowanego źródła, zawierać metadane
  kompletności i bezwzględne współrzędne oraz nie przechowywać bitmap.
- Dodać testy czystej lokalizacji: pięć anchorów, projektowa perturbacja,
  brak/niejednoznaczność komponentów i brak dostępu do nazw plików albo
  expected range.
- Dodać testy regresji wykorzystujące korpus TASK-0402 wyłącznie jako
  checksummowany input lokalizatora. Nie wymagać w tym tasku wyniku OCR ani
  automatycznego range proofu.
- Udokumentować wyłącznie kontrakt lokalizatora i jego ograniczenia.

## Out of scope

- Paddle OCR, parsowanie cyfr, dopasowanie do expected range, grupowanie,
  wybór reprezentanta, job, staging, API, UI i feature flag.
- Zmiana historycznych v1–v5, ich fingerprintów, checkpointów lub runtime'u.
- Board detection, geometria strony/planszy, cropper plansz i symbol inference.

## Invariants

- Lokalizator przyjmuje tylko kanonizowany RGB i nie zna nazwy pliku, katalogu,
  indeksu źródła, zakresu oczekiwanego ani wyniku sąsiedniego zdjęcia.
- Pięć anchorów jest wyłącznie lokalizacją cropów, nie dowodem zakresu.
- Brak pełnego, jednoznacznego anchoru jest reason-coded wynikiem `unknown`,
  nigdy interpolacją numeru.
- Współrzędne cropów należą do przestrzeni
  `exif-transposed-rgb-v1`; EXIF jest wykonywany dokładnie raz przed wejściem.
- Komponent nie importuje modułów geometrii plansz, detekcji, croppera ani
  klasyfikatora symboli.

## Acceptance criteria

- [x] Każdy udany wynik zawiera dokładnie pięć nazwanych, source-direct cropów.
- [x] Wynik nieudany jest reason-coded i nie zwraca częściowego dowodu jako
  sukcesu.
- [x] Kontrakt jest fingerprintowany oraz niezależny od runtime'ów v1–v5.
- [x] Fixture'y rzeczywistych ekranów przechodzą przez lokalizator bez używania
  human label albo nazwy pliku.
- [x] Testy potwierdzają brak importu ciężkich etapów i brak zapisu plików.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_five_anchor_range_label_locator.py services/worker/tests/test_range_ocr_real_regression_corpus.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_five_anchor_range_label_locator.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
```

## Outcome

Ukończono 2026-09-02. Dodano czysty, fingerprintowany lokalizator v6 pięciu
source-direct kandydatów etykiet wraz z diagnostyką `component_refined` /
`viewport_fallback`. Nie jest on podłączony do OCR, joba, grupowania ani
feature flagi, dlatego nie zmienia runtime'ów i fingerprintów v1–v5.

Testy potwierdzają stabilny porządek pięciu anchorów, ograniczenie cropów po
perturbacji projektowej, reason-coded błędy wejścia, regresję na czterech
checksummowanych ekranach bez odczytu ich human label oraz brak importu ciężkich
etapów i zapisu plików.
