---
title: Mumie — exact crop feedback qualification
status: verified
last_updated: 2026-10-06
---

# TASK-0860 qualification evidence

The operator completed 18 corrections and confirmed that capture 481537–500000
is different from validation capture 76555–103221. Independence from capture
1–23175 was already confirmed. D-502 qualifies only the exact reviewed raster
for symbol classification; it does not approve a board or geometry target.

## Immutable inputs and split

Artifact root: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-feedback-20261005`.
Pack: `c1392fb1954543a2d7b2aeb9c6fb9f5ccd093a1d20b7262a389fcf9c473f8b60`.
Composite manifest: `0cff2a15ea44aeb2fc77311845ae6d3190060891d65ef1549c4fd5e6d01e3de4`.
Base manifest: `d5dc865287ca2d4583b450ccdca84f6186e16ac86922dc6f95ebea3930151589`.

The pack retains the full revision-18 history, receipts, original reference,
approved dictionary and 18 exact PNGs from 17 photos. All 2,052 files in the
new recording belong to one component. Known SHA aliases and all original
components remain closed. Protected, validation, diagnostic, other-game and
comparison members reject the new development component before its pixels.
Source byte checks cover the full new folder; photo-pixel checks cover reviewed
photos and the base cohort. Unknown recoded duplicates outside these photos
are not claimed to be detected. Recording declarations remain necessary.

| Class | Development | Validation | Diagnostic test |
|---|---:|---:|---:|
| 10 | 21 | 12 | 0 |
| J | 32 | 4 | 0 |
| Q | 23 | 10 | 0 |
| K | 22 | 9 | 0 |
| A | 20 | 11 | 0 |
| Ra | 27 | 5 | 0 |
| Sarkofag | 38 | 12 | 0 |
| Mumia | 19 | 8 | 1 |
| Faraon | 37 | 9 | 0 |
| Sfinks | 25 | 4 | 8 |
| Total | 264 | 84 | 9 |

The first complete recording family moves to diagnostic_test only in this
new cohort. Its nine labels never enter generation-3 training. This small
diagnostic includes two classes and is not a blind final test: older models
saw these labels. Validation stays unchanged. The 18 corrections now belong
to training and cannot measure independent accuracy.

## Verification and separate review

Twenty new tests pass: latest replacement/non-class exclusion, complete history,
receipt integrity, create-only retry, new-process pack verification, directory
isolation, full-folder hidden aliases, role/game/protected gates, split closure,
photo/crop conflicts, source/label/PNG/count/inventory drift and lost publication
reply. The existing manifest, batch and batch-label suites pass 42 tests.

Real prepare, freeze, fresh-process verify and identical freeze retry preserve
the same manifest and every pinned original SHA. Original batch decisions remain
trainable=false. The old D-498 adapter rejects the new format. Local run dispatch
accepts it only through the separate classifier feedback adapter. No HTTP or UI
contract changes, database writes, model activation or deployment occurred.

Scoped Ruff and strict mypy checks cover the changed modules. The first mypy
attempt reached its 120-second timeout while analyzing dependency libraries;
the replacement uses explicit Torch/ONNX import boundaries, retaining strict
checking of project modules. The controlled runner terminates the child tree.

Separate review checked each acceptance criterion against code, the frozen
manifest, test evidence and the accepted plan. No unresolved P0–P2 finding.
TASK-0861 may now perform the single bounded generation-3 pair.
