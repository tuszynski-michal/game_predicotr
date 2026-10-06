---
title: TASK-0880 — adapter i pakiet R2 RGB
status: done
last_updated: 2026-10-06
---

# TASK-0880 — adapter i pakiet R2 RGB

## Status

`done`

## Goal

Przygotować torch-free wejście R2 RGB i zweryfikowany, niezmienny pakiet do rejestracji.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0879 PASS; zamrożone eligibility 5b6af3…4ac7c i ONNX e4f9b2…37095.
Pracować w C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3.
Weryfikować rzeczywisty HEAD tej gałęzi przed numeracją commita.

## Recommended execution

gpt-6.1-sol / high; konfiguracja zgodna z tabelą planu.
Niezależny review: gpt-6.1-sol / high. Eskalować analizę przy sprzeczności
pochodzenia danych, kontraktu lub ochrony poprzednich konsumentów.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md
- ai_docs/process/DECISION_LOG.md — D-521
- ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md

## Scope

Wykonać dokładnie sekcję TASK-0880 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Runtime bez Torch zachowuje bilinear antialias RGB96→64.
- Logity i klasy na rzeczywistych cropach zgadzają się z referencją lab.
- Import i korekta używają tego samego dispatchu; stare modele zachowane.
- Publikacja pakietu jest idempotentna i sprawdzona w nowym procesie.
- Drift modelu, słownika, temperatury i dowodów jest odrzucany.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [x] Runtime bez Torch zachowuje bilinear antialias RGB96→64.
- [x] Logity i klasy na rzeczywistych cropach zgadzają się z referencją lab.
- [x] Import i korekta używają tego samego dispatchu; stare modele zachowane.
- [x] Publikacja pakietu jest idempotentna i sprawdzona w nowym procesie.
- [x] Drift modelu, słownika, temperatury i dowodów jest odrzucany.

## Technical notes

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Nowy: services/worker/src/game_predictor_worker/images/lab_rgb_preprocessing.py — CPU antialias.
- Istniejący: services/api/src/game_predictor_api/domain/symbol_model_snapshots.py — cropSize fingerprint.
- Istniejący: services/api/src/game_predictor_api/application/jobs.py — crop output size.
- Istniejący: services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py — spójny dispatch.
- Nowy: services/api/src/game_predictor_api/domain/lab_symbol_candidate.py — immutable package contract.
- Nowy: scripts/prepare_mumie_rgb_pilot.py — bounded verified package CLI.

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\symbol_onnx.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\manual_board_cell_symbol_prediction.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\production_workflow.py
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Runtime bez Torch zachowuje bilinear antialias RGB96→64. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Logity i klasy na rzeczywistych cropach zgadzają się z referencją lab. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Import i korekta używają tego samego dispatchu; stare modele zachowane. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Publikacja pakietu jest idempotentna i sprawdzona w nowym procesie. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Drift modelu, słownika, temperatury i dowodów jest odrzucany. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Planowane testy istniejące oraz jawnie proponowane nowe:
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_lab_rgb_preprocessing.py

```powershell
& 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3' --name '0880-focused' 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' -m pytest 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_lab_rgb_preprocessing.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_symbol_onnx.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_manual_board_cell_symbol_prediction.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_symbol_model_snapshot_resolver.py' -q
```

Polecenie jest planowane; nowe testy powstaną razem z właściwą implementacją.
Dla zmienionych modułów uruchomić tym samym ograniczonym runnerem python -m
ruff check, ruff format --check i mypy z dokładnymi absolutnymi ścieżkami modułów.
Dla pionów API/UI dodatkowo sprawdzone npm run openapi:generate/openapi:check,
admin:build i reviewer:build w wskazanym absolutnym worktree.
Odbiór obejmuje nowy proces i utraconą odpowiedź. Wyniki zapisuje Outcome;
planowane polecenie nie stanowi wyniku PASS.

## Risks / open questions

- Brak blokującej decyzji operatora dla przygotowania implementacji.
- Migracja/aktywacja na rzeczywistej bazie wymagają gotowego preview.
- Główna gałąź ma nowszą niezależną pracę RGB0878; zachować ją przy integracji.

## Outcome

### Changed

Added the lab-rgb-symbol-onnx-v1 CPU adapter with exact RGB96 float bilinear
antialias preprocessing, opset17, input64 and crop96. Import, recrop, manual
prediction, deferred render fallback and pending reinference share this contract.
The complete source quad uses padding0.0; existing virtual padding0.08,
opset18, legacy preprocessing and snapshot fingerprints remain unchanged.
Training/export Torch imports are lazy; runtime entrypoints remain Torch-free.
Prepared a content-addressed package with explicit lab_import provenance,
283 human/44 AI development records and no invented DB approvals/accuracy.

### Verification results

- Commit: v1.7.222 / e8de3b18d389207a5ceaa5d171e8a9e14d46c346.
  Confirmed git show/stat and remaining status after publication.

- Focused render/release/pending/virtual-repository/package suite:77 passed.
- Broader existing ONNX/manual/resolver/production workflow and adapter suite:
  108 passed. The final package/pending-R2 suite:23 passed.
- Ruff check and format for15 changed files PASS; scoped mypy8modules PASS.
  A broader follow-imports=silent invocation exceeded120s and was bounded;
  no orphan remained. Broader skip-import analysis reports15 preexisting
  dependency-typing diagnostics in unchanged lines of jobs, repository and
  workflow; these are outside this adapter change.
- Actual source→production render parity:405cells/3photos, zero pixel/class
  differences; input max7.153e-7, logits max1.908e-6. Source evidence verifies
  all9352pins and full accepted eligibility semantics before/after inference.
- Fresh process: actual manual405+production135 inference, three runtime
  entrypoint imports, canonical pending snapshot roundtrip, zero Torch imports.
- Independent gpt-6.1-sol/high audit PASS, no remaining P0–P2. Auditor reproduced
  original source rendering and manual405+production405 runtime independently.
- Candidate FP5e0489db5f0b1aaa03854e5dabe7104ad85e444d077ff20d5c747f67d062a480;
  manifest72125739eec0e03e212de5b586ed5b417837e00b0f4382903f88405b0331a5c2.
  Managed package: main artifacts/mumie-main-app-pilot-20261006/prepared/models/
  lab-symbol-candidates/<FP>; report package-render-preflight.json.
  The obsolete tensor-only package is preserved and rejected by the new contract.

### Not completed

No live DB writes, migration, main merge, deployment, training or model activation.
Registry/UI/folder integration belongs to0881–0883; this task's criteria are met.

### Documentation updates

Plan, D-521, architecture supplement and CURRENT_STATE record the exact full-quad
render boundary and distinguish runtime parity from population accuracy.

### Recommended next task

TASK-0881. Continue the explicitly requested integration plan after this commit.
