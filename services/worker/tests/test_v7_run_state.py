from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    fingerprint_sources,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    LocalSourceManifest,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7DecorationVisibility,
    V7FrameQuality,
    V7OcclusionSeverity,
    V7SymbolContentLoss,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7RunStateError,
    V7RunStatePhase,
    V7ScanObservation,
    V7ScanRunState,
)

RANGES = (SemiAutomaticSelectionRange(1, 9), SemiAutomaticSelectionRange(10, 18))
SELECTION_ID = UUID("00000000-0000-0000-0000-000000000701")


def _manifest(*contents: bytes) -> LocalSourceManifest:
    return _manifest_with_paths(
        tuple((f"frame-{index}.jpg", content) for index, content in enumerate(contents))
    )


def _manifest_with_paths(entries: tuple[tuple[str, bytes], ...]) -> LocalSourceManifest:
    sources = tuple(
        SemiAutomaticSelectionSource(
            source_index=index,
            relative_path=relative_path,
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )
        for index, (relative_path, content) in enumerate(entries)
    )
    fingerprint = fingerprint_sources(sources)
    payload = json.dumps(
        {"sources": [item.as_dict() for item in sources]}, sort_keys=True, separators=(",", ":")
    ).encode()
    return LocalSourceManifest(
        selection_id=SELECTION_ID,
        display_name="v7 fixture",
        source_root=Path("C:/v7-fixture"),
        sources=sources,
        source_fingerprint=fingerprint,
        total_bytes=sum(item.size_bytes for item in sources),
        content=payload,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )


def _state(
    manifest: LocalSourceManifest, checkpoint: dict[str, object] | None = None
) -> V7ScanRunState:
    return V7ScanRunState(
        manifest,
        expected_ranges=RANGES,
        border_style=V7BorderStyle.TOP_AND_SIDES,
        checkpoint=checkpoint,
    )


def _quality(
    state: V7ScanRunState, source_index: int, *, major_loss: bool = False
) -> V7FrameQuality:
    boards = tuple(
        V7BoardQuality(
            position_index=position,
            symbol_content_loss=(
                V7SymbolContentLoss.MAJOR
                if major_loss and position == 4
                else V7SymbolContentLoss.NONE
            ),
            readability=V7BoardReadability.CLEAR,
            visibility=V7BoardVisibility.FULL,
            blur=V7BlurSeverity.NONE,
            occlusion=V7OcclusionSeverity.NONE,
            decoration=V7DecorationVisibility.COMPLETE,
        )
        for position in range(9)
    )
    source = state.source_manifest.sources[source_index]
    return V7FrameQuality(source.source_id, source_index, boards)


def _proof(
    state: V7ScanRunState, source_index: int, sequence_range: SemiAutomaticSelectionRange
) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.STRONG_FIVE_LABEL,
        sequence_range=sequence_range,
        supporting_source_ids=(state.source_manifest.sources[source_index].source_id,),
        reason_codes=(),
    )


def _none() -> V7RangeProofResult:
    return V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("NO_LOCAL_PROOF",))


def _weak_evidence(source_id: str) -> V7WeakFrameEvidence:
    return V7WeakFrameEvidence(
        source_id=source_id,
        visual_hash=0,
        visual_signature=bytes(64),
        labels=(
            V7LabelEvidence(0, 1, 0.99, 0.99),
            V7LabelEvidence(4, 5, 0.99, 0.99),
            V7LabelEvidence(8, 9, 0.99, 0.99),
        ),
    )


def _three_plus_three(
    state: V7ScanRunState,
    sequence_range: SemiAutomaticSelectionRange,
    source_indexes: tuple[int, int],
) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,
        sequence_range=sequence_range,
        supporting_source_ids=tuple(
            state.source_manifest.sources[index].source_id for index in source_indexes
        ),
        reason_codes=(),
    )


def _consume(
    state: V7ScanRunState,
    source_index: int,
    sequence_range: SemiAutomaticSelectionRange | None = None,
    *,
    major_loss: bool = False,
) -> None:
    state.consume(
        V7ScanObservation(
            source_index=source_index,
            proof=_none()
            if sequence_range is None
            else _proof(state, source_index, sequence_range),
            quality=_quality(state, source_index, major_loss=major_loss),
        )
    )


