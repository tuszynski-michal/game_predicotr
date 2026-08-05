from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Any, cast

import pytest
from game_predictor_worker.images.selection.adapters import build_default_adapters
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
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
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    BEST_AVAILABLE_SELECTOR_MANIFEST_V4,
    BEST_EFFORT_SELECTOR_MANIFEST_V7,
    CONTINUITY_SELECTOR_MANIFEST_V3,
    DEFAULT_SELECTOR_MANIFEST,
    DIGIT_AWARE_SELECTOR_MANIFEST_V5,
    EXACT_GAP_SELECTOR_MANIFEST_V6,
    FIRST_USABLE_SELECTOR_MANIFEST_V8,
    LEGACY_SELECTOR_MANIFEST_V2,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ai_docs" / "quality" / "fast-image-selector-v2-golden.json"
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
            recognized_range=SequenceRange(
                start=int(start),
                end=int(end),
                confidence=float(confidence),
            ),
            board_count=int(value.get("verifiedBoardCount", expected_board_count or 0)) or None,
            geometry_complete=quality_name != "geometry_incomplete",
            full_frame_visible=quality_name not in {"cropped", "occluded"},
            reason_codes=("IMAGE_OCCLUDED",) if quality_name == "occluded" else (),
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
            recognized_range=None,
            board_count=3,
            geometry_complete=False,
            full_frame_visible=False,
            reason_codes=("BOARD_CANDIDATE_COUNT", "RANGE_LABEL_LATTICE_INCOMPLETE"),
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

    first = FastImageSelector().select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )
    second = FastImageSelector().select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert first.to_dict() == second.to_dict()


def test_single_last_photo_can_form_a_verified_new_range() -> None:
    case = _golden_cases()[0]
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"][:3])

    result = FastImageSelector().select(
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

    result = FastImageSelector().select(
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

    result = FastImageSelector().select(
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


def test_v8_is_the_default_first_usable_manifest() -> None:
    assert DEFAULT_SELECTOR_MANIFEST.algorithm_version == "fast-image-selector-v8"
    assert (
        DEFAULT_SELECTOR_MANIFEST.fingerprint
        == "284eb7f842b6d09910aa34bbf4a889f9b246f26ae6767b138d4ed8cdee2a68f3"
    )
    assert (
        FIRST_USABLE_SELECTOR_MANIFEST_V8.fingerprint
        == "9dc754cca7e7e7afe23e8a25c8574e0ef4ed5f7fd5829a24984c25f4c256f42d"
    )


def test_v9_manifest_is_versioned_but_not_activated_before_final_gate() -> None:
    assert APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.algorithm_version == "fast-image-selector-v9"
    assert (
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.fingerprint
        == "eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb"
    )
    assert DEFAULT_SELECTOR_MANIFEST.algorithm_version == "fast-image-selector-v8"
    assert (
        selector_manifest_for_fingerprint(APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.fingerprint)
        is APPEARANCE_ONLY_SELECTOR_MANIFEST_V9
    )


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
    current = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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
    result = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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
    result = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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
    current = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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

    result = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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
    current = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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


@pytest.mark.parametrize(
    "manifest",
    (
        EXACT_GAP_SELECTOR_MANIFEST_V6,
        BEST_EFFORT_SELECTOR_MANIFEST_V7,
        DEFAULT_SELECTOR_MANIFEST,
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
        DEFAULT_SELECTOR_MANIFEST,
        scan_workers=4,
        scan_prefetch=4,
    ).select(
        sources,
        analyzer=analyzer,
        verifier=GoldenVerifier(observations),
        audit_sink=sink,
    )
    sequential = FastImageSelector(DEFAULT_SELECTOR_MANIFEST).select(
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
