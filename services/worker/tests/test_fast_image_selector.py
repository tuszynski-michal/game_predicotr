from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Any, cast

import pytest
from game_predictor_worker.images.selection.adapters import (
    DeterministicParallelCandidateVerifier,
    build_default_adapters,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionResult,
    ImageSelectionSource,
    RangeEvidence,
    RepresentativeAssessment,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SelectorOpenGroupState,
    SelectorResumeState,
    SequenceRange,
)
from game_predictor_worker.images.selection.engine import FastImageSelector
from game_predictor_worker.images.selection.manifest import (
    ACCURACY_FIRST_SELECTOR_MANIFEST_V10,
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101,
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_GEOMETRY,
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE,
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INITIAL,
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_PROGRESSIVE_FALLBACK,
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    BEST_AVAILABLE_SELECTOR_MANIFEST_V4,
    BEST_EFFORT_SELECTOR_MANIFEST_V7,
    CENTER_FIRST_SELECTOR_MANIFEST_V106,
    COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102,
    CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103,
    CONTINUITY_SELECTOR_MANIFEST_V3,
    DEFAULT_SELECTOR_MANIFEST,
    DIGIT_AWARE_SELECTOR_MANIFEST_V5,
    EXACT_GAP_SELECTOR_MANIFEST_V6,
    FIRST_USABLE_SELECTOR_MANIFEST_V8,
    FOUR_LABEL_SELECTOR_MANIFEST_V107,
    HYBRID_BOUNDED_SELECTOR_MANIFEST_V104,
    LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108,
    LEGACY_SELECTOR_MANIFEST_V2,
    PARTIAL_LAYOUT_ANCHORED_SELECTOR_MANIFEST_V109,
    QUALITY_RECOVERY_SELECTOR_MANIFEST_V105,
    REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ai_docs" / "quality" / "fast-image-selector-v2-golden.json"
V105_ACCEPTANCE_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-v105-acceptance-contract.json"
)
V106_ACCEPTANCE_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-v106-acceptance-contract.json"
)
V107_ACCEPTANCE_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-v107-acceptance-contract.json"
)
V108_ACCEPTANCE_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-v108-acceptance-contract.json"
)
V109_ACCEPTANCE_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-v109-acceptance-contract.json"
)
FINGERPRINTS = {
    "a": "0" * 64,
    "b": "f" * 64,
    "c": "a" * 64,
    "d": "5" * 64,
    "e": "3" * 64,
    "drift-0": f"{0:064x}",
    "drift-7": f"{(1 << 7) - 1:064x}",
    "drift-14": f"{(1 << 14) - 1:064x}",
    "drift-21": f"{(1 << 21) - 1:064x}",
    "poison-reference": f"{0:064x}",
    "poison-last": f"{(1 << 8) - 1:064x}",
    "poison-next": f"{((1 << 16) - (1 << 8)):064x}",
    "transition-old": f"{0:064x}",
    "transition-1": f"{(1 << 13) - 1:064x}",
    "transition-2": f"{((1 << 28) - (1 << 13)):064x}",
    "transition-3": f"{((1 << 36) - (1 << 13)):064x}",
}


def _quality(name: str) -> ImageQualityMetrics:
    values = {
        "good": (0.95, 0.92, 0.98, 0.95, 0.92, 0.91, 1.0, 0.95),
        "reflection": (0.92, 0.90, 0.96, 0.80, 0.90, 0.90, 1.0, 0.89),
        "blur": (0.05, 0.92, 0.98, 0.95, 0.92, 0.91, 1.0, 0.75),
        "cropped": (0.92, 0.92, 0.98, 0.95, 0.92, 0.10, 1.0, 0.75),
        "occluded": (0.92, 0.92, 0.98, 0.95, 0.92, 0.91, 0.60, 0.75),
        "geometry_incomplete": (0.92, 0.92, 0.98, 0.95, 0.30, 0.91, 0.50, 0.70),
        "quality_fallback": (0.82, 0.50, 0.96, 0.40, 0.86, 0.80, 1.0, 0.58),
        "range_73_clear": (0.627, 0.241, 0.95, 0.956, 0.70, 0.30, 0.50, 0.491),
        "v9_unusable_early": (0.07, 0.70, 0.90, 0.85, 0.70, 0.70, 0.70, 0.28),
        "v9_usable_first": (0.30, 0.65, 0.80, 0.80, 0.70, 0.70, 0.70, 0.55),
        "v9_usable_better": (0.52, 0.72, 0.92, 0.90, 0.78, 0.78, 0.82, 0.68),
        "v9_fallback_low": (0.05, 0.25, 0.60, 0.60, 0.35, 0.35, 0.35, 0.20),
        "v9_fallback_best": (0.09, 0.62, 0.78, 0.80, 0.65, 0.65, 0.65, 0.29),
    }
    return ImageQualityMetrics(*values[name])


@dataclass
class GoldenAnalyzer:
    values: tuple[dict[str, Any], ...]

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        value = self.values[source.order_index]
        quality_name = str(value["quality"])
        return CheapImageObservation(
            source=source,
            width=960,
            height=1280,
            fingerprint_hex=FINGERPRINTS[str(value["fingerprint"])],
            geometry_signature=(0.2, 0.2, 0.2, 0.1),
            board_count=int(value["boardCount"]),
            geometry_confidence=(0.35 if quality_name == "geometry_incomplete" else 0.95),
            quality=_quality(quality_name),
        )


@dataclass
class GoldenVerifier:
    values: tuple[dict[str, Any], ...]
    calls: int = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        self.calls += 1
        value = self.values[observation.source.order_index]
        quality_name = str(value["quality"])
        start, end, confidence = cast(list[float], value["range"])
        return CandidateVerification(
            representative=RepresentativeAssessment(
                board_count=int(value.get("verifiedBoardCount", expected_board_count or 0)) or None,
                geometry_complete=quality_name != "geometry_incomplete",
                full_frame_visible=quality_name not in {"cropped", "occluded"},
                reason_codes=("IMAGE_OCCLUDED",) if quality_name == "occluded" else (),
            ),
            range_evidence=RangeEvidence(
                recognized_range=SequenceRange(
                    start=int(start),
                    end=int(end),
                    confidence=float(confidence),
                ),
            ),
        )


@dataclass
class GapVerifier(GoldenVerifier):
    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        value = self.values[observation.source.order_index]
        if value["range"] is not None:
            return super().verify(
                observation,
                expected_board_count=expected_board_count,
            )
        self.calls += 1
        return CandidateVerification(
            representative=RepresentativeAssessment(
                board_count=3,
                geometry_complete=False,
                full_frame_visible=False,
                reason_codes=("BOARD_CANDIDATE_COUNT",),
            ),
            range_evidence=RangeEvidence(
                recognized_range=None,
                reason_codes=("RANGE_LABEL_LATTICE_INCOMPLETE",),
            ),
        )


def _sources(case_id: str, count: int) -> tuple[ImageSelectionSource, ...]:
    return tuple(
        ImageSelectionSource(
            order_index=index,
            relative_path=f"{case_id}/photo{index + 1}.jpg",
            stored_relative_path=f"{index + 1:08d}.jpg",
            checksum_sha256=hashlib.sha256(f"{case_id}:{index}".encode()).hexdigest(),
            size_bytes=1024 + index,
        )
        for index in range(count)
    )


def _golden_cases() -> tuple[dict[str, Any], ...]:
    payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert payload["selectorVersion"] == LEGACY_SELECTOR_MANIFEST_V2.algorithm_version
    return tuple(payload["cases"])


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: str(case["id"]))
@pytest.mark.parametrize(
    "manifest",
    (
        LEGACY_SELECTOR_MANIFEST_V2,
        CONTINUITY_SELECTOR_MANIFEST_V3,
    ),
    ids=("v2", "v3"),
)
def test_fast_selector_matches_grouping_and_quality_golden(
    case: dict[str, Any],
    manifest: SelectorManifest,
) -> None:
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    verifier = GoldenVerifier(observations)

    result = FastImageSelector(manifest).select(
        _sources(str(case["id"]), len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=verifier,
    )

    assert [group.status.value for group in result.groups] == case["expectedStatuses"]
    assert [
        None if group.range is None else [group.range.start, group.range.end]
        for group in result.groups
    ] == case["expectedRanges"]
    if "expectedDuplicateOf" in case:
        assert [group.duplicate_of_group_order for group in result.groups] == case[
            "expectedDuplicateOf"
        ]
    assert verifier.calls <= len(result.groups) * manifest.top_k
    assert result.verification_count == verifier.calls


def test_fast_selector_is_deterministic_for_same_manifest_and_bytes() -> None:
    case = _golden_cases()[0]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    sources = _sources(str(case["id"]), len(observations))

    first = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    second = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert first.to_dict() == second.to_dict()


def test_single_last_photo_can_form_a_verified_new_range() -> None:
    case = _golden_cases()[0]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"][:3])

    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        _sources("single-last-range", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in result.groups
    ] == [(19, 27), (400, 408)]
    assert all(group.status.value == "auto_selected" for group in result.groups)


def test_full_range_verification_supersedes_unstable_cheap_frame_geometry() -> None:
    source = _sources("dark-cabinet", 1)[0]
    analyzer = GoldenAnalyzer(
        (
            {
                "boardCount": 5,
                "fingerprint": "a",
                "quality": "geometry_incomplete",
                "range": [1, 9, 0.99],
            },
        )
    )
    verifier = GoldenVerifier(
        (
            {
                "boardCount": 9,
                "fingerprint": "a",
                "quality": "good",
                "range": [1, 9, 0.99],
                "verifiedBoardCount": 9,
            },
        )
    )

    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        (source,),
        analyzer=analyzer,
        verifier=verifier,
    )

    assert result.groups[0].status.value == "auto_selected"
    assert result.groups[0].selected_candidate is not None