def test_complete_global_finalization_uses_later_a_without_rewinding_cursor() -> None:
    manifest = _manifest(b"a", b"b", b"c")
    state = _state(manifest)

    _consume(state, 0, RANGES[0], major_loss=True)
    _consume(state, 1, RANGES[1])
    _consume(state, 2, RANGES[0])
    state.complete_scan()

    finalization = state.finalize(manifest)

    assert state.phase is V7RunStatePhase.FINALIZED
    assert state.cursors.sequence_cursor_index == 1
    assert [(item.sequence_range, item.source_index) for item in finalization.selections] == [
        (RANGES[0], 2),
        (RANGES[1], 1),
    ]
    assert state.finalize(manifest) == finalization


def test_run_state_rejects_weak_evidence_for_another_pinned_source() -> None:
    manifest = _manifest(b"a")
    state = _state(manifest)

    with pytest.raises(V7RunStateError) as error:
        state.consume(
            V7ScanObservation(
                source_index=0,
                proof=_none(),
                quality=_quality(state, 0),
                weak_evidence=_weak_evidence("foreign-source"),
            )
        )

    assert error.value.code == "V7_SCAN_OBSERVATION_INVALID"
    assert state.cursors.next_source_index == 0


def test_pause_checkpoint_restart_eof_and_finalization_are_idempotent() -> None:
    manifest = _manifest(b"a", b"b")
    state = _state(manifest)
    _consume(state, 0, RANGES[0])
    state.set_viewed_source_index(0)
    state.pause()

    restored = _state(manifest, json.loads(json.dumps(state.checkpoint())))
    assert restored.phase is V7RunStatePhase.PAUSED
    assert restored.cursors == state.cursors
    restored.resume()
    _consume(restored, 1, RANGES[0])
    restored.complete_scan()

    after_eof = _state(manifest, json.loads(json.dumps(restored.checkpoint())))
    assert after_eof.phase is V7RunStatePhase.FINALIZATION_PENDING
    first = after_eof.finalize(manifest)
    after_finalization = _state(manifest, json.loads(json.dumps(after_eof.checkpoint())))

    assert after_finalization.phase is V7RunStatePhase.FINALIZED
    assert after_finalization.finalize(manifest) == first
    assert len(first.selections) == 1


def test_incomplete_cancelled_or_unscanned_state_cannot_finalize() -> None:
    manifest = _manifest(b"a", b"b")
    state = _state(manifest)
    _consume(state, 0, RANGES[0])

    with pytest.raises(V7RunStateError) as incomplete:
        state.complete_scan()
    assert incomplete.value.code == "V7_SCAN_INCOMPLETE"
    with pytest.raises(V7RunStateError) as not_complete:
        state.finalize(manifest)
    assert not_complete.value.code == "V7_SCAN_FINALIZATION_REQUIRED"

    state.cancel()
    with pytest.raises(V7RunStateError) as cancelled:
        state.finalize(manifest)
    assert cancelled.value.code == "V7_SCAN_FINALIZATION_REQUIRED"


def test_unchanged_but_undecodable_source_is_explicit_source_error_not_manifest_drift() -> None:
    manifest = _manifest(b"broken", b"good")
    state = _state(manifest)
    state.consume(
        V7ScanObservation(
            source_index=0,
            proof=_none(),
            quality=None,
            source_error_code="SOURCE_DECODE_FAILED",
        )
    )
    _consume(state, 1, RANGES[1])
    state.complete_scan()

    finalization = state.finalize(manifest)

    assert state.source_errors == {0: "SOURCE_DECODE_FAILED"}
    assert [(item.sequence_range, item.source_index) for item in finalization.selections] == [
        (RANGES[1], 1)
    ]


def test_checkpoint_retains_quality_of_the_first_own_half_of_a_three_plus_three_proof() -> None:
    manifest = _manifest(b"first", b"second")
    state = _state(manifest)
    _consume(state, 0)
    state.consume(
        V7ScanObservation(
            source_index=1,
            proof=_three_plus_three(state, RANGES[0], (0, 1)),
            quality=_quality(state, 1, major_loss=True),
        )
    )
    state.complete_scan()
    restored = _state(manifest, json.loads(json.dumps(state.checkpoint())))

    (selection,) = restored.finalize(manifest).selections

    assert selection.source_index == 0
    assert selection.proof_kinds == (V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,)


