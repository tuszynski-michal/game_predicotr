---
title: TASK-0882 — neural folder i korekta
status: done
last_updated: 2026-10-06
---

# TASK-0882 — neural folder i korekta

## Status

`done`

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

- [x] Neural staging korzysta z neutralnego geometry_core i przypiętych artefaktów.
- [x] Nieweryfikowana geometria trafia do durable pending/review, bez blokady całej partii.
- [x] 24 węzły zachowane przez preview/save/render/revisions.
- [x] Pięć slotów, brak środkowy i nieprzypisane detekcje nie zmieniają sequence.
- [x] Partial/outside poprawnie ograniczają cropy i targets.
- [x] Symbol można zmieniać bez zmiany siatki; default workflow 777 zachowany.
- [x] Restart, utracona odpowiedź, konflikt rewizji i approved-protection.

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

Read-only preparation: deterministic 100-source diagnostic completed on the
three independently recorded folders. It produced 897 structurally valid
proposals and 13,455 RGB cell predictions; 99 sources matched their filename
counts. These are proposal/count checks, not measured population accuracy.
Frozen report: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\source-diagnostic-100\summary.json.
The last filename, seq_499996-500004.jpg, declares nine positions, while visual
inspection shows five numbered boards ending at 500000 and six neural
detections. Do not silently clip its range using Game.expected_layout_count.
It requires explicit source range correction and detection-to-slot binding;
no canonical sequence may be inferred from detection count or visual ordering.
Preserve the original filename range in proposal provenance.

Compatibility findings for implementation: the current canonical preflight
rejects valid nonterminal short ranges. Enable the accepted 1–9-slot contract
only for the frozen neural-pilot path. Browser source range correction is not
available in the existing keep/reject filename verifier; add explicit range
confirmation to the source binding, preserving original provenance. Existing
page-source asset/save routes lose their staged JPEG after retention: extend
their existing owner with verified server-side managed handoff and use the
existing managedSourceJobId for re-preflight. Do not create a parallel queue.

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Nowy: services/api/alembic/versions/0145_neural_page_geometry_binding.py —
  zgodne opcjonalne pochodzenie pełnego lattice/bindingu w istniejącym override.
- Istniejący: services/api/src/game_predictor_api/storage/models.py — tylko
  ImagePageGeometryOverrideModel, po zamknięciu registryTASK0881.
- Istniejące domain/application/storage/page_geometry_overrides oraz
  api/image_imports.py i Admin page-geometry-correction-panel.tsx.

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

Frozen neural staging uses geometry_core and an owned bounded CPU runtime.
Immutable per-source checkpoints survive restart/response loss. Source-only
timeouts become pending; model/source/startup/cleanup failures abort.
Explicit source binding preserves original ranges, missing slots and ignored
detections. Migration0145 extends the existing page override owner; no fake
quad, sequence or human approval is created. Managed originals and exclusions
remain usable after staging retention.

The actual folder Import panel accepts completed neural manifests with review
items, including an all-unbound source-only handoff. Backend, OpenAPI, generated
client, wrapper and request tests form one additive contract. Exact24 float
nodes survive preview/render/save/revisions and durable browser draft retries.
Symbols are editable on opening without recropping a valid proposal. Legacy777
defaults, partial/outside restrictions and approved geometry remain protected.

### Verification results

- Root new41, broader production120 and managed source24 tests PASS.
- Backend core46, legacy HTTP10 and client86 tests PASS. Counts overlap.
- Independent fresh backend96 tests and folder/helper/request checks PASS;
  final independent gpt-6.1-sol/high audit PASS,0 openP0–P2.
- Isolated PostgreSQL1 PASS/0skip: populated0144→0145 partitions,9 malformed
  nested bindings, application-role CAS, cold-process original receipt replay,
  RLS and guarded downgrade. Operator database untouched.
- UI pure41/final import66, Reviewer interactions15 and Admin interactions21
  PASS. Actual Import panel tests include99 review sources and managed recovery.
- Strict Mypy root7/backend29 modules PASS; Ruff/format, UI/client types,
  OpenAPI/SDK drift and both builds PASS. Earlier bounded combined runs were
  replaced with focused proofs, not declared PASS. Existing Admin lint warning
  remains. Mobile Edge touch390/360×844 PASS; physical Android not tested.
- Actual production staging100 pinned real photos in five20-source steps:
  900 expected slots retained,897 valid full24-node proposals/13455 full cells,
  99 ordered source drafts/1 unbound. Fresh replay0/4 preserves manifestSHA
  without inference. This is structural acceptance, not symbol accuracy.
- Separate20-photo Windows memory measurement: parent130682880B and neural
  child433102848B individual peaks; handler16.75s. No combined peak claim.

Evidence: ai_docs/quality/MUMIE_NEURAL_FOLDER_CORRECTION_20261006.md and
C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\0882-final-proof.json.
Separate commitv1.7.224/8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e; show/stat and remaining status verified.

### Not completed

No operator DB migration/write, main merge, activation, service restart, push,
Super target or model refit. Training feedback belongs to0883. Actual operator
database remains0143; concurrent RGB777 operations continue unchanged.

### Documentation updates

Task, CURRENT_STATE, D-521, accepted pilot plan and quality report updated.
The operator plan uses a prepared100-photo folder; folder uploads are not
automatically capped at100. Existing dirty historical metadata is excluded.

### Definition of Done / plan comparison

All seven acceptance criteria have concrete tests above. The accepted0882
source owner, exact lattice, slot/partial behavior, contract vertical,
restart/conflict/response-loss and legacy protections are implemented.
Independent gpt-6.1-sol/high signoff PASS,0 openP0–P2. Separate task commit follows.

### Recommended next task

ContinueTASK0883 after audit and commit; complete the accepted plan through
concrete0144/0145 deployment preview before requesting operator DB approval.
