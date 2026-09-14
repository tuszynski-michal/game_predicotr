from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.geometry_qualification import (
    GeometryQualification,
    geometry_training_exclusion_reason,
    page_anchor_exclusion_reason,
)
from game_predictor_api.domain.image_geometry_v2 import (
    GeometryEngineKind,
    ImageGeometryContractError,
    SourcePoint,
    SourceQuad,
    derive_virtual_cells,
)
from game_predictor_api.schemas.geometry_qualification import (
    AutomaticPartialGeometryProposalPayload,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.global_symbol_lattice import GlobalSymbolCandidate
from game_predictor_worker.images.lateral_partial_contract import LateralPartialGeometrySnapshot
from game_predictor_worker.images.page_geometry_registration import (
    LateralPageRegistrationCandidate,
    PageRegistrationInitialization,
)
from game_predictor_worker.images.partial_grid_learning import (
    PartialGridPattern,
    PartialGridTrainingProfile,
)
from game_predictor_worker.images.structured_geometry import lattice_refinement_v4 as v4
from game_predictor_worker.images.virtual_cell_extraction import VirtualCellRenderer
from test_manual_partial_geometry import _configuration, _geometry
from test_structured_geometry_global_initialization import _frame
from test_structured_lattice_refinement_v3 import _board, _source

POLICY = LateralPartialGeometrySnapshot()
TOPOLOGY = BoardCellTopology(rows=3, columns=5)


def _candidate(quad: SourceQuad) -> LateralPageRegistrationCandidate:
    return LateralPageRegistrationCandidate(
        initialization=PageRegistrationInitialization(
            anchor_source_checksum_sha256="a" * 64,
            active_board_slots=(0,),
            initialization_quads=(tuple(Point(point.x, point.y) for point in quad.corners),),
            native_homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            inlier_count=100,
            inlier_ratio=0.8,
            p95_reprojection_error=0.5,
            feature_count=1000,
        ),
        policy_checksum_sha256=POLICY.checksum_sha256,
        board_red_edge_coverages=(0.8,),
    )


def _crop(side: str):
    source, quad = _source(_board())
    x0, x1, y0, y1 = 0, source.shape[1], 0, source.shape[0]
    if side in {"left", "both", "top", "bottom"}:
        x0 = 240
    if side in {"right", "both"}:
        x1 = 665
    if side == "top":
        y0 = 170
    if side == "bottom":
        y1 = 540
    return source[y0:y1, x0:x1].copy(), SourceQuad(
        corners=tuple(SourcePoint(point.x - x0, point.y - y0) for point in quad.corners)
    )


def _refine(source, quad, candidate=True):
    return v4.refine_structured_symbol_lattice_v4(
        source,
        analysis_quad=quad,
        board_frame_quad=quad,
        topology=TOPOLOGY,
        source_checksum_sha256="b" * 64,
        position_index=0,
        lateral_candidate=_candidate(quad) if candidate else None,
        policy=POLICY,
    )


def _evaluate_origin_with_missing(monkeypatch, missing, *, offset=1):
    candidates = tuple(
        GlobalSymbolCandidate(
            candidate_index=index,
            x=float(column * 100 + 50),
            y=float(row * 100 + 50),
            width=40,
            height=40,
            area=1600,
            weight=1.0,
            touches_border=False,
        )
        for index, (row, column) in enumerate(
            (row, column) for row in range(3) for column in range(3)
        )
    )
    values = tuple((index // 3, index % 3, candidate) for index, candidate in enumerate(candidates))
    monkeypatch.setattr(v4, "unavailable_source_cell_indices", lambda *args, **kwargs: missing)
    return v4._evaluate_origin(
        np.eye(3, dtype=np.float64),
        values=values,
        selected=tuple(range(9)),
        offset=offset,
        candidates=candidates,
        analysis_to_source=np.diag((499 / 500, 299 / 300, 1.0)),
        source_shape=(300, 500, 3),
        p95=0.0,
        policy=POLICY,
        source_checksum_sha256="b" * 64,
        position_index=0,
    )


def test_learned_profile_only_resolves_one_supported_ambiguous_mask() -> None:
    left = (0, 5, 10)
    right = (4, 9, 14)
    proposals = [
        SimpleNamespace(
            qualification=GeometryQualification("pending_partial", left, True, "missing_pixels")
        ),
        SimpleNamespace(
            qualification=GeometryQualification("pending_partial", right, True, "missing_pixels")
        ),
    ]
    insufficient = PartialGridTrainingProfile(
        (PartialGridPattern(left, sample_count=2, source_count=2),), 2
    )
    assert v4._select_learned_proposals(proposals, insufficient) == proposals
    learned = PartialGridTrainingProfile(
        (PartialGridPattern(left, sample_count=3, source_count=3),), 3
    )
    assert v4._select_learned_proposals(proposals, learned) == [proposals[0]]


@pytest.mark.parametrize(
    "side,expected",
    [
        ("left", (0, 5, 10)),
        ("right", (4, 9, 14)),
        ("both", (0, 4, 5, 9, 10, 14)),
    ],
)
def test_lateral_partial_preserves_original_cell_indices(side, expected) -> None:
    source, quad = _crop(side)
    result = _refine(source, quad)
    assert result.status == "pending_partial", result.to_payload()
    assert result.additional_passes == 1
    assert result.proposal.qualification.unavailable_cell_indices == expected
    assert result.proposal.qualification.exclude_from_geometry_training
    assert result.proposal.content_safety.status == "passed"
    assert result.proposal.content_safety.protected_candidate_count >= 9
    assert {r for r, c in result.proposal.inlier_slots} == {0, 1, 2}
    assert len({c for r, c in result.proposal.inlier_slots}) >= 3
    assert result.to_payload()["automaticPartialProposal"]["requiresManualConfirmation"] is True


def test_complete_v3_result_remains_identical_without_a_second_detector(monkeypatch) -> None:
    source, quad = _source(_board())
    baselines = []
    real_v3 = v4.refine_structured_symbol_lattice_v3

    def captured_v3(*args, **kwargs):
        baseline = real_v3(*args, **kwargs)
        baselines.append(baseline)
        return baseline

    monkeypatch.setattr(v4, "refine_structured_symbol_lattice_v3", captured_v3)
    monkeypatch.setattr(
        v4, "_fit_lateral_lattice", lambda *a, **k: pytest.fail("partial pass on full board")
    )
    result = _refine(source, quad)
    assert result.status == "full"
    assert len(baselines) == 1
    assert result.baseline is baselines[0]
    assert result.to_payload() == baselines[0].to_payload()
    assert result.additional_passes == 0


def test_failed_v3_without_registration_does_not_run_extra_pass(monkeypatch) -> None:
    source, quad = _crop("left")
    monkeypatch.setattr(v4, "_fit_lateral_lattice", lambda *a, **k: pytest.fail("unattested pass"))
    result = _refine(source, quad, candidate=False)
    assert result.status == "needs_review"
    assert result.reason_code == "lateral_registration_unavailable"
    assert result.additional_passes == 0


@pytest.mark.parametrize(
    "missing",
    [
        (0, 5),
        (0, 1, 2, 5, 6, 7, 10, 11, 12),
        (2, 7, 12),
    ],
)
def test_lateral_origin_rejects_inconsistent_or_unsafe_available_columns(
    monkeypatch, missing
) -> None:
    proposal, reason = _evaluate_origin_with_missing(monkeypatch, missing)
    assert proposal is None
    assert reason == "lateral_unavailable_mask_inconsistent"


def test_lateral_origin_rejects_an_inlier_in_an_unavailable_cell(monkeypatch) -> None:
    proposal, reason = _evaluate_origin_with_missing(monkeypatch, (0, 5, 10), offset=0)
    assert proposal is None
    assert reason == "lateral_inlier_source_support_inconsistent"


@pytest.mark.parametrize("side", ["top", "bottom"])
def test_vertical_clipping_is_a_preparation_defect_without_partial_pass(side, monkeypatch) -> None:
    source, quad = _crop(side)
    monkeypatch.setattr(v4, "_fit_lateral_lattice", lambda *a, **k: pytest.fail("vertical pass"))
    result = _refine(source, quad)
    assert result.status == "source_preparation_error"
    assert result.reason_code == "source_vertical_crop_defect"
    assert result.proposal is None


def test_analysis_does_not_use_replicated_pixels_as_component_evidence() -> None:
    source, quad = _crop("both")
    analysis, support, _ = v4._supported_analysis(source, quad)
    assert not support.all()
    assert np.all(analysis[~support] == 0)
    candidates = v4._supported_candidates(analysis, support)
    assert len(candidates) >= 9
    for candidate in candidates:
        assert support[
            candidate.top : candidate.top + candidate.height,
            candidate.left : candidate.left + candidate.width,
        ].all()


def test_mismatched_policy_is_a_technical_error() -> None:
    source, quad = _crop("left")
    with pytest.raises(ValueError, match="different pinned policy"):
        v4.refine_structured_symbol_lattice_v4(
            source,
            analysis_quad=quad,
            board_frame_quad=quad,
            topology=TOPOLOGY,
            source_checksum_sha256="b" * 64,
            position_index=0,
            lateral_candidate=replace(_candidate(quad), policy_checksum_sha256="f" * 64),
            policy=POLICY,
        )


@pytest.mark.parametrize("side", ["left", "right", "both"])
def test_only_available_cells_render_after_manual_confirmation(side) -> None:
    source, quad = _crop(side)
    proposal = _refine(source, quad).proposal
    assert proposal is not None
    frame = _frame(source)
    # An automatic proposal cannot silently masquerade as manually accepted.
    manual = _geometry(frame, proposal.symbol_grid_quad, proposal.qualification)
    with pytest.raises(ImageGeometryContractError, match="not an automatic geometry fallback"):
        replace(manual, engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1)
    cells = derive_virtual_cells(geometry=manual, configuration=_configuration())
    assert tuple(cell.cell_index for cell in cells) == tuple(
        index for index in range(15) if index not in proposal.qualification.unavailable_cell_indices
    )
    renders = VirtualCellRenderer().render(frame, cells)
    assert len(renders) == len(cells)
    assert _configuration().padding_fraction == 0.08
    for cell in cells:
        assert all(
            0 <= point.x <= source.shape[1] - 1 and 0 <= point.y <= source.shape[0] - 1
            for point in cell.source_quad.corners
        )
    metadata = AutomaticPartialGeometryProposalPayload.model_validate(proposal.metadata_payload())
    assert metadata.requires_manual_confirmation is True
    assert (
        geometry_training_exclusion_reason(
            {"geometryQualification": proposal.qualification.to_dict()}
        )
        == "missing_pixels"
    )
    assert (
        page_anchor_exclusion_reason([proposal.qualification.to_dict()], expected_board_count=1)
        == "incomplete_anchor"
    )


def test_only_one_extra_ransac_for_all_column_offsets(monkeypatch) -> None:
    source, quad = _crop("both")
    original = cv2.findHomography
    calls = 0

    def observed(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(cv2, "findHomography", observed)
    result = _refine(source, quad)
    assert result.status == "pending_partial"
    assert result.hypothesis_count == 3
    assert calls == 1


def test_multiple_valid_column_origins_are_never_selected_by_best_score(monkeypatch) -> None:
    source, quad = _crop("both")
    original = v4._evaluate_origin
    reference = _refine(source, quad).proposal
    assert reference is not None

    def two_origins(matrix, **kwargs):
        if kwargs["offset"] in {0, 1}:
            return replace(reference, column_offset=kwargs["offset"]), None
        return original(matrix, **kwargs)

    monkeypatch.setattr(v4, "_evaluate_origin", two_origins)
    result = _refine(source, quad)
    assert result.status == "needs_review"
    assert result.reason_code == "ambiguous_column_indices"
    assert result.proposal is None


def test_component_bbox_crossing_boundary_rejects_partial(monkeypatch) -> None:
    source, quad = _crop("left")
    original = v4._supported_candidates

    def conflicting(*args, **kwargs):
        candidates = original(*args, **kwargs)
        first = candidates[0]
        return tuple(
            replace(c, core_left=100.0, core_width=35.0)
            if c.candidate_index == first.candidate_index
            else c
            for c in candidates
        )

    monkeypatch.setattr(v4, "_supported_candidates", conflicting)
    result = _refine(source, quad)
    assert result.status == "needs_review"
    assert result.reason_code == "content_boundary_conflict"


@pytest.mark.parametrize("case", ["two_rows", "two_columns", "eight_inliers", "excessive_residual"])
def test_insufficient_lateral_proof_remains_manual(monkeypatch, case) -> None:
    source, quad = _crop("both")
    if case in {"two_rows", "two_columns"}:
        original = v4._supported_candidates

        def fewer(*args, **kwargs):
            values = original(*args, **kwargs)
            return (
                tuple(c for c in values if c.y < 200)
                if case == "two_rows"
                else tuple(c for c in values if c.x < 300)
            )

        monkeypatch.setattr(v4, "_supported_candidates", fewer)
    else:
        original_h = v4._deterministic_lateral_fit

        def bad_fit(*args, **kwargs):
            matrix, mask = original_h(*args, **kwargs)
            if case == "eight_inliers":
                mask[:] = 0
                mask[:8] = 1
            else:
                matrix[0, 2] += 20
            return matrix, mask

        monkeypatch.setattr(v4, "_deterministic_lateral_fit", bad_fit)
    result = _refine(source, quad)
    assert result.status == "needs_review"
    assert result.proposal is None


def test_replay_preserves_proposal_mask_and_column_index() -> None:
    source, quad = _crop("both")
    cv2.setRNGSeed(111)
    first = _refine(source, quad).to_payload()
    cv2.setRNGSeed(999)
    assert first == _refine(source.copy(), quad).to_payload()


def test_partial_fit_does_not_change_rng_for_next_full_v3_board() -> None:
    source, quad = _crop("both")
    cv2.setRNGSeed(123)
    expected = np.zeros((8, 8), dtype=np.float32)
    cv2.randu(expected, 0, 1)
    cv2.setRNGSeed(123)
    _refine(source, quad)
    actual = np.zeros((8, 8), dtype=np.float32)
    cv2.randu(actual, 0, 1)
    assert np.array_equal(actual, expected)
