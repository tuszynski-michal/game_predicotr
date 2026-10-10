---
title: TASK-0884 — wdrożenie pilota Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0884 — wdrożenie pilota Mumii

## Status

`done`

## Goal

Uruchomić odebrany pilot w głównej aplikacji i przyjąć realną pierwszą partię bez wpływu na model 777.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0880–0883 PASS; konkretna zgoda na 0144/operacje DB; bezpieczny checkpoint RGB0878.
Implementacja: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3.
Zatwierdzone wdrożenie: C:\Users\tuszy\Documents\game_predicotr.
Weryfikować rzeczywiste HEAD obu gałęzi przed numeracją commita integracji.

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

Wykonać dokładnie sekcję TASK-0884 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Scalenie zachowuje aktualną pracę obu gałęzi.
- Backup, schema current/head i preview zapisane przed operacją.
- Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane.
- Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze.
- Recovery działa bez usuwania źródeł, decyzji i historii.
- Bez nieautoryzowanego push ani przerywania aktywnych zapisów.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [x] Scalenie zachowuje aktualną pracę obu gałęzi.
- [x] Backup, schema current/head i preview zapisane przed operacją.
- [x] Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane.
- [x] Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze.
- [x] Recovery działa bez usuwania źródeł, decyzji i historii.
- [x] Bez nieautoryzowanego push ani przerywania aktywnych zapisów.

## Technical notes

Operator approved the complete concrete deployment preview with "tak" on
2026-10-06: backup/restore rehearsal, main merge/builds, migrations0144/0145,
service restart, Mumie candidate import/activation and the first100 photos.
No repeat approval is needed for those operations. Preserve RGB0878 and all
pre-existing worktree metadata. Expected changes: this task, CURRENT_STATE,
the deployment preview/acceptance documents and necessary conflict resolution
in CURRENT_STATE/DECISION_LOG on MAIN. Runtime receipts remain in artifacts.

The operator then explicitly overrode the120s limit for this operation:
take the necessary time, monitor whether the process is alive and retry a
failed process. Backup uses a bounded1800s step; the49GB restore uses3600s,
with monitored progress and disk space; extend if needed without
asking again. Check orphan processes and the failure cause before retry.

Operational adjustment after the operator objected to the time spent restoring
historical777 data: the root openly removed full-restore completion as a gate
for the already authorized Mumie deployment. Require the completed full backup,
independent SHA/TOC, passed isolated0144/0145 PostgreSQL tests, fresh stopped
MAIN/services and unchanged777 baseline. Keep the healthy isolated restore
under its guardian as a separate recovery check. Do not claim full restore
verification before exit0/revision/counts/777 acceptance, kill it, delete its
database, reset the model or broaden the live changes. The accepted plan and
preview record this change consistently before merge/migration.

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\package.json
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\install_grid_engine_models.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\run_mumie_image_import.py
- Istniejące w MAIN: C:\Users\tuszy\Documents\game_predicotr\ai_docs\tasks\0878-symbol-rgb-v2-band-99-100.md
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

Integration fixes discovered by the real deployment are in scope of the
existing worker/readiness acceptance criteria. They preserve the training protocol and the777 model.
The later cropSize snapshot fix is an optional API contract extension:
- C:\Users\tuszy\Documents\game_predicotr\scripts\start_controlled_api.ps1
- C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_controlled_api_readiness.py
- C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_image_symbol_review_query_storage.py
- C:\Users\tuszy\Documents\game_predicotr\services\worker\src\game_predictor_worker\symbols\lab_candidate_import.py
- C:\Users\tuszy\Documents\game_predicotr\services\worker\tests\test_lab_candidate_import_handler.py


Additional real import integration files in MAIN:
- C:\Users\tuszy\Documents\game_predicotr\services\api\src\game_predictor_api\schemas\jobs.py
- C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_image_imports_api.py
- C:\Users\tuszy\Documents\game_predicotr\packages\admin-api-client\openapi\openapi.json
- C:\Users\tuszy\Documents\game_predicotr\packages\admin-api-client\src\generated\index.ts
- C:\Users\tuszy\Documents\game_predicotr\packages\admin-api-client\src\generated\sdk.gen.ts
- C:\Users\tuszy\Documents\game_predicotr\packages\admin-api-client\src\generated\types.gen.ts
- C:\Users\tuszy\Documents\game_predicotr\packages\admin-api-client\test\lab-rgb-job.test.mjs
- C:\Users\tuszy\Documents\game_predicotr\services\worker\src\game_predictor_worker\images\production_workflow.py
- C:\Users\tuszy\Documents\game_predicotr\services\worker\tests\test_neural_folder_correction_pipeline.py
- C:\Users\tuszy\Documents\game_predicotr\services\worker\tests\test_production_image_workflow.py
- C:\Users\tuszy\Documents\game_predicotr\ai_docs\quality\MUMIE_MAIN_APP_PILOT_ACCEPTANCE_20261006.md

## Test cases

- Scalenie zachowuje aktualną pracę obu gałęzi. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Backup, schema current/head i preview zapisane przed operacją. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Recovery działa bez usuwania źródeł, decyzji i historii. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Bez nieautoryzowanego push ani przerywania aktywnych zapisów. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Po gotowym preview i zgodzie: istniejące npm install, npm run admin:build,
npm run reviewer:build, npm run db:migrate w głównym checkoutcie.
Przed operacją sprawdzić Alembic current/heads, po operacji potwierdzić jedyny
oczekiwany head zawierający0144. Builds z zapowiedzianym dłuższym timeout;
readiness usług w10s; konkretne polecenia startu ustalić z aktualnego PID i
istniejących skryptów przy preview, bez uruchamiania drugiej kopii usług.
Odbiór100 rzeczywistych źródeł i zachowanych reguł rejestru/777, bez benchmarku.

