from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import uuid4


def _load_script() -> Any:
    path = Path(__file__).parents[3] / "scripts" / "reverify_777_grids.py"
    spec = spec_from_file_location("reverify_777_grids", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    # Dataclasses resolve string annotations through ``sys.modules``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()
QUAD = ((10.0, 10.0), (110.0, 10.0), (110.0, 60.0), (10.0, 60.0))


def _observation(
    quad: Any = QUAD,
    *,
    status: str = "estimated",
    inliers: int = 15,
    residual: float | None = 0.5,
    scale: float = 1.0,
) -> Any:
    return SCRIPT.VerifierObservation(
        hint_scale=scale,
        status=status,
        quad=quad,
        inlier_count=inliers,
        p95_residual_px=residual,
        fallback_reason=None,
        elapsed_ms=1.0,
    )


def _shift(quad: Any, corner: int, dx: float) -> Any:
    points = list(quad)
    x, y = points[corner]
    points[corner] = (x + dx, y)
    return tuple(points)


def test_parse_quad_accepts_points_and_rejects_invalid_payloads() -> None:
    payload = [{"x": x, "y": y} for x, y in QUAD]
    assert SCRIPT.parse_quad(payload) == QUAD
    assert SCRIPT.parse_quad(payload[:3]) is None
    assert SCRIPT.parse_quad([{"x": True, "y": 1}, *payload[1:]]) is None
    assert SCRIPT.parse_quad([{"x": float("nan"), "y": 1}, *payload[1:]]) is None
    assert SCRIPT.parse_quad("abcd") is None


def test_max_corner_distance_is_the_worst_single_corner() -> None:
    assert SCRIPT.max_corner_distance(QUAD, QUAD) == 0.0
    assert SCRIPT.max_corner_distance(QUAD, _shift(QUAD, 2, 5.0)) == 5.0


def test_scale_quad_keeps_centroid() -> None:
    scaled = SCRIPT.scale_quad(QUAD, 1.1)
    assert (
        SCRIPT.max_corner_distance(scaled, ((5.0, 7.5), (115.0, 7.5), (115.0, 62.5), (5.0, 62.5)))
        < 1e-9
    )


def test_confidence_gate_requires_complete_low_residual_in_image_lattice() -> None:
    thresholds = SCRIPT.Thresholds(tau_px=2.0, max_residual_px=1.0, min_inliers=15)
    size = {"width": 200, "height": 100}
    assert SCRIPT.verifier_is_confident(_observation(), thresholds, **size)
    assert not SCRIPT.verifier_is_confident(_observation(status="needs_review"), thresholds, **size)
    assert not SCRIPT.verifier_is_confident(_observation(inliers=14), thresholds, **size)
    assert not SCRIPT.verifier_is_confident(_observation(residual=1.5), thresholds, **size)
    assert not SCRIPT.verifier_is_confident(_observation(residual=None), thresholds, **size)
    assert not SCRIPT.verifier_is_confident(_observation(), thresholds, width=100, height=100)
    unlimited = SCRIPT.Thresholds(tau_px=2.0, max_residual_px=None, min_inliers=15)
    assert SCRIPT.verifier_is_confident(_observation(residual=None), unlimited, **size)


def test_validation_board_requires_agreement_with_the_engine() -> None:
    thresholds = SCRIPT.Thresholds(tau_px=2.0, max_residual_px=None, min_inliers=15)
    size = {"width": 200, "height": 100}
    assert SCRIPT.validation_board_accepted(
        _observation(), _shift(QUAD, 1, 2.0), thresholds, **size
    )
    assert not SCRIPT.validation_board_accepted(
        _observation(), _shift(QUAD, 1, 2.5), thresholds, **size
    )


def _golden(kind: str, *, engine: Any, human: Any, verifier: Any) -> Any:
    board = SCRIPT.GoldenBoard(
        kind=kind,
        recognized_board_id=uuid4(),
        source_image_id=uuid4(),
        position_index=0,
        sequence_number=1,
        width=200,
        height=100,
        hint=QUAD,
        engine_quad=engine,
        human_quad=human,
    )
    board.observations = [_observation(verifier, scale=scale) for scale in SCRIPT.HINT_SCALES]
    return board


def test_evaluate_counts_false_accepts_against_the_human_geometry() -> None:
    wrong_engine = _shift(QUAD, 0, 4.0)
    golden = [
        # Engine correct and verifier agrees -> true accept.
        _golden("approved_unchanged", engine=QUAD, human=QUAD, verifier=QUAD),
        # Engine wrong by 4 px, verifier copies the engine -> false accept at 2/3 px.
        _golden("human_revised", engine=wrong_engine, human=QUAD, verifier=wrong_engine),
        # Engine wrong, verifier disagrees with the engine -> correctly refused.
        _golden("human_revised", engine=wrong_engine, human=QUAD, verifier=QUAD),
        # Pending slot, verifier 6 px off the human -> false accept at every limit.
        _golden("pending_resolved", engine=None, human=QUAD, verifier=_shift(QUAD, 3, 6.0)),
    ]
    thresholds = SCRIPT.Thresholds(tau_px=2.0, max_residual_px=None, min_inliers=15)
    result = SCRIPT._evaluate(golden, [], 1.0, thresholds)
    assert result["goldenValidationTotal"] == 3
    assert result["goldenValidationAccepted"] == 2
    assert result["goldenValidationFalseAcceptsByHumanErrorPx"] == {"2.0": 1, "3.0": 1, "5.0": 0}
    assert result["goldenPendingAccepted"] == 1
    assert result["goldenPendingFalseAcceptsByHumanErrorPx"] == {"2.0": 1, "3.0": 1, "5.0": 1}
    assert result["sampleValidationCoverage"] is None
