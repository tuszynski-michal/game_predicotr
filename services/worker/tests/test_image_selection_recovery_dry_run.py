from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.recovery import RecoveryProjection

from scripts.run_image_selection_range_recovery_dry_run import (
    _owner_audit,
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
    assert [item["derivedGroupOrder"] for item in affected_sample] == list(
        range(25, 125)
    )


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