def test_unconfirmed_visual_change_does_not_create_a_singleton_group() -> None:
    observations = (
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [1, 9, 0.99]},
        {"boardCount": 9, "fingerprint": "b", "quality": "good", "range": [1, 9, 0.99]},
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [1, 9, 0.99]},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [10, 18, 0.99]},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [10, 18, 0.99]},
    )

    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        _sources("unstable-frame", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert len(result.groups) == 2
    assert [group.source_count for group in result.groups] == [3, 2]
    assert [(group.range.start, group.range.end) for group in result.groups if group.range] == [
        (1, 9),
        (10, 18),
    ]


def test_v3_uses_temporal_continuity_without_merging_the_next_page() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "drift-0",
            "quality": "good",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "drift-7",
            "quality": "reflection",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "drift-14",
            "quality": "reflection",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "drift-21",
            "quality": "reflection",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "b",
            "quality": "good",
            "range": [10, 18, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "b",
            "quality": "good",
            "range": [10, 18, 0.99],
        },
    )
    sources = _sources("temporal-camera-drift", len(observations))

    legacy = FastImageSelector(LEGACY_SELECTOR_MANIFEST_V2).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    stabilized = FastImageSelector(CONTINUITY_SELECTOR_MANIFEST_V3).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert [group.source_count for group in legacy.groups] == [2, 2, 2]
    assert [group.source_count for group in stabilized.groups] == [4, 2]
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in stabilized.groups
    ] == [(1, 9), (10, 18)]


def test_legacy_v2_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        LEGACY_SELECTOR_MANIFEST_V2.fingerprint
        == "6da6fb8a247b41827a87437e6936cc4c449e06a0bbd24acd8b3159d576c1ce8e"
    )
    assert (
        selector_manifest_for_fingerprint(LEGACY_SELECTOR_MANIFEST_V2.fingerprint)
        is LEGACY_SELECTOR_MANIFEST_V2
    )


def test_v3_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        selector_manifest_for_fingerprint(CONTINUITY_SELECTOR_MANIFEST_V3.fingerprint)
        is CONTINUITY_SELECTOR_MANIFEST_V3
    )


def test_v4_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        BEST_AVAILABLE_SELECTOR_MANIFEST_V4.fingerprint
        == "2e327902cb38cade250df019b4589ea0364512358d1cb3cb20e5525c390c8e37"
    )
    assert (
        selector_manifest_for_fingerprint(BEST_AVAILABLE_SELECTOR_MANIFEST_V4.fingerprint)
        is BEST_AVAILABLE_SELECTOR_MANIFEST_V4
    )


def test_v5_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        DIGIT_AWARE_SELECTOR_MANIFEST_V5.fingerprint
        == "ff75216bcd71f7f2484fef2c2868eda639152ba7efd98e00f23e08a89585e3fb"
    )
    assert (
        selector_manifest_for_fingerprint(DIGIT_AWARE_SELECTOR_MANIFEST_V5.fingerprint)
        is DIGIT_AWARE_SELECTOR_MANIFEST_V5
    )


def test_v6_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        EXACT_GAP_SELECTOR_MANIFEST_V6.fingerprint
        == "22b0d13545c087b53e197dd20edaf214fbebd99b51036cd84dc624c76577bf1e"
    )
    assert (
        selector_manifest_for_fingerprint(EXACT_GAP_SELECTOR_MANIFEST_V6.fingerprint)
        is EXACT_GAP_SELECTOR_MANIFEST_V6
    )


def test_v7_manifest_remains_resolvable_for_durable_job_resume() -> None:
    assert (
        BEST_EFFORT_SELECTOR_MANIFEST_V7.fingerprint
        == "21d634e0657c2e53564157901d3873747d0c642bf7d30141449c990646fd0d55"
    )
    assert (
        selector_manifest_for_fingerprint(BEST_EFFORT_SELECTOR_MANIFEST_V7.fingerprint)
        is BEST_EFFORT_SELECTOR_MANIFEST_V7
    )


def test_v8_manifests_remain_resolvable_after_v9_activation() -> None:
    assert (
        REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8.fingerprint
        == "284eb7f842b6d09910aa34bbf4a889f9b246f26ae6767b138d4ed8cdee2a68f3"
    )
    assert (
        FIRST_USABLE_SELECTOR_MANIFEST_V8.fingerprint
        == "9dc754cca7e7e7afe23e8a25c8574e0ef4ed5f7fd5829a24984c25f4c256f42d"
    )


def test_v10_9_manifest_is_the_default_and_older_versions_remain_resolvable() -> None:
    assert APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.algorithm_version == "fast-image-selector-v9"
    assert (
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.fingerprint
        == "eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb"
    )
    assert DEFAULT_SELECTOR_MANIFEST is PARTIAL_LAYOUT_ANCHORED_SELECTOR_MANIFEST_V109
    assert DEFAULT_SELECTOR_MANIFEST.algorithm_version == "fast-image-selector-v10.9"
    assert (
        DEFAULT_SELECTOR_MANIFEST.fingerprint
        == "6c14854d3f38744a3451da11e516bc4f10c348d3f8a4c32e9a999c69e9979720"
    )
    assert (
        LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108.fingerprint
        == "eb5006f3b6ed5e63b668074bf2e81d8b162d5794d542fd00457ee6a860682769"
    )
    assert (
        FOUR_LABEL_SELECTOR_MANIFEST_V107.fingerprint
        == "322d4f5319f036cd0e1dc01f2dc781e68cb0a17dbb05f25abba409f842a732d6"
    )
    assert (
        CENTER_FIRST_SELECTOR_MANIFEST_V106.fingerprint
        == "bedb6d0fcba5e44faffcad849d5aa40d4ecc0e5277a7b0d5876dc000e33c3050"
    )
    assert (
        QUALITY_RECOVERY_SELECTOR_MANIFEST_V105.fingerprint
        == "6ba81ff5a277c92a0cbf01b88aea7f8c896eee76aebb8323b2ed9cb4b3e28a32"
    )
    assert (
        HYBRID_BOUNDED_SELECTOR_MANIFEST_V104.fingerprint
        == "8e913c923036ba7aa3f448d1049a37676d133b603103d0b641912ef17004ee7e"
    )
    assert (
        COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102.fingerprint
        == "793aa567d59b6f443d774c84b11349dbbe8a797e8ea46c8d15d186b800566143"
    )
    assert (
        CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103.fingerprint
        == "b5210620e3127fa4addebcb158d4e717df7d89ed08c6d09f354756bf18cab7e4"
    )
    assert (
        ACCURACY_FIRST_SELECTOR_MANIFEST_V10.fingerprint
        == "464d7af527f3532d4115c14666f4160831a9b0074343408584d1e2376614004c"
    )
    assert (
        ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INITIAL.fingerprint
        == "c0d91155e5afb254a0e4aad9d2a689a1c6a951b59b267ddcb0f658e1e2e605dc"
    )
    assert (
        ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_GEOMETRY.fingerprint
        == "dc01816c49f0b2c9124b661201367b96b78095d9f13169d105806a70006071a7"
    )
    assert (
        ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101.fingerprint
        == "af009c7ecc726f4eb6daa296b20b55f7795e3ca714ffa8f03e9ceb61c3a4b020"
    )
    assert (
        ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_PROGRESSIVE_FALLBACK.fingerprint
        == "da6e7a70821f7c418808b84480d47e7ca09f35025b8ee0a3cad7e93d1baa016d"
    )
    assert (
        ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE.fingerprint
        == "286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40"
    )
    assert (
        selector_manifest_for_fingerprint(LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108.fingerprint)
        is LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108
    )
    assert (
        selector_manifest_for_fingerprint(FOUR_LABEL_SELECTOR_MANIFEST_V107.fingerprint)
        is FOUR_LABEL_SELECTOR_MANIFEST_V107
    )
    assert (
        selector_manifest_for_fingerprint(CENTER_FIRST_SELECTOR_MANIFEST_V106.fingerprint)
        is CENTER_FIRST_SELECTOR_MANIFEST_V106
    )
    assert (
        selector_manifest_for_fingerprint(QUALITY_RECOVERY_SELECTOR_MANIFEST_V105.fingerprint)
        is QUALITY_RECOVERY_SELECTOR_MANIFEST_V105
    )
    assert (
        selector_manifest_for_fingerprint(
            CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103.fingerprint
        )
        is CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103
    )
    assert (
        selector_manifest_for_fingerprint(
            COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102.fingerprint
        )
        is COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102
    )
    assert (
        selector_manifest_for_fingerprint(
            ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INITIAL.fingerprint
        )
        is ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INITIAL
    )
    assert (
        selector_manifest_for_fingerprint(
            ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_GEOMETRY.fingerprint
        )
        is ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_GEOMETRY
    )
    assert (
        selector_manifest_for_fingerprint(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101.fingerprint)
        is ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101
    )
    assert (
        selector_manifest_for_fingerprint(
            ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_PROGRESSIVE_FALLBACK.fingerprint
        )
        is ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_PROGRESSIVE_FALLBACK
    )
    assert (
        selector_manifest_for_fingerprint(
            ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE.fingerprint
        )
        is ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE
    )


