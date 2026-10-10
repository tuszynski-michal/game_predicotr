---
title: V3 import presentation and application inventory
status: done
last_updated: 2026-10-06
---

# TASK-0887 — V3 import presentation and application inventory

## Status

`done`

## Goal

Present the actual Mumie neural engine in MAIN import, preserve V1.1 for 777,
and document the operator flow and a high-level application review.

## Context

The operator sees V1.0/V1.1/V1.2 choices while Mumie already imports through
the neural pilot. The backend normalizes the former V1.1 request to the neural
route; the picker and success text do not explain this. The user asks to hide
obsolete choices, retain V1.1, and inventory other functions before removing
or moving them. The future online review application is a separate scope.

## Dependencies / entry conditions

- MAIN branch v1.1-vision-lab-hybrid-geometry at v1.7.228 / 55669e93.
- D-523 automatic full bound crops is already implemented.
- Existing GameResponse.shapeGeometryConfiguration identifies the Mumie
  profile. ImageImportEnginePolicyResponse.policy is not a neural-engine ID.
- Pre-existing dirty completion hashes and unrelated directories are preserved.

## Recommended execution

gpt-6.1-sol / high. Small UI change with historical-report protection and
read-only data analysis. Reassess if a new API or data migration is required.
No delegated work is authorized for this task.

## Relevant docs

- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/ADMIN_APP.md — import engine and D-523
- ai_docs/requirements/IMAGE_INGESTION.md — current variants and source ordering
- ai_docs/architecture/API_CONTRACT.md — profiles and neural import payloads
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md
- ai_docs/guides/DATABASE_MAINTENANCE.md
- ai_docs/delivery/APP_V3_IMPORT_PRESENTATION_20261006.md

## Scope

- Use the existing game profile to show V3 for Mumie and omit classical
  variant arguments for its report, preflight and import.
- Show V1.1 for classical games, including 777; hide V1.0 and V1.2 choices
  with a deprecation notice. Preserve historical records and pinned retries.
- Correct visible engine labels on reports and import success.
- Document folder upload, explicit preflight/import, automatic full crops,
  correction, bulk symbols and pooled learning.
- Create an evolving high-level screen/function inventory with current,
  requested and proposed changes distinguished.
- Capture bounded, read-only storage metadata and cleanup candidates.

## Out of scope

No removal of other screen functions, online panel implementation, new model training or
activation, real-data upload, cleanup execution, migration, push or merge.

## Acceptance criteria

- [x] MAIN Mumie import visibly selects V3; no V1.0/V1.2 radio or V1.1 action.
- [x] Mumie report/preflight/import omit geometryEngineVariant.
- [x] 777 retains V1.1 and historical report versions remain readable.
- [x] Interaction tests cover both routes, explicit start and fresh mount.
- [x] Operator guide states real button names and distinguishes neural grid
      training from the existing calibration action.
- [x] Inventory covers current game sections and future shared online review.
- [x] Storage preview reports measured sizes and boundaries, without deletion.
- [x] Scoped lint/types/tests and UI verification pass; documented limitations
      and pre-existing dirty files are preserved.

## Technical notes

CatalogWorkspace passes the existing optional shapeGeometryConfiguration
property into ImageFolderImportPanel. Only grid_profile_mumie_v1 selects V3,
matching SqlAlchemyGridProfileSnapshotResolver. Do not call structural policy
structured_lattice_v3 a neural model or activate the 777 neural profile.
Historical classical report selection still restores its pinned variant.
New classical selections remain V1.1. Hidden engines remain available to the
backend for history; only obsolete UI entry points were removed from selection.
Other screen functions, engine implementations and data remain.

## Expected files

- Existing: apps/admin/src/features/catalog/catalog-workspace.tsx,
  apps/admin/src/features/imports/image-folder-import-panel.tsx,
  apps/admin/test-interactions/neural-import-readiness.test.mjs.
- Existing: apps/admin/src/app/globals.css (scoped picker layout) and
  apps/admin/test/image-folder-import-panel-contract.test.mjs (changed UI contract).
- Existing: operator guide, ADMIN_APP.md, IMAGE_INGESTION.md, CURRENT_STATE.md.
- Proposed: requirements/APP_V3_FUNCTIONAL_INVENTORY.md and this task's plan.
- Ignored evidence: artifacts/app-v3-review-20261006/.

## Test cases

Mumie fresh mount and report → V3, omitted classical variant, explicit import
only; 777 mount → V1.1 remains enabled; classical pinned V1.2 history → exact
historical report without restoring the obsolete option to the picker.

## Verification

Run the Node interaction suite through the absolute tsx loader with
TSX_TSCONFIG_PATH pointing to apps/admin/tsconfig.json. Run Admin TypeScript
and scoped ESLint with the existing bounded run_step.py (120 seconds).
Inspect a fresh MAIN browser page without mutating user data. Storage
catalog reads use read-only transactions and statement/connection timeouts.

## Risks / open questions

The future screen moves and grid-network training UI are inventory proposals,
not implemented functionality. Logical DB size does not establish reclaimable
Windows disk space. Destructive cleanup requires its own concrete preview and
operator confirmation under AGENTS.md and DATABASE_MAINTENANCE.md.

## Outcome

### Changed

- MAIN picker follows the existing game profile: Mumie V3 with no classical
  request variant; 777 V1.1. Historical reports and pinned reprocess preserved.
- V1.0/V1.2 choices and forced V1.0 UI action hidden; backend/actions library
  preserved. Scoped responsive picker style and V3 success message corrected.
- Operator guide expanded; draft function/screen inventory created with
  current behaviour, requested gaps and future online panel distinguished.
- Read-only catalog preview: MAIN 51.73 GB, 777 partitions48.16 GB, Mumie
  partitions71 MB. Retained restore-test DB46.97 GB has zero connections and
  a verified backup receipt on D:. No deletion or compaction executed.

### Verification results

- Import unit/contract suites66 PASS; interaction8 PASS (V3 request omission,
  success label, fresh mount, explicit preflight/start, 777 and pinned V1.2).
- Admin tsc PASS; scoped ESLint PASS with the pre-existing Next img warning;
  final Prettier check PASS. Admin production build PASS,34.11 seconds.
- Fresh MAIN UI and reload: selected V3, enabled folder upload; actual 777
  import retains V1.1. No real upload/start/training performed in UI.
- Catalog queries use read-only transactions, connection5s and statement10s.
  Disk metadata and backup file size inspected without a new full copy.
- Evidence: artifacts/app-v3-review-20261006/ and deployment run_step logs
  named0887. Screenshot mumie-v3-import.png shows the completed picker.
- Commit: v1.7.229 / 5130cbc80c676560a6ec6c5f77828c48074ff462.

### Not completed

- No data deletion, migration, model activation/training, push or merge.
- Other screen moves/removals and online panel are inventory entries only.
- Neural grid training from Admin is not implemented; current calibration
  button is documented accurately. Old shared-geometry/readiness and
  completeness texts are listed for a separate screen task, not hidden.
- No OS reboot or physical Android test; fresh mount, browser reload and
  fresh test processes cover this persisted UI change.

### Documentation updates

Operator guide, ADMIN_APP, IMAGE_INGESTION, API_CONTRACT (existing route only),
README, D-524, draft inventory, plan and CURRENT_STATE.

### Recommended next task

Review inventory IMPORT-07/08 and MODEL-06: simplify import status and expose
separate neural-grid feedback/training. Cleanup of the named test restore
requires concrete operator confirmation after this preview.
