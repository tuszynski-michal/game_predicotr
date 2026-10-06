---
title: TASK-0882 — neural folder i korekta
status: todo
last_updated: 2026-10-06
---

# TASK-0882 — neural folder i korekta

## Status

`todo`

## Goal

Wgrany folder Mumii pokazuje neural propozycje w istniejącej korekcie, z edycją symboli na otwarciu.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0881 PASS; import preview nie oznacza autoaktywacji ani zapisu na produkcji.
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

Wykonać dokładnie sekcję TASK-0882 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Neural staging korzysta z neutralnego geometry_core i przypiętych artefaktów.
- Nieweryfikowana geometria trafia do durable pending/review, bez blokady całej partii.
- 24 węzły zachowane przez preview/save/render/revisions.
- Pięć slotów, brak środkowy i nieprzypisane detekcje nie zmieniają sequence.
- Partial/outside poprawnie ograniczają cropy i targets.
- Symbol można zmieniać bez zmiany siatki; default workflow 777 zachowany.
- Restart, utracona odpowiedź, konflikt rewizji i approved-protection.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [ ] Neural staging korzysta z neutralnego geometry_core i przypiętych artefaktów.
- [ ] Nieweryfikowana geometria trafia do durable pending/review, bez blokady całej partii.
- [ ] 24 węzły zachowane przez preview/save/render/revisions.
- [ ] Pięć slotów, brak środkowy i nieprzypisane detekcje nie zmieniają sequence.
- [ ] Partial/outside poprawnie ograniczają cropy i targets.
- [ ] Symbol można zmieniać bez zmiany siatki; default workflow 777 zachowany.
- [ ] Restart, utracona odpowiedź, konflikt rewizji i approved-protection.

## Technical notes

Właścicielem source pending bez sequence jest PageGeometryOverrideService,
browser page-geometry routes api/image_imports.py i Admin page-geometry-correction-panel.tsx.
Staging manifest wiąże upload/sourceSHA/dimensions/revision oraz24nodes;
stan slot_binding_required trwa po restarcie. Override utrwala unikalne
detectionID→active positionIndex, expected proposal SHA i rewizję. Dopiero
jednoznaczny binding pozwala utworzyć board pending z sequence.
associate_expected_slots nie kompaktuje braków:101–105 z detekcjami a,b,d,e
po ręcznym a0,b1,d3,e4 zostawia103 missing i d na104. Przy mismatch bez bindingu
całe źródło pozostaje source-level pending. Reading_order tylko sortuje.
Przy pełnej zgodnej liczności można przedstawić ordered proposal do review,
ale nie canonical qualification; ambiguity/overlap/extra wymaga source review.

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\page_geometry_preflight.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\production_workflow.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\images\board_cell_geometry_deferred_writer.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\application\virtual_grid_geometry.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\schemas\image_grid_reviews.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\apps\reviewer\src\features\operational-reviews\grid-audit-correction-workspace.tsx
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Neural staging korzysta z neutralnego geometry_core i przypiętych artefaktów. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Nieweryfikowana geometria trafia do durable pending/review, bez blokady całej partii. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- 24 węzły zachowane przez preview/save/render/revisions. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Pięć slotów, brak środkowy i nieprzypisane detekcje nie zmieniają sequence. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Partial/outside poprawnie ograniczają cropy i targets. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Symbol można zmieniać bez zmiany siatki; default workflow 777 zachowany. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Restart, utracona odpowiedź, konflikt rewizji i approved-protection. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Planowane testy istniejące oraz jawnie proponowane nowe:
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_neural_page_geometry_preflight.py

```powershell
& 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3' --name '0882-focused' 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' -m pytest 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_neural_page_geometry_preflight.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_virtual_grid_geometry.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_manual_board_cell_symbol_prediction.py' -q
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

TASK-0883. Kontynuować zgodnie z planem po audycie i commicie.
