---
title: TASK-0872 — źródło RGB v2 w filtrze weryfikacji symboli
status: done
last_updated: 2026-10-06
---

# TASK-0872 — źródło RGB v2 w filtrze weryfikacji symboli

## Status

`done`

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

- [x] `npm run openapi:check` zielone; testy API i Admina zielone.
- [x] Dotychczasowe opcje filtra działają jak wcześniej.

## Test cases

- Testy repozytorium/route dla nowych wartości; test żądania klienta; typecheck i lint Admina.

## Outcome

- Wykonawca: agent `claude-sonnet-5-5` w izolowanym worktree (bez commitu),
  przegląd i scalenie przez `claude-opus-5-5`. Commit przed TASK-0871, bo
  test PostgreSQL writera sprawdza także ten filtr (kolejność zadań etapu A
  zmieniona: 0870 → 0872 → 0871 → 0873).
- API: `SymbolCellReviewPredictionSource` ma `rgb_v2` i `rgb_v2_tentative`;
  `RGB_V2_PREDICTION_MODEL_VERSION = "symbol-rgb-v2"`. Każdy pisarz ma własny
  skorelowany `EXISTS` (aliasy `library_revision`, `rgb_revision`) na wpis
  komórki w jej bieżącej rewizji (`referenceLibrary` / `rgbV2`, dla
  `rgb_v2_tentative` z `status = tentative`); `model` = ani biblioteka, ani
  RGB v2. OpenAPI i klient wygenerowane; Admin ma opcje „RGB v2” i
  „RGB v2 — do przeglądu”.
- Testy (agent): filtry 21 PASS, API 62 PASS + 1 FAIL istniejący wcześniej
  (`test_list_endpoint_uses_keyset_cursors_without_duplicates`: oczekuje
  limitu 5 000 ms przy domyślnych 20 000 ms; pada też na głównym checkoucie,
  osobna propozycja zadania); `openapi:check` PASS; Admin typecheck, lint
  (0 błędów), testy 630 PASS; klient 83 PASS. Powtórzone w worktree planu:
  API 62 PASS + ten sam 1 FAIL.
- PostgreSQL: filtr sprawdzony testem integracyjnym TASK-0871 (`rgb_v2`,
  `rgb_v2_tentative`, `model`, `reference_library` na zapisanej planszy).
- Nie sprawdzono: podgląd UI w przeglądarce; wydajność `model` (dwa
  skorelowane `NOT EXISTS` zamiast jednego).
