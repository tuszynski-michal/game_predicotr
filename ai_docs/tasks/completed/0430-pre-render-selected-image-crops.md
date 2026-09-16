---
title: TASK-0430 Pre-render selected image crops
status: done
last_updated: 2026-09-04
---

# TASK-0430 — Pre-render selected image crops

## Problem

Review currently performs full-resolution decode, render, two SHA-256 passes and
a filesystem write after every `F`/`ArrowRight`. This makes rapid inspection
feel frozen even though automatic band detection itself is bounded.

## Scope

- prepare every missing output crop before review in a serialized, resumable
  local pass,
- keep prepared output distinct from human review,
- make acceptance update only durable review state,
- rerender and replace only the current output after a manual line change,
- show separate preparation and review progress.

## Out of scope

- parallel image decoding, server jobs, API or database changes,
- automatic human acceptance,
- geometry, rotation or perspective correction.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Definition of Done

- all `cut` JPEGs exist before review becomes interactive,
- interrupted preparation resumes from persisted completed results,
- `F`/`ArrowRight` on an unchanged prepared crop performs no image render or
  checksum pass,
- edited lines replace only the matching owned output,
- legacy manifests treat already rendered results as reviewed,
- focused tests, lint, typecheck and Admin build pass.

## Outcome

- Added durable `reviewedFileNames`, preserving legacy manifests by treating
  their existing results as reviewed.
- Missing crops are detected, rendered, checksummed and journaled sequentially
  before review; restart skips completed outputs.
- Review loads the smaller files from `cut`. Unchanged `F`/`ArrowRight`
  updates only review state, while `Dostosuj linie` rerenders one owned output.
- Core and focused Admin tests plus both typechecks passed.
