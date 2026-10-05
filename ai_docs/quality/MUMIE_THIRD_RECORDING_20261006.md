---
title: Mumie — third independent recording diagnosis and exact review
status: done
last_updated: 2026-10-06
---

# TASK-0863 evidence

The operator's new `C:\Users\tuszy\Documents\mumie\24517 - 50112 cut`
contains2,844 images from a separate film. The two moved previous directories
retain their original recording identity. D-503 records the declaration that
each future new directory in this set is a different film, subject to technical
alias/SHA checks. No repeated recording question is required.

Full inventory has0 byte duplicates and0 byte matches to excluded training,
validation, diagnostic or protected sources. Sixty deterministic evenly spaced
photos cover seq_24517–24525 through seq_50104–50112. The batch excludes2,699
source identities, including the entire feedback recording and all protected/
family/alias closures, plus30 known complete-photo pixel identities. Current
physical source bindings and the persisted location sidecar remain pinned.

## Qualified model and actual coverage

The single generation3 pair qualified in TASK-0861: RGB/gray/fusion83/84 on
identical frozen validation, no per-class regression against V1, CPU Torch/ORT
parity84 per branch. Eighteen training-feedback targets are18/18, limited
post-selection diagnostics9/9; these are not new-film accuracy. Batch admission
recomputes the actual class gate from pinned real V1/current reports rather than
trusting a boolean, and keeps validation calibration fixed. No further training.

| Measured diagnostic | Count |
|---|---:|
| Photos | 60 |
| Filename-expected boards | 540 |
| Detected/selected boards | 540/540 |
| Count anomalies | 0 |
| Cut/predicted cells | 8100/8100 |
| Unavailable cells | 0 |
| Model-uncertain cells | 424 (5.23%) |
| RGB/gray disagreements | 37 (0.46%) |

Matching filename counts and structural checks are not human approval of540
grids. Visual inspection of the first/last overlay found boards aligned with
their visible rows/columns; this is a limited check, not geometry accuracy.
There are no ground-truth labels for this film, so accuracy remains null.
Confidence/coverage are not correctness. White drawn marks and occlusions
remain visible in exact review crops; unreadable/grid-issue actions remain
available. Super frames have no human labels and are outside this task.

## Concrete usable review

Twenty-four immutable RGB96 PNGs from15 photos cover two proposals per each
of the10 approved classes plus four additional uncertain cases. These are
model-selected diagnostic proposals, not generated labels. Reference:
`82f925f2a6f14ac549658cd230f65f41aef07e411b7ae21e86cea0c76892d27a`. New review revision0, all24 pending; original18 decisions remain
unchanged. Exact SHA/pixel/quad and per-case source rendering were checked.

D-504 preparation validates the complete qualified batch/cohort and original
approval dictionary. New V3 packets reuse the matching original D-498 approval
provenance, current history/geometry guards, immutable cohort/batch and exact
case sources, without rehashing all2,052 unrelated feedback photos on every
UI operation. Review remains trainable=false. Future training qualification
must repeat complete source/decision/split gates. Existing references/defaults
remain unchanged. No HTTP/API/OpenAPI contract or frontend code changed.

Actual browser shows0/24, direct selection, all10 palette entries, shortcuts
1–9/0 and explicit save, with separate unreadable/grid-issue actions. The editor
does not require changing a correct grid. Read-only live crop previews returned
the exact new reference and24 pending items through backend and UI proxy:
0.110s/0.109s in this local smoke check, not an SLA or save benchmark.
Both review galleries and editor returned HTTP200.

- Editor: http://127.0.0.1:3102/symbols/batch
- Click-to-edit case portal: http://127.0.0.1:8108/third-symbol-review-priority/review.html
- All60 diagnostic photos: http://127.0.0.1:8108/third-24517-50112-v3-60/review.html

The saved runtime.json points to the new reference/label root. Only recorded,
identity-matching lab API/UI processes were restarted through the existing
launcher; production services were not restarted. New API25800/UI23928 match
saved commands. Use PowerShell7 (`pwsh.exe`) for the existing launcher: Windows
PowerShell5.1 cannot execute its IsPathFullyQualified preflight. The failed5.1
attempt stopped before any process mutation; the7 invocation succeeded in new
processes. Runtime before the switch is preserved in runtime.before-third-review.json.

## Durability and verification

Controlled driver PID44612 completed in three portions25/25/10 with a600s
budget and bounded110s child-tree runners. The driver and children exited.
Each photo result is create-only and source/assets-bound. A new-process replay
performed0 photos and reproduced the summary, exact review preparation and all
270 artifact hashes. All original evaluation/source/store/model pins
remained unchanged. This covers process restart/retry; no computer reboot was
performed. Saved runtime and new-process launcher/readback establish persistence.

Forty-two focused batch/input/editor-backend tests and36 feedback/augmentation
regressions pass. They cover relocation/external exclusions, strict old default,
explicit fresh geometry, real-reference gate, claimed pooled-score class
regression, source/reference/baseline drift, exact crop review/current guards,
and lost-response/new-process replay. Ruff lint/format and scoped strict mypy
pass for all changed source modules, with explicit Torch/ONNX dependency
boundaries. No frontend/schema change; build/OpenAPI regeneration not applicable.
The first new test fixture put cohort metadata at its entire fixture root and
correctly hit the output-overlap guard; separate input/output roots fixed the
fixture without weakening that guard. The import-order lint issue was fixed.

Separate final review: no unresolved P0–P2. Acceptance criteria1–5 and applicable
Definition of Done met: independent exclusions, real60-source results, usable
exact review, bounded/PID-aware execution and restart, tests/documentation/commit.
Commit v1.7.210 on feat/grid-engine-v3. Previous data/decisions/runs unchanged;
pre-existing unrelated worktree metadata edits excluded from this task commit.

## Human boundary and operations

The operator must now classify the24 actual new crops in the editor. Choose
the visible class, then Save; use unreadable or grid issue when appropriate.
No additional30-per-class batch or folder upload is needed at this boundary.
Without these human labels, further accuracy/feedback qualification cannot be
claimed. The ready portal points to specific cases rather than only full photos.

Absolute persistent restart/status commands:

```powershell
& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_symbol_review.ps1' -Action Status -Config 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json'
& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_symbol_review.ps1' -Action Start -Config 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json'
```

Evidence lives under `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-feedback-20261005`: third-inventory, third-operation/status,
third-review-ready, third-replay, third-http; independent photos/gallery under
the separate third-24517-50112-v3-60 artifact. No DB/migrations/deletion,
pseudo-labels, new training, model activation, merge/push or production deployment.
