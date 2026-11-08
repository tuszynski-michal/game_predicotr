"""Source content never follows a grid correction or invents hidden symbol geometry."""

import math
from datetime import UTC, datetime
from uuid import UUID

import pytest
from game_predictor_api.domain.grid_cell_content import (
    ContentError,
    ContentRevision,
    ContentSource,
    ContentTarget,
    content_capture_counts,
    content_readiness,
    content_readiness_views,
    oracle_qualification,
)
from game_predictor_api.domain.grid_content_repeatability import (
    bbox_diagonal,
    nearest_rank_p95,
    point_to_filled_quad,
    repeatability_report,
    symmetric_board_nme,
    symmetric_quad_hausdorff,
)
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
)

GAME = UUID(int=1)
SESSION = UUID(int=2)
NOW = datetime(2026, 11, 8, tzinfo=UTC)
NODES = tuple((float(col * 20 + 10), float(row * 20 + 10)) for row in range(4) for col in range(6))


def target(photo=1, slot=0, role="TRAIN", full=False, game=GAME):
    return ContentTarget(
        gameId=game,
        source=ContentSource(
            sourceId=UUID(int=photo + 100),
            sourceSha256=f"{photo:064x}",
            sourceRepresentativeSha256=f"{photo + 1000:064x}",
            width=200,
            height=120,
        ),
        positionIndex=slot,
        sequenceNumber=(photo - 1) * 9 + slot + 1,
        role=role,
        fullPhoto=full,
        targetSha256="a" * 64,
        roleProofSha256="b" * 64,
    )


def test_unresolved_role_photo_cannot_disappear_from_readiness():
    member = target()
    report = content_readiness(
        [member], [revision(member)], [GAME], unresolved_photos={(str(GAME), "TRAIN"): 1}
    )
    role = report["games"][str(GAME)]["TRAIN"]
    assert role["unresolvedPhotos"] == 1
    assert role["state"] == "not_evaluable"
    assert "CONTENT_ROLE_MEMBERSHIP_INCOMPLETE" in role["reasonCodes"]


def revision(t, pass_number=1, shift=0.0, states=None, nodes=NODES, actor="local-owner"):
    cells = []
    for index in range(15):
        row, col = divmod(index, 5)
        x, y = col * 20 + 15 + shift, row * 20 + 15
        state = states[index] if states else "visible"
        quad = ((x, y), (x + 10, y), (x + 10, y + 10), (x, y + 10)) if state == "visible" else None
        cells.append(CellContentReference(state=state, quad=quad))
    return ContentRevision(
        source=t.source,
        reference=BoardContentReference(
            gameId=t.gameId,
            sourceRepresentativeSha256=t.source.sourceRepresentativeSha256,
            positionIndex=t.positionIndex,
            revision=pass_number,
            humanApproved=True,
            cells=tuple(cells),
        ),
        sequenceNumber=t.sequenceNumber,
        origin="manual_blind",
        actor=actor,
        approvedBy=actor,
        approvedAt=NOW,
        recordedAt=NOW,
        sessionId=SESSION,
        passNumber=pass_number,
        measuredNodes=nodes,
    )


def test_visible_requires_full_quad_other_states_do_not_invent_hidden_extent():
    for state in ("unknown", "occluded", "out_of_frame"):
        assert CellContentReference(state=state).quad is None
    with pytest.raises(ValueError, match="VISIBILITY_VISIBLE_CONTENT_REQUIRED"):
        CellContentReference(state="visible")


def test_source_frame_and_approval_are_not_claimed_by_machine():
    doc = revision(target()).model_dump(mode="json")
    doc["actor"] = "worker:auto"
    with pytest.raises(ValueError, match="validated human"):
        ContentRevision.model_validate(doc)
    doc = revision(target()).model_dump(mode="json")
    doc["approvedBy"] = None
    with pytest.raises(ValueError, match="CONTENT_APPROVAL_INVALID"):
        ContentRevision.model_validate(doc)
    doc = revision(target()).model_dump(mode="json")
    doc["source"]["sourceRepresentativeSha256"] = "f" * 64
    with pytest.raises(ValueError, match="CONTENT_SOURCE_IDENTITY_CONFLICT"):
        ContentRevision.model_validate(doc)


