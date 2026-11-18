# TASK-1246 — Mumie A2 activation and two-staging processing

Verified 2026-11-18, 03:17 UTC through fresh owner-API reads. The operator
explicitly approved the concrete repair, merge/push, API-only restart,
activation/processing scope and final branch/worktree cleanup.

## Deployed model and repair

- Mumie A2: `246a1f54-eee8-49d5-b11a-0fde70e5eecd`.
- Active grid model: `6cc10344-1d69-5765-b8c8-423a0313984a`, assignment revision 7.
- Publication revision 1; evaluation report `e74c552e-25e3-55dd-884f-3d0a4feb0c8e`;
  all 25 currentness notices proven before publication/activation.
- Previous assignment `abe39bce-dd29-549b-ac66-8ce4283d7598` is preserved.
- Global default remains `01767a49-980e-5ab6-962e-e22d8414a93e`, revision 5.
  The symbol-classifier assignment was not changed. This is a grid-model rollout.
- Code commit: `cbc1463c829dd2574635c63634f9a3a557f7d107` (v1.7.671), main/origin.
  New browser preflight follows the active assignment; managed-source resumes
  and saved human detection bindings retain their immutable model pins.
- No migration, new training or worker restart. API-only deployment restart.

## Persisted processing results

Both new preflights and imports pin the exact active grid version above.
Both imports finished processing on attempt 1 with zero failed photos and are
`waiting_for_review`. That state means human decisions remain, not stalled work.

| Folder | Photos processed | Ready boards | Pending symbol cells |
|---|---:|---:|---:|
| 398584 - 373591 (`40ceb31e`) | 2778 / 2778 | 24993 | 374895 |
| 423676-398592 (`2e027bed`) | 2789 / 2789 | 25090 | 376350 |
| Total | 5567 / 5567 | 50083 | 751245 |

- First preflight `c79e8f6e-2451-46fe-b46a-8639c162d1a5`;
  import `5fd0aca9-b703-430b-a666-f5cbf31609df`.
  Geometry SHA `fc0551be60e138e2526150229892c10e60fbbbb989f5d0d8f270b371fffd425e`.
- Second preflight `aa4f9993-4936-498c-ac6e-432c55b22ec9`;
  import `02379ba9-d694-4975-8ea7-241a50aa3c09`.
  Geometry SHA `87373a5124bb20149869a3f14c32c61081cc25d0814d498de589b3dfc104b3f0`.
- Zero unbound sources in both previews; no source exclusion or guessed sequence.
- Actual filename ranges are 373591–398592 and 398584–423684. Their nine
  overlapping positions are different photo bytes. All 5567 source checksums
  are distinct. Canonical ownership retained positions 373591–373599 from
  prior data and 398584–398592 from the first import; no human work overwritten.
- First folder has 2777 complete images and one superseded image. Second has
  2786 complete images, one superseded image, and two incomplete images.
  Boards **404094** and **407991** are deferred with `incomplete_lattice`;
  each needs manual geometry correction. The other eight boards on each of
  those photos are ready. No acceptance exception was entered.
- Symbol-review API returned pending items filtered to each exact import.
  Six real crop assets (three per folder), bound to crop/render-spec checksums,
  rendered and decoded successfully. No labels or crop approvals were entered.

Open [Admin](http://127.0.0.1:3000), select Mumie A2, then Symbol Verification
and the relevant folder. The two deferred boards are visible in geometry review.

## Validation and preservation

- 121 focused/regression tests PASS; the original HTTP regression failed on old
  code as expected. Restart/lost-response replay, real completed old-model
  manifests, protected bindings and managed-source preservation are covered.
- Scoped format/lint, OpenAPI freshness, code maps and documentation PASS.
  The changed-module type check passed with pre-existing import artifacts
  excluded; full project typecheck is not claimed (see task Outcome).
- [Claude round-2 audit](TASK-1246_AUDIT_claude-opus-5-5.md): PASS, 0 P0/P1/P2.
  No production-code change followed this audit.
- Both lost import-start responses were recovered by reading unique persisted
  jobs. No duplicate start was issued. The original wrong-model preflight is
  retained as historical evidence and is not used by either accepted import.
- Full-byte post-operation verification: all 5567 staged originals and both
  immutable source manifests match the pre-operation baseline.
- All 45 tracked operator changes and 17 untracked files were preserved during
  deployment; unrelated worktree directories and worker processes were retained.
  Recovery stash/byte backups remain. Final evidence integration preserves them.

Detailed local receipt: `D:/game_predicotr/.runtime/task1246-deployment.json`.
Per-import geometry/review proofs and observation log share the prefix
`D:/game_predicotr/.runtime/new-model-stagings-`. Source baseline SHA:
`fd4f9bbdc2a589bb823d0be5eae3f914605813b72a3fdb456d73bfaff6a6ba11`.
Raw audit evidence is preserved outside the worktree in
`D:/game_predicotr/.runtime/task1246-audit-evidence/` with a checksum manifest.
