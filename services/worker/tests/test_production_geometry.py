"""Grid-node derivation and label levels of the production geometry export (TASK-0800)."""

from __future__ import annotations

import math

import cv2
import numpy as np
import pytest
from game_predictor_worker.vision_lab import production_geometry as pg

RECTANGLE: pg.Quad = ((100.0, 50.0), (600.0, 50.0), (600.0, 350.0), (100.0, 350.0))
# A photographed screen: converging sides, a tilted top edge.
PERSPECTIVE: pg.Quad = ((120.5, 80.25), (590.75, 60.0), (640.0, 360.5), (95.25, 330.125))


def _manifest(nodes: tuple[pg.Point, ...]) -> dict[int, pg.Quad]:
    return dict(enumerate(pg.cell_quads_from_nodes(nodes)))


def test_rectangle_nodes_are_an_even_row_major_lattice() -> None:
    nodes = pg.derive_grid_nodes(RECTANGLE)
    assert len(nodes) == pg.NODE_COUNT == 24
    for row in range(4):
        for column in range(6):
            x, y = nodes[row * 6 + column]
            assert x == pytest.approx(100.0 + column * 100.0)
            assert y == pytest.approx(50.0 + row * 100.0)
    assert nodes[0] == pytest.approx(RECTANGLE[0])
    assert nodes[5] == pytest.approx(RECTANGLE[1])
    assert nodes[23] == pytest.approx(RECTANGLE[2])
    assert nodes[18] == pytest.approx(RECTANGLE[3])


def test_perspective_nodes_match_an_independent_homography() -> None:
    nodes = pg.derive_grid_nodes(PERSPECTIVE)
    unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(unit, np.array(PERSPECTIVE, dtype=np.float32))
    grid = np.array(
        [[[column / 5, row / 3] for column in range(6)] for row in range(4)], dtype=np.float64
    ).reshape(-1, 1, 2)
    expected = cv2.perspectiveTransform(grid.astype(np.float32), matrix).reshape(-1, 2)
    assert np.allclose(np.array(nodes), expected, atol=5e-3)
    # The map is projective, not affine: a node is not the average of its row ends.
    assert nodes[3][1] != pytest.approx((nodes[0][1] + nodes[5][1]) / 2, abs=1e-6)


def test_derived_cells_share_corners_and_reproduce_the_manifest_exactly() -> None:
    nodes = pg.derive_grid_nodes(PERSPECTIVE)
    cells = pg.cell_quads_from_nodes(nodes)
    assert len(cells) == pg.CELL_COUNT == 15
    assert cells[0][1] == cells[1][0]
    assert cells[0][2] == cells[6][0] == cells[1][3]
    assert cells[14][2] == nodes[23]
    assert pg.max_manifest_deviation(nodes, _manifest(nodes)) == 0.0
    shifted = {
        index: tuple((x + 0.5, y) for x, y in quad) for index, quad in _manifest(nodes).items()
    }
    assert pg.max_manifest_deviation(nodes, shifted) == pytest.approx(0.5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "quad",
    [
        ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),  # collinear
        ((0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)),  # self-intersecting bow tie
        ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0), (0.0, 10.0)),  # zero-area corner
        ((0.0, 0.0), (10.0, 0.0), (4.0, 4.0), (0.0, 10.0)),  # concave
    ],
)
def test_degenerate_quads_are_rejected_instead_of_guessed(quad: pg.Quad) -> None:
    with pytest.raises(pg.ProductionGeometryError) as error:
        pg.derive_grid_nodes(quad)
    assert error.value.code == pg.EXCLUSION_QUAD_DEGENERATE


def test_parse_quad_never_invents_a_quad() -> None:
    good = [{"x": 1, "y": 2}, {"x": 3.5, "y": 2}, {"x": 3, "y": 9}, {"x": 1, "y": 9}]
    assert pg.parse_quad(good) == ((1.0, 2.0), (3.5, 2.0), (3.0, 9.0), (1.0, 9.0))
    assert pg.parse_quad(None) is None
    assert pg.parse_quad(good[:3]) is None
    assert pg.parse_quad("abcd") is None
    assert pg.parse_quad([*good[:3], {"x": 1}]) is None
    assert pg.parse_quad([*good[:3], {"x": True, "y": 1}]) is None
    assert pg.parse_quad([*good[:3], {"x": math.nan, "y": 1}]) is None
    assert pg.parse_quad([*good[:3], [1, 2]]) is None