def test_no_content_geometry_revision_coupling_or_unknown_full_geometry_loss():
    t = target()
    before = revision(t)
    after = revision(t, pass_number=2, nodes=tuple((x + 2, y) for x, y in NODES))
    assert before.reference.cells == after.reference.cells
    assert "geometryRevision" not in before.model_dump()
    doc = before.model_dump(mode="json")
    doc["geometryRevision"] = 7
    with pytest.raises(ValueError):
        ContentRevision.model_validate(doc)


def test_nearest_rank_not_interpolation_and_invalid_never_zero():
    assert nearest_rank_p95(list(range(1, 21))) == 19
    assert nearest_rank_p95([1, 2]) == 2
    for values in ([], [math.nan], [-1]):
        with pytest.raises(ValueError):
            nearest_rank_p95(values)
    with pytest.raises(ValueError):
        bbox_diagonal([(0.0, 0.0)] * 4)


def test_filled_convex_hausdorff_is_corner_order_independent_and_symmetric():
    outer = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
    inner = ((1.0, 1.0), (9.0, 1.0), (9.0, 9.0), (1.0, 9.0))
    assert point_to_filled_quad((5.0, 5.0), outer) == 0
    assert symmetric_quad_hausdorff(outer, inner) == pytest.approx(math.sqrt(2))
    assert symmetric_quad_hausdorff(inner, outer) == pytest.approx(math.sqrt(2))
    assert symmetric_quad_hausdorff(outer, outer[2:] + outer[:2]) == 0


def test_delta_uses_worse_gt_bbox_direction_and_exact_24_point_mean():
    enlarged = tuple((x * 1.01, y * 1.01) for x, y in NODES)
    mean = sum(math.dist(a, b) for a, b in zip(NODES, enlarged, strict=True)) / 24
    expected = mean / bbox_diagonal(NODES)
    assert symmetric_board_nme(NODES, enlarged) == pytest.approx(expected)
    assert symmetric_board_nme(enlarged, NODES) == pytest.approx(expected)


def test_repeatability_minima_caps_photographic_mean_and_blind_provenance():
    targets = [target(photo, slot) for photo in range(1, 11) for slot in range(3)]
    first = [revision(t) for t in targets]
    second = [revision(t, pass_number=2, shift=0.1) for t in targets]
    result = repeatability_report(targets, first, second, [GAME])
    game = result["games"][str(GAME)]
    assert result["state"] == "ready"
    assert game["u"] == pytest.approx(0.1 / math.sqrt(800))
    assert game["delta"] == 0
    assert game["operatorScope"] == "intra_operator"
    assert game["photos"] == 10
    failed = repeatability_report(
        targets, first, [revision(t, 2, shift=1) for t in targets], [GAME]
    )
    assert "CONTENT_U_LIMIT" in failed["games"][str(GAME)]["reasonCodes"]
    incomplete = repeatability_report(targets, first, second[:-1], [GAME])
    assert incomplete["games"][str(GAME)]["missingPairs"] == 1
    with pytest.raises(ContentError, match="TRAIN/A"):
        repeatability_report([target(role="REGRESSION")], [], [], [GAME])


def test_unknown_ratio_counts_missing_labels_full_reg_photos_and_games_separately():
    targets = [
        target(photo, slot, "REGRESSION", True) for photo in range(1, 6) for slot in range(9)
    ]
    revisions = [revision(t) for t in targets]
    ready = content_readiness(targets, revisions, [GAME])["games"][str(GAME)]["REGRESSION"]
    assert ready["fullPhotos"] == 5 and ready["slots"] == 675
    unknown = content_readiness(targets, revisions[:-5], [GAME])["games"][str(GAME)]["REGRESSION"]
    assert unknown["states"]["unknown"] == 75
    assert "CONTENT_UNKNOWN_LIMIT" in unknown["reasonCodes"]
    other = content_readiness(targets, revisions, [GAME, UUID(int=3)])["games"][str(UUID(int=3))][
        "REGRESSION"
    ]
    assert other["fullPhotos"] == 0 and other["missingFullPhotos"] == 5