def test_v10_5_acceptance_contract_remains_pinned_to_its_historical_manifest() -> None:
    contract = json.loads(V105_ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert contract["selectorVersion"] == QUALITY_RECOVERY_SELECTOR_MANIFEST_V105.algorithm_version
    assert contract["selectorFingerprint"] == QUALITY_RECOVERY_SELECTOR_MANIFEST_V105.fingerprint
    assert contract["gates"] == {
        "maximumFullRunSeconds": 18_000,
        "maximumManualPercent": 35.0,
        "minimumKnownRangePercent": 95.0,
        "ownerReviewedWrongRangeCount": 0,
        "ownerReviewedWrongRepresentativeCount": 0,
    }
    assert (
        selector_manifest_for_fingerprint(ACCURACY_FIRST_SELECTOR_MANIFEST_V10.fingerprint)
        is ACCURACY_FIRST_SELECTOR_MANIFEST_V10
    )
    assert (
        selector_manifest_for_fingerprint(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.fingerprint)
        is APPEARANCE_ONLY_SELECTOR_MANIFEST_V9
    )


def test_v10_6_acceptance_contract_remains_pinned_to_its_historical_manifest() -> None:
    contract = json.loads(V106_ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert contract["selectorVersion"] == CENTER_FIRST_SELECTOR_MANIFEST_V106.algorithm_version
    assert contract["selectorFingerprint"] == CENTER_FIRST_SELECTOR_MANIFEST_V106.fingerprint
    assert contract["sampling"] == {
        "centerCandidateCount": 5,
        "edgeCandidateCountPerSide": 3,
        "fallbackOrder": ["center", "edges", "best-readable-cheap-scan"],
    }


def test_v10_7_acceptance_contract_remains_pinned_to_its_historical_manifest() -> None:
    contract = json.loads(V107_ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert contract["selectorVersion"] == FOUR_LABEL_SELECTOR_MANIFEST_V107.algorithm_version
    assert contract["selectorFingerprint"] == FOUR_LABEL_SELECTOR_MANIFEST_V107.fingerprint
    assert contract["ocr"] == {
        "candidateLevels": [9, 18, 36],
        "consecutiveLabelCount": 4,
        "minimumOcrConfidence": 0.72,
    }
    assert FOUR_LABEL_SELECTOR_MANIFEST_V107.progressive_visible_label_fallback_policy is not None
    assert (
        FOUR_LABEL_SELECTOR_MANIFEST_V107.progressive_visible_label_fallback_policy.candidate_levels
        == (9, 18, 36)
    )
    assert FOUR_LABEL_SELECTOR_MANIFEST_V107.contiguous_sequence_window_policy is not None
    assert (
        FOUR_LABEL_SELECTOR_MANIFEST_V107.contiguous_sequence_window_policy.consecutive_label_count
        == 4
    )


def test_v10_8_acceptance_contract_remains_pinned_to_its_historical_manifest() -> None:
    contract = json.loads(V108_ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert contract["selectorVersion"] == LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108.algorithm_version
    assert contract["selectorFingerprint"] == LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108.fingerprint
    assert contract["ocr"] == {
        "candidateLevels": [9, 18],
        "consecutiveLabelCount": 4,
        "minimumOcrConfidence": 0.72,
        "unanchoredFourLabelInference": False,
    }
    assert contract["layoutAnchor"] == {
        "expectedLayoutCount": 9,
        "minimumObservedLayoutFrames": 5,
        "minimumRedSaturation": 60,
        "minimumRedValue": 30,
        "minimumSharpLayoutCount": 5,
        "minimumLayoutSharpness": 0.05,
        "requiresAllRowsAndColumns": True,
    }
    assert contract["sampling"] == {
        "centerCandidateCount": 5,
        "edgeCandidateCountPerSide": 3,
    }


def test_v10_9_acceptance_contract_matches_the_default_manifest() -> None:
    contract = json.loads(V109_ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert contract["selectorVersion"] == DEFAULT_SELECTOR_MANIFEST.algorithm_version
    assert contract["selectorFingerprint"] == DEFAULT_SELECTOR_MANIFEST.fingerprint
    assert contract["layoutAnchor"]["minimumObservedLayoutFrames"] == 3
    assert contract["layoutAnchor"]["requiresTwoRowsAndColumns"] is True
    assert contract["ocr"]["strongLabelCount"] == 3
    assert contract["ocr"]["weakLabelCount"] == 2
    assert contract["ocr"]["weakEvidenceDistinctJpegCount"] == 2


@pytest.mark.parametrize(
    ("manifest", "redundant_status"),
    (
        (
            LAYOUT_ANCHORED_SELECTOR_MANIFEST_V108,
            SelectionGroupStatus.SKIPPED_UNREADABLE,
        ),
        (DEFAULT_SELECTOR_MANIFEST, SelectionGroupStatus.SKIPPED_EXISTING_RANGE),
    ),
)
def test_layout_anchored_selectors_collapse_redundant_fragments_and_one_exact_missing_range(
    manifest: SelectorManifest,
    redundant_status: SelectionGroupStatus,
) -> None:
    sources = _sources("v108-fragment-recovery", 7)

    def candidate(index: int) -> CandidateResult:
        return CandidateResult(
            source=sources[index],
            decision=CandidateDecision.SELECTED_AUTOMATIC,
            quality=_quality("good"),
            recognized_range=None,
            reason_codes=("RANGE_LABEL_LATTICE_INCOMPLETE",),
        )

    def group(
        order: int,
        status: SelectionGroupStatus,
        recognized_range: SequenceRange | None = None,
    ) -> SelectionGroupResult:
        selected = candidate(order) if status is SelectionGroupStatus.RANGE_REQUIRED else None
        return SelectionGroupResult(
            group_order=order,
            source_count=1,
            range=recognized_range,
            fingerprint_sha256=hashlib.sha256(str(order).encode()).hexdigest(),
            board_count_consensus=9,
            status=status,
            selected_candidate=selected,
            top_candidates=(() if selected is None else (selected,)),
            reference_fingerprint_hex="0" * 64,
        )

    groups = [
        group(0, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(10, 18, 0.99)),
        group(1, SelectionGroupStatus.RANGE_REQUIRED),
        group(2, SelectionGroupStatus.RANGE_REQUIRED),
        group(3, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(19, 27, 0.99)),
        group(4, SelectionGroupStatus.RANGE_REQUIRED),
        group(5, SelectionGroupStatus.RANGE_REQUIRED),
        group(6, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(37, 45, 0.99)),
    ]

    recovered = FastImageSelector(manifest)._recover_bounded_best_available_groups(groups)

    assert [group.status for group in recovered] == [
        SelectionGroupStatus.AUTO_SELECTED,
        redundant_status,
        redundant_status,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        SelectionGroupStatus.AUTO_SELECTED,
    ]
    assert all(
        "RANGE_REDUNDANT_TRANSITION_FRAGMENT" in candidate.reason_codes
        for group in recovered[1:3]
        for candidate in group.top_candidates
    )
    if redundant_status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE:
        assert all(group.range == SequenceRange(10, 18, 0.99) for group in recovered[1:3])
        assert all(group.duplicate_of_group_order == 0 for group in recovered[1:3])
    inferred = recovered[4]
    assert inferred.range == SequenceRange(28, 36, 0.9)
    assert inferred.selected_candidate is not None
    assert "RANGE_EXACT_GAP_INFERRED" in inferred.selected_candidate.reason_codes
    assert recovered[5].duplicate_of_group_order == inferred.group_order


def test_historical_v10_manifest_keeps_forced_cursor_behavior() -> None:
    signatures = tuple(
        signature
        for page in range(2)
        for signature in (_appearance_signature(page), _appearance_signature(page, drift=0.1))
    )
    ranges = (
        SequenceRange(1, 9, 0.99),
        SequenceRange(1, 9, 0.99),
        SequenceRange(400, 408, 0.99),
        SequenceRange(400, 408, 0.99),
    )

    result = FastImageSelector(ACCURACY_FIRST_SELECTOR_MANIFEST_V10).select(
        _sources("historical-v10-continuity", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_V10RangeVerifier(ranges),
        first_sequence_number=1,
    )

    assert [group.range for group in result.groups] == [
        SequenceRange(1, 9, 1.0),
        SequenceRange(10, 18, 1.0),
    ]


def test_v10_evaluates_the_whole_group_and_selects_the_best_candidate() -> None:
    signatures = tuple(_appearance_signature(0, drift=index * 0.05) for index in range(4))
    qualities = tuple(
        _quality(name)
        for name in (
            "v9_usable_first",
            "good",
            "v9_usable_better",
            "reflection",
        )
    )

    @dataclass
    class Verifier:
        calls: int = 0

        def verify(
            self,
            observation: CheapImageObservation,
            *,
            expected_board_count: int | None,
        ) -> CandidateVerification:
            del expected_board_count
            self.calls += 1
            return CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(SequenceRange(1, 9, 0.96)),
            )

    verifier = Verifier()
    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-whole-group", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
        first_sequence_number=1,
    )

    assert verifier.calls == 4
    assert result.groups[0].selected_candidate is not None
    assert result.groups[0].selected_candidate.source.order_index == 1
    assert result.groups[0].range == SequenceRange(1, 9, 0.96)


@dataclass
class _SeparatedEvidenceVerifier:
    verifications: tuple[CandidateVerification, ...]

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        return self.verifications[observation.source.order_index]


@dataclass
class _AdaptiveConsensusVerifier:
    ranges: tuple[SequenceRange | None, ...]
    incomplete_representatives: frozenset[int] = frozenset()
    verify_calls: list[int] = field(default_factory=list)
    representative_calls: list[int] = field(default_factory=list)
    stops: list[tuple[str, int, int]] = field(default_factory=list)

    def _result(
        self,
        observation: CheapImageObservation,
        *,
        include_range: bool,
    ) -> CandidateVerification:
        index = observation.source.order_index
        complete = index not in self.incomplete_representatives
        return CandidateVerification(
            representative=RepresentativeAssessment(9 if complete else 4, complete, complete),
            range_evidence=RangeEvidence(
                self.ranges[index] if include_range else None,
                () if include_range else ("RANGE_EVIDENCE_NOT_REQUESTED",),
            ),
        )

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        self.verify_calls.append(observation.source.order_index)
        return self._result(observation, include_range=True)

    def assess_representative(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        self.representative_calls.append(observation.source.order_index)
        return self._result(observation, include_range=False)

    def record_adaptive_range_stop(
        self,
        reason: str,
        *,
        evidence_count: int,
        candidate_count: int,
    ) -> None:
        self.stops.append((reason, evidence_count, candidate_count))


def test_v10_1_adaptive_consensus_stops_ocr_after_two_agreeing_frames() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    qualities = (_quality("good"), _quality("good")) + tuple(
        _quality("reflection") for _ in range(10)
    )
    verifier = _AdaptiveConsensusVerifier(
        tuple(SequenceRange(400, 408, 0.98) for _ in range(12)),
        incomplete_representatives=frozenset({0, 1}),
    )

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-adaptive-two", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
    )

    group = result.groups[0]
    assert verifier.verify_calls == [0, 1]
    assert verifier.representative_calls == list(range(2, 12))
    assert verifier.stops == [("confirmed", 2, 12)]
    assert group.range == SequenceRange(400, 408, 0.98)
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 2


def test_v10_4_verifies_only_two_range_frames_and_selects_best_whole_group_image() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    qualities = (_quality("reflection"), _quality("reflection"), _quality("good")) + tuple(
        _quality("quality_fallback") for _ in range(9)
    )
    verifier = _AdaptiveConsensusVerifier(tuple(SequenceRange(400, 408, 0.98) for _ in range(12)))

    result = FastImageSelector(HYBRID_BOUNDED_SELECTOR_MANIFEST_V104).select(
        _sources("v10-4-bounded-whole-group", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
        first_sequence_number=400,
    )

    group = result.groups[0]
    assert verifier.verify_calls == [2, 0]
    assert verifier.representative_calls == []
    assert result.verification_count == 2
    assert group.range == SequenceRange(400, 408, 0.98)
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 2


def test_v10_5_stops_after_one_exact_range_and_keeps_full_group_quality_ranking() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    verifier = _AdaptiveConsensusVerifier(tuple(SequenceRange(7300, 7308, 0.98) for _ in range(12)))

    result = FastImageSelector(QUALITY_RECOVERY_SELECTOR_MANIFEST_V105).select(
        _sources("v10-5-exact-first", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
        first_sequence_number=7300,
    )

    group = result.groups[0]
    assert verifier.verify_calls == [0]
    assert result.verification_count == 1
    assert group.status is SelectionGroupStatus.AUTO_SELECTED
    assert group.range == SequenceRange(7300, 7308, 0.98)
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 0


def test_v10_5_accepts_two_matching_fuzzy_reads_but_never_one() -> None:
    @dataclass
    class FuzzyVerifier:
        calls: list[int] = field(default_factory=list)

        def verify(
            self,
            observation: CheapImageObservation,
            *,
            expected_board_count: int | None,
        ) -> CandidateVerification:
            del expected_board_count
            self.calls.append(observation.source.order_index)
            return CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(
                    SequenceRange(7300, 7308, 0.82),
                    ("RANGE_OCR_FUZZY_CANDIDATE",),
                ),
            )

    verifier = FuzzyVerifier()
    signatures = (_appearance_signature(0), _appearance_signature(0, drift=0.1))
    result = FastImageSelector(QUALITY_RECOVERY_SELECTOR_MANIFEST_V105).select(
        _sources("v10-5-fuzzy-consensus", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
        first_sequence_number=7300,
    )

    assert verifier.calls == [0, 1]
    assert result.groups[0].status is SelectionGroupStatus.AUTO_SELECTED
    assert result.groups[0].range == SequenceRange(7300, 7308, 0.92)
    assert result.groups[0].selected_candidate is not None
    assert "RANGE_OCR_FUZZY_CONSENSUS" in result.groups[0].selected_candidate.reason_codes


def test_two_label_evidence_requires_two_distinct_jpeg_checksums() -> None:
    sources = _sources("same-jpeg-fuzzy-evidence", 2)
    duplicate = replace(sources[1], checksum_sha256=sources[0].checksum_sha256)
    analyzer = _AppearanceAnalyzer((_appearance_signature(0), _appearance_signature(0)))
    observations = (analyzer.analyze(sources[0]), analyzer.analyze(duplicate))
    verification = CandidateVerification(
        representative=RepresentativeAssessment(9, True, True),
        range_evidence=RangeEvidence(
            SequenceRange(7300, 7308, 0.82),
            ("RANGE_OCR_FUZZY_CANDIDATE",),
        ),
    )

    assert FastImageSelector(DEFAULT_SELECTOR_MANIFEST)._hybrid_group_range(  # noqa: SLF001
        [(observations[0], verification), (observations[1], verification)]
    ) == (None, None)


def test_v10_5_keeps_v10_4_boundary_buffer_with_the_broad_descriptor() -> None:
    signatures = (
        _appearance_signature(0),
        _appearance_signature(1, drift=-1.0),
        _appearance_signature(1, drift=1.0),
    )
    verifier = _AdaptiveConsensusVerifier(
        (
            SequenceRange(100, 108, 0.98),
            SequenceRange(109, 117, 0.98),
            SequenceRange(109, 117, 0.98),
        )
    )

    result = FastImageSelector(QUALITY_RECOVERY_SELECTOR_MANIFEST_V105).select(
        _sources("v10-5-boundary-buffer", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
        first_sequence_number=100,
    )

    assert [group.source_count for group in result.groups] == [1, 2]
    assert [group.range for group in result.groups] == [
        SequenceRange(100, 108, 0.98),
        SequenceRange(109, 117, 0.98),
    ]


def test_v10_6_selects_a_readable_representative_from_five_center_frames() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(15))
    qualities = tuple(
        _quality("reflection") if index == 7 else _quality("quality_fallback")
        for index in range(15)
    )
    verifier = _AdaptiveConsensusVerifier(tuple(None for _ in range(15)))

    result = FastImageSelector(CENTER_FIRST_SELECTOR_MANIFEST_V106).select(
        _sources("v10-6-center-five", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
    )

    group = result.groups[0]
    assert set(verifier.verify_calls).issubset({5, 6, 7, 8, 9})
    assert group.status is SelectionGroupStatus.RANGE_REQUIRED
    assert group.range is None
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 7


def test_v10_6_falls_back_to_three_frames_from_each_edge() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(15))
    unreadable = replace(_quality("blur"), sharpness=0.01, overall_score=0.10)
    qualities = tuple(
        _quality("good") if index in {0, 1, 2, 12, 13, 14} else unreadable for index in range(15)
    )
    verifier = _AdaptiveConsensusVerifier(tuple(None for _ in range(15)))

    result = FastImageSelector(CENTER_FIRST_SELECTOR_MANIFEST_V106).select(
        _sources("v10-6-edge-six", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
    )

    group = result.groups[0]
    assert set(verifier.verify_calls).issubset({0, 1, 2, 12, 13, 14})
    assert group.status is SelectionGroupStatus.RANGE_REQUIRED
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 0


def test_v10_9_checks_edges_after_readable_center_frames_have_no_range() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(15))
    verifier = _AdaptiveConsensusVerifier(tuple(None for _ in range(15)))

    result = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
        _sources("v10-8-center-then-edges", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
    )

    expected = {0, 1, 2, 5, 6, 7, 8, 9, 12, 13, 14}
    group = result.groups[0]
    assert set(verifier.verify_calls) == expected
    assert group.status is SelectionGroupStatus.RANGE_REQUIRED
    assert group.selected_candidate is not None


def test_v10_6_skips_an_entirely_unreadable_group_without_ocr_or_review() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(15))
    unreadable = replace(_quality("blur"), sharpness=0.01, overall_score=0.10)
    verifier = _AdaptiveConsensusVerifier(tuple(None for _ in range(15)))

    result = FastImageSelector(CENTER_FIRST_SELECTOR_MANIFEST_V106).select(
        _sources("v10-6-unreadable", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, tuple(unreadable for _ in range(15))),
        verifier=verifier,
    )

    group = result.groups[0]
    assert verifier.verify_calls == []
    assert result.verification_count == 0
    assert group.status is SelectionGroupStatus.SKIPPED_UNREADABLE
    assert group.selected_candidate is None
    assert all(
        "QUALITY_UNREADABLE_GROUP" in candidate.reason_codes for candidate in group.top_candidates
    )


def test_v10_4_pending_frames_only_need_to_confirm_change_from_old_group() -> None:
    signatures = (
        _appearance_signature(0),
        _appearance_signature(1, drift=-1.0),
        _appearance_signature(1, drift=1.0),
    )
    verifier = _AdaptiveConsensusVerifier(
        (
            SequenceRange(100, 108, 0.98),
            SequenceRange(109, 117, 0.98),
            SequenceRange(109, 117, 0.98),
        )
    )

    result = FastImageSelector(HYBRID_BOUNDED_SELECTOR_MANIFEST_V104).select(
        _sources("v10-4-boundary-buffer", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
        first_sequence_number=100,
    )

    assert [group.source_count for group in result.groups] == [1, 2]
    assert [group.range for group in result.groups] == [
        SequenceRange(100, 108, 0.98),
        SequenceRange(109, 117, 0.98),
    ]
    assert verifier.verify_calls == [0, 1, 2]


def test_v10_4_accepts_fuzzy_range_only_from_two_matching_grid_reads() -> None:
    @dataclass
    class FuzzyVerifier:
        calls: list[int] = field(default_factory=list)

        def verify(
            self,
            observation: CheapImageObservation,
            *,
            expected_board_count: int | None,
        ) -> CandidateVerification:
            del expected_board_count
            self.calls.append(observation.source.order_index)
            return CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(
                    SequenceRange(7300, 7308, 0.82),
                    ("RANGE_OCR_FUZZY_CANDIDATE",),
                ),
            )

    verifier = FuzzyVerifier()
    signatures = (_appearance_signature(0), _appearance_signature(0, drift=0.1))

    result = FastImageSelector(HYBRID_BOUNDED_SELECTOR_MANIFEST_V104).select(
        _sources("v10-4-fuzzy-consensus", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
    )

    assert verifier.calls == [0, 1]
    assert result.groups[0].status is SelectionGroupStatus.AUTO_SELECTED
    assert result.groups[0].range == SequenceRange(7300, 7308, 0.92)
    assert result.groups[0].selected_candidate is not None
    assert "RANGE_OCR_FUZZY_CONSENSUS" in result.groups[0].selected_candidate.reason_codes


def test_v10_1_missing_evidence_expands_to_the_next_level() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    ranges = (None, None, SequenceRange(100, 108, 0.97), SequenceRange(100, 108, 0.98)) + (
        (None,) * 8
    )
    verifier = _AdaptiveConsensusVerifier(ranges)

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-adaptive-four", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
    )

    assert verifier.verify_calls == [0, 1, 2, 3]
    assert verifier.representative_calls == list(range(4, 12))
    assert verifier.stops == [("confirmed", 4, 12)]
    assert result.groups[0].range == SequenceRange(100, 108, 0.98)


def test_v10_1_conflict_keeps_range_evidence_enabled_through_top_12() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    ranges = (
        SequenceRange(1, 9, 0.99),
        SequenceRange(400, 408, 0.99),
        *(SequenceRange(1, 9, 0.98) for _ in range(10)),
    )

    def run() -> tuple[ImageSelectionResult, _AdaptiveConsensusVerifier]:
        verifier = _AdaptiveConsensusVerifier(ranges)
        result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
            _sources("v10-1-adaptive-conflict", len(signatures)),
            analyzer=_AppearanceAnalyzer(signatures),
            verifier=verifier,
        )
        return result, verifier

    first, first_verifier = run()
    second, second_verifier = run()

    assert first_verifier.verify_calls == list(range(12))
    assert first_verifier.representative_calls == []
    assert first_verifier.stops == [("conflict_exhausted", 12, 12)]
    assert first.to_dict() == second.to_dict()
    assert first_verifier.verify_calls == second_verifier.verify_calls


def test_v10_1_parallel_verification_matches_single_worker_result_and_order() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(12))
    qualities = (_quality("good"), _quality("good")) + tuple(
        _quality("reflection") for _ in range(10)
    )
    ranges = tuple(SequenceRange(400, 408, 0.98) for _ in range(12))
    sequential_verifier = _AdaptiveConsensusVerifier(ranges)
    sequential = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-single-parity", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=sequential_verifier,
    )
    parallel_workers = (
        _AdaptiveConsensusVerifier(ranges),
        _AdaptiveConsensusVerifier(ranges),
    )
    parallel = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-single-parity", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=DeterministicParallelCandidateVerifier(parallel_workers),
    )

    assert parallel.to_dict() == sequential.to_dict()
    assert sorted(index for worker in parallel_workers for index in worker.verify_calls) == [0, 1]
    assert sorted(
        index for worker in parallel_workers for index in worker.representative_calls
    ) == list(range(2, 12))


def test_v10_1_best_representative_can_use_range_from_another_frame() -> None:
    signatures = (_appearance_signature(0), _appearance_signature(0, drift=0.1))
    verifier = _SeparatedEvidenceVerifier(
        (
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(None, ("RANGE_ANCHOR_UNREADABLE",)),
            ),
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(SequenceRange(400, 408, 0.98)),
            ),
        )
    )

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-separated-evidence", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, (_quality("good"), _quality("reflection"))),
        verifier=verifier,
    )

    group = result.groups[0]
    assert group.status is SelectionGroupStatus.AUTO_SELECTED
    assert group.range == SequenceRange(400, 408, 0.98)
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 0
    assert group.selected_candidate.recognized_range == group.range


