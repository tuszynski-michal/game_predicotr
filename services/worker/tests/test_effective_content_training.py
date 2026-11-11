"""Real CPU batches prove partial human geometry never becomes detector background."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from game_predictor_api.domain.grid_visibility_contract import (
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_worker.images.grid_training_data import ScreenGridBatches
from game_predictor_worker.training_core.grid_training import screen_grid_losses
from game_predictor_worker.training_core.neural_grid_network import BoardNetwork
from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset
from test_grid_content_mixed_batch import batch


class Detector(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.bn = torch.nn.BatchNorm2d(3)
        self.weight = torch.nn.Parameter(torch.ones(1))
        self.forwarded = []

    def forward(self, image):
        self.forwarded.append(image.detach().clone())
        values = self.bn(image).mean(dim=1, keepdim=True)[:, :, :2, :2] * self.weight
        return values, values.expand(-1, 8, -1, -1)


def test_partial_crop_learns_without_detector_forward_gradient_or_batchnorm():
    torch.set_num_threads(1)
    torch.manual_seed(1184)
    full_detector, mixed_detector = Detector(), Detector()
    mixed_detector.load_state_dict(full_detector.state_dict())
    board = BoardNetwork(width=8).train()
    data = batch(torch.rand(1, 3, 192, 320) * 255, mixed=True, two_photos=True, auxiliary=False)
    data["image"][0] = torch.rand_like(data["image"][0])
    data["image"][1] = 2000  # A partial photo must not affect detector statistics.
    for key in ("nodes", "visibility_targets"):
        data[key][0] = data[key][1]
    data["weights"].fill_(1)
    data["node_weights"].fill_(1)
    data["visibility_mask"].fill_(1)
    data["crop_skipped"].zero_()
    data["screen_eligible"] = torch.tensor([True, False])
    full = {key: value[:1].detach().clone() for key, value in data.items()}
    full.pop("screen_eligible")
    recipe = load_preset("A")[0]
    expected = screen_grid_losses(
        SimpleNamespace(screen=full_detector, board=deepcopy(board)), full, recipe, "cpu"
    )
    actual = screen_grid_losses(
        SimpleNamespace(screen=mixed_detector, board=board), data, recipe, "cpu"
    )
    expected["total"].backward()
    actual["total"].backward()
    assert mixed_detector.forwarded[0].shape[0] == 1
    torch.testing.assert_close(actual["heat"], expected["heat"], rtol=0, atol=0)
    torch.testing.assert_close(actual["offsets"], expected["offsets"], rtol=0, atol=0)
    for key, value in full_detector.named_buffers():
        torch.testing.assert_close(value, dict(mixed_detector.named_buffers())[key], rtol=0, atol=0)
    for key, value in full_detector.named_parameters():
        torch.testing.assert_close(
            value.grad, dict(mixed_detector.named_parameters())[key].grad, rtol=0, atol=0
        )
    assert torch.count_nonzero(data["crops"].grad[1]) > 0
    assert actual["valid_nodes"] == 48
    members = [{"sourceId": "full"}, {"sourceId": "partial"}]
    exposure = ScreenGridBatches.content_exposure_members(
        SimpleNamespace(exposure_members=lambda step: members), 0, data, actual
    )
    assert exposure == {"screen": [members[0]], "board": members}


class MixedPhotos:
    def __init__(self):
        self.snapshot = SimpleNamespace(manifest={"gameId": "game"}, manifest_sha256="a" * 64)
        self.rows = [
            (
                {
                    "screenEligible": full,
                    "sourceId": f"source-{index}",
                    "sourceIdentity": {"checksum_sha256": str(index) * 64},
                    "targets": [{"positionIndex": p} for p in range(9 if full else 1)],
                },
                None,
            )
            for index, full in enumerate((True, False))
        ]

    def __len__(self):
        return len(self.rows)

    def rgb(self, index):
        return np.full((100, 100, 3), 80 + index, np.uint8)

    def targets(self, index):
        nodes = np.array([[10 + col * 14, 10 + row * 24] for row in range(4) for col in range(6)])
        return [(nodes, 4)] * (9 if index == 0 else 1)


def test_real_batches_preserve_partial_weights_unknown_labels_and_restart_order():
    photos = MixedPhotos()
    options = dict(
        output_contract=GridOutputContract(supervision=visibility_supervision([])),
        content_experiment=True,
        partial_training=True,
    )
    sources = [
        ScreenGridBatches(photos, load_preset("A")[0], 2, 20261108, 1, **options) for _ in range(2)
    ]
    try:
        for source in sources:
            source.sampler = SimpleNamespace(indices=lambda step: [0, 1])
        left, right = [source._build(7) for source in sources]
        for key in left:
            torch.testing.assert_close(left[key], right[key], rtol=0, atol=0)
        assert left["screen_eligible"].tolist() == [True, False]
        assert left["weights"][1].tolist() == [4, 0, 0, 0]
        assert left["node_weights"][1, 0].sum() > 0
        assert left["visibility_mask"].sum() == 0  # Geometry is not a content label.
        exposed = sources[0].content_exposure_members(7, left, None)
        assert [r["sourceId"] for r in exposed["screen"]] == ["source-0"]
        assert {r["sourceId"] for r in exposed["board"]} == {"source-0", "source-1"}
        for source in sources:
            source.sampler = SimpleNamespace(indices=lambda step: [1, 1])
            assert source._indices(1199) == [0, 1]  # Still two photos, no added step.
    finally:
        for source in sources:
            source.close()


def test_partial_only_cannot_claim_full_detector_learning():
    photos = MixedPhotos()
    photos.rows[0][0]["screenEligible"] = False
    with pytest.raises(ValueError, match="FULL_TRAIN_REQUIRED"):
        ScreenGridBatches(
            photos,
            load_preset("A")[0],
            2,
            20261108,
            1,
            output_contract=GridOutputContract(supervision=visibility_supervision([])),
            content_experiment=True,
            partial_training=True,
        )


def test_frozen_partial_train_requires_explicit_pin_and_keeps_legacy_reader_strict(tmp_path):
    from game_predictor_worker.images.grid_cohort_dataset import (
        ContentTrainingDataset,
        GridBoardDataset,
        GridCohortDatasetError,
    )
    from game_predictor_worker.images.grid_training_data import CohortPhotos
    from test_grid_content_partial_selection import partial_snapshot

    fixture, snapshot, _ = partial_snapshot(tmp_path, train=True)
    with pytest.raises(GridCohortDatasetError, match="explicit geometry-only"):
        ContentTrainingDataset(snapshot).indexed()
    source = fixture.sources[-1]
    source["geometryOnlyTraining"] = True
    frozen = snapshot.manifest
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda doc: doc.update(
            **{key: frozen[key] for key in ("schemaVersion", "policyVersion", "photoSplit")}
        ),
    )
    with pytest.raises(GridCohortDatasetError, match="nine full targets"):
        GridBoardDataset(snapshot).indexed()
    photos = CohortPhotos(snapshot, "TRAIN", full_only=False, content_training=True)
    assert len(photos) == 1 and len(photos.targets(0)) == 1
    assert photos.targets(0)[0][1] == 4
    assert photos.rgb(0).shape == (48, 64, 3)
    assert photos.content_references(0) == [None]


@pytest.mark.parametrize(
    "contract",
    [
        None,
        {},
        {
            "classifier": {"cropPolicyVersion": "full-cell-v2"},
            "renderConfiguration": {"paddingFraction": 0.08},
        },
    ],
)
def test_new_full_cell_plan_rejects_missing_or_eight_percent_render_before_data_reads(contract):
    from game_predictor_worker.images.grid_content_experiment_data import require_render_preflight

    snapshot = SimpleNamespace(
        manifest={"photoSplit": {"contentSampling": {"evaluationContract": contract}}},
        sources=lambda: pytest.fail("render rejection must precede source reads"),
    )
    with pytest.raises(ValueError, match="CONTENT_FULL_CELL_RENDER_REQUIRED"):
        require_render_preflight([snapshot], "full-cell-v2")
