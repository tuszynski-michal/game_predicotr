---
title: TASK-1050 — Photo crop pilot on operator data (plan, awaiting decision)
status: todo
last_updated: 2026-10-17
---

# TASK-1050 — Photo crop pilot on operator data

## Status

`todo` — plan for operator acceptance. A blocker (below) needs a decision first.

## Goal

A measured result on the operator's data for a small set of originals: crops
created and verified, then (only if decided) originals deleted, with Admin and
Reviewer checked and a report with bytes, time per original and an
extrapolation for the eligible library. Every step that writes data has its
own preview and its own operator consent.

## Context

Stage C of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md)
(section TASK-1050). Stages A and B are in `main` (`c3d0fec5`); the operator
database is at `0168_source_crop_runs` (manifest v19), with no crop run and no
crop. The pilot set is the 40 P1 originals of the accepted gallery
(`artifacts/photo-crop-preview-20261014/gallery/report.json`, games `7` and
`mumie`). Measured in P1: 10,992,053 original bytes, 7,646,890 after the
lossless crop (−30.4%), orientation 1, sampling 4:4:4 and 4:2:0.

## Blocker found while planning (read-only measurement, 2026-10-17)

- Every import of the library is `waiting_for_review` (55,462 + 56,812 +
  54,915 sources; 24 sources in a cancelled import). No blob has all its
  sources in a `completed` import (0 of 165,786).
- All 40 P1 blobs belong to `waiting_for_review` imports (48 sources); 36 of
  them are also sources in another game.
- Eligibility (TASK-1044) requires `import_status == 'completed'`
  (`IMPORT_NOT_COMPLETED`), plan R5 says "import in a terminal state". A crop
  or deletion preview today would therefore find **no eligible original**.
- Why the rule exists: resuming an import re-runs `ensure_original` for every
  original of its manifest (`images/source_ingestion.py`). A deleted original
  is copied back from the import source when it still exists (the saving is
  lost) and fails the import when it does not. Deleting originals of an
  import that can still resume is therefore unsafe; cropping them is not,
  because a crop never replaces a present original.

## Decision needed

| Option | What changes | Pilot result | Risk |
|---|---|---|---|
| **A (recommended)** | New small task TASK-1051: the crop run accepts sources of `waiting_for_review` imports (no other rule relaxed); the deletion run keeps requiring `completed` imports. | Crop pilot on the 40 P1 originals now; deletion pilot only once some imports are completed. | Low: crops are additive (+~7.6 MB for 40); originals stay and are preferred by the loader. |
| B | Deletion also for `waiting_for_review` imports; import resume must accept a verified crop instead of the original (`ensure_original` and every resumed stage that reads whole frames). | Full pilot now. | High and irreversible: needs its own plan, decision record and audit. |
| C | No code change. | Pilot waits until the operator completes the review of some imports. | None, but no measurement now (today: zero completed imports). |

## Pilot procedure (after option A; every numbered step needs its own consent)

The agent prepares previews and read-only checks through the local API; the
operator starts runs in Admin → Storage (TASK-1049 panel), or tells the agent
to start them. Services are started by the operator:
`npm run api:dev`, `npm run worker:poll`, `npm run admin:dev`,
`npm run reviewer:dev`. Before step 1: `.\.tooling\libjpeg-turbo-3.2.0\bin\jpegtran.exe -version`.

1. **Baseline (read-only).** For the 40 P1 originals record SHA-256, size and
   mtime of `data/originals/...`, and the checksums of their cell previews and
   source images served by the API, into
   `artifacts/photo-crop-pilot-<date>/baseline.json`. No data change. Cost:
   one small script, minutes.
2. **Crop preview.** `POST /admin/image-storage/source-crop-previews` with
   `scope.onlyChecksums` = the 40 P1 checksums. The plan job only writes its
   manifest. Report: eligible count, exclusion reasons, original bytes,
   estimated saving. Seconds.
3. **Crop run (consent).** Start the preview with its token. Expected: about
   40 crops and attestations in `data/originals-cropped`, about 7.6 MB of new
   files, registry rows `verified`; originals unchanged (SHA-256, size, mtime
   compared with step 1). About 1–3 minutes. Recorded: time per original,
   outcomes, failures.
4. **Checks after cropping (read-only).** Admin and Reviewer show the same
   sources and overlays (the originals are still used); cell previews equal the
   baseline. Result recorded.
5. **Optional, separate consent: library-wide crop preview** (scope "all").
   Read-only on PostgreSQL but heavy (eligibility over 165,786 blobs, 332
   pages); measures planning time and the eligible count. While it is open no
   other crop run can start; a new preview supersedes it.
6. **Deletion** — not part of this pilot under option A. It becomes a later
   pilot step (deletion preview → start with `acknowledgeIrreversible`, then
   cell previews equal to the baseline, full-frame source images, reprocess
   refused with `SOURCE_ORIGINAL_CROPPED`, `data/originals` smaller by the
   measured bytes) when completed imports exist, or after option B.
7. **Report** `ai_docs/quality/PHOTO_CROP_PILOT_<date>.md`: bytes before and
   after, time per original, outcomes, checks, extrapolation for the eligible
   pool, and the open deletion decision.

## Scope

Steps 1–4 and 7 after option A (and step 5 if consented). TASK-1051 is a
separate task with its own commit, tests and Codex audit (`gpt-6.1-sol` /
`high`, or none when the quota is exhausted, per the operator decision).

## Out of scope

Deleting any original (step 6), option B, a library-wide crop run.

## Acceptance criteria

- [ ] Decision A/B/C recorded.
- [ ] Baseline, preview, run and checks recorded with exact numbers.
- [ ] Originals of the pilot unchanged after the crop run.
- [ ] Report in `ai_docs/quality/`.

## Cost and time

- Tokens: TASK-1051 is a small change in eligibility with tests and one
  audit; the pilot steps are short API calls, checks and one report. Well
  below stage B.
- Time on the machine: steps 2–4 take minutes; step 5 is unmeasured (the
  point of measuring it).
- Disk: about +7.6 MB of crops for the pilot; no space is freed until
  originals are deleted.

## Risks / open questions

- The eligible pool after option A is unknown until step 2 or 5: other rules
  (pending geometry corrections, grid issues, registration anchors, active
  jobs) still exclude sources.
- Imports in `waiting_for_review` may never be completed in normal work; then
  storage savings require option B.

## Outcome

Wypełnia agent po pracy.
