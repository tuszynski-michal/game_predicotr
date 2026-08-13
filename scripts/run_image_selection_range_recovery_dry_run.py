"""Evaluate an immutable image-selection range recovery without database writes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = REPOSITORY_ROOT / "services" / "api" / "src"
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(API_SOURCE))
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_api.config import get_settings  # noqa: E402
from game_predictor_api.domain.image_selections import (  # noqa: E402
    ImageSelectionExecutionMode,
)
from game_predictor_api.storage.models import ImageSelectionRunModel  # noqa: E402
from game_predictor_worker.images.selection.cache import (  # noqa: E402
    CachedCandidateVerifier,
    CachedCheapImageAnalyzer,
    FileImageScanObservationCache,
    FileImageVerificationCache,
)
from game_predictor_worker.images.selection.contracts import (  # noqa: E402
    SelectionGroupResult,
    SelectionGroupStatus,
)
from game_predictor_worker.images.selection.io import (  # noqa: E402
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.job import (  # noqa: E402
    BROWSER_SELECTION_DIRECTORY,
    BROWSER_SELECTION_MANIFEST,
    ImageSelectionJobHandler,
    SqlAlchemyImageSelectionJobStore,
)
from game_predictor_worker.images.selection.manifest import (  # noqa: E402
    TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
)
from game_predictor_worker.images.selection.recovery import (  # noqa: E402
    RecoveryEvaluationProgress,
    RecoveryProjection,
    RecoverySourceGroup,
    evaluate_recovery,
    plan_recovery_blocks,
)
from game_predictor_worker.images.selection.telemetry import (  # noqa: E402
    StageTimingCollector,
)

TARGET_SOURCE_RUN_ID = UUID("6c6afaf9-e144-4d5d-9cc6-8dc30a395bbd")
EXPECTED_DATABASE_REVISION = "0042_image_selection_derived_recovery"
EXPECTED_UNRESOLVED_GROUPS = 748
DEFAULT_AUDIT_SAMPLE_SIZE = 100
_PROTECTED_USER_STATUSES = frozenset(
    {
        SelectionGroupStatus.MANUALLY_SELECTED,
        SelectionGroupStatus.MISSING_IMAGE,
        SelectionGroupStatus.RANGE_CONFIRMED,
        SelectionGroupStatus.REJECTED_BY_USER,
    }
)
_OUTPUT_STATUSES = frozenset(
    {
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.MANUALLY_SELECTED,
        SelectionGroupStatus.RANGE_CONFIRMED,
    }
)
_FORBIDDEN_RECOVERY_REASONS = frozenset(
    {
        "RANGE_EXACT_GAP_INFERRED",
        "RANGE_INFERRED_FROM_BOUNDED_GAP",
        "RANGE_OWNER_ANCHOR",
    }
)


class DryRunError(RuntimeError):
    """A safety precondition prevents the read-only recovery evaluation."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=TARGET_SOURCE_RUN_ID)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "artifacts"
            / "image-selection-v1012-range-recovery-dry-run-6c6afaf9.json"
        ),
    )
    parser.add_argument(
        "--expected-unresolved-groups",
        type=int,
        default=EXPECTED_UNRESOLVED_GROUPS,
    )
    parser.add_argument("--scan-workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--verification-workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--audit-sample-size", type=int, default=DEFAULT_AUDIT_SAMPLE_SIZE)
    parser.add_argument("--audit-decisions", type=Path)
    return parser.parse_args()