@pytest.mark.parametrize(
    "current",
    [
        (b"a", b"changed", b"c"),  # changed unselected source checksum
        (b"a", b"b", b"c", b"added"),  # added source
        (b"a", b"c"),  # removed source / shifted natural order
    ],
)
def test_any_manifest_change_blocks_finalization_even_when_unselected(
    current: tuple[bytes, ...],
) -> None:
    original = _manifest(b"a", b"b", b"c")
    state = _state(original)
    _consume(state, 0, RANGES[0])
    _consume(state, 1)
    _consume(state, 2)
    state.complete_scan()

    with pytest.raises(V7RunStateError) as error:
        state.finalize(_manifest(*current))

    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
    assert state.phase is V7RunStatePhase.BLOCKED_SOURCE_DRIFT
    with pytest.raises(V7RunStateError, match="manifest changed"):
        state.finalize(original)


def test_renamed_source_blocks_finalization() -> None:
    original = _manifest(b"a", b"b")
    state = _state(original)
    _consume(state, 0, RANGES[0])
    _consume(state, 1)
    state.complete_scan()
    renamed = _manifest_with_paths((("frame-0.jpg", b"a"), ("renamed.jpg", b"b")))

    with pytest.raises(V7RunStateError) as error:
        state.finalize(renamed)

    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"


def test_drift_after_finalization_remains_recoverably_blocked_with_historical_proposals() -> None:
    original = _manifest(b"a", b"b", b"unselected")
    state = _state(original)
    _consume(state, 0, RANGES[0])
    _consume(state, 1)
    _consume(state, 2)
    state.complete_scan()
    historical = state.finalize(original)

    with pytest.raises(V7RunStateError) as drift:
        state.finalize(_manifest(b"a", b"b", b"changed"))
    assert drift.value.code == "V7_SOURCE_MANIFEST_DRIFT"

    restored = _state(original, json.loads(json.dumps(state.checkpoint())))

    assert restored.phase is V7RunStatePhase.BLOCKED_SOURCE_DRIFT
    assert restored.finalization == historical
    with pytest.raises(V7RunStateError) as retry:
        restored.finalize(original)
    assert retry.value.code == "V7_SOURCE_MANIFEST_DRIFT"


def test_checkpoint_rejects_foreign_quality_missing_result_and_tampered_finalization() -> None:
    manifest = _manifest(b"a", b"b")
    state = _state(manifest)
    _consume(state, 0, RANGES[0])
    checkpoint = deepcopy(state.checkpoint())

    missing_result = deepcopy(checkpoint)
    missing_result["frameQualities"] = []
    with pytest.raises(V7RunStateError) as missing_error:
        _state(manifest, missing_result)
    assert missing_error.value.code == "V7_RUN_STATE_CHECKPOINT_INVALID"

    foreign_quality = deepcopy(checkpoint)
    qualities = foreign_quality["frameQualities"]
    assert isinstance(qualities, list)
    assert isinstance(qualities[0], dict)
    qualities[0]["sourceId"] = "f" * 64
    with pytest.raises(V7RunStateError) as foreign_error:
        _state(manifest, foreign_quality)
    assert foreign_error.value.code == "V7_RUN_STATE_CHECKPOINT_INVALID"

    _consume(state, 1, RANGES[0])
    state.complete_scan()
    state.finalize(manifest)
    tampered = deepcopy(state.checkpoint())
    finalization = tampered["finalization"]
    assert isinstance(finalization, dict)
    selections = finalization["selections"]
    assert isinstance(selections, list)
    assert isinstance(selections[0], dict)
    selections[0]["sourceIndex"] = 1
    with pytest.raises(V7RunStateError) as tampered_error:
        _state(manifest, tampered)
    assert tampered_error.value.code == "V7_RUN_STATE_CHECKPOINT_INVALID"


def test_checkpoint_cannot_resume_against_a_different_pinned_manifest() -> None:
    manifest = _manifest(b"a", b"b")
    state = _state(manifest)
    _consume(state, 0, RANGES[0])

    with pytest.raises(V7RunStateError) as error:
        _state(_manifest(b"a", b"changed"), state.checkpoint())

    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
