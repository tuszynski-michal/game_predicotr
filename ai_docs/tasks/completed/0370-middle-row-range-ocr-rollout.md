---
title: TASK-0370 — Odbiór jakościowy i wydajnościowy OCR v4.1
status: done
release: "0.10"
last_updated: 2026-09-01
---

# TASK-0370 — Odbiór jakościowy i wydajnościowy OCR v4.1

## Status

`done`

## Goal

Zweryfikować wariant `semi-automatic-range-only-ocr-v4-middle-row-triple-v2`
na checksum-bound tuning, golden i challenge setach oraz na dwóch rzeczywistych
próbach po 1000 źródeł, bez osłabienia exact proof i bez automatycznego
włączenia rolloutu.

## Context

TASK-0368 dostarczył locator i exact proof, a TASK-0369 recognition-only Paddle,
batch 6, orientację, grouping i recovery. Rzeczywisty katalog
`E:\blazing zd\blazing 21400` zawiera 21 210 surowych JPEG-ów; jego pierwsze 19
źródeł odpowiada dostarczonej challenge sequence zakresu `21169–21177`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `.runtime/plans/plan_ocr_srodkowy_rzad_v4_1.md`
- `C:\Users\user\Downloads\plan_ocr_srodkowy_rzad_v4_1.md`, sekcja 23

## Scope

- Oddzielne, checksum-bound tuning, frozen golden i challenge manifests.
- Parametryczny, read-only harness v4.1 z warm-upem i raportem jakości/czasu.
- Próba 100 źródeł przed dwoma próbami po 1000 źródeł.
- Pomiar trudnego offsetu 0 oraz łatwiejszego offsetu około 9000.
- Ręczna kontrola wszystkich automatycznie wybranych reprezentantów.
- Raport bramek precision, coverage, grouping, skalowania i throughputu.
- Projekcja czasu dla 42 000 źródeł.
- Aktualizacja wymagań, architektury, Current State, Decision Log i raportu
  jakościowego.

## Out of scope

- Zmiana zachowania lub fingerprintów v1–v3.
- Osłabienie exact proof, fuzzy OCR albo inferowanie z nazwy/indeksu/sąsiadów.
- Board detection, geometria, cropper plansz/symboli i symbol inference.
- Migracja, API, UI, nowy worker lane, Redis, Celery lub model ML.
- Automatyczne włączenie v4.1 jako domyślnego recognizera.

## Acceptance criteria

- [x] `falseExactCount = 0` na frozen golden i challenge set.
- [x] `selectedFrameOwnProofRate = 100%`.
- [x] `selectedRangePrecision = 100%` na ręcznie sprawdzonych wynikach.
- [ ] `readableFrameCoverage >= 50%`.
- [ ] `rangeGroupCaptureRate >= 90%` (cel 95%).
- [x] Trudna próba osiąga co najmniej 2 źródła/s.
- [x] Łatwiejsza próba osiąga co najmniej 3 źródła/s.
- [x] Mediana czasu/źródło dla 1000 nie przekracza wyniku próbki 100 o więcej
  niż 10% albo raport wskazuje konkretną przyczynę.
- [x] Żaden wybrany plik nie jest `unknown` i każdy ma własny exact triple.
- [x] V4.1 pozostaje za flagą do osobnej decyzji operatora.

## Expected files

- `scripts/run_middle_row_range_ocr_v4_acceptance.py`
- `services/worker/tests/test_middle_row_range_ocr_v4_acceptance.py`
- `ai_docs/quality/semi-automatic-range-ocr-v4-*.json`
- `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V4_ACCEPTANCE.md`
- dokumentacja wskazana powyżej

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_middle_row_range_ocr_v4_acceptance.py services/worker/tests/test_middle_row_runtime.py services/worker/tests/test_middle_row_grouping.py -q
.venv\Scripts\python.exe -m ruff check scripts/run_middle_row_range_ocr_v4_acceptance.py services/worker/tests/test_middle_row_range_ocr_v4_acceptance.py
.venv\Scripts\python.exe -m mypy --follow-imports=skip scripts/run_middle_row_range_ocr_v4_acceptance.py
npx prettier --check ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V4_ACCEPTANCE.md
```

## Rollback

Usunąć read-only harness, manifesty i raport. Runtime v4.1 pozostaje nadal
nieaktywny, a v1–v3 nie zmieniają zachowania.

## Outcome

Odbiór zakończono decyzją negatywną dla rolloutu. Challenge osiągnął `0` false
exact, `62,5%` readable coverage i `100%` group capture. Frozen golden zachował
`0` false exact i `100%` precision sześciu reprezentantów, ale osiągnął tylko
`26,3%` readable coverage oraz `35,3%` group capture, więc nie przeszedł dwóch
bramek coverage.

Próby po 1000 surowych JPEG-ów osiągnęły `4,83` i `5,05` źródła/s. Mediany
stanowiły `105,5%` oraz `101,8%` mediany próbki 100. Ręcznie sprawdzono wszystkie
120 automatycznie wybranych reprezentantów; każdy miał właściwy zakres i własny
exact proof. Pełny raport znajduje się w
`ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V4_ACCEPTANCE.md`.

V4.1 pozostaje wyłączone. Dominującą przyczyną braku coverage jest wybór
niewłaściwego rzędu przez locator (`NO_EXPECTED_RANGE_MATCH`), a nie polityka
exact proof. Dalsza poprawa wymaga nowego fingerprintu, oddzielnego tuningu i
nowego holdoutu; frozen golden nie może służyć do strojenia.

## Commit

`v0.10.70 - validate middle row range OCR rollout`
