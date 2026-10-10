---
title: TASK-0854 — Mumie: kwalifikacja i split symboli
status: done
last_updated: 2026-10-05
---

# TASK-0854 — kwalifikacja Mumii

## Status

`done`

## Goal

Zamrozić kwalifikowany, pozbawiony przecieku podział świeżych etykiet Mumii.

## Context

Operator potwierdził różne ujęcia i nagrania dla wszystkich trzech grup.
Zgoda na dalszą autonomiczną pracę pozostaje. Brak pochodzenia z TASK-0853
jest rozstrzygnięty; nie wolno ponownie go zgłaszać jako brak deklaracji.

## Dependencies / entry conditions

Pakiet 0853, aktualna D-496, słownik v1 i 339 technicznie ważnych approve.
Kontrola konfliktów grafu/pikseli nadal musi się odbyć. T06b ogólny i stare
wyjątki geometry-only nie są używane jako skrót.

## Recommended execution

gpt-6.1-sol, high; własny odrębny przegląd, bez delegowania. Konflikt nowych
deklaracji z rzeczywistym źródłem lub protected zatrzymuje freeze.

## Relevant docs

- `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`, `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-489, D-496, D-498)
- `ai_docs/quality/MUMIE_SYMBOL_PREPARATION_20261005.md`

## Scope

Nowy per-game manifest i lokalny adapter, trzy jawne deklaracje, pełne
komponenty, źródła i dokładne cropy, create-only freeze, testy drift/restart.

## Out of scope

Zmiany magazynów/etykiet/ról geometrycznych, DB/API/UI, trening przed commitem,
Super, aktywacja, wdrożenie i pozostałe gry.

## Acceptance criteria

- [x] 339 aktualnych decyzji, wszystkie klasy w development/validation.
- [x] Żaden pełny komponent nie przecina części ani chronionych źródeł.
- [x] Deklaracje i techniczna kontrola przypięte, drift blokuje adapter.
- [x] Restart/retry/integralność PASS, oryginalne magazyny niezmienione.
- [x] Testy/lint/format/typy, audyt i osobny commit.

## Technical notes

Kontrakt wykonawczy w planie: osobna kwalifikacja D-498 bez zmiany D-496
i stale splitu. Nowy manifest wiąże przygotowany niezmienny pakiet zamiast
ponownie renderować piksele. Freeze rewaliduje obecny stan pod blokadą.

## Expected files

- Sprawdzone istniejące `symbol_preparation.py::build_bundle/verify_bundle`,
  `symbol_store.py::locked/preview_grant/local_row`, `splits.py::build_components`.
- Proponowany `symbol_training_manifest.py` i test modułu.
- Plan, wymagania/architektura, Decision Log, CURRENT_STATE i raport.

## Test cases / Verification

Nowe pytest + regresje D-496/0853 (120s), Ruff (60s), scoped Mypy(120s).
Main `.venv/Scripts/python.exe`; PYTHONPATH absolutny worker/src worktree.
Freeze/verify w nowym procesie przez istniejący bounded runner(120s).

## Risks / open questions

Mały validation: J i Sfinks po4 przykłady; nie jest testem końcowym.
Nie wymaga dalszego przypisywania przed pierwszym ograniczonym treningiem.

## Outcome

339 aktualnych etykiet; development255/validation84. Wszystkie10 klas w obu
częściach. Pełna suma dawnych i obecnych komponentów; identyczne cropy/zdjęcia
nie przecinają części. Zapis create-only i odczyt/retry w nowym procesie PASS.
Manifest `d5dc865287ca2d4583b450ccdca84f6186e16ac86922dc6f95ebea3930151589`.
Oryginalne magazyny/referencja niezmienione. 32 pytest, Ruff/format/Mypy PASS.
Własny odrębny review: wszystkie kryteria i kontrakt planu spełnione; bez P0–P2.
Osobny commit `v1.7.200`, hash dopisywany po commicie. Bez DB, treningu lub
aktywacji w tym tasku. Następnie0855 zgodnie z zakresem autonomicznej pracy.
