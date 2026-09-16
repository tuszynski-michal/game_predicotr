---
id: TASK-0384
title: Promote structured v0.10 image engine per game
status: done
version: 0.10
---

# TASK-0384 — Promote structured v0.10 image engine per game

## Goal

Expose the already supported `structured_default / virtual_default` runtime as
the production per-game choice for new imports. Keep historical v19 and shadow
jobs replayable, but do not present shadow as an engine that can be used for
operator decisions.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Add the user-selectable `structured_default` engine policy mapped to
  `structured_default / virtual_default`.
- Preserve `structured_shadow / virtual_shadow` as a readable historical policy.
- Offer only stable v19 and production v0.10 in the Admin picker.
- Pin the selected policy in new import jobs and describe historical shadow jobs
  honestly in the UI.
- Extend OpenAPI and the generated Admin client in the same vertical slice.
- Add focused domain, API/client and Admin tests.

## Out of scope

- No in-place conversion of existing legacy crop rows.
- No deletion or mutation of completed imports or accepted decisions.
- No automatic reprocessing of managed originals.
- No change to the structured geometry algorithm itself.

## Invariants

- A job always replays the immutable engine snapshot stored in its payload.
- Changing the game policy affects only jobs created afterwards.
- `virtual_default` is the only structured asset mode that can be used for
  review decisions.
- Shadow results remain measurement-only and never masquerade as current crops.
- Existing v19, shadow and structured-default jobs remain readable.

## Verification

- focused policy and job snapshot tests;
- Admin picker and mode-label tests;
- OpenAPI generated-client consistency;
- Admin lint, typecheck and production build;
- Ruff and mypy for the changed backend modules.

## Definition of Done

- The per-game selector can choose production v0.10.
- A new import created under that policy is pinned to
  `structured_default / virtual_default`.
- The symbol-review workspace needs no renderer selector and renders the asset
  identity persisted on each current cell.
- Existing imports remain unchanged and are explicitly identified by their
  pinned engine.

## Outcome

Implemented `structured_default / virtual_default` as a user-selectable,
preview-bound per-game policy for new imports. The Admin picker offers stable
v19 and production v0.10, while still reading and labelling historical shadow
jobs. OpenAPI and the generated client carry the new enum value. Existing jobs
and crop identities are intentionally unchanged; a managed-original rerun is
required to create current v0.10 assets for an already processed source.