def test_derive_consistent_nodes_takes_the_candidate_the_manifest_was_rendered_from() -> None:
    truth = pg.derive_grid_nodes(PERSPECTIVE)
    wrong = pg.QuadCandidate("frame", RECTANGLE)
    right = pg.QuadCandidate("symbol_grid", PERSPECTIVE)
    derived = pg.derive_consistent_nodes([wrong, right], _manifest(truth))
    assert derived.quad_source == "symbol_grid"
    assert derived.nodes == truth
    assert derived.max_deviation_px == 0.0
    assert derived.manifest_cell_indices == tuple(range(15))
    assert derived.missing_cell_indices == ()


def test_stored_quad_rounded_within_tolerance_is_accepted_and_beyond_it_is_not() -> None:
    truth = pg.derive_grid_nodes(PERSPECTIVE)
    near = tuple((x + pg.NODE_TOLERANCE_PX / 4, y) for x, y in PERSPECTIVE)
    far = tuple((x + 0.5, y) for x, y in PERSPECTIVE)
    assert (
        pg.derive_consistent_nodes([pg.QuadCandidate("a", near)], _manifest(truth)).max_deviation_px  # type: ignore[arg-type]
        < pg.NODE_TOLERANCE_PX
    )
    with pytest.raises(pg.ProductionGeometryError) as error:
        pg.derive_consistent_nodes([pg.QuadCandidate("a", far)], _manifest(truth))  # type: ignore[arg-type]
    assert error.value.code == pg.EXCLUSION_NODES_MISMATCH


def test_board_without_a_matching_or_any_quad_is_excluded() -> None:
    manifest = _manifest(pg.derive_grid_nodes(PERSPECTIVE))
    with pytest.raises(pg.ProductionGeometryError) as mismatch:
        pg.derive_consistent_nodes([pg.QuadCandidate("frame", RECTANGLE)], manifest)
    assert mismatch.value.code == pg.EXCLUSION_NODES_MISMATCH
    with pytest.raises(pg.ProductionGeometryError) as missing:
        pg.derive_consistent_nodes([], manifest)
    assert missing.value.code == pg.EXCLUSION_QUAD_MISSING
    flat: pg.Quad = ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0))
    with pytest.raises(pg.ProductionGeometryError) as degenerate:
        pg.derive_consistent_nodes([pg.QuadCandidate("flat", flat)], manifest)
    assert degenerate.value.code == pg.EXCLUSION_QUAD_DEGENERATE
    with pytest.raises(pg.ProductionGeometryError) as empty:
        pg.derive_consistent_nodes([pg.QuadCandidate("a", PERSPECTIVE)], {})
    assert empty.value.code == pg.EXCLUSION_MANIFEST_MALFORMED


