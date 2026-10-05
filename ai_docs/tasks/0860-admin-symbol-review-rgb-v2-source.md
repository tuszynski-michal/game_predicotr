---
title: TASK-0860 — źródło RGB v2 w filtrze weryfikacji symboli
status: todo
last_updated: 2026-10-05
---

# TASK-0860 — źródło RGB v2 w filtrze weryfikacji symboli

## Status

`todo`

## Goal

Admin → Weryfikacja symboli → „Źródło predykcji” ma opcje „RGB v2” i „RGB v2 — do przeglądu” obok istniejących; API listy, liczników, pomijania i operacji masowych przyjmuje nowe wartości.

## Context

Etap A planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
(zaakceptowany przez operatora 2026-10-05). Metoda i ograniczenia:
`ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`.

## Dependencies / entry conditions

- Plan zaakceptowany; poprzednie taski etapu A wykonane w kolejności planu.

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium` (zgodnie z tabelą planu; audyt wstrzymany
przez operatora 2026-10-01).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- `SymbolCellReviewPredictionSource` i filtr w `image_symbol_review_repository.py` (wpis predykcji z kluczem `rgbV2` w rewizji `symbol-rgb-v2`; status z `rgbV2.status`).
- OpenAPI, wygenerowany klient, wrapper, test żądania, Admin `symbol-review-workspace.tsx`.

## Out of scope

- Zapis w bazie operatora (etap B), trening i zmiana checkpointu CNN,
  zatwierdzanie komórek, geometria.

## Acceptance criteria

- [ ] `npm run openapi:check` zielone; testy API i Admina zielone.
- [ ] Dotychczasowe opcje filtra działają jak wcześniej.

## Test cases

- Testy repozytorium/route dla nowych wartości; test żądania klienta; typecheck i lint Admina.

## Outcome

Brak.
