from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceStatus,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_CANDIDATE_POLICY_V2,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
    ExistingProofFirstRangeOnlyBridge,
    RangeOnlyCandidatePolicy,
    RangeOnlyLabelEvidence,
    RangeOnlyOcrAdapter,
    RangeOnlyRecognition,
    calibrate_unproven_gap_policy,
)

_CHECKSUM = "a" * 64


def _source() -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(0, "capture-1.jpg", 123, _CHECKSUM)


def _rgb() -> np.ndarray:
    return np.zeros((32, 64, 3), dtype=np.uint8)


@dataclass(frozen=True)
class _LegacyRange:
    start: int
    end: int
    confidence: float


@dataclass(frozen=True)
class _LegacyLabel:
    position_index: int
    sequence_number: int
    confidence: float
    route: str = "label_lattice"


@dataclass(frozen=True)
class _LegacyResult:
    recognized_range: _LegacyRange | None
    reason_codes: tuple[str, ...]
    label_observations: tuple[_LegacyLabel, ...]


class _LegacyRecognizer:
    version = "proof-first-test-v1"

    def __init__(self, result: _LegacyResult) -> None:
        self.result = result
        self.calls = 0
        self.received_boards: tuple[object, ...] | None = None

    def recognize(
        self,
        rgb_image: np.ndarray,
        boards: tuple[object, ...],
    ) -> _LegacyResult:
        assert rgb_image.shape == (32, 64, 3)
        self.calls += 1
        self.received_boards = boards
        return self.result


class _RangeRecognizer:
    version = "test-range-only-v1"
    fingerprint = "b" * 64

    def __init__(self, result: RangeOnlyRecognition) -> None:
        self.result = result
        self.calls = 0

    def recognize(self, rgb_image: np.ndarray) -> RangeOnlyRecognition:
        assert rgb_image.shape == (32, 64, 3)
        self.calls += 1
        return self.result


def _exact_recognition(start: int = 1, end: int = 9) -> RangeOnlyRecognition:
    return RangeOnlyRecognition(
        observed_range=SemiAutomaticSelectionRange(start, end),
        confidence=0.94,
        has_strong_local_proof=True,
        reason_codes=("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",),
        label_evidence=tuple(
            RangeOnlyLabelEvidence(position, start + position, 0.94, "label_lattice")
            for position in (0, 1, 4)
        ),
    )


def test_bridge_calls_existing_recognizer_once_with_no_board_geometry() -> None:
    legacy = _LegacyRecognizer(
        _LegacyResult(
            _LegacyRange(1, 9, 0.94),
            ("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",),
            tuple(_LegacyLabel(position, 1 + position, 0.94) for position in (0, 1, 4)),
        )
    )
    proof_calls = 0

    def strong_proof(
        recognized: object,
        reasons: tuple[str, ...],
        labels: tuple[object, ...],
    ) -> bool:
        nonlocal proof_calls
        proof_calls += 1
        assert cast(Any, recognized).start == 1
        assert reasons == ("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",)
        assert len(labels) == 3
        return True

    bridge = ExistingProofFirstRangeOnlyBridge(
        legacy,
        strong_proof_classifier=strong_proof,
        identity={"modelFingerprint": "c" * 64},
    )

    result = bridge.recognize(_rgb())

    assert legacy.calls == 1
    assert legacy.received_boards == ()
    assert proof_calls == 1
    assert result == _exact_recognition()


def test_historical_v1_contract_fingerprint_remains_immutable() -> None:
    assert RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1 == (
        "ee695bcc1e21e03313b129d45096e7a3556cd0a0f5e5a5455d477d418deab041"
    )
    assert RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2 != (
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1
    )
    assert RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT == (
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3
    )
    assert RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3 not in {
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1,
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
    }


def test_v2_candidate_policy_accepts_real_label_proportions_and_rejects_noise() -> None:
    policy = RANGE_ONLY_CANDIDATE_POLICY_V2

    assert policy.accepts(
        center=(390.0, 720.0),
        crop_shape=(34, 42),
        image_shape=(1920, 1080),
    )
    assert policy.accepts(
        center=(750.0, 820.0),
        crop_shape=(34, 65),
        image_shape=(1920, 1080),
    )
    assert not policy.accepts(
        center=(100.0, 720.0),
        crop_shape=(34, 65),
        image_shape=(1920, 1080),
    )
    assert not policy.accepts(
        center=(390.0, 720.0),
        crop_shape=(34, 20),
        image_shape=(1920, 1080),
    )


def test_candidate_policy_requires_strictly_increasing_progressive_levels() -> None:
    with pytest.raises(ValueError):
        RangeOnlyCandidatePolicy(candidate_levels=(12, 12, 36))
    with pytest.raises(ValueError):
        RangeOnlyCandidatePolicy(candidate_levels=(24, 12, 36))