def test_invalid_blind_geometry_is_reported_not_a_zero_measurement():
    t = target()
    bad = revision(t, 2, nodes=((0.0, 0.0),) * 24)
    game = repeatability_report([t], [revision(t)], [bad], [GAME])["games"][str(GAME)]
    assert game["invalidGeometryPairs"] == 1
    assert game["delta"] is None and game["u"] is None


def test_live_complete_labels_cannot_upgrade_legacy_frozen_pin_coverage():
    targets = [target(10, role="TRAIN"), target(11, role="A"), target(12, role="B")]
    targets += [
        target(photo, slot, "REGRESSION", True) for photo in range(1, 6) for slot in range(9)
    ]
    labels = [revision(t) for t in targets]
    legacy = content_readiness_views(targets, labels, [], [GAME])
    assert legacy["annotationProgress"]["state"] == "evaluable"
    assert legacy["frozenPinCoverage"]["state"] == legacy["state"] == "not_evaluable"
    assert legacy["basis"] == "frozen_content_pins"
    pinned = content_readiness_views(targets, [], labels, [GAME])
    assert pinned["state"] == "evaluable"
    assert pinned["annotationProgress"]["state"] == "not_evaluable"


def test_oracle_negative_board_is_not_clipping_or_full_qualification():
    negative = revision(target(), states=["occluded"] * 15)
    # Legal TRAIN negatives remain available as labels independently of oracle qualification.
    role = content_readiness([target()], [negative], [GAME])["games"][str(GAME)]["TRAIN"]
    assert role["states"]["occluded"] == 15 and role["state"] == "evaluable"
    no_visible = oracle_qualification(["checked", "not_evaluable"])
    assert no_visible["qualificationState"] == "not_evaluable"
    assert no_visible["blockedBoards"] == 0 and no_visible["notEvaluableBoards"] == 1
    clipped = oracle_qualification(["checked", "not_evaluable", "render_contract_blocked"])
    assert clipped["qualificationState"] == "render_contract_blocked"
    assert clipped["blockedBoards"] == 1
    assert oracle_qualification(["checked"])["qualificationState"] == "ready"


def test_train_negative_pin_does_not_require_full_content_oracle_pass():
    from types import SimpleNamespace

    from game_predictor_api.storage.grid_cell_content_pins import content_pin

    t = target()
    label = revision(t, states=["occluded"] * 15)
    row = SimpleNamespace(
        document=label.model_dump(mode="json"),
        document_sha256=label.sha256,
        revision=1,
        oracle={"state": "not_evaluable"},
    )
    session = SimpleNamespace(scalar=lambda _query: row)
    source = {
        "id": str(t.source.sourceId),
        "checksum_sha256": t.source.sourceSha256,
        "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
        "oriented_width": t.source.width,
        "oriented_height": t.source.height,
        "coordinate_space": t.source.coordinateSpace,
        "normalization_adapter_version": t.source.normalizationAdapterVersion,
    }
    pin = content_pin(
        session,
        GAME,
        source,
        {"positionIndex": t.positionIndex, "sequenceNumber": t.sequenceNumber},
        purpose="TRAIN",
    )
    assert pin["contentReferenceSha256"] == label.sha256
    assert all(c["state"] == "occluded" for c in pin["contentAnnotation"]["reference"]["cells"])
    assert pin["contentOracle"]["state"] == "not_evaluable"