def test_v10_2_rejects_wrong_screen_representative_and_selects_matching_frame() -> None:
    sources = _sources("v10-2-false-merge", 2)
    analyzer = _AppearanceAnalyzer(
        (_appearance_signature(0), _appearance_signature(0)),
        (_quality("good"), _quality("reflection")),
    )
    observations = [analyzer.analyze(source) for source in sources]
    old_range = SequenceRange(18_406, 18_414, 0.99)
    new_range = SequenceRange(18_415, 18_423, 0.99)
    verified = [
        (
            observations[0],
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(None, ("RANGE_EVIDENCE_NOT_REQUESTED",)),
            ),
        ),
        (
            observations[1],
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(old_range),
            ),
        ),
    ]
    candidates = tuple(
        CandidateResult(
            source=observation.source,
            decision=CandidateDecision.ELIGIBLE,
            quality=observation.quality,
            recognized_range=verification.recognized_range,
            reason_codes=(),
            width=observation.width,
            height=observation.height,
        )
        for observation, verification in verified
    )
    verifier = _SeparatedEvidenceVerifier(
        (
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(new_range),
            ),
            verified[1][1],
        )
    )

    selected, updated, extra = FastImageSelector(
        COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102
    )._select_coherent_representative(
        eligible=list(candidates),
        candidates=candidates,
        verified=verified,
        verifier=verifier,
        expected_range=old_range,
        board_count_consensus=9,
        range_conflict=False,
    )

    assert selected is not None
    assert selected.source.order_index == 1
    assert extra == 1
    wrong_screen = updated[0]
    assert wrong_screen.decision is CandidateDecision.REJECTED
    assert "REPRESENTATIVE_RANGE_MISMATCH" in wrong_screen.reason_codes


