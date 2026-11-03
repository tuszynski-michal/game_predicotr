from uuid import uuid4

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.symbol_readability import create_symbol_readability_router
from game_predictor_api.domain.symbol_readability import (
    GAME_ID,
    confirmed_for_replacement,
    crop_identity,
    identity_is_current,
)
from game_predictor_worker.symbols import readability_workflow as workflow


def snapshot() -> dict:
    source = str(uuid4())
    return dict(
        cell_id=str(uuid4()),
        source_id=source,
        source_sha256="a" * 64,
        geometry_revision=3,
        board_geometry_revision=3,
        source_geometry_revision_id=source,
        board_source_geometry_revision_id=source,
        crop_sample_id="b" * 64,
        crop_checksum_sha256="c" * 64,
        render_spec_checksum_sha256="d" * 64,
        rendered_pixel_checksum_sha256="e" * 64,
        render_identity_v2_sha256="f" * 64,
        board_status="accepted",
    )


@pytest.mark.parametrize(
    "field",
    [
        "source_id",
        "source_sha256",
        "geometry_revision",
        "source_geometry_revision_id",
        "crop_sample_id",
        "crop_checksum_sha256",
        "render_spec_checksum_sha256",
        "rendered_pixel_checksum_sha256",
        "render_identity_v2_sha256",
    ],
)
def test_pixel_provenance_drift_invalidates_each_label(field: str) -> None:
    before = snapshot()
    changed = {**before, field: 4 if field == "geometry_revision" else "different"}
    assert identity_is_current(before, before)
    assert not identity_is_current(before, changed)
    assert crop_identity(before) != crop_identity(changed)


@pytest.mark.parametrize("field", ["board_geometry_revision", "board_source_geometry_revision_id"])
def test_current_board_identity_is_checked_separately_from_cell_projection(field: str) -> None:
    before = snapshot()
    assert not identity_is_current(before, {**before, field: 99})
    assert not identity_is_current(before, None)
    assert not identity_is_current(before, {**before, "board_status": "rejected"})
    assert identity_is_current(
        before, {**before, "revision": 99, "assigned_symbol_id": str(uuid4())}
    )


def test_overlap_readable_does_not_qualify_replacement() -> None:
    assert not confirmed_for_replacement("readable", current=True)
    assert not confirmed_for_replacement("unreadable", current=False)
    assert confirmed_for_replacement("unreadable", current=True)


def test_source_with_135_cells_uses_two_bounded_feature_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def extract(model: object, crops: list) -> np.ndarray:
        calls.append(len(crops))
        assert len(crops) <= 128
        return np.asarray([[value] for value in crops])

    monkeypatch.setattr(workflow, "extract_features", extract)
    assert workflow.extract_source_features(object(), list(range(135))).ravel().tolist() == list(
        range(135)
    )
    assert calls == [128, 7]


def test_late_artifact_writer_cannot_replace_the_accepted_content_address(tmp_path) -> None:
    import json

    from game_predictor_worker.filesystem import long_path_aware

    game, model = uuid4(), uuid4()
    accepted = dict(fingerprint="a" * 64, weights=[1, 2])
    late = dict(fingerprint="b" * 64, weights=[3, 4])
    accepted_path = workflow.publish_quality_artifact(tmp_path, game, model, accepted)
    late_path = workflow.publish_quality_artifact(tmp_path, game, model, late)
    assert accepted_path != late_path
    assert json.loads(long_path_aware(tmp_path / accepted_path).read_text()) == accepted
    assert json.loads(long_path_aware(tmp_path / late_path).read_text()) == late
    assert not list((tmp_path / accepted_path).parent.glob("*.tmp"))


