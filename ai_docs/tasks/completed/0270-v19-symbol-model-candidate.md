---
title: TASK-0270 v19 symbol model candidate
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0270 — Warunkowy retrening modelu na cropach v19

## Goal

Wytrenować od początku audytowalnego kandydata modelu symboli wyłącznie na
zweryfikowanej kohorcie cropów v19 zamrożonej przez TASK-0269. Kandydat ma
pozostać nieaktywny i przejść porównanie z aktualnym modelem na identycznych,
rozłącznych źródłowo zbiorach test/regression.

## Context

TASK-0269 potwierdził istotny residual M2 `plum -> grapes`: 9 błędów z dwóch
nowych rodzin źródeł, w tym 6 z confidence co najmniej 0,99. Warunek
uruchomienia retreningu został spełniony. Zamrożona kohorta obejmuje 321 plansz,
4815 cropów, 41 rodzin źródeł i sześć stagingów; 12 plansz z konfliktem etykiety
lub slotu jest wykluczonych fail-closed.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/quality/V19_SYMBOL_RESIDUAL_COHORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0256-deferred-self-improving-page-geometry.md`

## Scope

- wersjonowany adapter niezmiennej kohorty v19 do treningu,
- deterministyczny trening `spatial-symbol-cnn-v1` od początku,
- eksport ONNX, bezpieczna kalibracja i kontrola PyTorch–ONNX parity,
- porównanie kandydata z przypiętym aktywnym modelem na identycznych splitach,
- audyt błędów o confidence co najmniej 0,99 na 100 deterministycznie wybranych
  planszach,
- content-addressed raport i manifest decyzji `candidate_ready` albo `rejected`.

## Out of scope

- aktywacja lub promocja kandydata,
- zmiana aktywnego wskaźnika modelu,
- ponowne cięcie albo zmiana geometrii,
- użycie niezweryfikowanych cropów i poprawianie konfliktów etykiet TASK-0269,
- zmiana pipeline'u importu lub inferencji produkcyjnej.

## Acceptance criteria

- [x] Dataset zawiera dokładnie 321 plansz i 4815 cropów v19 z sześciu stagingów.
- [x] Split ma 38 rodzin train oraz po jednej validation, test i regression, bez
      przecieku źródeł.
- [x] Trening jest deterministyczny i startuje od losowej inicjalizacji ze stałym
      seedem, nie z aktywnego checkpointu.
- [x] ONNX zachowuje top-1 parity z PyTorch, a kalibracja respektuje bezpieczny
      zakres temperatury.
- [x] Kandydat poprawia accuracy całych plansz o co najmniej 2 pp albo accuracy
      symboli o co najmniej 1 pp względem aktywnego modelu.
- [x] Recall żadnej klasy nie spada o więcej niż 1 pp.
- [ ] Audyt 100 plansz nie zawiera błędu z confidence co najmniej 0,99. Kandydat
      został poprawnie odrzucony po jednym błędzie `lemon -> orange` z confidence
      `0,99999698`.
- [x] Wynik jest zapisany jako `candidate_ready` albo kontrolowane `rejected`.
- [x] Aktywny fingerprint modelu jest identyczny przed i po zadaniu.

## Outcome

- Zamrożony adapter datasetu użył dokładnie 321 plansz i 4815 cropów v19 ze
  splitem 38/1/1/1 bez przecieku źródeł.
- Trening 40 epok wybrał epokę 24. Kandydat poprawił accuracy całych plansz o
  5,8824 pp i accuracy symboli o 0,7843 pp, bez regresji recall powyżej 1 pp.
- ONNX parity przeszło, a temperatura `0,60057958` pozostała w bezpiecznym
  zakresie.
- Audyt 100 plansz wykrył jeden błąd wysokiej pewności: sekwencja 35, komórka
  13, `lemon -> orange`, confidence `0,99999698`. Kandydat został zgodnie z
  bramką oznaczony `rejected`.
- Aktywny model nie został zmieniony. Raport decyzji ma checksumę
  `4e6ace22cc4d90ee230cc66ae4a3a306afa54c6b19f9e8d96544dbebee421578`.
