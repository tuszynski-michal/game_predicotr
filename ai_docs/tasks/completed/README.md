---
title: Completed tasks archive
status: active
last_updated: 2026-08-23
---

# Ukończone zadania

Katalog przechowuje zamknięte zadania wraz z odpowiedziami właściciela i
Outcome. Nie są one aktywnym kontekstem implementacyjnym.

Aktywne zadanie znajduje się bezpośrednio w `ai_docs/tasks/` i musi mieć status
`todo`, `in_progress` albo `blocked`.

## Zamknięcie kolejki przed wersją 0.7

W dniu 2026-08-21 uporządkowano całą pozostałą kolejkę wersji 0.4–0.6. Zadania
oznaczone jako zastąpione lub odroczone zachowują pełny Outcome i Closure do
audytu; nie są aktywnym zakresem wersji 0.7.

- [TASK-0141 — Mobile 0.3 acceptance](0141-version-0-3-mobile-regression-and-pixel-acceptance.md)
- [TASK-0142 — Admin 0.2 owner acceptance regressions](0142-v02-owner-acceptance-regressions.md)
- [TASK-0149 — Pending-only re-inference and import pinning](0149-pending-only-reinference-and-import-pinning.md)
- [TASK-0150 — Iterative supervised loop acceptance](0150-iterative-supervised-loop-acceptance.md)
- [TASK-0157 — Image-selection scale and owner acceptance](0157-image-selection-scale-quality-and-owner-acceptance.md)
- [TASK-0171 — Fast-selection real-corpus activation](0171-fast-selection-real-corpus-regression-and-activation.md)
- [TASK-0178 — Image-selection v10 accuracy-first](0178-image-selection-v10-accuracy-first-selection.md)
- [TASK-0197 — V10.1 owner gate](0197-image-selection-v101-first-5000-owner-gate.md)
- [TASK-0208 — Image-import scaling observability](0208-image-import-scaling-observability.md)
- [TASK-0209 — Cancelled baseline diagnostics](0209-image-selection-cancelled-baseline-and-false-merge-diagnostics.md)
- [TASK-0211 — Windows worker process tree](0211-windows-worker-process-tree.md)
- [TASK-0218 — Manual gap export and owner gate](0218-manual-gap-export-and-owner-gate.md)
- [TASK-0241 — v10.10 label lattice recovery](0241-image-selection-v1010-label-lattice-safety-recovery.md)
- [TASK-0242 — v10.11 derived range recovery](0242-image-selection-v1011-derived-range-recovery.md)
- [TASK-0246 — Local manual image selection](0246-manual-local-image-selection.md)
- [TASK-0247 — Attested `seq_*` import](0247-attested-seq-range-import.md)
- [TASK-0248 — Representative quality ranking](0248-representative-quality-ranking.md)

## Wersja 0.7

- [TASK-0251 — Uzgodnienie wyniku tworzenia reguł](0251-rules-creation-response-reconciliation.md)
- [TASK-0252 — Uproszczenie edytora wzorców](0252-simplify-payline-editor.md)
- [TASK-0253 — Widoczność stagingu importu plansz i nazewnictwo panelu](0253-board-import-staging-visibility-and-terminology.md)
- [TASK-0272 — Analiza zdalnej ręcznej selekcji zdjęć](0272-remote-manual-image-selection-analysis.md)
- [TASK-0273 — Browser capability zdalnego źródła](0273-remote-source-browser-capability-spike.md)
- [TASK-0274 — Wspólny silnik ręcznej selekcji i adapter lokalny](0274-manual-image-selection-shared-core.md)
- [TASK-0275 — Kontrakty domenowe zdalnej ręcznej selekcji](0275-remote-manual-selection-domain-contracts.md)
- [TASK-0276 — Trwały model zdalnej ręcznej selekcji](0276-remote-manual-selection-persistence.md)

## Zawartość

