---
title: TASK-0407 — Rejestracja trwałego runu OCR pięciu anchorów v6
status: done
created: 2026-09-02
---

# TASK-0407 — Rejestracja trwałego runu OCR pięciu anchorów v6

## Goal

Zarejestrować gotowy recognition-only runtime v6 jako nowy, jawny wariant
trwałego runu półautomatycznej selekcji, bez zmiany rozpoczętych ani przyszłych
domyślnych runów v1–v5.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0406-five-anchor-range-runtime.md`

## Scope

- Dodać zamknięty identyfikator wariantu `five_anchor_v6`, jego trwały
  fingerprint runtime'u oraz niezależną politykę grupowania/wyboru środka.
- Udostępnić wariant przez capabilities i opcjonalne, walidowane pole startu
  runu; domyślny start pozostaje na istniejącym wariancie v3.
- Wykonać pełny checkpointowany skan v6, grouping i wybór wyłącznie źródeł z
  własnym exact proofem.
- Zachować idempotencję: identyczne żądanie v6 zwraca ten sam run, a żądania
  różniące się wariantem tworzą odrębne tożsamości runu.
- Wygenerować zgodny klient OpenAPI i dodać selektor Admina z oznaczeniem
  eksperymentalnym.

## Out of scope

- Zmiana, migracja lub ponowne uruchomienie historycznych runów v1–v5.
- Włączenie v6 jako wariantu domyślnego, rollout na danych użytkownika albo
  pomiar jakościowy OCR.
- Zmiana reguł proofu, lokalizatora, geometrii plansz, croppera lub symboli.

## Invariants

- Klient przekazuje wyłącznie nazwę wariantu z zamkniętej listy; nie może
  wskazać dowolnego fingerprintu.
- Run v6 jest przypięty do fingerprintu i polityki grupowania zapisywanych w
  jego tożsamości. Retry odczytuje wyłącznie te wartości.
- V6 nie używa nazwy pliku, indeksu ani sąsiadów jako dowodu zakresu.
- Wariant jest jawnie eksperymentalny i nie zmienia istniejącego domyślnego
  wyboru v3.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_image_selections.py services/worker/tests/test_semi_automatic_selection_job.py services/worker/tests/test_five_anchor_range_runtime.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/application/semi_automatic_image_selections.py services/api/src/game_predictor_api/schemas/semi_automatic_image_selections.py services/worker/src/game_predictor_worker/semi_automatic_selection services/api/tests/test_semi_automatic_image_selections.py services/worker/tests/test_semi_automatic_selection_job.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/application/semi_automatic_image_selections.py services/api/src/game_predictor_api/schemas/semi_automatic_image_selections.py services/worker/src/game_predictor_worker/semi_automatic_selection
npm run openapi:check
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
```

## Outcome

Completed in `v0.10.110`.

- Registered the closed, experimental `five_anchor_v6` variant in capabilities,
  API validation and Admin upload flow while retaining `default_v3` as default.
- Bound v6 runs to the source-local runtime fingerprint plus an independent
  exact-evidence-span grouping fingerprint; v3 and v6 are separate identities,
  while duplicate v6 starts are idempotent.
- Added the checkpointed v6 scan, audit selector support and representative
  selection from exact v6 evidence only. Historical v1–v5 resolver branches
  remain unchanged.
- Verified focused API/worker tests, Ruff, mypy, OpenAPI generation, Admin
  contract test, lint, typecheck and production build. No real OCR run, job,
  migration or user-data mutation was performed.