def test_partial_board_may_miss_only_cells_of_its_unavailable_mask() -> None:
    nodes = pg.derive_grid_nodes(PERSPECTIVE)
    manifest = _manifest(nodes)
    for index in (0, 5):
        del manifest[index]
    candidate = [pg.QuadCandidate("grid", PERSPECTIVE)]
    derived = pg.derive_consistent_nodes(candidate, manifest, unavailable_cell_indices=[0, 5, 10])
    assert derived.missing_cell_indices == (0, 5)
    assert derived.manifest_cell_indices == (1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    with pytest.raises(pg.ProductionGeometryError) as error:
        pg.derive_consistent_nodes(candidate, manifest, unavailable_cell_indices=[0])
    assert error.value.code == pg.EXCLUSION_CELLS_MISSING
    manifest[99] = manifest[1]
    with pytest.raises(pg.ProductionGeometryError):
        pg.derive_consistent_nodes(candidate, manifest, unavailable_cell_indices=[0, 5])


def test_difficulty_metrics_of_a_rectangle_and_a_perspective_quad() -> None:
    flat = pg.quad_difficulty(RECTANGLE)
    assert flat["areaPx"] == pytest.approx(500.0 * 300.0)
    assert flat["edgeRatioHorizontal"] == pytest.approx(1.0)
    assert flat["edgeRatioVertical"] == pytest.approx(1.0)
    assert flat["maxAngleDeviationDeg"] == pytest.approx(0.0, abs=1e-9)
    tilted = pg.quad_difficulty(PERSPECTIVE)
    assert tilted["edgeRatioHorizontal"] > 1.0
    assert tilted["maxAngleDeviationDeg"] > 1.0
    assert pg.quad_area(PERSPECTIVE) == pytest.approx(tilted["areaPx"])


def test_nodes_outside_the_image_and_page_slots() -> None:
    nodes = ((0.0, 0.0), (99.0, 0.0), (100.0, 5.0), (-0.1, 5.0), (5.0, 59.0), (5.0, 60.0))
    assert pg.nodes_outside_image(nodes, 100, 60) == 3
    assert pg.page_position(0) == {
        "pageRow": 0,
        "pageColumn": 0,
        "outerColumn": True,
        "outerRow": True,
    }
    assert pg.page_position(4) == {
        "pageRow": 1,
        "pageColumn": 1,
        "outerColumn": False,
        "outerRow": False,
    }
    assert pg.page_position(8) == {
        "pageRow": 2,
        "pageColumn": 2,
        "outerColumn": True,
        "outerRow": True,
    }
    assert pg.page_position(7)["outerRow"] is True


def _facts(**overrides: object) -> pg.LabelFacts:
    base: dict[str, object] = {
        "geometry_revision": 0,
        "approved_geometry_revision": None,
        "approved_by": None,
        "revision_authors": (),
        "source_geometry_source": "auto",
        "source_status": "accepted",
        "source_created_by": "system:image-pipeline-v0.10",
    }
    base.update(overrides)
    return pg.LabelFacts(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("facts", "level", "basis", "actor"),
    [
        # B: engine geometry, accepted source revision, nobody approved.
        (_facts(), "B", "engine_accepted_unapproved", None),
        # G: a person approved the engine geometry at revision 0 (local-admin, 63 boards).
        (
            _facts(approved_geometry_revision=0, approved_by="local-admin"),
            "G",
            "human_approval",
            "local-admin",
        ),
        # G: a person saved and approved revision 1 (local-admin, 135 boards).
        (
            _facts(
                geometry_revision=1,
                approved_geometry_revision=1,
                approved_by="local-admin",
                revision_authors=[(1, "local-admin")],
                source_geometry_source="manual",
            ),
            "G",
            "human_approval",
            "local-admin",
        ),
        # S: reverify approval.
        (
            _facts(
                geometry_revision=1,
                approved_geometry_revision=1,
                approved_by="system:grid-reverify-777-v1",
                revision_authors=[(1, "system:grid-reverify-777-v1")],
                source_geometry_source="manual",
            ),
            "S",
            "system_reverify",
            "system:grid-reverify-777-v1",
        ),
        # S: another known system approval is classified explicitly.
        (
            _facts(
                approved_geometry_revision=0,
                approved_by="system:import-qualified-manual-geometry",
                source_geometry_source="manual",
            ),
            "S",
            "system_import_qualified_manual_geometry",
            "system:import-qualified-manual-geometry",
        ),
        # G: a Reviewer revision carried over by the legacy conversion (no approval record).
        (
            _facts(
                geometry_revision=2,
                revision_authors=[(1, "reviewer-operator"), (2, pg.LEGACY_CONVERSION_ACTOR)],
                source_geometry_source="manual",
                source_created_by=pg.LEGACY_CONVERSION_ACTOR,
            ),
            "G",
            "human_saved_revision_via_legacy_conversion",
            "reviewer-operator",
        ),
        # G: a person saved the current revision but nobody approved it.
        (
            _facts(
                geometry_revision=1,
                revision_authors=[(1, "reviewer-operator")],
                source_geometry_source="manual",
            ),
            "G",
            "human_saved_revision_unapproved",
            "reviewer-operator",
        ),
        # U: unknown system approver, unknown person, unknown revision author.
        (
            _facts(approved_geometry_revision=0, approved_by="system:future-job"),
            "U",
            "unknown_system_approver",
            "system:future-job",
        ),
        (
            _facts(approved_geometry_revision=0, approved_by="someone"),
            "U",
            "unknown_approver",
            "someone",
        ),
        (
            _facts(geometry_revision=1, revision_authors=[(1, "someone")]),
            "U",
            "unknown_revision_author",
            "someone",
        ),
        # U: legacy conversion without any earlier human revision.
        (
            _facts(
                geometry_revision=1,
                revision_authors=[(1, pg.LEGACY_CONVERSION_ACTOR)],
                source_geometry_source="manual",
            ),
            "U",
            "legacy_conversion_without_human_revision",
            None,
        ),
        # U: manual source geometry with no authorship (449 boards in the dev database).
        (
            _facts(source_geometry_source="manual", source_created_by=pg.LEGACY_CONVERSION_ACTOR),
            "U",
            "manual_source_geometry_without_authorship",
            None,
        ),
        # U: engine geometry whose source revision is not accepted.
        (_facts(source_status="needs_review"), "U", "engine_geometry_not_accepted", None),
        # U: approval of an older revision of a board that changed since.
        (
            _facts(geometry_revision=2, approved_geometry_revision=1, approved_by="local-admin"),
            "U",
            "approval_of_older_revision",
            "local-admin",
        ),
        (_facts(source_geometry_source=None), "U", "unrecognized_lineage", None),
    ],
)
def test_label_level_rule(facts: pg.LabelFacts, level: str, basis: str, actor: str | None) -> None:
    result = pg.classify_label_level(facts)
    assert (result.level, result.basis, result.approval_actor) == (level, basis, actor)


# --- original production output (TASK-0804) ---------------------------------------------------


def _lineage(*items: tuple[int, str, str]) -> list[pg.RevisionFacts]:
    return [pg.RevisionFacts(revision, source, kind) for revision, source, kind in items]


def test_original_is_the_last_automatic_engine_revision_before_the_first_manual() -> None:
    selection = pg.select_production_original(
        _lineage(
            (2, "manual", "manual_v1"),
            (0, "auto", "structured_opencv_v1"),
            (1, "auto", "structured_opencv_v1"),
            (3, "auto", "structured_opencv_v1"),
        )
    )
    assert selection == pg.OriginalSelection(1, 2, None)


def test_original_without_manual_revision_is_the_newest_engine_revision() -> None:
    selection = pg.select_production_original(
        _lineage((0, "auto", "structured_opencv_v1"), (1, "auto", "structured_opencv_v1"))
    )
    assert selection == pg.OriginalSelection(1, None, None)


@pytest.mark.parametrize(
    "lineage",
    [
        (),
        ((0, "manual", "manual_v1"), (1, "manual", "manual_v1")),
        ((0, "manual", "manual_v1"), (1, "auto", "structured_opencv_v1")),
        ((0, "auto", "legacy_v20"),),
    ],
)
def test_lineage_without_engine_revision_before_manual_has_no_original(
    lineage: tuple[tuple[int, str, str], ...],
) -> None:
    selection = pg.select_production_original(_lineage(*lineage))
    assert selection.original_revision is None
    assert selection.missing_reason == pg.ORIGINAL_MISSING_NO_AUTOMATIC_REVISION


def test_original_board_nodes_come_from_the_symbol_grid_quad() -> None:
    entry = {"symbolGridQuad": [{"x": x, "y": y} for x, y in PERSPECTIVE]}
    nodes, reason = pg.original_board_nodes(entry)
    assert reason is None
    assert nodes == pg.derive_grid_nodes(PERSPECTIVE)


@pytest.mark.parametrize(
    ("quad", "reason"),
    [
        (None, pg.ORIGINAL_BOARD_WITHOUT_GRID),
        ([{"x": 0, "y": 0}] * 3, pg.ORIGINAL_BOARD_WITHOUT_GRID),
        (
            [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}, {"x": 3, "y": 0}],
            pg.EXCLUSION_QUAD_DEGENERATE,
        ),
    ],
)
def test_original_board_without_a_usable_grid_is_explicit(quad: object, reason: str) -> None:
    assert pg.original_board_nodes({"symbolGridQuad": quad}) == (None, reason)
