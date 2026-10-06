---
title: TASK-0876 — B9 — zapis RGB v2 dla pasma 80–90% (osiem symboli)
status: done
last_updated: 2026-10-06
---

# TASK-0876 — B9 — zapis RGB v2 dla pasma 80–90% (osiem symboli)

## Status

`done`

## Goal

Oczekujące komórki ośmiu symboli z pierwotną pewnością modelu 80–90% dostają
predykcję RGB v2 tam, gdzie zmienia się symbol albo status pewna/do przeglądu
(D-520 z poprawką z TASK-0874).

## Context

Etap B planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`. Bramkę
pasma przegląda wykonawca (polecenie operatora 2026-10-06).

## Dependencies / entry conditions

- Poprzednie pasmo zapisane i zweryfikowane.

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (tabela planu).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md`
- `ai_docs/process/DECISION_LOG.md` (D-520)

## Scope

- Podgląd części (≤ 60 000 komórek), przegląd próbek kategorii, zapis, weryfikacja.

## Out of scope

- Pozostałe pasma, zatwierdzanie komórek.

## Acceptance criteria

- [x] Przegląd próbek każdej kategorii przed zapisem, wynik w Outcome.
- [x] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [x] `verify` każdej części zgodny z manifestem.

## Test cases

- `verify` po każdej części.

## Outcome

- Podgląd 2026-10-06 00:07–00:31 UTC: 59 261 komórek, 590 zapisów (pewne
  zmiany 128, pewne bez zmiany symbolu 154, obniżenia 197, niepewne zmiany bez
  wsparcia biblioteki 111); 12 181 komórek chronionych regułą
  `library_keeps_current`.
- Przegląd próbek: pewne zmiany poprawne (wiśnie, śliwki, winogrona, gwiazdy,
  siódemki, pomarańcze); niepewne zmiany bez wsparcia biblioteki mieszane
  (część błędów CNN, np. gwiazda → cytryna) — trafiają do przeglądu 0,50
  zgodnie z decyzją operatora.
- Zapis 00:32–00:39 UTC: 590 z 590 komórek `rgb_prediction` na 563 planszach,
  0 błędów, 0 `stale`.
