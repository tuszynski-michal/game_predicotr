from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_worker.images.selection.contracts import (
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionContractError,
    SelectionGroupResult,
    SelectorCheckpoint,
    SelectorResumeState,
    SequenceRange,
)
from game_predictor_worker.images.selection.engine import FastImageSelector
from game_predictor_worker.images.selection.manifest import (
    DEFAULT_SELECTOR_MANIFEST,
    SelectorManifest,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ai_docs" / "quality" / "fast-image-selector-v1-golden.json"
FINGERPRINTS = {
    "a": "0" * 64,
    "b": "f" * 64,
    "c": "a" * 64,
    "d": "5" * 64,
    "e": "3" * 64,
}


def _quality(name: str) -> ImageQualityMetrics:
    values = {
        "good": (0.95, 0.92, 0.98, 0.95, 0.92, 0.91, 1.0, 0.95),
        "reflection": (0.92, 0.90, 0.96, 0.80, 0.90, 0.90, 1.0, 0.89),
        "blur": (0.05, 0.92, 0.98, 0.95, 0.92, 0.91, 1.0, 0.75),
        "cropped": (0.92, 0.92, 0.98, 0.95, 0.92, 0.10, 1.0, 0.75),
        "occluded": (0.92, 0.92, 0.98, 0.95, 0.92, 0.91, 0.60, 0.75),
        "geometry_incomplete": (0.92, 0.92, 0.98, 0.95, 0.30, 0.91, 0.50, 0.70),
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
            board_count=expected_board_count,
            geometry_complete=quality_name != "geometry_incomplete",
            full_frame_visible=quality_name not in {"cropped", "occluded"},
            reason_codes=("IMAGE_OCCLUDED",) if quality_name == "occluded" else (),
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
    assert payload["selectorVersion"] == DEFAULT_SELECTOR_MANIFEST.algorithm_version
    return tuple(payload["cases"])


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: str(case["id"]))
def test_fast_selector_matches_grouping_and_quality_golden(case: dict[str, Any]) -> None:
    observations = tuple(cast(dict[str, Any], value) for value in case["observations"])
    verifier = GoldenVerifier(observations)

    result = FastImageSelector().select(
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
    assert verifier.calls <= len(result.groups) * DEFAULT_SELECTOR_MANIFEST.top_k
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


def test_selector_resumes_at_the_next_file_after_a_durable_checkpoint() -> None:
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
        FastImageSelector(manifest).select(
            sources,
            analyzer=GoldenAnalyzer(observations),
            verifier=GoldenVerifier(observations),
            audit_sink=sink,
        )

    assert sink.resume_state is not None
    resumed_calls: list[int] = []
    resumed = FastImageSelector(manifest).select(
        sources,
        analyzer=_CountingAnalyzer(observations, resumed_calls),
        verifier=GoldenVerifier(observations),
        resume_state=SelectorResumeState.from_dict(sink.resume_state.to_dict()),
        existing_groups=tuple(sink.finalized_groups or ()),
    )
    uninterrupted = FastImageSelector(manifest).select(
        sources,
        analyzer=GoldenAnalyzer(observations),
        verifier=GoldenVerifier(observations),
    )

    assert resumed_calls == [4, 5]
    assert resumed.to_dict() == uninterrupted.to_dict()