def test_confident_overlay_uses_pinned_classifier_not_historical_import_confidence() -> None:
    import torch
    from game_predictor_worker.symbols.readability_confidence import (
        PROVENANCE,
        PinnedCalibration,
        pinned_top1,
    )

    class Classifier(torch.nn.Module):
        def forward(self, value):
            probabilities = torch.tensor([0.2] + [0.8 / 7] * 7, dtype=torch.float32)
            return probabilities.log().repeat(len(value), 1)

    values = pinned_top1(
        Classifier(), [np.zeros((64, 64, 3), dtype=np.uint8)], PinnedCalibration(1.0)
    )
    item = dict(
        cell_id=str(uuid4()),
        source_id=str(uuid4()),
        sequence_number=1,
        historical_unreadable=False,
        state="unreadable",
        overlap=True,
        sharp=True,
        similar_readable=False,
        sample_kind="pilot",
        identity="i",
        snapshot=dict(
            source_sha256="s",
            rendered_pixel_checksum_sha256="r",
            import_job_id="import",
            symbol_class="test",
            prediction_confidence=0.99,
            quality_top1=values[0],
            confidence_provenance=PROVENANCE,
        ),
    )
    assert workflow.sample_from_item(item).top1 == pytest.approx(0.2)
    assert workflow.sample_from_item(item).top1 < 0.95
    item["snapshot"]["confidence_provenance"] = None
    assert workflow.sample_from_item(item).top1 is None
    assert pinned_top1(Classifier(), [np.zeros((64, 64, 3), dtype=np.uint8)], None) == [None]


def test_pinned_calibration_checks_manifest_dataset_and_its_bytes(tmp_path, monkeypatch) -> None:
    import hashlib
    import json

    from game_predictor_api.domain.symbol_readability import CHECKPOINT_SHA, DATASET_SHA
    from game_predictor_worker.symbols import readability_confidence as confidence
    from game_predictor_worker.symbols.readability_features import FrozenBase, ReadabilityError

    calibration = json.dumps(dict(version=confidence.CALIBRATION_VERSION, temperature=0.5)).encode()
    calibration_sha = hashlib.sha256(calibration).hexdigest()
    manifest = json.dumps(
        dict(
            datasetManifestSha256=DATASET_SHA,
            classCodes=["a", "b"],
            artifacts=dict(
                checkpoint=dict(sha256=CHECKPOINT_SHA), calibration=dict(sha256=calibration_sha)
            ),
        )
    ).encode()
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    monkeypatch.setattr(confidence, "MANIFEST_SHA", manifest_sha)
    monkeypatch.setattr(confidence, "CALIBRATION_SHA", calibration_sha)
    root = tmp_path / confidence.ROOT
    (root / "manifests").mkdir(parents=True)
    (root / "calibration").mkdir()
    (root / "manifests" / f"{manifest_sha}.json").write_bytes(manifest)
    path = root / "calibration" / f"{calibration_sha}.json"
    path.write_bytes(calibration)
    base = FrozenBase(CHECKPOINT_SHA, DATASET_SHA, "split", ("a", "b"), ())
    assert confidence.load_pinned_calibration(tmp_path, base).temperature == 0.5
    path.write_bytes(calibration + b" ")
    with pytest.raises(ReadabilityError) as changed:
        confidence.load_pinned_calibration(tmp_path, base)
    assert changed.value.code == "READABILITY_INPUT_DRIFT"


def test_http_contract_allows_pilot_without_detector_and_preserves_label_identity() -> None:
    received = []
    run_id = uuid4()
    result = dict(
        id=run_id,
        kind="pilot",
        status="created",
        revision=0,
        job_id=uuid4(),
        model_id=None,
        inventory_fingerprint=None,
        item_count=0,
        processed_count=0,
        error_code=None,
        error_message=None,
    )

    class Repository:
        def start(self, game, request):
            received.append((game, request.model_dump()))
            return result

        def label(self, game, run, request):
            received.append((game, run, request.model_dump()))
            return result

    app = FastAPI()
    app.include_router(create_symbol_readability_router(lambda: Repository()))
    client = TestClient(app)
    base = f"/admin/games/{GAME_ID}/symbol-cell-reviews/readability"
    key = str(uuid4())
    assert (
        client.post(base + "/runs", json={"kind": "pilot", "idempotencyKey": key}).status_code
        == 200
    )
    assert received[0][1]["model_id"] is None
    target = {"cellId": str(uuid4()), "expectedIdentity": "a" * 64, "expectedRevision": 3}
    body = {
        "idempotencyKey": str(uuid4()),
        "targets": [target],
        "state": "readable",
        "overlap": True,
    }
    response = client.post(base + f"/runs/{run_id}/labels", json=body)
    assert response.status_code == 200, response.text
    assert received[1][2]["state"] == "readable" and received[1][2]["overlap"] is True
    assert received[1][2]["targets"][0]["expected_revision"] == 3
    assert (
        client.post(base + f"/runs/{run_id}/labels", json={**body, "targets": []}).status_code
        == 422
    )
    assert (
        client.post(base + f"/runs/{run_id}/labels", json={**body, "state": "approved"}).status_code
        == 422
    )