def test_content_pin_sequence_failure_has_explicit_counts_and_no_qualified_target():
    from types import SimpleNamespace

    from game_predictor_api.storage.grid_cell_content_pins import content_pin

    t, label = target(), revision(target())
    row = SimpleNamespace(document=label.model_dump(mode="json"), document_sha256=label.sha256)
    source = {
        "id": str(t.source.sourceId),
        "checksum_sha256": t.source.sourceSha256,
        "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
        "oriented_width": t.source.width,
        "oriented_height": t.source.height,
        "coordinate_space": t.source.coordinateSpace,
        "normalization_adapter_version": t.source.normalizationAdapterVersion,
    }
    with pytest.raises(ContentError) as failed:
        content_pin(
            SimpleNamespace(scalar=lambda _query: row),
            GAME,
            source,
            {"positionIndex": 0, "sequenceNumber": t.sequenceNumber + 1},
            purpose="TRAIN",
        )
    assert failed.value.code == "CONTENT_REFERENCE_IDENTITY_CONFLICT"
    positions = [
        {"label": None, "reason": failed.value.code},
        {"label": {"nodes": NODES}, "reason": None},
        {"label": {"contentAnnotation": label.model_dump(mode="json")}, "reason": None},
    ]
    counts = content_capture_counts(3, positions)
    assert counts == {
        "canonicalBoards": 3,
        "contentUsedBoards": 2,
        "contentQualifiedBoards": 1,
        "contentMissingBoards": 2,
        "contentReasonCounts": {
            "CONTENT_LABELS_MISSING": 1,
            "CONTENT_REFERENCE_IDENTITY_CONFLICT": 1,
        },
    }


def test_readiness_retains_excluded_frozen_target_as_unresolved_photo(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
    from game_predictor_worker.images import grid_cohort_dataset

    t, annotation = target(), revision(target())
    source_id = str(t.source.sourceId)
    board = {
        "positionIndex": 0,
        "sequenceNumber": t.sequenceNumber,
        "contentAnnotation": annotation.model_dump(mode="json"),
        "contentReferenceSha256": annotation.sha256,
        "contentReferenceRevision": 1,
    }
    frozen = {
        "sourceId": source_id,
        "role": "TRAIN",
        "purposeProofSha256": "c" * 64,
        "sourceIdentity": {
            "id": source_id,
            "checksum_sha256": t.source.sourceSha256,
            "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
            "oriented_width": t.source.width,
            "oriented_height": t.source.height,
            "coordinate_space": t.source.coordinateSpace,
            "normalization_adapter_version": t.source.normalizationAdapterVersion,
        },
        "targets": [board],
    }
    pin = {
        "sourceId": source_id,
        "representative": True,
        "role": "TRAIN",
        "pixelSha256": t.source.sourceRepresentativeSha256,
        "canonicalBoards": 2,
    }
    snapshot = SimpleNamespace(
        manifest={"photoSplit": {"sources": [pin]}}, sources=lambda: iter([frozen])
    )

    class Dataset:
        def __init__(self, _snapshot, role):
            self.role = role

        def indexed(self):
            return [(frozen, [])] if self.role == "TRAIN" else []

    monkeypatch.setattr(grid_cohort_dataset, "GridBoardDataset", Dataset)
    monkeypatch.setattr(grid_cohort_dataset, "GridAssessmentDataset", Dataset)
    repo = SqlAlchemyGridCellContentRepository(None, tmp_path)
    monkeypatch.setattr(repo, "bind", lambda _game: None)
    monkeypatch.setattr(repo, "snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(
        repo, "latest", lambda *_args: SimpleNamespace(document=annotation.model_dump(mode="json"))
    )
    report = repo.readiness(GAME, UUID(int=99), "d" * 64)
    role = report["frozenPinCoverage"]["games"][str(GAME)]["TRAIN"]
    assert role["boards"] == 1 and role["unresolvedPhotos"] == 1
    assert role["state"] == "not_evaluable"
    assert "CONTENT_ROLE_MEMBERSHIP_INCOMPLETE" in role["reasonCodes"]
