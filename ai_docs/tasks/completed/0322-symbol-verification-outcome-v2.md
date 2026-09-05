---
title: TASK-0322 explicit symbol verification outcome v2
status: done
last_updated: 2026-08-30
---

# TASK-0322 — Jawny wynik weryfikacji symbolu v2

## Status

`done`

## Goal

Rozdzielić brak przypisania, nierozpoznany wynik, nieczytelny crop, błąd
geometrii, pozycję wymagającą review i zweryfikowany realny symbol. `?` ma
pozostać wyłącznie reprezentacją UI, a nie symbolem ani wartością domenową.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać czysty, wersjonowany kontrakt `SymbolVerificationOutcome`:
  `unassigned`, `unknown`, `unreadable`, `grid_issue`, `requires_review`,
  `verified_symbol`.
- Wymusić, aby tylko `verified_symbol` posiadał realne `assigned_symbol_id`.
- Zdefiniować, które wyniki są terminalną decyzją człowieka i które mogą
  dostarczyć etykietę do dalszej weryfikacji treningowej.
- Dodać deterministyczny adapter obecnego `review_state + quality_issue +
  assigned_symbol_id + prediction` do kontraktu v2.
- Niejednoznaczne historyczne kombinacje kończyć stabilnym błędem i kierować do
  późniejszego raportu migracji zamiast zgadywania.
- Udokumentować semantykę oraz granicę kompatybilności.

## Out of scope

- Bez migracji Alembic, nowych kolumn i backfillu.
- Bez zmiany bieżących constraints, ORM, API, OpenAPI i UI.
- Bez przepisywania istniejących eventów, verified labels i datasetów.
- Bez zmiany zachowania bieżącego Reviewera lub Weryfikacji Symboli.
- Bez uruchamiania pipeline'u, treningu albo rolloutu.

## Acceptance criteria

- [x] `verified_symbol` wymaga UUID realnego symbolu.
- [x] Każdy inny outcome odrzuca `assigned_symbol_id`.
- [x] `unknown` pozostaje wynikiem nierozwiązanym, a ręcznie potwierdzone
  `unreadable` jest osobnym terminalnym wynikiem bez symbolu.
- [x] `grid_issue` nie jest mylone z `unreadable` ani `requires_review`.
- [x] Predykcja modelu pozostaje sugestią i nie staje się przypisanym symbolem.
- [x] Adapter jednoznacznie mapuje bezpieczne historyczne kombinacje.
- [x] Adapter fail-closed odrzuca zatwierdzony brak symbolu bez dowodu
  `unreadable` oraz podejrzane pending przypisanie człowieka.
- [x] `?` nie występuje jako wartość żadnego outcome ani assigned symbolu.
- [x] Testy domeny, Ruff, format i scoped mypy przechodzą.

## Expected files

- `services/api/src/game_predictor_api/domain/symbol_verification_outcomes.py`
- `services/api/tests/test_symbol_verification_outcomes.py`
- dokumentacja modelu danych, decyzji i current state

## Compatibility strategy

Bieżące kolumny i eventy pozostają źródłem historycznym. Kontrakt v2 jest
addytywny i na tym etapie nie jest jeszcze write modelem SQL. Późniejszy schema
ownership review zdecyduje, czy outcome otrzyma osobną kolumnę oraz jak wykonać
bounded backfill. Adapter v1→v2 ma być jedynym miejscem interpretacji starej
kombinacji stanów.

## Risks

- Obecny model dopuszcza realny symbol przy `quality_issue = unreadable`.
  Adapter zachowuje wtedy logiczną etykietę jako `verified_symbol`; informacja o
  jakości nadal pozostaje niezależnie w starym polu do czasu migracji.
- `unassigned` opisuje stan przed próbą predykcji i nie jest wyprowadzany z już
  zmaterializowanego rekordu legacy bez dodatkowego dowodu.

## Planned commit

`v0.10.15 - define explicit symbol verification outcomes`

## Outcome

Dodano czysty kontrakt `symbol-verification-outcome-v2` z sześcioma rozłącznymi
wynikami. `SymbolCellVerification` wymusza realny UUID wyłącznie dla
`verified_symbol`; pozostałe wyniki nie mogą przenosić assignmentu. `unknown`
i wynik modelu wymagający review pozostają nierozwiązane, natomiast ręcznie
potwierdzone `unreadable` jest terminalne bez symbolu i bez etykiety
treningowej.

Fail-closed adapter legacy zachowuje bezpieczne realne etykiety, rozdziela
grid/unreadable oraz usuwa modelową sugestię z assignmentu v2. Zatwierdzony
NULL bez unreadable, pending przypisanie człowieka/board decision oraz pending
assignment bez odpowiadającej predykcji zwracają stabilny błąd do przyszłego
raportu migracji. Nie zmieniono ORM, constraints, API, OpenAPI, UI ani danych.

Weryfikacja:

- 26 testów nowego kontraktu i istniejącej domeny review — passed;
- Ruff i format check dwóch plików — passed;
- scoped mypy nowego modułu — passed;
- import i podstawowa asercja kontraktu w nowym procesie — passed.