def _database_preflight(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            active = tuple(
                connection.execute(
                    text(
                        "SELECT id::text, status::text, stage "
                        "FROM jobs "
                        "WHERE job_type::text = 'image_selection' "
                        "AND status::text IN ('created', 'processing') "
                        "ORDER BY created_at"
                    )
                ).mappings()
            )
    finally:
        engine.dispose()
    if revision != EXPECTED_DATABASE_REVISION:
        raise DryRunError(
            "Database revision must be "
            f"{EXPECTED_DATABASE_REVISION}; current revision is {revision!r}."
        )
    if active:
        labels = ", ".join(
            f"{row['id']} ({row['status']}, {row['stage'] or 'no stage'})" for row in active
        )
        raise DryRunError(
            f"Recovery dry-run refuses to compete with an active image-selection job: {labels}."
        )


def _range_key(group: SelectionGroupResult) -> tuple[int, int] | None:
    if group.range is None:
        return None
    return group.range.start, group.range.end


def _selected_identity(group: SelectionGroupResult) -> tuple[int, str] | None:
    if group.selected_candidate is None:
        return None
    source = group.selected_candidate.source
    return source.order_index, source.checksum_sha256


def _projection_issues(
    source_groups: tuple[RecoverySourceGroup, ...],
    projection: RecoveryProjection,
    *,
    snapshot_before: str,
    snapshot_after: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    source_ids = {group.origin_group_id for group in source_groups}
    if snapshot_before != snapshot_after:
        issues.append("SOURCE_SNAPSHOT_CHANGED_DURING_DRY_RUN")
    if set(projection.origin_group_ids.values()) - source_ids:
        issues.append("PROJECTION_ORIGIN_OUTSIDE_SOURCE")
    if set(projection.origin_group_ids) != set(range(len(projection.groups))):
        issues.append("PROJECTION_ORIGIN_COVERAGE_MISMATCH")

    selected = [
        identity
        for group in projection.groups
        if (identity := _selected_identity(group)) is not None
    ]
    if len(selected) != len(set(selected)):
        issues.append("DUPLICATE_SELECTED_SOURCE")

    output_ranges = [
        key
        for group in projection.groups
        if group.status in _OUTPUT_STATUSES and (key := _range_key(group)) is not None
    ]
    if len(output_ranges) != len(set(output_ranges)):
        issues.append("DUPLICATE_OUTPUT_RANGE")

    blocks = plan_recovery_blocks(source_groups)
    affected_origins = {
        source.origin_group_id for block in blocks for source in block.source_groups
    }
    for group in projection.groups:
        if (
            projection.origin_group_ids[group.group_order] not in affected_origins
            or group.status is not SelectionGroupStatus.AUTO_SELECTED
        ):
            continue
        selected_candidate = group.selected_candidate
        selected_range = None if selected_candidate is None else selected_candidate.recognized_range
        forbidden_reason = selected_candidate is not None and any(
            reason in _FORBIDDEN_RECOVERY_REASONS for reason in selected_candidate.reason_codes
        )
        if (
            group.range is None
            or selected_range is None
            or (group.range.start, group.range.end) != (selected_range.start, selected_range.end)
            or forbidden_reason
        ):
            issues.append(f"RECOVERED_RANGE_WITHOUT_OWN_EVIDENCE:{group.group_order}")

    derived_by_origin = {
        origin: projection.groups[group_order]
        for group_order, origin in projection.origin_group_ids.items()
    }
    for source in source_groups:
        if source.result.status not in _PROTECTED_USER_STATUSES:
            continue
        derived = derived_by_origin.get(source.origin_group_id)
        if derived is None:
            issues.append(f"PROTECTED_DECISION_MISSING:{source.origin_group_id}")
            continue
        if (
            derived.status is not source.result.status
            or _range_key(derived) != _range_key(source.result)
            or _selected_identity(derived) != _selected_identity(source.result)
        ):
            issues.append(f"PROTECTED_DECISION_CHANGED:{source.origin_group_id}")
    return tuple(dict.fromkeys(issues))


def _stratified_audit_sample(
    projection: RecoveryProjection,
    *,
    sample_size: int,
    origin_group_ids: set[UUID] | None = None,
) -> list[dict[str, object]]:
    if sample_size < 1:
        raise DryRunError("Audit sample size must be positive.")
    eligible = [
        group
        for group in projection.groups
        if group.status in _OUTPUT_STATUSES
        and group.range is not None
        and group.selected_candidate is not None
        and (
            origin_group_ids is None
            or projection.origin_group_ids[group.group_order] in origin_group_ids
        )
    ]
    if not eligible:
        return []
    count = min(sample_size, len(eligible))
    indexes = (
        [0]
        if count == 1
        else [round(index * (len(eligible) - 1) / (count - 1)) for index in range(count)]
    )
    sample: list[dict[str, object]] = []
    for index in indexes:
        group = eligible[index]
        assert group.range is not None
        assert group.selected_candidate is not None
        sample.append(
            {
                "checksumSha256": group.selected_candidate.source.checksum_sha256,
                "derivedGroupOrder": group.group_order,
                "derivedRangeEnd": group.range.end,
                "derivedRangeStart": group.range.start,
                "expectedRangeEnd": None,
                "expectedRangeStart": None,
                "originGroupId": str(projection.origin_group_ids[group.group_order]),
                "sourceRelativePath": group.selected_candidate.source.relative_path,
                "status": group.status.value,
            }
        )
    return sample


def _owner_audit(
    sample: list[dict[str, object]],
    decisions_path: Path | None,
    *,
    source_run_id: UUID,
) -> dict[str, object]:
    result: dict[str, object] = {
        "requiredCount": DEFAULT_AUDIT_SAMPLE_SIZE,
        "sampleCount": len(sample),
        "auditedCount": 0,
        "wrongRangeCount": None,
        "status": "pending",
    }
    if decisions_path is None:
        return result
    try:
        payload = cast(dict[str, Any], json.loads(decisions_path.read_text(encoding="utf-8")))
        decisions = cast(list[dict[str, Any]], payload["decisions"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DryRunError("Owner audit decisions cannot be read.") from error
    if (
        payload.get("schemaVersion") != 1
        or payload.get("sourceRunId") != str(source_run_id)
        or not isinstance(decisions, list)
    ):
        raise DryRunError("Owner audit decisions use an unsupported contract.")
    expected: dict[str, tuple[int, int]] = {}
    try:
        for decision in decisions:
            expected[str(decision["checksumSha256"])] = (
                int(decision["expectedRangeStart"]),
                int(decision["expectedRangeEnd"]),
            )
    except (KeyError, TypeError, ValueError) as error:
        raise DryRunError("Owner audit decisions contain an invalid range.") from error
    wrong = 0
    audited = 0
    for item in sample:
        key = str(item["checksumSha256"])
        expected_range = expected.get(key)
        if expected_range is None:
            continue
        audited += 1
        if expected_range != (
            int(cast(int, item["derivedRangeStart"])),
            int(cast(int, item["derivedRangeEnd"])),
        ):
            wrong += 1
    required = DEFAULT_AUDIT_SAMPLE_SIZE
    result.update(
        {
            "auditedCount": audited,
            "wrongRangeCount": wrong,
            "status": "passed" if audited >= required and wrong == 0 else "failed",
        }
    )
    return result


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _run(args: argparse.Namespace) -> tuple[Path, bool]:
    settings = get_settings()
    _database_preflight(settings.database_url)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    try:
        with session_factory() as session:
            source_run = session.get(ImageSelectionRunModel, cast(UUID, args.run_id))
        if source_run is None:
            raise DryRunError("Source image-selection run does not exist.")
        if (
            ImageSelectionExecutionMode(source_run.execution_mode)
            is not ImageSelectionExecutionMode.FULL
        ):
            raise DryRunError("Recovery source must be a full image-selection run.")
        if source_run.first_sequence_number is None:
            raise DryRunError("Recovery source has no first sequence number.")

        source_root = (
            settings.import_root / BROWSER_SELECTION_DIRECTORY / str(source_run.source_selection_id)
        ).resolve(strict=True)
        sources, manifest_sha256 = load_browser_selection_manifest(
            source_root / BROWSER_SELECTION_MANIFEST
        )
        if manifest_sha256 != source_run.input_manifest_sha256:
            raise DryRunError("Managed source manifest changed after the source run was created.")

        store = SqlAlchemyImageSelectionJobStore(session_factory)
        snapshot_before, source_groups = store.load_recovery_source(source_run.id)
        unresolved_count = sum(
            group.result.status is SelectionGroupStatus.RANGE_REQUIRED for group in source_groups
        )
        expected_unresolved = cast(int, args.expected_unresolved_groups)
        if unresolved_count != expected_unresolved:
            raise DryRunError(
                f"Expected {expected_unresolved} unresolved groups, found {unresolved_count}."
            )

        telemetry = StageTimingCollector()
        handler = ImageSelectionJobHandler(
            store,
            browser_upload_root=settings.import_root,
            artifact_root=settings.artifact_root,
            repository_root=REPOSITORY_ROOT,
            selector_manifest=TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
            scan_workers=cast(int, args.scan_workers),
            verification_workers=cast(int, args.verification_workers),
        )
        analyzer, verifier = handler.build_runtime_adapters(
            source_root,
            TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
            telemetry,
        )
        cached_analyzer = CachedCheapImageAnalyzer(
            analyzer,
            FileImageScanObservationCache(settings.artifact_root),
            scan_adapter_fingerprint=(
                TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012.scan_adapter_fingerprint
            ),
        )
        cached_verifier = CachedCandidateVerifier(
            verifier,
            FileImageVerificationCache(settings.artifact_root),
            selector_fingerprint=TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012.fingerprint,
        )

        print(
            "range recovery dry-run: "
            f"{unresolved_count} unresolved groups, {len(sources)} staged JPEGs",
            flush=True,
        )
        started = perf_counter()

        def report_progress(progress: RecoveryEvaluationProgress) -> None:
            print(
                "recovery "
                f"block={progress.completed_blocks}/{progress.block_count} "
                f"candidates={progress.completed_candidates}/{progress.candidate_count} "
                f"failures={progress.scan_failure_count}",
                flush=True,
            )

        evaluation = evaluate_recovery(
            source_groups,
            manifest=TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
            analyzer=cached_analyzer,
            verifier=cached_verifier,
            sequence_direction=source_run.sequence_direction,
            first_sequence_number=source_run.first_sequence_number,
            scan_workers=cast(int, args.scan_workers),
            progress_callback=report_progress,
        )
        elapsed_seconds = perf_counter() - started
        snapshot_after, _ = store.load_recovery_source(source_run.id)
    finally:
        engine.dispose()

    status_counts = Counter(group.status.value for group in evaluation.projection.groups)
    readable_unresolved = sum(
        group.status is SelectionGroupStatus.RANGE_REQUIRED and group.selected_candidate is not None
        for group in evaluation.projection.groups
    )
    issues = _projection_issues(
        source_groups,
        evaluation.projection,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
    )
    sample = _stratified_audit_sample(
        evaluation.projection,
        sample_size=cast(int, args.audit_sample_size),
        origin_group_ids={
            group.origin_group_id
            for block in plan_recovery_blocks(source_groups)
            for group in block.source_groups
        },
    )
    owner_audit = _owner_audit(
        sample,
        cast(Path | None, args.audit_decisions),
        source_run_id=source_run.id,
    )
    automatic_gates_passed = readable_unresolved <= 14 and not issues
    owner_audit_passed = owner_audit["status"] == "passed"
    ready = automatic_gates_passed and owner_audit_passed
    report: dict[str, object] = {
        "schemaVersion": 1,
        "contract": "image-selection-range-recovery-dry-run-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "source": {
            "runId": str(source_run.id),
            "sourceSelectionId": str(source_run.source_selection_id),
            "inputManifestSha256": manifest_sha256,
            "sourceSnapshotSha256": snapshot_before,
            "stagedJpegCount": len(sources),
            "groupCount": len(source_groups),
            "rangeRequiredCount": unresolved_count,
        },
        "selector": {
            "version": TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012.algorithm_version,
            "fingerprint": TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012.fingerprint,
        },
        "evaluation": {
            "blockCount": evaluation.block_count,
            "candidateCount": evaluation.candidate_count,
            "derivedGroupCount": len(evaluation.projection.groups),
            "elapsedSeconds": round(elapsed_seconds, 3),
            "scanFailureCount": evaluation.scan_failure_count,
            "verificationCount": evaluation.verification_count,
            "statusCounts": dict(sorted(status_counts.items())),
            "readableRangeRequiredCount": readable_unresolved,
            "scanCache": cached_analyzer.snapshot(),
            "verificationCache": cached_verifier.snapshot(),
            "stageTiming": telemetry.snapshot(),
        },
        "gates": {
            "automaticGatesPassed": automatic_gates_passed,
            "maximumReadableRangeRequired": 14,
            "structuralIssues": list(issues),
            "ownerAudit": owner_audit,
            "readyForRecoveryCreation": ready,
        },
        "auditSample": sample,
    }
    output = cast(Path, args.output).resolve()
    _write_json_atomic(output, report)
    return output, ready


def main() -> int:
    args = _parse_args()
    try:
        output, ready = _run(args)
    except (DryRunError, OSError, ValueError) as error:
        print(f"range recovery dry-run blocked: {error}", file=sys.stderr)
        return 2
    print(f"range recovery dry-run report: {output}", flush=True)
    print(f"ready for recovery creation: {str(ready).lower()}", flush=True)
    return 0 if ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
