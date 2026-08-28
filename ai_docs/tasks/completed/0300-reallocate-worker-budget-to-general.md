---
title: Reallocate local worker budget to the general lane
status: done
version: 0.8
relevant_docs:
  - ai_docs/architecture/SYSTEM_ARCHITECTURE.md
  - ai_docs/guides/LOCAL_OPERATION_GUIDE.md
  - ai_docs/process/CURRENT_STATE.md
---

# TASK-0300: Reallocate local worker budget to the general lane

## Goal

Use the workstation's seven available processing slots for general jobs while
automatic image selection is not used, without oversubscribing native OpenCV
threads or allowing two general jobs to mutate shared projections at once.

## Scope

- make the default supervised startup run only the general lane,
- assign a cooperative budget of seven workers to the general lane,
- bind page-geometry registration parallelism to that budget,
- keep native image-library parallelism at one thread per registered page,
- retain an explicit command for starting both historical lanes with the safe
  `2 + 5` split when image selection is needed again,
- update focused tests and operator documentation.

## Invariants

- PostgreSQL continues to allow only one processing job per execution slot,
- image-selection jobs remain claimable only by the dedicated lane,
- no image-selection process starts in the default general-only profile,
- changing the budget does not change job payloads, checkpoints or results,
- the setting is durable across a new terminal and computer restart.

## Outcome

- `npm run workers:start` now launches only general with budget 7.
- `npm run workers:start:all` retains the explicit safe 2+5 dual-lane profile.
- General page-geometry registration consumes the cooperative budget while
  native OpenCV/BLAS work remains single-threaded per page.
- The general execution slot remains unique and image selection retains its
  dedicated job type and lane.
- Focused worker tests, Ruff, formatting, mypy, JSON and PowerShell syntax
  checks passed.  No benchmark was executed.
