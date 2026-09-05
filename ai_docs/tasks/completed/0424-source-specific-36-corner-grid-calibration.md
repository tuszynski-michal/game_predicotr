# TASK-0424 — Source-specific 36-corner grid calibration

Status: done

## Goal

Make the grid-improvement workflow train and activate the production page
registration profile from nine independently approved board quads (36 source
corners), instead of accepting or rejecting that profile with the legacy
per-position median-offset gate.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/tasks/completed/0319-v0-10-keypoint-geometry-fallback.md`

## Scope

- Freeze a versioned source-level geometry cohort while retaining all nine
  independently approved quads for every complete page.
- Select a bounded, deterministic and geometry-diverse set of training anchors.
- Gate candidates on complete 36-corner source coverage and a source-disjoint
  validation set, not on the legacy median-offset projection.
- Pin the exact selected anchor set into every future image job.
- Preserve historical offset profiles and their replay behavior.
- Update Admin diagnostics and documentation to describe the actual production
  profile.

## Out of scope

- Neural keypoint model activation.
- Reprocessing historical imports automatically.
- Relaxing the target-image ORB, ordering or red-edge hard gates.
- Changing manual source-geometry persistence.

## Definition of Done

- A new candidate is based on complete source pages containing 9 quads / 36
  corners and cannot silently fall back to four global page corners.
- Validation sources never become registration anchors.
- Anchor selection is deterministic, bounded and geometry-diverse.
- The runtime still fails closed when a target image cannot prove all nine
  boards.
- Existing schema-v1 cohorts and activated jobs remain replayable.
- Focused API/domain/worker/Admin tests, lint and type checks pass.

## Outcome

- Manifest schema v2 grupuje bieżące zatwierdzone geometrie w kompletne źródła
  9 × 4, odrzuca niekompletne/nieuporządkowane źródła i zachowuje rozłączny
  split po checksumie obrazu.
- Profil wybiera maksymalnie 16 kotwic algorytmem medoid + farthest point na
  pełnych 72 współrzędnych. Walidacyjne źródła nie mogą zostać kotwicami.
- Snapshot joba przypina dokładny zestaw kotwic. Runtime nadal używa własnej
  homografii zdjęcia oraz dziewięciu niezależnych red-edge gates.
- Historyczny manifest schema v1 nadal wybiera dotychczasowy profil offsetów i
  dawny zestaw pierwszych siedmiu kotwic.
- Bieżące dane gry `777` zostały sprawdzone read-only: 32 kompletne źródła,
  1152 narożniki łącznie, zero niekompletnych źródeł i kandydat przechodzący
  nową bramkę.
