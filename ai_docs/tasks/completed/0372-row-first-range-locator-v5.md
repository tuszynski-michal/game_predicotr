---
title: TASK-0372 — Row-first range locator v5
status: done
version: 0.10
---

# TASK-0372 — Row-first range locator v5

## Goal

Provide a versioned, source-local locator that finds independent top, middle
and bottom numeric rows without needing a full affine 3×3 lattice.  It must
support two visible rows, perspective and number/control merges, but may not
recognize text or decide ranges.

## Scope

- Independent horizontal row hypotheses and progressive ROI.
- Baseline fitting with perspective tolerance.
- Split defensible wide number/control components.
- Position-only row assignment, optional locked position prior and
  source-resolution crop extraction.
- Focused synthetic tests plus a bounded read-only check of the two reported
  real source examples.

## Out of scope

- OCR runtime, grouping, worker integration, API, migrations, jobs, staging,
  database writes and filesystem mutation.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Definition of Done

- The new locator does not alter v1–v4.1 behavior.
- It emits independent source-local rows, including two visible rows, without
  requiring seven lattice cells.
- A position prior has no numeric information and cannot establish a range.
- A number/control merge does not make a complete row unavailable.
- No OCR, geometry, cropper or symbol path is invoked.

## Outcome

- Added a separately fingerprinted `row_first_locator_v5` with progressive
  ROI, independent horizontal triplets, perspective-tolerant baseline fitting
  and source-resolution crop extraction.
- The optional position prior maps only row geometry; it has no numeric field
  and cannot establish a range.
- A bounded, read-only check located the visible top row on
  `blazing 21400_010501.jpg` (`33256–33264`) and top, middle and bottom rows
  on `blazing 21400_016501.jpg` (`40753–40761`). It performed no OCR or
  downstream image processing.
- `8` focused locator tests, Ruff and mypy pass. Existing v4.1 modules were
  not changed.