def test_v10_2_requires_manual_review_when_no_representative_proves_group_range() -> None:
    source = _sources("v10-2-no-coherent-representative", 1)[0]
    observation = _AppearanceAnalyzer((_appearance_signature(0),)).analyze(source)
    initial = CandidateVerification(
        representative=RepresentativeAssessment(9, True, True),
        range_evidence=RangeEvidence(None, ("RANGE_EVIDENCE_NOT_REQUESTED",)),
    )
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.ELIGIBLE,
        quality=observation.quality,
        recognized_range=None,
        reason_codes=(),
        width=observation.width,
        height=observation.height,
    )
    verifier = _SeparatedEvidenceVerifier(
        (
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(SequenceRange(18_415, 18_423, 0.99)),
            ),
        )
    )

    selected, updated, extra = FastImageSelector(
        COHERENT_REPRESENTATIVE_SELECTOR_MANIFEST_V102
    )._select_coherent_representative(
        eligible=[candidate],
        candidates=(candidate,),
        verified=[(observation, initial)],
        verifier=verifier,
        expected_range=SequenceRange(18_406, 18_414, 0.99),
        board_count_consensus=9,
        range_conflict=False,
    )

    assert selected is None
    assert extra == 1
    assert "REPRESENTATIVE_RANGE_MISMATCH" in updated[0].reason_codes


def test_v10_3_selects_soft_geometry_candidate_that_proves_consensus_range() -> None:
    source = _sources("v10-3-consensus-backed-representative", 1)[0]
    observation = _AppearanceAnalyzer((_appearance_signature(0),)).analyze(source)
    expected_range = SequenceRange(73, 81, 0.99)
    verification = CandidateVerification(
        representative=RepresentativeAssessment(5, False, False),
        range_evidence=RangeEvidence(expected_range),
    )
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.REJECTED,
        quality=observation.quality,
        recognized_range=expected_range,
        reason_codes=(
            "GEOMETRY_INCOMPLETE",
            "FRAME_NOT_FULLY_VISIBLE",
            "RANGE_BOARD_COUNT_MISMATCH",
        ),
        width=observation.width,
        height=observation.height,
    )

    selected, updated, extra = FastImageSelector(
        CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103
    )._select_coherent_representative(
        eligible=[],
        candidates=(candidate,),
        verified=[(observation, verification)],
        verifier=_SeparatedEvidenceVerifier((verification,)),
        expected_range=expected_range,
        board_count_consensus=9,
        range_conflict=False,
    )

    assert selected is not None
    assert selected.source.order_index == 0
    assert selected.recognized_range == expected_range
    assert "RANGE_COHERENT_BEST_AVAILABLE" in selected.reason_codes
    assert updated[0] == selected
    assert extra == 0


def test_v10_3_does_not_select_soft_candidate_with_mismatched_range() -> None:
    source = _sources("v10-3-mismatched-consensus", 1)[0]
    observation = _AppearanceAnalyzer((_appearance_signature(0),)).analyze(source)
    expected_range = SequenceRange(73, 81, 0.99)
    wrong_range = SequenceRange(82, 90, 0.99)
    verification = CandidateVerification(
        representative=RepresentativeAssessment(9, False, False),
        range_evidence=RangeEvidence(wrong_range),
    )
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.REJECTED,
        quality=observation.quality,
        recognized_range=wrong_range,
        reason_codes=("GEOMETRY_INCOMPLETE",),
        width=observation.width,
        height=observation.height,
    )

    selected, updated, extra = FastImageSelector(
        CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103
    )._select_coherent_representative(
        eligible=[],
        candidates=(candidate,),
        verified=[(observation, verification)],
        verifier=_SeparatedEvidenceVerifier((verification,)),
        expected_range=expected_range,
        board_count_consensus=9,
        range_conflict=False,
    )

    assert selected is None
    assert "REPRESENTATIVE_RANGE_MISMATCH" in updated[0].reason_codes
    assert extra == 0


def test_v10_1_readable_number_does_not_promote_cropped_representative() -> None:
    signatures = (_appearance_signature(0), _appearance_signature(0, drift=0.1))
    verifier = _SeparatedEvidenceVerifier(
        (
            CandidateVerification(
                representative=RepresentativeAssessment(4, False, False),
                range_evidence=RangeEvidence(SequenceRange(73, 81, 0.99)),
            ),
            CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(None, ("RANGE_ANCHOR_UNREADABLE",)),
            ),
        )
    )

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-1-cropped-ocr-frame", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, (_quality("good"), _quality("reflection"))),
        verifier=verifier,
    )

    group = result.groups[0]
    assert group.status is SelectionGroupStatus.AUTO_SELECTED
    assert group.range == SequenceRange(73, 81, 0.99)
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 1
    cropped = next(
        candidate for candidate in group.top_candidates if candidate.source.order_index == 0
    )
    assert cropped.decision is CandidateDecision.REJECTED
    assert "GEOMETRY_INCOMPLETE" in cropped.reason_codes
    assert "FRAME_NOT_FULLY_VISIBLE" in cropped.reason_codes


def test_v10_1_descending_first_anchor_keeps_canonical_range_order() -> None:
    assert FastImageSelector._range_from_anchor(
        10_000,
        board_count=9,
        direction="descending",
    ) == SequenceRange(9_992, 10_000, 1.0)


@dataclass
class _V10RangeVerifier:
    ranges: tuple[SequenceRange | None, ...]
    calls: int = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        self.calls += 1
        return CandidateVerification(
            representative=RepresentativeAssessment(9, True, True),
            range_evidence=RangeEvidence(self.ranges[observation.source.order_index]),
        )


