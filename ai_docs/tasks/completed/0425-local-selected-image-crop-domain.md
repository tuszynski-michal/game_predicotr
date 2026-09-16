---
title: TASK-0425 Local selected image crop domain
status: done
last_updated: 2026-09-04
---

# TASK-0425 — Local selected image crop domain

## Scope

- define a framework-independent, horizontal full-width crop band,
- validate top-level `seq_<start>-<end>.jpg|jpeg` inputs deterministically,
- define the versioned `manual-image-crop-output-v1.json` contract,
- model journaled save operations and restart reconciliation,
- persist only directory handles and lightweight viewport state in IndexedDB.

## Out of scope

- image decoding and JPEG rendering,
- file-system mutation,
- React workspace,
- API, jobs and PostgreSQL.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- crop coordinates are validated in EXIF-canonical pixel space,
- inherited crop proportions work across different image sizes,
- invalid, duplicate and overlapping sequence files are rejected,
- the manifest binds source inventory, crop coordinates and checksums,
- pending operations resolve fail-closed and deterministically,
- focused domain and local persistence tests pass.

## Outcome

- Added a framework-independent full-width crop-band model with deterministic
  defaults, proportional inheritance and minimum-height validation.
- Added the versioned manifest and journal transitions, including fail-closed
  restart reconciliation for missing, matching and conflicting outputs.
- Reused strict numeric `seq_*` validation and added a dedicated IndexedDB v1
  store containing handles and lightweight viewport state only.
- Verification: manual-selection core tests (27/27), package typecheck and
  Admin typecheck passed.
