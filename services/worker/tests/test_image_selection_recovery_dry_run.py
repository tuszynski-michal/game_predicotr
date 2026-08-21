from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.recovery import (
    RecoveryProjection,
    RecoverySourceGroup,
)

from scripts.run_image_selection_range_recovery_dry_run import (
    _owner_audit,
    _projection_image_coverage,
    _stratified_audit_sample,
)

QUALITY = ImageQualityMetrics(*(0.8 for _ in range(8)))


def _group(order: int) -> SelectionGroupResult:
    recognized_range = SequenceRange(order * 9 + 1, order * 9 + 9, 0.96)
    source = ImageSelectionSource(
        order_index=order,
        relative_path=f"{order:06d}.jpg",
        stored_relative_path=f"files/{order:06d}.jpg",
        checksum_sha256=f"{order:064x}",
        size_bytes=100,
    )
    selected = CandidateResult(
        source=source,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=QUALITY,
        recognized_range=recognized_range,
        reason_codes=("RANGE_OCR_EXACT",),
    )
    return SelectionGroupResult(
        group_order=order,
        source_count=1,
        range=recognized_range,
        fingerprint_sha256="a" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.AUTO_SELECTED,
        selected_candidate=selected,
        top_candidates=(selected,),
    )


def _observation(source: ImageSelectionSource) -> CheapImageObservation:
    return CheapImageObservation(
        source=source,
        width=100,
        height=100,
        fingerprint_hex="a" * 16,
        geometry_signature=(0.1,),
        board_count=9,
        geometry_confidence=0.9,
        quality=QUALITY,
    )


def _source_group(group: SelectionGroupResult) -> RecoverySourceGroup:
    assert group.selected_candidate is not None
    return RecoverySourceGroup(
        origin_group_id=UUID(int=group.group_order + 1),
        result=group,
        sources=(group.selected_candidate.source,),
    )


def test_image_coverage_requires_one_manifest_image_per_logical_group() -> None:
    selected_group = _group(0)
    manual_source = _group(1).selected_candidate
    assert manual_source is not None
    manual_group = SelectionGroupResult(
        group_order=1,
        source_count=1,
        range=SequenceRange(10, 18, 1.0),
        fingerprint_sha256="b" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.MANUAL_REQUIRED,
        selected_candidate=None,
        top_candidates=(),
    )
    skipped_group = SelectionGroupResult(
        group_order=2,
        source_count=1,
        range=SequenceRange(10, 18, 1.0),
        fingerprint_sha256="c" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        selected_candidate=None,
        top_candidates=(),
    )
    origins = {order: UUID(int=order + 1) for order in range(3)}
    projection = RecoveryProjection(
        groups=(selected_group, manual_group, skipped_group),
        group_sources={1: (_observation(manual_source.source),)},
        origin_group_ids=origins,
    )
    source_groups = (_source_group(selected_group),)

    coverage = _projection_image_coverage(
        source_groups,
        projection,
        staged_checksums={
            selected_group.selected_candidate.source.checksum_sha256,
            manual_source.source.checksum_sha256,
        },
        affected_origins=set(origins.values()),
    )

    assert coverage.logical_group_count == 2
    assert coverage.groups_with_image_count == 2
    assert coverage.groups_without_image == ()
    assert coverage.groups_with_unknown_image == ()


def test_image_coverage_uses_preserved_sources_only_for_untouched_groups() -> None:
    source_result = _group(0)
    source_group = _source_group(source_result)
    empty_result = SelectionGroupResult(
        group_order=0,
        source_count=1,
        range=source_result.range,
        fingerprint_sha256=source_result.fingerprint_sha256,
        board_count_consensus=9,
        status=SelectionGroupStatus.MANUAL_REQUIRED,
        selected_candidate=None,
        top_candidates=(),
    )
    projection = RecoveryProjection(
        groups=(empty_result,),
        group_sources={},
        origin_group_ids={0: source_group.origin_group_id},
    )
    staged = {source_group.sources[0].checksum_sha256}

    untouched = _projection_image_coverage(
        (source_group,),
        projection,
        staged_checksums=staged,
        affected_origins=set(),
    )
    rebuilt = _projection_image_coverage(
        (source_group,),
        projection,
        staged_checksums=staged,
        affected_origins={source_group.origin_group_id},
    )

    assert untouched.groups_with_image_count == 1
    assert untouched.groups_without_image == ()
    assert rebuilt.groups_with_image_count == 0
    assert rebuilt.groups_without_image == (0,)


