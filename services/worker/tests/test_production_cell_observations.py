"""Bounded real-renderer/input tests, never evaluation evidence for a model."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.production_cell_geometry import assess_content
from game_predictor_worker.geometry_core.metrics import evaluate_photo as match_photo
from game_predictor_worker.geometry_core.settings import BoardPreset
from game_predictor_worker.images.production_cell_evaluation import (
    ProductionContentObserver,
    ambiguous_matching,
    real_source_support,
    reference_context,
    render_cells,
)
from game_predictor_worker.images.production_cell_input import observe_input, verify_input
from game_predictor_worker.images.production_cell_run import summarize_content
from game_predictor_worker.training_core.grid_correction_metrics import (
    CorrectionControlPhoto,
    evaluate_photo,
)
from game_predictor_worker.training_core.grid_evaluation import predictions
from test_grid_cell_content_reference import oracle_fixture


def fixture(content_inset=5, inset=0.1, state="visible"):
    frame, cells, annotation, nodes, _ = oracle_fixture(inset, content_inset, state)
    context = {
        "state": "available",
        "classifier": {"testPinnedClassifier": "real-renderer"},
        "renderConfiguration": cells[0].configuration.to_dict(),
        "importJobId": str(UUID(int=3)),
        "fileExecutionKey": "b" * 64,
        "topologyRulesVersionId": str(UUID(int=4)),
        "sequenceRangeStart": 1,
        "sequenceRangeEnd": 1,
    }
    body = {
        "version": "production-cell-evaluation-reference-v1",
        "sourceContext": context,
        "sourceContextSha256": digest(context),
        "measurement": None,
    }
    target = {
        "positionIndex": 0,
        "sequenceNumber": 1,
        "contentAnnotation": annotation.model_dump(mode="json"),
        "contentReferenceSha256": annotation.sha256,
        "contentReferenceRevision": 1,
        "productionContentReference": {**body, "sha256": digest(body)},
    }
    source = {
        "sourceId": str(annotation.source.sourceId),
        "sourceIdentity": {
            "normalized_pixel_checksum_sha256": annotation.source.sourceRepresentativeSha256,
            "checksum_sha256": annotation.source.sourceSha256,
            "oriented_width": 200,
            "oriented_height": 120,
            "coordinate_space": annotation.source.coordinateSpace,
            "exif_orientation": None,
            "normalization_adapter_version": annotation.source.normalizationAdapterVersion,
        },
        "targets": [target],
    }
    return frame, source, target, np.asarray(nodes, dtype=np.float32), context


def board_preset(margin=0.0):
    return BoardPreset(
        margin=margin,
        corner_jitter=0,
        shift_jitter=0,
        scale_jitter=0,
        rotation_jitter_degrees=0,
        boards_per_image=1,
        coordinate_loss_weight=1,
        heatmap_loss_weight=1,
        heatmap_sigma=1,
        visibility_loss_weight=1,
    )


def test_actual_renderer_float32_footprint_and_immutable_inset():
    frame, _, target, nodes, context = fixture(content_inset=1)
    rendered = render_cells(frame, nodes.astype(np.float64) + 0.0000007, target, context)
    assert len(rendered) == 15
    assert all(item["renderedPixelSha256"] for item in rendered)
    for item in rendered:
        assert (
            item["float32Footprint"]
            == np.asarray(item["float32Footprint"], dtype=np.float32).astype(float).tolist()
        )
    quad = target["contentAnnotation"]["reference"]["cells"][0]["quad"]
    assert assess_content(quad, rendered[0]["support"], 0)["state"] == "clipped"
    assert context["renderConfiguration"]["paddingFraction"] == 0.1


def observer_result(found_base, found_candidate, *, state="visible", content_inset=5, inset=0.1):
    frame, source, _, nodes, _ = fixture(content_inset, inset, state)
    observer = object.__new__(ProductionContentObserver)
    observer.snapshot = SimpleNamespace(
        manifest={"gameId": str(UUID(int=6))}, frame=lambda *_args, **_kwargs: frame
    )
    observer.role, observer.u, observer.sources, observer.input_reader = (
        "VALIDATION",
        0.0,
        {source["sourceId"]: source},
        None,
    )
    photo = CorrectionControlPhoto(
        source["sourceId"], "group", "a" * 64, (nodes,), lambda: frame.rgb, full_geometry=False
    )
    engine = SimpleNamespace(settings=SimpleNamespace(board=board_preset()))
    observed = {}
    for name, found in (("base", found_base), ("candidate", found_candidate)):
        measured = evaluate_photo(
            photo.source_id, photo.group_id, [nodes], predictions(found), full_geometry=False
        )
        observed[name] = found, measured, engine
    return observer(photo, frame.rgb, observed)


def detection(nodes, quad=None):
    return SimpleNamespace(nodes=nodes, screen_quad=nodes[[0, 5, 23, 18]] if quad is None else quad)


def test_missing_prediction_is_missing_not_unknown_and_cannot_be_offset():
    _, _, _, nodes, _ = fixture()
    result = observer_result([detection(nodes)], [])
    summary = summarize_content([result])
    assert summary["unknown"] == 0 and summary["visible"] == 15
    assert summary["candidate"]["missing"] == 15 and summary["degradedInstances"] == 15
    assert summary["base"]["usableBoards"] == 1 and summary["candidate"]["usableBoards"] == 0
    assert not result["fullGeometry"]


def test_identical_hungarian_candidates_are_ambiguous_and_never_usable():
    _, _, _, nodes, _ = fixture()
    result = match_photo("p", "g", [nodes], [(nodes, True), (nodes.copy(), True)])
    assert ambiguous_matching([nodes], [nodes, nodes.copy()], result.matches) == {0}
    photo = observer_result([detection(nodes)], [detection(nodes), detection(nodes.copy())])
    assert photo["boards"][0]["candidate"]["matchAmbiguous"]
    assert not photo["boards"][0]["candidate"]["usable"]
    assert summarize_content([photo])["newMatchAmbiguities"] == 1


def test_unknown_and_optional_fragment_never_supply_preserved_evidence():
    _, _, _, nodes, _ = fixture()
    for state in ("unknown", "occluded", "out_of_frame"):
        photo = observer_result([detection(nodes)], [detection(nodes)], state=state)
        assert all("candidate" not in cell for cell in photo["boards"][0]["cells"])
        assert summarize_content([photo])["candidate"]["preserved"] == 0
        assert not photo["boards"][0]["candidate"]["usable"]


def test_neural_input_cut_does_not_falsify_final_production_crop():
    _, _, _, nodes, _ = fixture()
    input_quad = nodes[[0, 5, 23, 18]].copy()
    input_quad[:2, 1] += 12
    photo = observer_result([detection(nodes)], [detection(nodes, input_quad)])
    cells = photo["boards"][0]["cells"]
    assert all(c["candidate"]["finalContentState"] == "preserved" for c in cells)
    assert any(c["candidate"]["inputContentState"] == "clipped" for c in cells)
    assert photo["boards"][0]["candidate"]["inputEvidence"]["inputCropped"] is True


def test_input_proof_replays_pixels_and_rejects_self_rehashed_lie():
    frame, source, target, nodes, _ = fixture()
    engine = SimpleNamespace(settings=SimpleNamespace(board=board_preset()))
    proof = observe_input(frame, source, target, detection(nodes), engine, UUID(int=6))
    assert proof is not None and proof["inputCropped"] is False
    assert verify_input(frame, source, target, proof, UUID(int=6)) == proof
    changed = deepcopy(proof)
    changed["inputCropped"] = True
    changed["sha256"] = digest({k: v for k, v in changed.items() if k != "sha256"})
    with pytest.raises(ValueError, match="EVIDENCE_CHANGED"):
        verify_input(frame, source, target, changed, UUID(int=6))


def test_render_reference_hash_is_not_optional_when_present():
    _, _, target, _, _ = fixture()
    assert reference_context(target) is not None
    target["productionContentReference"]["sourceContext"]["renderConfiguration"][
        "paddingFraction"
    ] = 0
    with pytest.raises(ValueError, match="REFERENCE_INVALID"):
        reference_context(target)


def test_canonical_crop_offset_is_applied_once_and_input_intersects_real_pixels(tmp_path):
    from game_predictor_api.domain.grid_visibility_contract import CellContentReference
    from game_predictor_worker.images.normalization import CanonicalSourceLoader
    from game_predictor_worker.images.production_cell_input import _input
    from test_source_crop_frame import _write_managed

    path, sha, _pixels, attestation = _write_managed(tmp_path, 6)
    path.unlink()  # This test's own original; the real managed-crop loader now takes over.
    frame = CanonicalSourceLoader(allow_crop=True).load(path, expected_source_checksum_sha256=sha)
    box = attestation.crop_box
    assert real_source_support(frame) == [
        [box.left, box.top],
        [box.right, box.top],
        [box.right, box.bottom],
        [box.left, box.bottom],
    ]
    # A wide NN canvas contains the quad geometrically, but padding is not source evidence.
    quad = ((1.0, 1.0), (8.0, 1.0), (8.0, 8.0), (1.0, 8.0))
    ref = SimpleNamespace(cells=[CellContentReference(state="visible", quad=quad)] * 15)
    screen = np.asarray(
        [
            [0, 0],
            [frame.source.width, 0],
            [frame.source.width, frame.source.height],
            [0, frame.source.height],
        ]
    )
    result = _input(frame, ref, screen, board_preset(0.2), None)
    assert result["inputCropped"] is True
    assert result["sourceCanvasSha256"] == attestation.canvas_pixel_checksum_sha256
