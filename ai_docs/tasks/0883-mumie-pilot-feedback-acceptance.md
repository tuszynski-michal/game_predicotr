---
title: TASK-0883 — feedback i odbiór pilota
status: todo
last_updated: 2026-10-06
---

# TASK-0883 — feedback i odbiór pilota

## Status

`todo`

## Goal

Potwierdzić pełny przepływ folder/korekta/kwalifikacja kolejnego treningu i przygotować preview wdrożenia.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0882 PASS; tylko odizolowane dane testowe i read-only istniejące źródła przed 0884.
Pracować w C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3.
Weryfikować rzeczywisty HEAD tej gałęzi przed numeracją commita.

## Recommended execution

gpt-6.1-sol / medium; konfiguracja zgodna z tabelą planu.
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

Wykonać dokładnie sekcję TASK-0883 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Korekty kwalifikują aktualne piksele, bez treningu na predykcjach.
- Siatki i symbole mają osobne targets/snapshots i podział po źródłach.
- Rzeczywiste 100 zdjęć w ograniczonych krokach; rzetelny raport liczności/czasów.
- Fresh-process E2E i response-loss nie tworzą duplikatów.
- API/UI/build/kontrakt i regresje zmienionych pionów PASS.
- Konkretne preview 0144/importu/aktywacji oraz instrukcja operatora.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [ ] Korekty kwalifikują aktualne piksele, bez treningu na predykcjach.
- [ ] Siatki i symbole mają osobne targets/snapshots i podział po źródłach.
- [ ] Rzeczywiste 100 zdjęć w ograniczonych krokach; rzetelny raport liczności/czasów.
- [ ] Fresh-process E2E i response-loss nie tworzą duplikatów.
- [ ] API/UI/build/kontrakt i regresje zmienionych pionów PASS.
- [ ] Konkretne preview 0144/importu/aktywacji oraz instrukcja operatora.

## Technical notes

DB pilot gwarantuje whole-photo split, nie whole-recording; raport ujawnia
brak trwałego recordingID. Przed nowym Mumie TRAIN preview/freeze verified
cohort i dataset builder stosują frozen protected-source-exclusions-v1,
powiązany z R2 eligibility i fingerprintem kohorty/treningu. Wykluczenia
validation/diagnostic/human26/human8/AI audit wiążą całe source byteSHA oraz
exif-normalized decoded pixelSHA; development regression ma osobny opis.
Brak/zmiana exclusions blokuje TRAIN, nie upload/korektę. Zaimportowane,
prawdziwie zatwierdzone kontrolne źródło i jego reencoded alias nadal daje
PROTECTED_EVALUATION_SOURCE; żadna komórka nie jest TRAIN. Human decyzji i
historycznych manifestów nie zmieniać. Korekta holdoutu nie przesuwa splitu;
konflikt prawdy testowej OPEN blokuje promocję. Testować oba wejścia i fresh
freeze/builder, nie tylko filtr preview.

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_geometry_export.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_production_snapshot.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\apps\admin\src\features\model-quality\model-quality-actions.ts
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\ai_docs\delivery\MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Korekty kwalifikują aktualne piksele, bez treningu na predykcjach. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Siatki i symbole mają osobne targets/snapshots i podział po źródłach. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Rzeczywiste 100 zdjęć w ograniczonych krokach; rzetelny raport liczności/czasów. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Fresh-process E2E i response-loss nie tworzą duplikatów. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- API/UI/build/kontrakt i regresje zmienionych pionów PASS. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Konkretne preview 0144/importu/aktywacji oraz instrukcja operatora. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Planowane testy istniejące oraz jawnie proponowane nowe:
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_mumie_pilot_feedback.py

```powershell
& 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3' --name '0883-focused' 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' -m pytest 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_mumie_pilot_feedback.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_vision_lab_symbol_db_integration.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_symbol_model_catalog_binding.py' -q
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

TASK-0884. Kontynuować zgodnie z planem po audycie i commicie.
