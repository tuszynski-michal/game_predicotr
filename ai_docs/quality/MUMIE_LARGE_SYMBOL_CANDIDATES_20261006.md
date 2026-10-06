---
title: Mumie — większy zbiór dokładnych wycinków do treningu RGB
status: done
last_updated: 2026-10-06
---

# Evidence and scope

TASK-0871 prepared 2000 new unique exact rasters from 41 allowed third-recording
photos. Each of the 20 references contains 100 cases. Proposed CNN classes were
used only for deterministic sampling and were hidden from both reviewers.
The maximum contribution of one photo was 54 cases, below the cap of 80.

All source files, quads, dictionary bindings and rendered RGB96 PNGs were
verified. Preparation took 916.50 seconds; the controlled worker exited.
The first recording, withheld photos, human26/human8 whole-photo groups,
validation/diagnostic and all earlier human/AI pixels remain protected.
The exclusion union contains 526 crop pixel hashes. Original pins were checked
before merging newer evidence so newer hashes cannot mask an older drift.

# Actual blind assessments

Both independent reviewers inspected all 2000 native96 montage tiles, the
20 human anchors and ambiguous PNGs individually. Reviewer A recorded 1753 high,
184 medium and 63 unreadable cases. Reviewer B recorded 1756 high, 229 medium
and 15 low; 1985 readable and 15 unreadable. Each reviewer independently verified
all of their reports and PNG hashes in a new process. Neither read CNN proposals,
the other review or selection class counts.

Only equal high/high readable classes are accepted. This yields **1726 accepted
and 274 rejected** new AI assessments. Rejected cases do not create targets.

| Symbol | Accepted new AI cases |
|---|---:|
| 10 | 204 |
| J | 203 |
| Q | 203 |
| K | 204 |
| A | 203 |
| Ra | 128 |
| Sarkofag | 139 |
| Mumia | 109 |
| Faraon | 133 |
| Sfinks | 200 |

Gold-frame observations remain separate. No Super targets, human approvals or
operator history entries were created. These counts describe fallible AI
agreement; they are not model accuracy or a population measurement.

# Immutable artifact bindings

Artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-large-training-20261006`.

- Selection ID: `12645e8fdf7657c696035ddf77a750b7acfaf6e198a9265a16a1166789d769ff`.
- Selection file SHA: `afcb8b40c25e7fd78aac2e7d69ec84c0a42cb1e25e0c82a33033ae37add089fe`.
- Qualification ID: `8a57f640f741be76259ec0cd5f7f8a384638754910b94fd004ca2807b40b8ac8`.
- Qualification file SHA: `c48ba7af2689aa972aa97cfd18082c5c034392a854113b9e7bfeeec0808c5b20`.
- Qualified-visual pointer SHA: `1e9c841315217bcce7d55ba8ec75ed33ce4ac1d421bb203428e8f501307c3a32`.
- Full qualification pins: 11472 files, including all 40 reviews, 20 assessments,
  20 references, blind inputs, copied anchors and exact PNGs.

The final qualifier snapshots selection/reference/review SHA before consensus,
checks every source/quad/PNG through the existing render function and rechecks
all pins immediately before publishing. It binds copied anchor metadata and
bytes to the original human anchors. Aggregation recomputes every consensus
and checks cross-packet uniqueness and the entire forbidden-pixel union.

# Verification and audit

Fresh-process selection reproduced the immutable output in 47.06 s.
Fresh packet0 replay reproduced the existing reference and exact100 crops in
36.62 s. Both visual reviewers separately completed fresh-process report/PNG
validation. All20 packet assessments passed exact rendering and binding checks.
Final aggregate completed in 13.39 s; fresh aggregate replay reproduced the
same qualification ID, pointer and bytes in 14.86 s.

Twelve focused tests pass: source drift, deterministic photo caps/pixel uniqueness,
invalid limits, selection/case/quad/pixel/index/anchor binding, uncertainty,
duplicate reviewer, changed review raster, resigned proof-pointer identity and
re-encoded protected-photo pixel grouping. Ruff passes for all four local
helpers; mypy passes for the three executable helpers. The local pytest command
explicitly uses the worktree pyproject and source path; ancestor main-checkout
configuration must not import its older code.

The independent preparation audit verified 9351 original pins, all2000 actual
source/quad/rendered pixels and native montage tiles. All earlier checksum,
pointer, restart, review-snapshot and copied-anchor findings are closed.
The independent final audit passed: actual deterministic selection and rendering
of all 2000 crops, all 40 reviews and 20 proofs, all 11472 pins, 14 detached
negative guards and complete human26/human8 receipt lineage. No open P0–P2.
Both original 61-output sets are preserved; the rejected R2 pair's sidecar is
still absent. Final report, Outcome and CURRENT_STATE match stage A.

Local reproducible entrypoints are prepare.py, prepare_job.py, launch_prepare.ps1
and qualify.py under the artifact root. Each packet child has a 120-second
deadline. Restart checks the newly launched wrapper or its verified Python child,
selection ID/SHA, controller start timestamp and process creation time; an old
status cannot report readiness even if a PID is reused.
Own invalid prototype manifests/proofs were preserved in backup paths. No source,
review, original label or user data was deleted.

# Outcome and next boundary

No CNN was started in TASK-0871. No application code, API/UI/schema/DB, migration,
active model, merge, push or deployment changed. The accepted plan continues to
TASK-0872 after the final audit and separate commit. That task introduces a new
explicit larger RGB protocol; it does not relax generation4 or reference limits.

The target of 2000–3000 training cases does not override visual evidence. Only
the 1726 new agreed cases may be considered by the next isolated adapter, with
AI origin preserved and unchanged human/test cohorts. Training and geometry
quality must be evaluated separately.
