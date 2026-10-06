---
title: Mumie — neural folder import and correction acceptance
status: done
last_updated: 2026-10-06
---

# Scope and result

TASK-0882 connects the frozen Mumie neural grid engine to the existing folder
preflight, durable pending and correction workflow. Every proposal remains
unqualified until a human decision. This report concerns implementation and
isolated acceptance, not deployment to the operator database.

The existing page override owner now stores an explicit source binding with
the original and confirmed filename ranges, immutable proposal checksum,
detection-to-slot assignments, missing positions and ignored detections.
Migration0145 adds that optional binding without changing legacy quad rules.
No board or sequence is fabricated for an unbound source. The corrected
499996–500000 range retains its original499996–500004 filename provenance.
Missing position2 in101–105 preserves103 as missing and the next board as104.

Mumie staging uses the neutral geometry_core and pinned CPU ONNX artifacts.
Bound proposals become durable board pending with exact24 float nodes;
unbound sources remain in the existing source correction owner. A source-only
inference deadline persists pending and continues the batch after reaping its
child. Startup failure, source/model drift, cancellation and cleanup failure
abort rather than publish a mixed manifest. Checkpoint replay skips inference.

The Admin Import button accepts a completed neural manifest containing review
items, including an all-unbound source-only import. Managed source handoff,
asset access, exclusions and re-preflight survive staging retention and a new
process. A new descriptor cannot overtake an active import. An identical
descriptor recovers the original job after response loss.

Reviewer previews, edits, renders and saves all24 nodes without rebuilding
their interior from four corners. Symbol selection is available on opening a
valid proposal. A symbol edit keeps the geometry. Source/manifest/revision
checks prevent stale saves and protect approved geometry. Durable draft
storage preserves an exact retry after remount. The old777 defaults remain.

# Acceptance evidence

All paths below are under
C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004
unless stated otherwise. Counts overlap between focused and regression runs;
they must not be summed as a unique test count.

- Root new contracts/runtime/preflight/pipeline:41 PASS.
  `0882-root-final-new-tests.json`.
- Broader production/source/import/manual-symbol regressions:120 PASS.
  `0882-root-broader-production.json`.
- Managed exclusion/source regressions:24 PASS.
  `0882-root-managed-exclusions-repaired.json`.
- Independent backend focused rerun:96 PASS,0 skipped. It covers full nodes,
  source drift before/during decode, removed lattice fields, strict transport
  types, all-unbound HTTP import, descriptor conflict and response-loss replay.
- Guarded disposable PostgreSQL:1 PASS,0 skipped,9 invalid nested bindings
  rejected. Populated0144→0145 upgrade preserves legacy rows and partitions;
  application-role CAS, cold-process receipt replay, RLS and fail-closed
  downgrade are verified. `0882-isolated-pg-final-proof.json`.
- Client request/legacy regressions:86 PASS. OpenAPI export, generated client
  drift check and client typecheck PASS. Backend proof:
  `0882-backend-final-proof.json`.
- UI pure41 and final import/legacy66 PASS. Reviewer interactions15 PASS;
  Admin interactions21 PASS, including the actual Import panel with99 review
  sources and managed source-only recovery. UI typecheck, focused lint,
  formatting and both production builds PASS. Admin lint retains one existing
  image warning in the final import scope.
- Mobile browser smoke PASS at390×844 and360×844 using Edge/Chromium touch
  emulation. Range confirmation, symbol editing and inner-node dragging work
  without horizontal overflow or browser errors. Physical Android was not
  tested. UI proof and four screenshots are in the worktree:
  artifacts/neural-lattice-mobile-smoke/ui-proof-allowlist.json.
- Root Ruff/format12 files and scoped strict Mypy7 modules PASS. Backend
  strict scoped Mypy27 modules, models and main composition PASS (29 sources).
  Earlier combined checks reached their bounded deadlines and are not PASS.

# Real-photo diagnostic

The actual production staging handler processed100 immutable photographs from
the three independently recorded folders in five20-source steps. The selection
SHA is a05827b5dac322d5d1d9c3f02c8a92f04e69630c36a2dae4439f2c2e275af922.
It retained900 filename positions, produced897 structurally valid full24-node
proposals and13455 full cell quads. There are99 ordered binding drafts and one
unbound source, seq_499996-500004.jpg, with six neural detections and five
visually numbered boards. Its range and ignored detection require an explicit
human correction. No canonical sequence is inferred for that source.

Each command completed below20 seconds. Fresh Python replay of batches0/4
reproduced the original manifest checksum with zero inference. The independent
audit verified all five manifests, source pins, checkpoint links and counts.
Report:
C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\adapter-diagnostic-100-deskew\summary.json.

A separate20-photo memory observation reproduced the same batch0 manifest.
It took16.75 seconds in the handler. Windows reported a parent process peak of
130682880 bytes and neural child peak of433102848 bytes. These are separate
process peaks, not simultaneous total resident memory. Resource report:
C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\adapter-memory-20\batch-0-resources.json.

These figures establish structural proposals, counts and replay behavior.
They do not measure population symbol accuracy or authorize training on
predictions. The operator upload folder contains identical copies of these
100 sources (31167375 bytes), with unchanged filenames and originals.

# Independent acceptance

Final independent review gpt-6.1-sol/high: PASS,0 openP0–P2. All seven criteria
and accepted0882 scope are covered.82 file hashes and quality receipts were
checked. Close with a separatev1.7.224 commit and continue0883.

# Deployment boundary and next step

No operator database migration/write, main merge, model activation or service
restart occurred. The live database remains0143, with zero Mumie source images
and boards. Concurrent RGB777 CLI work remains active and untouched.

After final independent acceptance and a separate task commit, continue
TASK-0883: protected whole-photo training membership, approved exact-node
geometry export, complete feedback acceptance and the operator guide. Then
prepare the specific0144/0145 migration, backup, artifact, activation and
service preview for TASK-0884. No additional labels are needed to implement
that preparation.