def test_adapter_accepts_exact_proof_without_any_quality_input() -> None:
    recognizer = _RangeRecognizer(_exact_recognition())
    adapter = RangeOnlyOcrAdapter(
        bounds=SemiAutomaticSequenceBounds(1, 18),
        recognizer=recognizer,
    )

    result = adapter.recognize(source=_source(), rgb_image=_rgb())

    assert recognizer.calls == 1
    assert result.status is RangeEvidenceStatus.EXACT_RANGE
    assert result.expected_index == 0


def test_adapter_can_record_an_unproven_scheduled_source_without_calling_ocr() -> None:
    recognizer = _RangeRecognizer(_exact_recognition())
    adapter = RangeOnlyOcrAdapter(
        bounds=SemiAutomaticSequenceBounds(1, 18),
        recognizer=recognizer,
    )

    result = adapter.unproven(
        source=_source(),
        reason_codes=("RANGE_OCR_SKIPPED_VISUAL_REDUNDANCY",),
    )

    assert recognizer.calls == 0
    assert result.status is RangeEvidenceStatus.RANGE_UNREADABLE
    assert "RANGE_OCR_SKIPPED_VISUAL_REDUNDANCY" in result.reason_codes


def test_high_confidence_without_strong_local_proof_remains_ambiguous() -> None:
    recognizer = _RangeRecognizer(
        RangeOnlyRecognition(
            observed_range=SemiAutomaticSelectionRange(1, 9),
            confidence=0.999,
            has_strong_local_proof=False,
            reason_codes=("RANGE_OCR_FUZZY_CANDIDATE",),
        )
    )
    adapter = RangeOnlyOcrAdapter(
        bounds=SemiAutomaticSequenceBounds(1, 9),
        recognizer=recognizer,
    )

    result = adapter.recognize(source=_source(), rgb_image=_rgb())

    assert result.status is RangeEvidenceStatus.RANGE_AMBIGUOUS
    assert "RANGE_PROOF_INSUFFICIENT" in result.reason_codes


def test_partial_final_range_requires_three_in_bounds_position_proofs() -> None:
    valid = _RangeRecognizer(
        RangeOnlyRecognition(
            observed_range=SemiAutomaticSelectionRange(19, 27),
            confidence=0.94,
            has_strong_local_proof=True,
            reason_codes=("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",),
            label_evidence=tuple(
                RangeOnlyLabelEvidence(position, 19 + position, 0.94, "label_lattice")
                for position in (0, 1, 4)
            ),
        )
    )
    invalid = _RangeRecognizer(
        RangeOnlyRecognition(
            observed_range=SemiAutomaticSelectionRange(19, 27),
            confidence=0.94,
            has_strong_local_proof=True,
            reason_codes=("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",),
            label_evidence=tuple(
                RangeOnlyLabelEvidence(position, 19 + position, 0.94, "label_lattice")
                for position in (0, 1, 5)
            ),
        )
    )
    bounds = SemiAutomaticSequenceBounds(1, 23)

    accepted = RangeOnlyOcrAdapter(bounds=bounds, recognizer=valid).recognize(
        source=_source(), rgb_image=_rgb()
    )
    rejected = RangeOnlyOcrAdapter(bounds=bounds, recognizer=invalid).recognize(
        source=_source(), rgb_image=_rgb()
    )

    assert accepted.status is RangeEvidenceStatus.EXACT_RANGE
    assert accepted.observed_range == SemiAutomaticSelectionRange(19, 23)
    assert rejected.status is RangeEvidenceStatus.RANGE_AMBIGUOUS


def test_invalid_rgb_is_source_error_and_does_not_call_ocr() -> None:
    recognizer = _RangeRecognizer(_exact_recognition())
    adapter = RangeOnlyOcrAdapter(
        bounds=SemiAutomaticSequenceBounds(1, 9),
        recognizer=recognizer,
    )

    result = adapter.recognize(
        source=_source(),
        rgb_image=np.zeros((32, 64), dtype=np.uint8),
    )

    assert result.status is RangeEvidenceStatus.SOURCE_ERROR
    assert recognizer.calls == 0


def test_real_checksum_bound_corpus_calibrates_only_the_unproven_gap() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "semi_automatic_range_gap_calibration_v1.json"
    )
    payload = json.loads(fixture_path.read_text("utf-8"))

    policy = calibrate_unproven_gap_policy(
        source_count=int(payload["sourceCount"]),
        proof_source_indexes=tuple(int(value) for value in payload["proofSourceIndexes"]),
        corpus_manifest_sha256=str(payload["corpusManifestSha256"]),
    )

    assert policy.maximum_consecutive_unproven_sources == 160
    assert policy.corpus_manifest_sha256 == (
        "3ad20befe90d214c46cd671fecbd29105fd9eb60b91c93524057ce57ce42b0ff"
    )