## Risks / open questions

Operational assumption confirmed from the first live import: Mumie has no
rules version, and the existing import contract requires one to pin its board
topology. Create only a3-row/5-column draft through the existing Admin API.
spinCost=0 is an explicit unused placeholder, not the game's payout or free-spin
rule. Do not publish the draft or invent paylines/payouts; no target calculation
is part of this pilot. Preserve the exact frozen start request and retry it.

- Brak blokującej decyzji operatora dla przygotowania implementacji.
- Migracja/aktywacja na rzeczywistej bazie wymagają gotowego preview.
- Główna gałąź ma nowszą niezależną pracę RGB0878; zachować ją przy integracji.
- Operator proposed a later manual Super workflow: detect at least three
  Mumie as a reviewable bonus trigger, then let the operator select the special
  base symbol in a separate game subsection for the ten free spins. Record the
  choice once per ordered bonus session; a retrigger retains that symbol.
  This is a proposal for a separate task, not a deployment blocker or consent
  to reset the existing model/data. Sequence gaps and uncertain detections must
  not silently establish bonus boundaries. No Super implementation in0884.

## Outcome

### Changed

The approved deployment is operational on MAIN, preserving both branch
histories and independent RGB0878. Completion commit: `v1.7.226 /4e73b92cd3b135496b42a836edeb1f979e8de46a`.
Integration sourcev1.7.225 /
820083aed4b3d2dda048c938bd2f3ed410132d95 and premerge MAINv1.7.222 /
48b6e0e104e19e915bde30cd89a80d508e81c0b3 remain ancestors.

Actual100 retained originals,99 bound pipeline sources and891 pending grids
are available for human correction. Same importf3ff4258-e561-4031-bc04-227c9dbf51b6
reached waiting_for_review on attempt3,199/199,99review/0failed. The ending
source seq_499996-500004.jpg remains unbound, without an invented board/target.
No human approvals, approved geometry, new cohorts or symbol_training jobs.

Mumie lab iterationfd5b15b6-e335-410d-9720-5f2d3bd6ec43 is active through
fa00eaa1-5f19-4675-8102-3f40e042ff7c. Candidate manifest72125739eec0e03e212de5b586ed5b417837e00b0f4382903f88405b0331a5c2.
The actual fresh MAIN runtime preserves the qualified RGB96→64 input and
24-node neural proposal identity. Exact prior777 registry columns and its
activation remain unchanged.

Real deployment fixes: controlled API owned-port readiness; version1 lab
VALIDATE checkpoints; optional strict cropSize96 snapshot DTO with regenerated
OpenAPI/SDK and start/replay/get/list+wrapper tests; manual crop producer
deferrals using the existing stage contract without weakening validation.
The same99 files were resumed by existing per-file API in20/20/20/20/19 steps
while the general worker was stopped. All297 earlier stage rows retain their
timestamps/digests, keys/order/checkpoints unchanged before restart. Generic
job retry alone was insufficient; no second import or checkpoint deletion.

Final services at18:25:43Z: API29756/listener30308, Admin45912 on3000,
Reviewer48888 on3001, general worker38536/48684. AllHTTP200; no reload or
duplicate UI process. Independent RGB and Vision Lab preserved. Real UI
sequence10 opens automatically with15/15 cells,24 editable nodes, suggestions
and10 keyboard choices. Symbol-only editing and unsaved-draft reload passed;
root removed only its trial choice, without saving a human decision.

Full13604719372B custom/zstd backup and isolated restore passed exit0,
0143/173tables/exact777/0Mumie sources. The restore filled C and triggered the
app's30GiB reserve; root acknowledged this error. Verified backup moved to
D:\game_predictor_backups\mumie-main-app-pilot-20261006\game_predictor_0143_20261006T153523Z.dump
after full source+destination SHA, pointer/cold reconciliation complete.
No DB deletion or reserve reduction; *_test and initial partial retained.
Live schema was already0145 before explicit migrationCLI, which was a no-op.
The earlier0143→0145 executor remains unattributed. Isolated actual migrations
passed and final current/head0145 plus all prior777 columns are verified.

### Verification results

MAIN install/Admin+Reviewer builds, contracts/types/lint/focused API/UI/client
checks passed. Additional readiness3, runtime lab worker2, query/catalog22,
lab+legacy HTTP2, neural+legacy stage5 and client88 tests passed; these groups
overlap broader suites. Final changed Python Ruff/format and runtime Mypy passed.
405 real source cells retain0 pixel/class drift, input max7.153e-7/logit1.907e-6.
Protected161-file controls install and fresh retry passed with0 retry writes.
Cold actual100 audit aafa8cf7-ca6b-4897-8bbb-9727c5b3b6fa at18:26:00Z PASS.
Independent gpt-6.1-sol/high code/liveSQL review PASS,0 openP0–P2. Final quality
report maps every task acceptance item and applicable DoD criterion to evidence.
Receipts: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006.

### Not completed

No operator review, larger500/2000 upload, TRAIN/refit, automatic neural-grid
training for new games, Super sessions, target calculation, cleanup or push.
34/34 selected controls are not population accuracy; R2pair andV5 remain FAIL.
Physical Android untested; earlier mobile viewport interactions passed.
The ending unbound source needs human range/binding review. These limits are
within the accepted pilot scope; first actual operator review is the next step.

### Documentation updates

CURRENT_STATE, accepted execution plan, deployment preview, live operator
guide and MUMIE_MAIN_APP_PILOT_ACCEPTANCE_20261006.md.

### Recommended next task

Operator reviews the existing pilot in MAIN Reviewer; pooled corrections
feed the existing explicit Ulepsz rozpoznawanie action. Larger batches follow
that review. Manual Super remains a separate proposed task.
