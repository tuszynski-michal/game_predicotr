# TASK-0852 — symbol review performance verification

Date: 2026-10-05. Branch: feat/grid-engine-v3. Scope: local Vision Lab symbols.

## Findings and behavior

The previous parent reloaded labels/dictionaries and the complete crop queue after
each write. Toggling queue `enabled` with the parent's busy/pending state also
started another queue read. A 500-item page required 17 sequential crop requests;
returning to a nonzero offset could require two full page series.

The queue now reads up to 2000 items in one existing lab_queue request. The default
backend limit remains 30, and writes still accept at most 30 bindings. PNG bytes
are bounded to 48 MiB before another crop is rendered. No partial response is
returned on failure. The validated labels-only grant avoids one redundant legacy
pilot-current check; all authorization and ordinary holdout checks remain.

The user explicitly requested frozen thumbnails until refresh. A matching,
valid receipt advances CAS and marks exactly the submitted bindings as assigned.
Images, tile positions and the next selection stay. Submitted/saved fields and a
second submit are disabled, while other fields and the next class remain editable
during an acknowledged write. Response loss locks editing and retains the exact
request for retry. The original read token is never renewed locally. Page
navigation first obtains a fresh server token with limit=1 and adjusts the offset
for locally assigned tiles. Old label-list rows are hidden until explicit read.

## Measurements on existing data (bounded diagnostic reads)

- Original 30-item crop request: 2.059 s with cProfile; 50 label rows: 3.335 s.
- New single 2000-item request: 5.464 s, 32.34 MiB of base64 PNG data.
- This is a crop-read measurement, not a measured user write latency or a load test.
- Real UI after restart: 2000 tiles; 64 lazily loaded images, 64 enabled fields,
  enabled symbol selector, no browser console errors. No labels submitted by agent.

## Verification results

- Focused Python: 57 passed (labels/store/board/API/candidates/dataset version).
- Snapshot and whole-game protection: 16 passed. Total Python: 73.
- Real React interactions and symbol workflow: 37 passed. Includes two batches,
  choosing the next class/field during a deferred write, lost response, identical
  replay, preserved images, no automatic read of an already open board and new token
  before navigation. The harness explicitly
  uses the app's pinned React for renderer/shared components; existing workspace
  React 19.2.8 and app React 19.2.3 otherwise produced invalid-hook failures.
- Client request tests: 5 passed, including one request for 2000 items, read token,
  changed/incomplete view rejection, FIFO and bounded preview timeout.
- Ruff format/check, scoped Mypy (3 modules), scoped Prettier, ESLint, UI/client
  TypeScript, OpenAPI export check and generated-client drift: PASS.
- Generated client regenerated; numeric limit has the same TypeScript shape.
  OpenAPI records maximum=2000; no artificial changes to generated types.
- Next production build: PASS, 7.88 s. Existing warning about duplicate workspace
  lockfiles/root inference remains outside scope; no new build failures.

## Restart and preserved operator state

Owned API/UI stopped while annotation and symbol locks were held. Existing files
were copied/hash-checked before stopping; no in-flight writer could be interrupted
inside publication. Start and Status ran from new PowerShell processes using the
existing persistent config and launcher. Final API PID=18980, UI PID=18320;
both independently verified ready. A diagnostic wrapper using captured subprocess
pipes timed out after its completed rebuild/start; detached Windows descendants
retained the pipe. The bounded runner terminated only that wrapper. The managed
services stayed ready, and both state hashes stayed identical. Diagnostic helper
now captures launcher output to files rather than inherited pipes. This is not a
failure of label publication or the persistent launcher.

- Symbol revision 63, 1045 historical decisions, 583 latest Mumie approve records;
  this count does not infer label validity for historical geometry/dictionary versions.
- Symbol state SHA256 before/after restart:
  `fa518e34b5547eec3b09e7158126a3c01b976bc989b472fa0c21ac54cb046e02`.
- Geometry state SHA256 before/after restart:
  `06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43`.
- Operator continued labeling during diagnosis; earlier revisions are not treated
  as immutable baselines. The baseline was captured immediately before restart.
- Artifacts: main checkout artifacts/mumie-symbol-review-performance-20261005;
  screenshot panel.jpg, bulk-read.json, before-restart.json and exact state copy.
- No DB writes/migrations, training, model activation, shadow, push or merge.
  No computer restart attempted. No unsaved selection in the user's tab was reset
  by the agent; browser verification used a separate read-only tab.

## Separate self-review

Acceptance criteria reviewed against task, D-497 and the updated Vision Lab
requirements/architecture. PASS: default behavior, write cap, whole-game/source
protection, immutable binding identity, receipt validation, CAS, exact retry,
read-token freshness, bounded read size, persistent restart and retained labels.
No unresolved P0–P2. Initial rendering still takes several seconds. A lost
response still requires explicit retry/read; it cannot safely be treated as saved.

## Next interaction

Reload the symbols page once to use the new bundle, after confirming any pending
old-page write. Continue selecting up to 30 fields for one class. Frozen saved
tiles remain until explicit queue refresh or navigation. Symbol training remains
a separate task with the existing provenance/split gates.
