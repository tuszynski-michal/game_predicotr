---
title: Mumie automatic import and symbol verification acceptance
status: accepted_scoped
last_updated: 2026-10-06
---

# TASK-0886 acceptance

MAIN branch: v1.1-vision-lab-hybrid-geometry. Starting commit:
v1.7.227 / c5549084291aef97068a63da5a8573f4d737152c.
The user authorized implementation, deployment and non-destructive Mumie
recovery. No new schema migration or model activation was needed.

## Acceptance against the execution plan

| Criterion | Evidence | Result |
|---|---|---|
| Full bound slots produce fifteen pending cells | Actual renderer and PostgreSQL projection test; real 891-board recovery | PASS |
| Missing/partial slots defer individually without compacting sequence | Worker sparse binding regression and incomplete-source PostgreSQL test | PASS |
| Exact 24-node lattice and reproducible legacy policy | Interior-node perturbation retained, legacy no-policy tests and versioned stage/fingerprint | PASS |
| Human owners and retry-safe reprocess | Cold projection replay, managed HTTP retry returns same job; exact before/after human metadata | PASS |
| Empty readiness and historical recovery | Real empty/history test, orphan durable job recovery, bounded count reconstruction | PASS |
| Useful preparation UI | Orphan starts once, failed start has resume, cold mount reuses job, previous-game response cannot overwrite current game | PASS |
| Bulk Mumie approval | Two visible crops approved through existing operation; outside blocked; legacy default disabled | PASS |
| Existing Mumie recovery | Existing managed originals and strict manifest v13 reused; projection and counts ready | PASS |
| Scoped checks and live acceptance | Focused suites, real PostgreSQL HTTP, generated contract, lint/types/build and actual Admin inspection | PASS |

## Live result

- Game fea55cc1-ebf4-4cee-b3ab-a520017ed1be retains 100 managed originals.
  Ninety-nine bound sources produce 891 current boards and 13,365 current
  symbol cells. Zero import failures and zero unresolved pending geometry
  among those bound boards. The unbound ending photo remains a source-binding
  correction; it is not a fabricated board.
- Reprocess af474e46-28bc-404d-af1c-07aeb05a165c finished processing 99/99
  sources and 199/199 pipeline steps, without error. waiting_for_review means
  operator symbol verification, not mandatory individual grid approval.
  Retrying the public reprocess endpoint returned this same job.
- 847 old unreviewed pending records became superseded; their history remains.
  All 44 previously human-approved geometries and the two captured human
  cell decisions match their original snapshot exactly. New operator decisions
  were not overwritten. Mumie and 777 model activation histories are unchanged.
- Final projection is ready, expected/persisted 13,365 cells and 891 boards,
  no invalid geometry/crop, no active backfill. Historical counts were separately
  repaired through durable backfill 13aabb68-aa50-42b7-9176-81552ca9b651,
  completed without error. Public count snapshot revision174 reports 13,365:
  40 approved and 13,325 pending.
- Actual Admin3000 inspection: Mumie, Mumia, page size2000, 423 rendered
  pending Mumia crops, exact counters, no preparation message. Selecting the
  page enables approval; selection was cleared without saving human decisions.
  Source preview remains a separate action. Inspection did not guess labels.

## Verification

- Focused initial API/worker regressions: 108 passed. Managed evidence/owner
  protection: 21 passed. Additional lateral scoped regression: 15 passed.
  These suites overlap and are not an aggregate unique-test count.
- Real isolated PostgreSQL automatic import, exact rendering, current HTTP
  symbol reassignment without geometry approval, cold replay, historical counts
  on fresh sessions, empty/history readiness: final two passed, zero skipped.
  Separate manual neural-slot HTTP regression: one passed.
- Count interleaving/cold cursor and worker finalization regressions: 12 passed.
- Admin changed interaction scope: final nine passed, including previous-game
  in-flight recovery. Generated SDK request suite: 78 passed.
- OpenAPI export and SDK generation checks passed. Scoped Ruff/format,
  Admin ESLint/types, SDK types, strict owned-source mypy passed. Third-party
  Torch/Torchvision import graphs were skipped by the explicit scoped mypy
  config; this is not a full-repository mypy pass.
- Admin production build passed. Fresh API/general-worker processes and actual
  HTTP/UI checks demonstrate that the fix is not limited to an old in-memory
  session. Physical Android hardware and a full operating-system reboot were
  not exercised; existing touch controls/layout were reused.

Two unrelated failures were reproduced on the unchanged HEAD implementation:
the partial-review bulk unreadable badge test expects immediate reconciliation
despite the frozen-page workflow; the public lateral browser fixture fails
existing JobResponse validation for missing job fields. They remain outside
this commit. Full-suite green status is not claimed. Baseline proof receipts
are 0886-ui-baseline-proof and 0886-schema-baseline-proof.

## Review and limits

Separate self-review compared all nine criteria with the accepted plan,
source identity, deterministic sequence, current crop training provenance,
human protection and existing API/legacy defaults. No open scoped P0–P2.
Structural crop availability does not certify population recognition accuracy.
No full database backup, cleanup, 777 recovery, new training/promotion, Super
mechanics, Redis/Celery or population load benchmark was executed.

Operator next step: bulk verify the existing crops, mark wrong cuts, then upload
about 500 photos followed by 2000. Training uses pooled human feedback rather
than requiring a fresh training session after every upload. Neural geometry
training remains a separate snapshot workflow described in the operator guide.

Detailed bounded check receipts are under artifacts/grid-v3-deployment-20261004;
human before/after, final counts and managed recovery evidence are under
artifacts/mumie-main-app-pilot-20261006. Artifacts are local and excluded from
the commit.