- [TASK-0001 — Architecture clarification](0001-architecture-clarification.md)
- [TASK-0002 — Monorepo and offline SQLite spike](0002-monorepo-offline-sqlite-spike.md)
- [TASK-0003 — Contracts, signature codec and validation](0003-contracts-signature-codec-validation.md)
- [TASK-0004 — Payout engine and golden tests](0004-payout-engine-golden-tests.md)
- [TASK-0005 — Target engine and golden tests](0005-target-engine-golden-tests.md)
- [TASK-0006 — Deterministic fixture generator](0006-deterministic-fixture-generator.md)
- [TASK-0007 — SQLite snapshot generator](0007-sqlite-snapshot-generator.md)
- [TASK-0008 — Matching repository and cyclic stream](0008-matching-repository-cyclic-stream.md)
- [TASK-0009 — Board reducer and components](0009-board-reducer-basic-components.md)
- [TASK-0010 — Prefix matching and candidate modal](0010-prefix-matching-unique-candidate-modal.md)
- [TASK-0011 — Exact matching and result states](0011-exact-matching-result-states.md)
- [TASK-0012 — Full-cycle Target integration](0012-full-cycle-target-integration.md)
- [TASK-0013 — Virtualized result table](0013-virtualized-result-table-calculation-state.md)
- [TASK-0014 — Release APK and device acceptance](0014-release-apk-device-acceptance.md)
- [TASK-0015 — Admin platform foundations and local configuration](0015-admin-platform-foundations-local-configuration.md)
- [TASK-0016 — PostgreSQL Compose and Alembic baseline](0016-postgresql-compose-alembic-baseline.md)
- [TASK-0017 — OpenAPI contract and generated admin client](0017-openapi-contract-generated-admin-client.md)
- [TASK-0018 — Games and symbols domain, repository and API](0018-games-symbols-domain-repository-api.md)
- [TASK-0019 — Admin shell and games identity UI](0019-admin-shell-games-identity-ui.md)
- [TASK-0020 — Symbols UI, reference assets and archival rules](0020-symbols-ui-reference-assets-archival-rules.md)
- [TASK-0021 — Rules versions domain, API and dimensions UI](0021-rules-versions-domain-api-dimensions-ui.md)
- [TASK-0022 — Payline grid editor and duplicate validation](0022-payline-grid-editor-duplicate-validation.md)
- [TASK-0023 — Per-symbol minimum and payout rules API/UI](0023-per-symbol-minimum-payout-rules-api-ui.md)
- [TASK-0024 — Immutable rules publication workflow](0024-immutable-rules-publication-workflow.md)
- [TASK-0025 — Mock dataset generation and staging](0025-mock-dataset-generation-staging.md)
- [TASK-0026 — Sequence and duplicate validation reports](0026-sequence-duplicate-validation-reports.md)
- [TASK-0027 — Dataset preview and immutable publication](0027-dataset-preview-immutable-publication.md)
- [TASK-0028 — Admin configuration vertical-slice acceptance](0028-admin-configuration-vertical-slice-acceptance.md)
- [TASK-0029 — Job state machine and Admin API](0029-job-state-machine-admin-api.md)
- [TASK-0030 — Local worker execution, lease and resume](0030-local-worker-lease-resume.md)
- [TASK-0031 — Jobs progress and error UI](0031-jobs-progress-error-ui.md)
- [TASK-0032 — Batch payout precomputation and audit](0032-batch-payout-precomputation-audit.md)
- [TASK-0033 — Payout completeness, restart and version safety](0033-payout-completeness-restart-version-safety.md)
- [TASK-0034 — Production SQLite snapshot generator](0034-production-sqlite-snapshot-generator.md)
- [TASK-0035 — Snapshot validator, manifest and artifact layout](0035-snapshot-validator-manifest-artifact-layout.md)
- [TASK-0036 — Mobile release domain and API](0036-mobile-release-domain-api.md)
- [TASK-0037 — Release workflow orchestration](0037-release-workflow-orchestration.md)
- [TASK-0038 — Android release panel and artifact UI](0038-android-release-panel-artifact-ui.md)
- [TASK-0039 — Release failure and immutability integration tests](0039-release-failure-immutability-integration-tests.md)
- [TASK-0040 — Representative 500k benchmark dataset](0040-representative-500k-benchmark-dataset.md)
- [TASK-0041 — SQLite, mobile and worker performance benchmark](0041-sqlite-mobile-worker-performance-benchmark.md)
- [TASK-0042 — Benchmark decision and release pipeline acceptance](0042-benchmark-decision-release-pipeline-acceptance.md)
- [TASK-0043 — CSV and JSON import contracts](0043-csv-json-import-contracts.md)
- [TASK-0044 — Import job creation, checksums and path safety](0044-import-job-checksums-path-safety.md)
- [TASK-0045 — Streaming parser and resumable staging](0045-streaming-parser-resumable-staging.md)
- [TASK-0046 — Layout normalization and row validation](0046-layout-normalization-row-validation.md)
- [TASK-0047 — Import integrity and duplicate reports](0047-import-integrity-duplicate-reports.md)
- [TASK-0048 — Manual import administration UI](0048-manual-import-administration-ui.md)
- [TASK-0049 — Transactional dataset publication from staging](0049-transactional-dataset-publication-from-staging.md)
- [TASK-0050 — Manual import scale and release acceptance](0050-manual-import-scale-release-acceptance.md)
- [TASK-0051 — Representative image corpus and golden annotations](0051-representative-image-corpus-golden-annotations.md)
- [TASK-0052 — Image discovery and source manifest](0052-image-discovery-source-manifest.md)
- [TASK-0053 — EXIF normalization and diagnostics](0053-exif-normalization-diagnostics.md)
- [TASK-0054 — Page and 3x3 board detection](0054-page-3x3-board-detection.md)
- [TASK-0055 — Per-board perspective correction and cell crops](0055-per-board-perspective-cell-crops.md)
- [TASK-0056 — Sequence number OCR and continuity validation](0056-sequence-number-ocr-continuity.md)
- [TASK-0057 — Geometry and OCR benchmark report](0057-geometry-ocr-benchmark-report.md)
- [TASK-0058 — Image prototype architecture decision](0058-image-prototype-architecture-decision.md)
- [TASK-0078 — Local administration threat model and Q-019 decision](0078-local-administration-threat-model-q019-decision.md)
- [TASK-0090 — Payout-v2 and snapshot](0090-payout-v2-left-prefix-and-snapshot.md)
- [TASK-0091 — Documentation consistency before M2](0091-documentation-consistency-before-m2.md)
- [TASK-0092 — M5 corpus, variable final page and OCR rework](0092-m5-corpus-variable-page-and-ocr-rework.md)
- [TASK-0093 — Bootstrap symbol label review tool](0093-bootstrap-symbol-label-review-tool.md)
- [TASK-0094 — Independent cell-grid golden annotations and crop quality gate](0094-cell-grid-golden-annotations-crop-quality-gate.md)
- [TASK-0095 — Board cell cropper v2 and corpus regeneration](0095-board-cell-cropper-v2-corpus-regeneration.md)
- [TASK-0096 — Grid calibration profiles and perspective editor](0096-grid-calibration-profiles-line-editor.md)
- [TASK-0269 — Kohorta pozostałych błędów modelu](0269-v19-symbol-residual-cohort.md)
