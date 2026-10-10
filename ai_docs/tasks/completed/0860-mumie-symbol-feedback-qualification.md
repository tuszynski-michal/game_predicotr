---
title: TASK-0860 — kwalifikacja 18 korekt symboli Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0860 — kwalifikacja feedbacku Mumii

## Status

`done`

## Goal

Przygotować dokładny immutable pakiet 18 decyzji i kwalifikowany pochodny
zbiór 264 development / 84 validation / 9 diagnostic_test bez zmiany oryginałów.

## Context

Operator ukończył18 korekt i jawnie zlecił kwalifikację oraz dalsze uczenie.
TASK-0859 wykazał regresje J/Mumii, których nie usuwa globalna podmiana RGB.

## Dependencies / entry conditions

18 aktualnych approve, D-498 i batch reference D-501. Operator potwierdził
relację481537–500000 do76555–103221: „Tak, inne nagranie”. Zgoda na inne znane nagrania
pozostaje; nie pytamy o nią ponownie.

## Recommended execution

gpt-6.1-sol, high; jeden wykonawca i własny odrębny review, bez delegacji.
Drift/powiązanie chronionego lub walidacyjnego źródła blokuje kwalifikację.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md; ai_docs/process/TASK_TEMPLATE.md
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md
- ai_docs/process/DECISION_LOG.md (D-498, D-501, D-502)
- ai_docs/delivery/MUMIE_SYMBOL_FEEDBACK_ITERATION_20261005.md
- ai_docs/quality/MUMIE_RGB_FEEDBACK_TRANSFER_20261005.md

## Scope

Dokładny pakiet, preview bramek, typed kwalifikacja, pełny graph/alias closure,
nowy pochodny manifest/adapter i testy. Format/purpose nowych danych jawne.
Po commicie kontynuować0861 zgodnie z aktualnym poleceniem operatora.

## Out of scope

Nowe decyzje za człowieka, pełna akceptacja geometrii, zmiana pierwotnego
trainable lub magazynów, DB, aktywacja, Super, merge/push/wdrożenie.

## Acceptance criteria

- [x] 18 dokładnych PNG, pełne decyzje i dictionary provenance; invalid review nie jest targetem.
- [x] Metadata role/graph/protected przed dekodowaniem; full-folder aliases w jednej części.
- [x] Pochodny manifest tylko po potwierdzonej relacji do validation.
- [x] 264/84/9 i wszystkie 10 klas w development/validation; duplicate/conflict gates.
- [x] Exact current quad/source/PNG/decision SHA i replay po restarcie.
- [x] Oryginały i adapter D-498 bez zmian; API/UI bez zmian.
- [x] Testy, lint/typecheck, własny review, commit, Outcome i CURRENT_STATE.

## Technical notes

Kontrakt i granice określa zaakceptowany plan wskazany wyżej. Geometry gate
dotyczy wyłącznie dokładnego zatwierdzonego rastra; nie nadaje pełnej geometrii.
Pierwsze nagranie9 etykiet jest diagnostic_test wyłącznie dla nowej iteracji.
Nie przenosimy go w starej kohorcie D-498 ani nie deklarujemy ślepego testu.

## Expected files

Nowe symbol_feedback.py i test_vision_lab_symbol_feedback.py. Istniejące
lokalne symbol_runs.py — opcjonalny adapter dispatch; requirements,
architecture, DECISION_LOG, plan, raport i CURRENT_STATE.

## Verification

Nowy test modułu i dotychczasowe testy adaptera/batch. Absolutny runner120s
dla każdego kroku; nowe procesy prepare/verify/retry i SHA originals.
Testy planowane; Outcome zawiera faktyczne wyniki.

## Outcome

Qualified classifier-only composite manifest 0cff2a15…1e3de4 and exact pack
c1392fb1…3f8b60 preserve 18 operator decisions and 17 source photos. All 2,052
new-folder members remain in the development component. Counts are 264/84/9,
with all 10 classes in development/validation. First-recording labels are
diagnostic only in the new iteration. Raw decisions remain trainable=false.

Twenty new pytest and 42 existing regression tests passed. Ruff format/lint,
scoped strict mypy, real fresh-process verify and identical freeze retry passed.
The first broad dependency mypy timed out after 120 seconds and its child tree
was terminated; the replacement scopes only Torch/ONNX imports. All original
pinned SHAs remain unchanged. Separate review found no unresolved P0–P2.

No DB, activation, HTTP/UI change, merge/push or deployment. Evidence:
ai_docs/quality/MUMIE_SYMBOL_FEEDBACK_QUALIFICATION_20261005.md.
Commit: `v1.7.206`. Continue TASK-0861 under the existing operator instruction.
