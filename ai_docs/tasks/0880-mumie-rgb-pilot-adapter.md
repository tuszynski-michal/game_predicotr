---
title: TASK-0880 — adapter i pakiet R2 RGB
status: todo
last_updated: 2026-10-06
---

# TASK-0880 — adapter i pakiet R2 RGB

## Status

`todo`

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

- [ ] Runtime bez Torch zachowuje bilinear antialias RGB96→64.
- [ ] Logity i klasy na rzeczywistych cropach zgadzają się z referencją lab.
- [ ] Import i korekta używają tego samego dispatchu; stare modele zachowane.
- [ ] Publikacja pakietu jest idempotentna i sprawdzona w nowym procesie.
- [ ] Drift modelu, słownika, temperatury i dowodów jest odrzucany.

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

Jeszcze nie ukończono.

### Verification results

Jeszcze nie uruchomiono testów odbioru tego taska.

### Not completed

Pozostały kryteria odbioru wskazane powyżej.

### Documentation updates

Plan MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md.

### Recommended next task

TASK-0881. Kontynuować zgodnie z planem po audycie i commicie.
