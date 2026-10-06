---
title: TASK-0883 — feedback i odbiór pilota
status: done
last_updated: 2026-10-06
---

# TASK-0883 — feedback i odbiór pilota

## Status

`done`

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

- [x] Korekty kwalifikują aktualne piksele, bez treningu na predykcjach.
- [x] Siatki i symbole mają osobne targets/snapshots i podział po źródłach.
- [x] Rzeczywiste 100 zdjęć w ograniczonych krokach; rzetelny raport liczności/czasów.
- [x] Fresh-process E2E i response-loss nie tworzą duplikatów.
- [x] API/UI/build/kontrakt i regresje zmienionych pionów PASS.
- [x] Konkretne preview 0144/importu/aktywacji oraz instrukcja operatora.

## Technical notes

Entry0882 verifiedv1.7.224/8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e. Feedback usesgpt-6.1-sol/medium;
root exact-lattice export analysis useshigh under the explicit label/geometry
escalation rule. Preserve all old consumers and versioned fingerprints.
Protected human control truth and promotion analysis also use
gpt-6.1-sol/high under that explicit escalation rule. Genuine frozen human
decisions are compared with current approvals; zero comparisons means
NO_CONFLICT. Missing proof is an integrity failure, not an invented OPEN.


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
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\vision_lab\production_geometry.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src\game_predictor_worker\vision_lab\production_snapshot.py
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\tests\test_mumie_geometry_export.py
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\integration\test_mumie_geometry_feedback_postgres.py
- Istniejący fixture: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\integration\test_vision_lab_geometry_export_postgres.py
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\install_mumie_feedback_controls.py
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

Implemented pooled human feedback with protected whole-photo byte/pixel
exclusions, current approved crop identities, immutable cohort/config/dataset
references and fresh gates through the first training epoch. Existing class,
source and training limits and legacy fingerprints are preserved.

Added 127 frozen genuine human controls with 136 proofs and explicit lab-to-DB
catalog mapping. Promotion of new production-training Mumie candidates checks
current exact bindings and locks pending/current controls. Genuine conflicts
are OPEN; no current comparisons means NO_CONFLICT/0. R2 lab import and other
games retain the old contract.

Geometry export retains exact approved 24 nodes and visibility masks.
Source-only geometry0 can be approved without recrop. Damaged/checksum-drifted
snapshots and stale/system-only approvals fail closed; explicit corner
conversion and old exports remain compatible. Added a create-only controls
installer, prepared100 real photos and concrete deployment/operator documents.

### Verification results

Root geometry67PASS; feedback/cohort/dataset/training/catalog53PASS;
bounded preview38PASS; controls installer15PASS; truth/registry/lab51PASS.
These suites overlap. Independent new modules55PASS. Two distinct guarded
PostgreSQL testsPASS: actual read-only export/cold resume and actual current
control SELECT/FOR SHARE with competing LOGIN update and verified teardown.

Strict real-import Mypy root4 and truth4 modulesPASS. Strict scoped feedback7
and API compositionPASS with only third-party torch/torchvision analysis
skipped; own/API/storage imports remain normal and strict. Full Torch graph
attempts were bounded at60/115/120s; no full-graph PASS is claimed.
Ruff/format all24 Python filesPASS. Admin warnings4tests, ESLint, tsc and
production build44.09sPASS; OpenAPI currentPASS. Unchanged Reviewer keeps0882
build/mobile/request evidence. No physical Android acceptance.

Prepared controls fresh-process retry:161 existing/0 new,24 original photos,
136 proofs/127 controls, descriptor25fedbdf124dfd1cf8038addb9f8a176817b2b2361cff62fe0f8f9a18f1d7812.
Independent rerender matched every frozen96px crop. Live descriptor absent.

Actual100 source evidence from0882:900 expected positions,897 structurally
valid24-node proposals,13455 full cells,99 ordered drafts/1unbound.
Five20-photo steps below20s; cold replay sameSHA/0infer. Individual process
memory peaks parent124.6MiB/child413.0MiB, not a combined RSS claim.
No population symbol/geometry accuracy without human labels of the full set.

### Not completed

No operator DB write/migration, MAIN merge, registry import, activation or
service restart. Full operator backup/restore is not yet executed. These are
TASK-0884 operations requiring the concrete preview approval and a safeRGB
checkpoint. No new V5 refit, automatic training/activation, deletion or push.

### Documentation updates

MUMIE_PILOT_FEEDBACK_ACCEPTANCE_20261006.md;
MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md;
MUMIE_MAIN_APP_DEPLOYMENT_PREVIEW_20261006.md; CURRENT_STATE.
Final code/document allowlist and bounded receipts are recorded in
C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\0883-final-proof.json.

### Recommended next task

TASK-0884 after the concrete0144/0145 deployment approval.
No further labels, recording-independence answers or implementation approval
are required. Independent gpt-6.1-sol/high audit PASS,0 open P0–P2.
Commit pending versioned task closure.