def test_image_coverage_rejects_references_outside_staged_manifest() -> None:
    group = _group(0)
    projection = RecoveryProjection(
        groups=(group,),
        group_sources={},
        origin_group_ids={0: UUID(int=1)},
    )

    coverage = _projection_image_coverage(
        (_source_group(group),),
        projection,
        staged_checksums=set(),
        affected_origins=set(),
    )

    assert coverage.groups_with_image_count == 0
    assert coverage.groups_without_image == (0,)
    assert coverage.groups_with_unknown_image == (0,)


def test_dry_run_builds_deterministic_100_item_stratified_audit() -> None:
    groups = tuple(_group(order) for order in range(150))
    projection = RecoveryProjection(
        groups=groups,
        group_sources={},
        origin_group_ids={order: UUID(int=order + 1) for order in range(150)},
    )

    sample = _stratified_audit_sample(projection, sample_size=100)

    assert len(sample) == 100
    assert sample[0]["derivedGroupOrder"] == 0
    assert sample[-1]["derivedGroupOrder"] == 149
    assert len({item["checksumSha256"] for item in sample}) == 100

    affected = {UUID(int=order + 1) for order in range(25, 125)}
    affected_sample = _stratified_audit_sample(
        projection,
        sample_size=100,
        origin_group_ids=affected,
    )
    assert [item["derivedGroupOrder"] for item in affected_sample] == list(range(25, 125))


def test_owner_audit_requires_every_sample_and_zero_wrong_ranges(tmp_path: Path) -> None:
    source_run_id = UUID(int=500)
    groups = tuple(_group(order) for order in range(100))
    projection = RecoveryProjection(
        groups=groups,
        group_sources={},
        origin_group_ids={order: UUID(int=order + 1) for order in range(100)},
    )
    sample = _stratified_audit_sample(projection, sample_size=100)
    decisions = {
        "schemaVersion": 1,
        "sourceRunId": str(source_run_id),
        "decisions": [
            {
                "checksumSha256": item["checksumSha256"],
                "expectedRangeStart": item["derivedRangeStart"],
                "expectedRangeEnd": item["derivedRangeEnd"],
            }
            for item in sample
        ],
    }
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(decisions), encoding="utf-8")

    result = _owner_audit(sample, path, source_run_id=source_run_id)

    assert result == {
        "requiredCount": 100,
        "sampleCount": 100,
        "auditedCount": 100,
        "wrongRangeCount": 0,
        "status": "passed",
    }


def test_owner_audit_does_not_pass_with_less_than_100_results(tmp_path: Path) -> None:
    source_run_id = UUID(int=500)
    groups = tuple(_group(order) for order in range(99))
    projection = RecoveryProjection(
        groups=groups,
        group_sources={},
        origin_group_ids={order: UUID(int=order + 1) for order in range(99)},
    )
    sample = _stratified_audit_sample(projection, sample_size=100)
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceRunId": str(source_run_id),
                "decisions": [
                    {
                        "checksumSha256": item["checksumSha256"],
                        "expectedRangeStart": item["derivedRangeStart"],
                        "expectedRangeEnd": item["derivedRangeEnd"],
                    }
                    for item in sample
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _owner_audit(sample, path, source_run_id=source_run_id)

    assert result["auditedCount"] == 99
    assert result["wrongRangeCount"] == 0
    assert result["status"] == "failed"
