---
title: TASK-0269 v19 symbol residual cohort
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0269 — Kohorta pozostałych błędów modelu

## Goal

Zamrozić niezależną, odtwarzalną kohortę poprawnych cropów v19 i na jej
podstawie rozdzielić pozostałe błędy rozpoznawania symboli na M1, M2, P1 albo
`OPEN`. Wynik ma prowadzić do jednoznacznej decyzji `retrain` albo
`no-retrain`, bez uruchamiania treningu i bez aktywacji modelu.

## Context

- TASK-0249/TASK 6 dostarczył poprawną geometrię komórek v19 i source-direct
  cropper z fail-closed bramką.
- Dotychczasowa diagnoza na 81 ręcznie poprawionych planszach osiągnęła
  `95,80%` poprawnych symboli i `72,84%` poprawnych całych plansz.
- Shadow benchmark objął 300 stron z sześciu stagingów, lecz nie stanowi
  jeszcze immutable kohorty ręcznie zweryfikowanych etykiet modelu.
- Produkcyjne dane zawierają ponad 300 rozstrzygniętych plansz, ale część z
  nich wymaga read-only odtworzenia cropów v19; cropy v18 nie mogą wejść do
  kohorty.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/quality/GRID_CROPPING_VS_SYMBOL_MODEL_DIAGNOSIS.md`
- `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zamrożenie co najmniej 300 zweryfikowanych plansz z sześciu stagingów,
- dopuszczenie wyłącznie pełnych, checksum-verified cropów v19 z jednoznaczną
  etykietą człowieka,
- deterministyczny split po rodzinie źródła, bez przecieku,
- kontrola parity preprocessingu treningowego i ONNX,
- confusion matrix, metryki per klasa, staging i source family,
- jawna lista błędów wysokiej pewności i wariantów symboli,
- klasyfikacja residuali M1/M2/P1/OPEN oraz decyzja retrain/no-retrain,
- content-addressed manifesty i powtarzalny tryb `--check`.

## Out of scope

- trening, eksport albo aktywacja nowego modelu,
- zmiana geometrii v19, croppera lub produkcyjnej inferencji,
- cropy v18, niepewna geometria, konflikty etykiet i decyzje inne niż
  `accepted/corrected`,
- automatyczna zmiana ręcznych decyzji lub danych domenowych.

## Acceptance criteria

- [x] Kohorta obejmuje minimum 300 plansz i sześć niezależnych stagingów.
- [x] Każda plansza ma dokładnie 15 cropów v19 i etykiet człowieka.
- [x] Checksumy źródeł i cropów są zweryfikowane, a manifest jest niezmienny.
- [x] Split po source family jest deterministyczny, pełny i bez przecieku.
- [x] Preprocessing treningowy i ONNX ma potwierdzone parity.
- [x] Raport zawiera confusion matrix, klasy/źródła, warianty i błędy wysokiej
      pewności.
- [x] Każdy istotny residual ma klasyfikację M1, M2, P1 albo `OPEN`.
- [x] Raport kończy się jednoznaczną decyzją `retrain` albo `no-retrain`.
- [ ] Obie komendy `--check`, testy workera, Ruff i mypy przechodzą.
- [x] Zadanie nie uruchamia treningu ani aktywacji modelu.

## Planned verification

```powershell
.venv\Scripts\python.exe scripts/build_v19_symbol_residual_cohort.py --check
.venv\Scripts\python.exe scripts/evaluate_v19_symbol_residuals.py --check
npm run python:lint
npm run python:typecheck
```

## Outcome

- Zamrożono 321 plansz i 4815 cropów v19 z 41 rodzin źródeł oraz dokładnie
  sześciu stagingów. Checksum manifestu:
  `eaa368b5fd6671103c1e2e65ff06ada082a08da0d47a09ea48f629791523ab88`.
- Wizualny audyt błędów confidence >= 0,99 wykrył 12 plansz z konfliktem
  etykiety lub slotu. Zostały wykluczone jako całe plansze, a 27 cropów
  dowodowych przypięto checksumami. Raport klasyfikuje je jako `OPEN`.
- Aktywny model osiągnął `99,3354%` accuracy symboli, `94,3925%` całych plansz
  oraz pełne parity preprocessingu `4815/4815`.
- Jedyny istotny residual to M2 `plum -> grapes`: 9 błędów na dwóch rodzinach
  niewidzianych w treningu. Raport
  `c617fdf461fa4e9a56d5bebc96a01f01ab3e3b3348c46670a731613c5d07d3cc`
  wydaje decyzję `retrain`.
- Nie utworzono iteracji treningowej, nie wyeksportowano modelu i nie zmieniono
  aktywacji. Szczegółowy protokół znajduje się w
  `ai_docs/quality/V19_SYMBOL_RESIDUAL_COHORT.md`.
- Walidacja TASK 8: obie komendy `--check` odtworzyły przypięte checksumy,
  celowane testy workera przeszły `13/13`, a Ruff i mypy dla zmienionych
  modułów nie zgłosiły błędów. Pełny worker został przerwany przy około 58% po
  osiągnięciu limitu 120 sekund bez zaobserwowanego błędu. Repo-wide Ruff nadal
  zgłasza osiem wcześniejszych problemów w migracjach `0045`/`0046` i
  `test_symbol_confidence.py`; pełny mypy nie zwrócił wyniku w limicie 60 s.