def test_v10_1_preserves_contiguous_and_jump_ranges_after_the_first_anchor() -> None:
    signatures = tuple(
        signature
        for page in range(3)
        for signature in (_appearance_signature(page), _appearance_signature(page, drift=0.1))
    )
    ranges = tuple(
        recognized
        for recognized in (
            SequenceRange(1, 9, 0.99),
            SequenceRange(10, 18, 0.98),
            SequenceRange(400, 408, 0.97),
        )
        for _ in range(2)
    )

    def run() -> ImageSelectionResult:
        return FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
            _sources("v10-real-jump", len(signatures)),
            analyzer=_AppearanceAnalyzer(signatures),
            verifier=_V10RangeVerifier(ranges),
            first_sequence_number=1,
        )

    first = run()
    second = run()

    assert [group.source_count for group in first.groups] == [2, 2, 2]
    assert [group.range for group in first.groups] == [
        SequenceRange(1, 9, 0.99),
        SequenceRange(10, 18, 0.98),
        SequenceRange(400, 408, 0.97),
    ]
    assert all(group.status is SelectionGroupStatus.AUTO_SELECTED for group in first.groups)
    assert first.to_dict() == second.to_dict()


def test_v10_1_first_anchor_conflict_is_not_hidden_by_cursor_projection() -> None:
    signatures = (_appearance_signature(0), _appearance_signature(0, drift=0.1))
    recognized = SequenceRange(100, 108, 0.99)

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-first-anchor-conflict", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_V10RangeVerifier((recognized, recognized)),
        first_sequence_number=1,
    )

    group = result.groups[0]
    assert group.status is SelectionGroupStatus.MANUAL_REQUIRED
    assert group.range == recognized
    assert group.selected_candidate is None
    assert all("RANGE_CONFLICT" in candidate.reason_codes for candidate in group.top_candidates)


def test_v10_1_later_ocr_conflict_is_not_replaced_with_the_next_range() -> None:
    signatures = tuple(
        signature
        for page in range(2)
        for signature in (_appearance_signature(page), _appearance_signature(page, drift=0.1))
    )
    ranges = (
        SequenceRange(1, 9, 0.99),
        SequenceRange(1, 9, 0.99),
        SequenceRange(100, 108, 0.99),
        SequenceRange(400, 408, 0.99),
    )

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-later-range-conflict", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_V10RangeVerifier(ranges),
        first_sequence_number=1,
    )

    assert result.groups[0].range == SequenceRange(1, 9, 0.99)
    conflict = result.groups[1]
    assert conflict.status is SelectionGroupStatus.MANUAL_REQUIRED
    assert conflict.range is None
    assert conflict.selected_candidate is None
    assert all("RANGE_CONFLICT" in candidate.reason_codes for candidate in conflict.top_candidates)


def test_v10_1_descending_anchor_applies_only_to_the_first_group() -> None:
    signatures = tuple(
        signature
        for page in range(2)
        for signature in (_appearance_signature(page), _appearance_signature(page, drift=0.1))
    )

    result = FastImageSelector(ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101).select(
        _sources("v10-descending-jump", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_V10RangeVerifier(
            (
                None,
                None,
                SequenceRange(400, 408, 0.98),
                SequenceRange(400, 408, 0.98),
            )
        ),
        sequence_direction="descending",
        first_sequence_number=10_000,
    )

    assert [group.range for group in result.groups] == [
        SequenceRange(9_992, 10_000, 1.0),
        SequenceRange(400, 408, 0.98),
    ]
    assert all(group.status is SelectionGroupStatus.AUTO_SELECTED for group in result.groups)


def test_v9_gradual_camera_drift_stays_in_one_group_and_page_change_splits() -> None:
    signatures = tuple(
        _appearance_signature(0, drift=drift) for drift in (-1.0, -0.6, -0.2, 0.2, 0.6, 1.0)
    ) + tuple(_appearance_signature(1, drift=drift) for drift in (-0.2, 0.0, 0.2))
    verifier = _ForbiddenVerifier()

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-drift-and-page", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=verifier,
    )

    assert [group.source_count for group in result.groups] == [6, 3]
    assert verifier.calls == 0
    assert result.verification_count == 0
    assert all(group.range is None for group in result.groups)


def test_v9_single_transition_frame_does_not_create_a_group() -> None:
    signatures = (
        _appearance_signature(0),
        _appearance_signature(0, drift=0.2),
        _appearance_signature(1),
        _appearance_signature(0, drift=-0.2),
        _appearance_signature(0),
        _appearance_signature(1),
        _appearance_signature(1, drift=0.1),
    )

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-single-transition", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_ForbiddenVerifier(),
    )

    assert [group.source_count for group in result.groups] == [5, 2]


def test_v9_private_real_consecutive_pages_are_not_merged() -> None:
    source_root = ROOT / "examples" / "imgs"
    names = (
        "5983122166590934317.jpg",
        "5983122166590934318.jpg",
        "5983122166590934319.jpg",
    )
    if any(not (source_root / name).is_file() for name in names):
        pytest.skip("The private user-provided consecutive-page corpus is not present.")
    repeated_names = tuple(name for name in names for _ in range(2))
    sources = tuple(
        ImageSelectionSource(
            order_index=index,
            relative_path=name,
            stored_relative_path=name,
            checksum_sha256=hashlib.sha256((source_root / name).read_bytes()).hexdigest(),
            size_bytes=(source_root / name).stat().st_size,
        )
        for index, name in enumerate(repeated_names)
    )
    analyzer, verifier = build_default_adapters(
        source_root,
        manifest=APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    )

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        sources,
        analyzer=analyzer,
        verifier=verifier,
    )

    assert [group.source_count for group in result.groups] == [2, 2, 2]
    assert result.verification_count == 0


@dataclass
class _AppearanceStateSink:
    states: list[SelectorResumeState]

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        del observation, group_order

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        del checkpoint

    def group_finalized(self, group: SelectionGroupResult) -> None:
        del group

    def selector_state_saved(self, state: SelectorResumeState) -> None:
        self.states.append(state)


def test_v9_checkpoint_keeps_a_fixed_descriptor_and_bounded_candidates() -> None:
    signatures = tuple(
        _appearance_signature(0, drift=((index % 11) - 5) / 5) for index in range(96)
    )
    sink = _AppearanceStateSink([])
    manifest = replace(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9, scan_batch_size=8)

    FastImageSelector(manifest).select(
        _sources("v9-bounded-state", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures),
        verifier=_ForbiddenVerifier(),
        audit_sink=sink,
    )

    open_groups = [state.current_group for state in sink.states if state.current_group]
    expected_size = len(signatures[0])
    assert open_groups
    assert all(len(group.appearance_centroid) == expected_size for group in open_groups)
    assert all(len(group.top_observations) <= manifest.top_k for group in open_groups)
    assert all(group.appearance_observation_count <= group.source_count for group in open_groups)
    captured = next(state for state in reversed(sink.states) if state.current_group is not None)
    restored = SelectorResumeState.from_dict(captured.to_dict())
    assert restored.current_group == captured.current_group


def _appearance_signature(page: int, *, drift: float = 0.0) -> tuple[float, ...]:
    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    phash = tuple(float(page % 2) for _ in range(config.phash_size**2))
    hue = [0.0] * config.hue_bins
    hue_index = (page * 3) % config.hue_bins
    hue[hue_index] = 1.0 - abs(drift) * 0.05
    hue[(hue_index + 1) % config.hue_bins] = abs(drift) * 0.05
    saturation = [0.0] * config.saturation_bins
    saturation[page % config.saturation_bins] = 1.0
    value = [0.0] * config.value_bins
    value[(page + 1) % config.value_bins] = 1.0
    edge_value = max(0.0, min(1.0, 0.20 + page * 0.45 + drift * 0.03))
    edge_grid = [edge_value] * (config.edge_grid_rows * config.edge_grid_columns)
    orientation = [0.0] * config.edge_orientation_bins
    orientation[page % config.edge_orientation_bins] = 1.0
    return (*phash, *hue, *saturation, *value, *edge_grid, *orientation)


@dataclass
class _AppearanceAnalyzer:
    signatures: tuple[tuple[float, ...], ...]
    qualities: tuple[ImageQualityMetrics, ...] | None = None
    failed_indexes: frozenset[int] = frozenset()

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        signature = self.signatures[source.order_index]
        if source.order_index in self.failed_indexes:
            return CheapImageObservation(
                source=source,
                width=1,
                height=1,
                fingerprint_hex=source.checksum_sha256,
                geometry_signature=(),
                board_count=None,
                geometry_confidence=0.0,
                quality=ImageQualityMetrics(*(0.0 for _ in range(8))),
                reason_codes=("IMAGE_SELECTION_SCAN_DECODE_FAILED",),
                appearance_signature=(),
            )
        fingerprint = hashlib.sha256(repr(signature).encode("ascii")).hexdigest()
        return CheapImageObservation(
            source=source,
            width=960,
            height=1280,
            fingerprint_hex=fingerprint,
            geometry_signature=(),
            board_count=None,
            geometry_confidence=0.0,
            quality=(
                _quality("good") if self.qualities is None else self.qualities[source.order_index]
            ),
            appearance_signature=signature,
        )


@dataclass
class _ForbiddenVerifier:
    calls: int = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del observation, expected_board_count
        self.calls += 1
        raise AssertionError("Appearance-only grouping must not invoke range verification.")


def test_v9_keeps_first_usable_representative_over_later_better_frames() -> None:
    signatures = tuple(_appearance_signature(0, drift=index * 0.05) for index in range(4))
    qualities = tuple(
        _quality(name)
        for name in (
            "v9_unusable_early",
            "v9_usable_first",
            "v9_usable_better",
            "good",
        )
    )
    verifier = _ForbiddenVerifier()

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-first-usable", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=verifier,
    )

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.status is SelectionGroupStatus.AUTO_SELECTED
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 1
    assert len(group.top_candidates) <= 2
    assert "QUALITY_BEST_AVAILABLE" not in group.selected_candidate.reason_codes
    assert verifier.calls == 0
    assert result.verification_count == 0


