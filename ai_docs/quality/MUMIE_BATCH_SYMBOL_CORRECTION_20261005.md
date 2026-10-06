# TASK-0858 — batch crop correction verification

Status: PASS, 2026-10-05. Own audit; no delegation or operator labels created.

## Functional result

Existing Vision Lab `/symbols/batch` edits the exact 18 diagnostic RGB96 crops.
Click selects a case instead of opening its photo. Approved dictionary IDs,
explicit save, 1–9/0 shortcuts, unreadable/grid_issue and separate photo links.
Receipt-confirmed choices keep every PNG frozen. The next choice can be prepared
while saving. A lost reply retains the exact request; no second mutation is
allowed before acknowledgement or explicit reread. Reread remounts PNGs.
Desktop shows a sticky palette next to crops; mobile puts it above the gallery.

## Tests actually completed

- Backend: 56 passed across batch labels, symbol API/store/labels and lab API.
- Vision Lab UI: 62 passed, including the actual React editor click/load/save,
  pending navigation, next selection, lost reply, exact retry and fresh reread.
- API client: 15 passed, including existing routes and exact batch payload.
- Ruff: all changed Python modules/test passed; format applied.
- Mypy: strict targeted check with follow-imports=silent passed six modules.
  Initial silent run was interrupted after 67 seconds; skip-imports diagnostic
  was discarded because it loses typed dependencies. Final full targeted
  check passed in 71.12 seconds. No test or type rule was weakened.
- OpenAPI export --check and generated client --check passed.
- Client typecheck, UI typecheck/lint and final Next build passed.
- Fresh subprocess recovered both corrections and revision 2 on an isolated
  fixture. Lost reply and replay produced one decision/receipt per explicit
  action. Source/policy/PNG/reference/case/class drift blocked publication.
- Publisher test preserves the original gallery, binds exact case links and
  never writes human labels. Fault before atomic state publication recovers.

## Live verification

Reference: 48341730f870b38590286bffa7ff289649cd8c73f9fcc0907c81ac3c16754c54.
18 exact PNGs and ten original dictionary entries. Direct API preview 0.203 s;
existing proxy preview 0.172 s. All byte/pixel hashes match, revision 0,
decision_id/symbol_id null, no decision state file created.

The saved launcher configuration includes absolute reference/label paths.
Controlled restart confirmed owned API PID 37604 and UI PID 10284 ready on
8102/3102. Main application services were not restarted. Browser selection
changed only the local choice; save was never clicked on real data. It was
cleared by an explicit reread. The editor is left open for the operator.
390×844 check: content width 375, every panel button height 44, no horizontal
overflow. Temporary viewport was reset. A screenshot records the visible
selected crop, palette and save button.

Original annotations rev591 SHA:
06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43.
Original symbols rev63 SHA:
fa518e34b5547eec3b09e7158126a3c01b976bc989b472fa0c21ac54cb046e02.
Both verified unchanged in a fresh process after API/UI restart.

## Audit and acceptance

All TASK-0858 acceptance criteria covered by the tests and live checks above.
Whole-board approval, sequence numbering, DB, migrations, training, model
activation, merge/push and production deployment remain outside this task.
New crop reviews remain trainable=false with explicit geometry/split blockers.
They need a later qualification/evaluation task after the operator chooses
the true classes. No unsupported accuracy claim or fabricated label.

Known existing warnings: Starlette/React renderer deprecations and Next's
multiple lockfile workspace-root warning. They did not fail changed checks.

## Operator artifacts and restart

Root: C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-symbol-batch-correction-20261005.
Persistent config: artifacts/mumie-symbol-dataset-version-20261005/runtime.json
under the main checkout. Actual decision state is under its BatchLabels root;
the original symbolstore is preserved. Runtime verification and screenshot
are runtime-verification.json and editor-ready.jpg in the new artifact root.

From a new PowerShell process, use the absolute worktree launcher path with
`-Action Start -Config` pointing to that saved absolute config. An already
running owned pair returns Status; Stop only terminates recorded identities.
Gallery regeneration: the versioned symbol_batch_labels CLI accepts
`--reference <absolute reference root> --gallery <absolute cases-parent/review.html>`.
It preserves review.before-editing.html and refuses another destination.
