---
title: Working V7 test entry from main Admin
status: done
last_updated: 2026-10-07
---

# TASK-0919 — Dostęp do poprawionego półautomatu z Admin3000

## Status

`done`

## Goal

Link użytkownika do głównego panelu ma umożliwiać wejście do działającego
półautomatu z wyborem katalogu zapisu, pełnymi propozycjami i korektą sąsiadów.

## Context

Main3000/8000 nie zawiera zmian brancha kalibracyjnego i pokazuje blocked V7.
Pilot3020/8020 jest aktywny i zawiera wcześniej przetestowane zmiany. Operator
zlecił odblokowanie testów, a nie włączenie nieodebranego automatu głównej bazy.

## Dependencies / entry conditions

- Main HEAD v1.7.248 /68ce73a800c21c197a2cf67376792515f1c13085.
- Pilot branch HEAD v1.7.221 /b087ad08b62992c54f5e26191e6408d287b64273.
- HTTP capabilities i browser main potwierdzają konflikt wersji, nie awarię.
- Zakres URL3000 wymaga zmiany main checkout; V7 worker/pilot zostaje w worktree.
- Nowe AGENTS: API/Admin lifecycle pozostaje wyłącznie użytkownikowi.

## Recommended execution

gpt-6.1-sol / high; własny review granicy lokalnych originów i zachowania
istniejących konsumentów, bez delegowania.

## Relevant docs

- AGENTS.md, process/PLAN_STANDARD.md, TASK_TEMPLATE.md, DEFINITION_OF_DONE.md.
- process/CURRENT_STATE.md, DECISION_LOG.md (D-531).
- requirements/IMAGE_SELECTION.md, architecture/IMAGE_SELECTION.md.
- delivery/V7_MAIN_PANEL_TEST_ENTRY_PLAN.md.
- Calibration worktree: delivery/V7_COMPLETE_DRAFT_COVERAGE_PLAN.md oraz
  requirements/architecture IMAGE_SELECTION.md; bez odczytu archiwum tasków.

## Scope

Lokalny entry link i regresje main UI; odczyt istniejącego pilota, rzeczywista
nawigacja do źródła/zapisu/review, operator instructions i osobny commit.

## Out of scope

Merge/cherry-pick całego brancha, transplant backend/worker, aktywacja main V7,
API/Admin restart, OCR/rescan, tworzenie runu lub decyzji, trening, migracje,
source/corpus/shared runtime mutation, monitor, push/deploy.

## Acceptance criteria

- [x] Na URL3000 użytkownik widzi działający entry zamiast samego disabled start.
- [x] Link otwiera istniejący panel z source i output picker oraz saved review.
- [x] Local-only origin, no game/run identity transfer, no runtime bypass.
- [x] Active, flag-off, existing run i crop workflow zachowują zachowanie.
- [x] Focused tests, format/lint/types i prawdziwy browser PASS.
- [x] Brak lifecycle/domain data mutations; dokumentacja i Outcome uzupełnione.

## Technical notes

Link jest zwykłą nawigacją; nie proxy'uje requestów głównej bazy do pilota,
nie usuwa jakościowej blokady API8000 i nie uruchamia procesu. Instrukcja
wyjaśnia wskazywanie katalogu oraz jawne oszacowania. Pełne pokrycie występuje
po przygotowaniu wyborów dla skonfigurowanych grup; deliberate deletion oraz
brak rzeczywistych plików/IO failure nie mogą udawać zapisanego zdjęcia.

## Expected files

- Existing: apps/admin/src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx.
- New: local-v7-pilot-entry.ts w tym samym module, test/local-v7-pilot-entry.test.mjs,
  test-interactions/v7-main-panel-entry.test.mjs.
- Relevant requirement/architecture, D-531, CURRENT_STATE, this plan/task.

## Test cases

3000 ->3020 workspace without game/run; custom loopback; reject remote/credentials,
self link, unsafe path/query/hash; SSR safe; blocked entry vs active form and
flag-off; reload stable href; no calls to source/create/approve on navigation.

## Verification

PowerShell main checkout; bounded existing task0852 wrapper (absolute worktree
path). Node --test pure helpers <=30s; tsx interactions <=60s; Prettier/ESLint
<=30s; tsc --noEmit <=120s. Fresh test processes and existing browser; actual
results in Outcome, no server start/stop/restart. Port/process reads only.

## Risks / open questions

Pilot services must already run, as they currently do. If unavailable after
restart, the user starts them in their terminal; agent does not. No blockers.

## Outcome

- Main3000 now offers "Otwórz półautomat V7" to existing Admin3020. The local
  entry replaces unusable setup when no main run is restored. It retains main
  run/review/crop workflows and does not transfer game/run IDs or change API8000.
- Origin routing rejects remote/credential/context/self URLs; explicit empty
  public override disables the link. SSR uses a separate origin snapshot.
  Initial lint caught effect-driven setState; corrected with useSyncExternalStore
  and verified without disabling the rule. Documentation follows D-531.
- Fresh-process helper/form/contract tests 19/19 and rendered interactions 6/6
  PASS. Prettier, scoped ESLint (zero warnings) and full Admin tsc --noEmit PASS.
  Remount, browser-free SSR, active/flag-off/non-local and existing-run regressions
  confirm persistence and compatibility. No production build was required/run.
- Actual browser: user's exact URL3000 -> working link ->3020; source picker,
  output picker and saved review all enabled. Existing range 77644–77652 shows
  an estimated-number JPEG, its output path and neighbour controls. Main reload
  retains entry, pilot restores prior run. No start/approve/cancel was clicked.
- Bounded read-only HTTP: capabilities8000 blocked/v1; 8020 and same-origin3020
  active/v2. File-name checks confirm 3135/3135 expected JPEGs in old output root
  and 3190/3190 in new output/propozycje, zero missing. This does not prove OCR
  accuracy; previous complete-coverage quality checks belong to calibration WT.
- No API/Admin/worker lifecycle, OCR/rescan, new run, approval, domain data write,
  migration, training, activation, branch merge, monitoring, push or deployment.
  Full main backend integration remains separate; the pilot must already run.
- Evidence: artifacts/v7-main-panel-entry-20261007/main-entry.jpg and
  verification.json. DoD/plan checked point by point; no open P0–P2 in own review.
- Completion version: v1.7.249; actual hash recorded after commit.