def test_v9_uses_deterministic_best_decodable_fallback_with_warning() -> None:
    signatures = tuple(_appearance_signature(0, drift=index * 0.05) for index in range(3))
    qualities = tuple(
        _quality(name)
        for name in (
            "v9_fallback_low",
            "v9_fallback_best",
            "v9_fallback_best",
        )
    )

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-best-fallback", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, qualities),
        verifier=_ForbiddenVerifier(),
    )

    group = result.groups[0]
    assert group.status is SelectionGroupStatus.AUTO_SELECTED
    assert group.selected_candidate is not None
    assert group.selected_candidate.source.order_index == 1
    assert group.selected_candidate.reason_codes == ("QUALITY_BEST_AVAILABLE",)
    assert len(group.top_candidates) == 1


def test_v9_isolates_decode_failure_and_still_selects_the_group() -> None:
    signatures = tuple(_appearance_signature(0, drift=index * 0.05) for index in range(3))

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-isolated-decode-failure", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, failed_indexes=frozenset({1})),
        verifier=_ForbiddenVerifier(),
    )

    assert result.scan_failure_count == 1
    assert len(result.groups) == 1
    assert result.groups[0].status is SelectionGroupStatus.AUTO_SELECTED
    assert result.groups[0].selected_candidate is not None
    assert result.groups[0].selected_candidate.source.order_index == 0


def test_v9_group_with_only_undecodable_files_remains_manual() -> None:
    signatures = tuple(_appearance_signature(0) for _ in range(2))

    result = FastImageSelector(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9).select(
        _sources("v9-all-decode-failed", len(signatures)),
        analyzer=_AppearanceAnalyzer(signatures, failed_indexes=frozenset({0, 1})),
        verifier=_ForbiddenVerifier(),
    )

    assert result.scan_failure_count == 2
    assert len(result.groups) == 1
    assert result.groups[0].status is SelectionGroupStatus.MANUAL_REQUIRED
    assert result.groups[0].selected_candidate is None
    assert all(
        candidate.decision is CandidateDecision.REJECTED
        for candidate in result.groups[0].top_candidates
    )


def test_v5_adjacent_boundary_is_not_vetoed_by_a_similar_historical_anchor() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "poison-reference",
            "quality": "good",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "poison-last",
            "quality": "reflection",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "poison-next",
            "quality": "good",
            "range": [10, 18, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "poison-next",
            "quality": "good",
            "range": [10, 18, 0.99],
        },
    )
    sources = _sources("historical-anchor-poison", len(observations))

    previous = FastImageSelector(BEST_AVAILABLE_SELECTOR_MANIFEST_V4).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    current = FastImageSelector(DIGIT_AWARE_SELECTOR_MANIFEST_V5).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert len(previous.groups) == 1
    assert previous.groups[0].status.value == "manual_required"
    assert [group.source_count for group in current.groups] == [2, 2]
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in current.groups
    ] == [(1, 9), (10, 18)]


def test_v5_tracks_a_multi_frame_transition_until_the_new_page_stabilizes() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "transition-old",
            "quality": "good",
            "range": [28, 36, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "transition-old",
            "quality": "good",
            "range": [28, 36, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "transition-1",
            "quality": "reflection",
            "range": [28, 36, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "transition-2",
            "quality": "reflection",
            "range": [37, 45, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "transition-3",
            "quality": "good",
            "range": [37, 45, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "transition-3",
            "quality": "good",
            "range": [37, 45, 0.99],
        },
    )

    result = FastImageSelector(DIGIT_AWARE_SELECTOR_MANIFEST_V5).select(
        _sources("multi-frame-page-transition", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert len(result.groups) == 2
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in result.groups
    ] == [(28, 36), (37, 45)]


def test_v4_selects_best_available_when_only_soft_quality_gate_fails() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "quality_fallback",
            "range": [1, 9, 0.99],
        },
    )
    sources = _sources("quality-best-available", 1)

    previous = FastImageSelector(CONTINUITY_SELECTOR_MANIFEST_V3).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    current = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert previous.groups[0].status.value == "manual_required"
    assert current.groups[0].status.value == "auto_selected"
    assert current.groups[0].selected_candidate is not None
    assert "QUALITY_GLARE" in current.groups[0].selected_candidate.reason_codes
    assert "QUALITY_BEST_AVAILABLE" in current.groups[0].selected_candidate.reason_codes


def test_v7_selects_explicitly_occluded_image_when_range_is_clear() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "occluded",
            "range": [1, 9, 0.99],
        },
    )

    previous = FastImageSelector(EXACT_GAP_SELECTOR_MANIFEST_V6).select(
        _sources("explicitly-occluded", 1),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        _sources("explicitly-occluded", 1),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert previous.groups[0].status.value == "manual_required"
    assert result.groups[0].status.value == "auto_selected"
    assert result.groups[0].selected_candidate is not None
    assert "IMAGE_OCCLUDED" in result.groups[0].selected_candidate.reason_codes
    assert "QUALITY_BEST_AVAILABLE" in result.groups[0].selected_candidate.reason_codes


def test_v7_selects_blurred_image_when_range_is_clear() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "blur",
            "range": [1, 9, 0.99],
        },
    )

    previous = FastImageSelector(EXACT_GAP_SELECTOR_MANIFEST_V6).select(
        _sources("unreadably-blurred", 1),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        _sources("unreadably-blurred", 1),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert previous.groups[0].status.value == "manual_required"
    assert result.groups[0].status.value == "auto_selected"
    assert result.groups[0].selected_candidate is not None
    assert "QUALITY_BLUR" in result.groups[0].selected_candidate.reason_codes
    assert "QUALITY_BEST_AVAILABLE" in result.groups[0].selected_candidate.reason_codes


def test_v8_stops_verification_after_first_reasonably_readable_range() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "reflection",
            "range": [73, 81, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [73, 81, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [73, 81, 0.99],
        },
    )
    sources = _sources("first-usable-range", len(observations))
    previous_verifier = GoldenVerifier(observations)
    current_verifier = GoldenVerifier(observations)

    previous = FastImageSelector(BEST_EFFORT_SELECTOR_MANIFEST_V7).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=previous_verifier,
    )
    current = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=current_verifier,
    )

    assert previous_verifier.calls == 3
    assert current_verifier.calls == 1
    assert previous.groups[0].selected_candidate is not None
    assert previous.groups[0].selected_candidate.source.order_index == 1
    assert current.groups[0].selected_candidate is not None
    assert current.groups[0].selected_candidate.source.order_index == 0
    assert current.groups[0].range is not None
    assert (current.groups[0].range.start, current.groups[0].range.end) == (73, 81)


def test_v8_tries_the_next_photo_when_first_candidate_has_no_range() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "reflection",
            "range": None,
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [73, 81, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [73, 81, 0.99],
        },
    )
    verifier = GapVerifier(observations)

    result = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        _sources("first-usable-range-fallback", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=verifier,
    )

    assert verifier.calls == 2
    assert result.verification_count == 2
    assert result.groups[0].selected_candidate is not None
    assert result.groups[0].selected_candidate.source.order_index == 1
    assert result.groups[0].range is not None
    assert (result.groups[0].range.start, result.groups[0].range.end) == (73, 81)


def test_current_selector_sends_cropped_layouts_73_to_81_to_cutting_from_one_gap() -> None:
    observations = (
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [82, 90, 0.99]},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [82, 90, 0.99]},
    )
    sources = _sources("bounded-gap-73-81", len(observations))

    previous = FastImageSelector(CONTINUITY_SELECTOR_MANIFEST_V3).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GapVerifier(observations),
    )
    current = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GapVerifier(observations),
    )

    assert [group.status.value for group in previous.groups] == [
        "auto_selected",
        "manual_required",
        "auto_selected",
    ]
    assert [group.status.value for group in current.groups] == [
        "auto_selected",
        "auto_selected",
        "auto_selected",
    ]
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in current.groups
    ] == [(64, 72), (73, 81), (82, 90)]
    selected = current.groups[1].selected_candidate
    assert selected is not None
    assert selected.quality.sharpness == 0.627
    assert "QUALITY_BEST_AVAILABLE" in selected.reason_codes
    assert "RANGE_INFERRED_FROM_BOUNDED_GAP" in selected.reason_codes
    assert "QUALITY_FRAME_CROPPED" in selected.reason_codes
    assert "GEOMETRY_INCOMPLETE" in selected.reason_codes
    assert "FRAME_NOT_FULLY_VISIBLE" in selected.reason_codes
    assert "RANGE_UNKNOWN" in selected.reason_codes


