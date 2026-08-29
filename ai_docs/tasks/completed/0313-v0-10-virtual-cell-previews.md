# TASK-0313 — Bounded virtual cell previews

## Status

`done`

## Version

`0.10.6`

## Goal

Serve current virtual-source symbol-cell previews without reintroducing persistent board or
cell crop artifacts. The Admin API must render bounded WebP atlases from managed originals,
cache only derived preview data, and preserve the existing legacy-file asset path.

## Scope

- Add a shared `VirtualCellPreviewService`.
- Accept batches of at most 100 current virtual cells with expected cell revisions and render
  specification checksums.
- Render a checksum-bound WebP atlas and return a deterministic tile descriptor.
- Store only regenerable preview cache entries under
  `data/working/virtual-preview-cache-v1/`, with a 15 minute TTL, 2 GiB LRU limit and
  per-batch single-flight rendering.
- Extend the existing symbol-cell asset route so that a virtual cell is rendered from the
  canonical managed original, while a legacy crop continues to use its existing file path.
- Publish batch preview contracts in OpenAPI and regenerate the Admin API client.

## Out of scope

- No geometry-review UI (TASK-0314).
- No virtualized Symbol Verification workspace or viewport scheduling (TASK-0315).
- No full-game thumbnail generation, persistent preview ground truth, migration, model change,
  or changes to a source geometry decision.

## Invariants

- A preview is derived cache data only; its source of truth remains the current cell provenance.
- Each request is bound to the current cell revision, geometry revision, render specification
  checksum and rendered-pixel checksum.
- A changed source, geometry, render specification or active owner must fail closed rather than
  serving an old preview.
- Cache contents may be deleted at any time and contain no symlinks or references from domain
  records.
- At most 100 cells are rendered in one batch; managed originals are decoded once per source
  within that render.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-254–D-258)
- `ai_docs/tasks/completed/0312-v0-10-virtual-geometry-pipeline-integration.md`

## Verification

- Batch limit, checksum validation, stale revision, missing source, cache TTL/LRU and concurrent
  single-flight tests.
- Focused API tests plus Ruff, mypy, OpenAPI/client drift checks and generated-client typecheck.

## Outcome

- `VirtualCellPreviewService` renders current `virtual_source` cells directly
  from checksum-verified managed originals into bounded WebP atlases. It keeps
  only a regenerable `data/working/virtual-preview-cache-v1` entry with
  15-minute TTL, 2 GiB LRU, atomic writes and process-local single-flight.
- The service verifies current board/source geometry revisions, source and
  normalized-pixel checksums, render spec checksum and rendered-pixel checksum
  before every render. Legacy crop files retain their prior endpoint behavior.
- Local Admin API exposes batch creation and atlas reads; the existing asset
  endpoint serves a virtual cell through the same cache when its render-spec
  checksum is supplied. OpenAPI and the generated Admin client were updated.
- Tests cover atlas checksums and tile descriptors, stale geometry, missing
  managed sources, TTL/LRU eviction, concurrent single-flight and the HTTP
  contract. Focused tests pass: `20 passed`.
- Ruff and generated-client typecheck pass; OpenAPI/client drift check passes.
  The workspace-wide mypy invocation still reports pre-existing dependency
  issues (untyped worker imports and existing application/repository errors),
  but none are emitted for the new preview service after its worker imports are
  scoped as intentionally untyped.
