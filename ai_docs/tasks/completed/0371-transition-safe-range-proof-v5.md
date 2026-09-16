---
title: TASK-0371 — Transition-safe range proof v5
status: done
version: 0.10
---

# TASK-0371 — Transition-safe range proof v5

## Goal

Define a pure, versioned v5 range-proof domain before changing the locator or
worker runtime. A single row may establish only provisional evidence. Automatic
selection requires two agreeing visible rows and rejects a visible conflicting
row, protecting against transition frames.

## Scope

- v5 row offsets, expected-range table and confidence policy;
- provisional and verified range-proof types;
- fail-closed unknown reasons and pure final-validation function;
- domain tests only.

## Out of scope

- image processing, OCR runtime, grouping, worker integration, HTTP, API,
  migration, staging, filesystem mutation and database operations.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Definition of Done

- The module has no image, OCR-runtime, SQL, FastAPI or React dependency.
- A single row never authorizes automatic selection.
- Two agreeing rows authorize a candidate only with no complete conflicting or
  unreadable row.
- Existing v1–v4 contracts remain untouched.

## Outcome

- Added `range_proof_v5` as a pure, separately fingerprinted v5 contract.
- A row proof is provisional only; final verification requires two agreeing
  rows and rejects any complete unresolved or conflicting row.
- `13` focused v5 tests and `27` existing v4.1 range/grouping tests pass.
- No runtime, worker, API, migration, staging or database path changed.