def test_v5_does_not_assign_one_gap_to_multiple_unresolved_groups() -> None:
    observations = (
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "c", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "c", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "d", "quality": "good", "range": [82, 90, 0.99]},
        {"boardCount": 9, "fingerprint": "d", "quality": "good", "range": [82, 90, 0.99]},
    )

    result = FastImageSelector(DIGIT_AWARE_SELECTOR_MANIFEST_V5).select(
        _sources("ambiguous-bounded-gap", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GapVerifier(observations),
    )

    assert [group.status.value for group in result.groups] == [
        "auto_selected",
        "manual_required",
        "manual_required",
        "auto_selected",
    ]


def test_v10_2_resolved_manual_group_owns_recovery_candidates_only_once() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "occluded",
            "range": [280, 288, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "occluded",
            "range": [280, 288, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "b",
            "quality": "good",
            "range": [280, 288, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "b",
            "quality": "good",
            "range": [280, 288, 0.99],
        },
    )

    result = FastImageSelector(CONSENSUS_BACKED_REPRESENTATIVE_SELECTOR_MANIFEST_V103).select(
        _sources("resolved-manual-range", len(observations)),
        analyzer=_AppearanceAnalyzer(
            (
                _appearance_signature(0),
                _appearance_signature(0, drift=0.02),
                _appearance_signature(1),
                _appearance_signature(1, drift=0.02),
            ),
            qualities=tuple(_quality(str(value["quality"])) for value in observations),
        ),
        verifier=GoldenVerifier(observations),
    )

    resolved, duplicate = result.groups
    assert resolved.status is SelectionGroupStatus.AUTO_SELECTED
    assert resolved.selected_candidate is not None
    assert resolved.selected_candidate.source.order_index in {2, 3}
    assert duplicate.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    assert duplicate.duplicate_of_group_order == resolved.group_order
    assert duplicate.selected_candidate is None
    assert duplicate.top_candidates == ()
    resolved_orders = {candidate.source.order_index for candidate in resolved.top_candidates}
    duplicate_orders = {candidate.source.order_index for candidate in duplicate.top_candidates}
    assert resolved_orders.isdisjoint(duplicate_orders)


@pytest.mark.parametrize(
    "manifest",
    (
        EXACT_GAP_SELECTOR_MANIFEST_V6,
        BEST_EFFORT_SELECTOR_MANIFEST_V7,
        REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8,
    ),
)
def test_v6_v7_and_v8_recover_multiple_full_pages_from_one_exact_sequence_gap(
    manifest: SelectorManifest,
) -> None:
    observations = (
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [64, 72, 0.99]},
        {"boardCount": 8, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 8, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 7, "fingerprint": "c", "quality": "range_73_clear", "range": None},
        {"boardCount": 7, "fingerprint": "c", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "d", "quality": "good", "range": [91, 99, 0.99]},
        {"boardCount": 9, "fingerprint": "d", "quality": "good", "range": [91, 99, 0.99]},
    )
    sink = _TrackingSink([], [], [])

    result = FastImageSelector(manifest).select(
        _sources("exact-multi-gap", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GapVerifier(observations),
        audit_sink=sink,
    )

    assert [group.status.value for group in result.groups] == [
        "auto_selected",
        "auto_selected",
        "auto_selected",
        "auto_selected",
    ]
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in result.groups
    ] == [(64, 72), (73, 81), (82, 90), (91, 99)]
    assert sink.finalized_orders[-2:] == [1, 2]
    assert all(
        group.selected_candidate is not None
        and "RANGE_INFERRED_FROM_BOUNDED_GAP" in group.selected_candidate.reason_codes
        for group in result.groups[1:3]
    )


def test_v6_does_not_fill_a_jump_that_is_not_an_exact_page_partition() -> None:
    observations = (
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [19, 27, 0.99]},
        {"boardCount": 9, "fingerprint": "a", "quality": "good", "range": [19, 27, 0.99]},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "b", "quality": "range_73_clear", "range": None},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [400, 408, 0.99]},
        {"boardCount": 9, "fingerprint": "c", "quality": "good", "range": [400, 408, 0.99]},
    )

    result = FastImageSelector(EXACT_GAP_SELECTOR_MANIFEST_V6).select(
        _sources("real-sequence-jump", len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GapVerifier(observations),
    )

    assert [group.status.value for group in result.groups] == [
        "auto_selected",
        "manual_required",
        "auto_selected",
    ]


def test_v2_checkpoint_without_temporal_anchor_remains_readable() -> None:
    observations = (
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [1, 9, 0.99],
        },
        {
            "boardCount": 9,
            "fingerprint": "a",
            "quality": "good",
            "range": [1, 9, 0.99],
        },
    )
    sources = _sources("legacy-checkpoint", 2)
    first_observation = GoldenAnalyzer(observations).analyze(sources[0])
    state = SelectorResumeState(
        checkpoint=SelectorCheckpoint(
            schema_version=1,
            selector_fingerprint=LEGACY_SELECTOR_MANIFEST_V2.fingerprint,
            next_order_index=1,
            processed_count=1,
            finalized_group_count=0,
        ),
        current_group=SelectorOpenGroupState(
            group_order=0,
            source_count=1,
            top_observations=(first_observation,),
            board_counts=((9, 1),),
            last_observation=first_observation,
        ),
        pending_observations=(),
        scan_failure_count=0,
        verification_count=0,
    )
    payload = state.to_dict()
    current_payload = cast(dict[str, object], payload["currentGroup"])
    current_payload.pop("lastObservation")

    result = FastImageSelector(LEGACY_SELECTOR_MANIFEST_V2).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
        resume_state=SelectorResumeState.from_dict(payload),
    )

    assert len(result.groups) == 1
    assert result.groups[0].source_count == 2


def test_fast_selector_rejects_non_contiguous_input_order() -> None:
    sources = list(_sources("bad-order", 2))
    sources[1] = ImageSelectionSource(
        order_index=3,
        relative_path=sources[1].relative_path,
        stored_relative_path=sources[1].stored_relative_path,
        checksum_sha256=sources[1].checksum_sha256,
        size_bytes=sources[1].size_bytes,
    )

    with pytest.raises(SelectionContractError) as error:
        FastImageSelector().select(
            sources,
            analyzer=GoldenAnalyzer(({}, {})),
            verifier=GoldenVerifier(({}, {})),
        )

    assert error.value.code == "IMAGE_SELECTION_ORDER_INVALID"


def test_selector_package_does_not_import_cell_cropper_or_symbol_model() -> None:
    selection_root = (
        ROOT / "services" / "worker" / "src" / "game_predictor_worker" / "images" / "selection"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(selection_root.glob("*.py"))
    )

    assert "BoardCellCropper" not in source
    assert "symbol_onnx" not in source
    assert "SymbolOnnx" not in source


@dataclass
class _TrackingSink:
    scanned_indexes: list[int]
    checkpoint_counts: list[int]
    finalized_orders: list[int]

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        del group_order
        self.scanned_indexes.append(observation.source.order_index)

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        self.checkpoint_counts.append(checkpoint.processed_count)

    def group_finalized(self, group: SelectionGroupResult) -> None:
        self.finalized_orders.append(group.group_order)


class _ParallelProbeAnalyzer:
    def __init__(self, values: tuple[dict[str, Any], ...]) -> None:
        self._delegate = GoldenAnalyzer(values)
        self._lock = Lock()
        self.active = 0
        self.max_active = 0
        self.completed_indexes: list[int] = []

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            sleep(0.02 if source.order_index % 4 == 0 else 0.005)
            result = self._delegate.analyze(source)
            with self._lock:
                self.completed_indexes.append(source.order_index)
            return result
        finally:
            with self._lock:
                self.active -= 1


def test_parallel_scan_is_concurrent_bounded_and_consumed_in_source_order() -> None:
    case = _golden_cases()[1]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    sources = _sources("parallel-ordered-scan", len(observations))
    analyzer = _ParallelProbeAnalyzer(observations)
    sink = _TrackingSink([], [], [])

    parallel = FastImageSelector(
        REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8,
        scan_workers=4,
        scan_prefetch=4,
    ).select(
        sources,
        analyzer=analyzer,
        verifier=GoldenVerifier(observations),
        audit_sink=sink,
    )
    sequential = FastImageSelector(REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert 2 <= analyzer.max_active <= 4
    assert analyzer.completed_indexes != list(range(len(observations)))
    assert sink.scanned_indexes == list(range(len(observations)))
    assert parallel.to_dict() == sequential.to_dict()


@pytest.mark.parametrize(
    ("workers", "prefetch"),
    ((0, 1), (9, 9), (4, 3), (4, 33)),
)
def test_parallel_scan_rejects_unbounded_runtime_configuration(
    workers: int,
    prefetch: int,
) -> None:
    with pytest.raises(ValueError):
        FastImageSelector(scan_workers=workers, scan_prefetch=prefetch)


def test_selector_streams_metrics_and_saves_bounded_batch_checkpoints() -> None:
    case = _golden_cases()[0]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    sink = _TrackingSink([], [], [])
    manifest = SelectorManifest(scan_batch_size=2)

    result = FastImageSelector(manifest).select(
        _sources(str(case["id"]), len(observations)),
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
        audit_sink=sink,
    )

    assert sink.scanned_indexes == list(range(len(observations)))
    assert sink.checkpoint_counts == [2, 4, 4]
    assert sink.finalized_orders == [0, 1]
    assert result.checkpoint.next_order_index == len(observations)


class _SimulatedCrash(RuntimeError):
    pass


@dataclass
class _CrashAfterCheckpointSink(_TrackingSink):
    crash_after_processed: int
    resume_state: SelectorResumeState | None = None
    finalized_groups: list[SelectionGroupResult] | None = None

    def group_finalized(self, group: SelectionGroupResult) -> None:
        super().group_finalized(group)
        assert self.finalized_groups is not None
        if group.group_order < len(self.finalized_groups):
            self.finalized_groups[group.group_order] = group
        else:
            self.finalized_groups.append(group)

    def selector_state_saved(self, state: SelectorResumeState) -> None:
        if state.checkpoint.processed_count == self.crash_after_processed:
            self.resume_state = state
            raise _SimulatedCrash


@dataclass
class _CountingAnalyzer(GoldenAnalyzer):
    calls: list[int] | None = None

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        assert self.calls is not None
        self.calls.append(source.order_index)
        return super().analyze(source)


def test_parallel_selector_resumes_at_the_next_file_after_a_durable_checkpoint() -> None:
    case = _golden_cases()[1]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    sources = _sources("resume-after-checkpoint", len(observations))
    manifest = SelectorManifest(scan_batch_size=2)
    sink = _CrashAfterCheckpointSink(
        [],
        [],
        [],
        crash_after_processed=4,
        finalized_groups=[],
    )

    with pytest.raises(_SimulatedCrash):
        FastImageSelector(manifest, scan_workers=4, scan_prefetch=4).select(
            sources,
            analyzer=GoldenAnalyzer(observations),
            verifier=GoldenVerifier(observations),
            audit_sink=sink,
        )

    assert sink.resume_state is not None
    resumed_calls: list[int] = []
    resumed = FastImageSelector(manifest, scan_workers=4, scan_prefetch=4).select(
        sources,
        analyzer=_CountingAnalyzer(observations, resumed_calls),
        verifier=GoldenVerifier(observations),
        resume_state=SelectorResumeState.from_dict(sink.resume_state.to_dict()),
        existing_groups=tuple(sink.finalized_groups or ()),
    )
    uninterrupted = FastImageSelector(manifest, scan_workers=4, scan_prefetch=4).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert resumed_calls == [4, 5]
    assert resumed.to_dict() == uninterrupted.to_dict()
