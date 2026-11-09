"""Versioned crops preserve history and bind the pixels of a manual decision."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.application.virtual_grid_geometry import bind_manual_crop_policy
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.symbol_model_snapshots import (
    FULL_CELL_CROP_POLICY_VERSION as FULL,
)
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    bootstrap_symbol_model_snapshot,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import _require_same_context
from test_virtual_grid_geometry import (
    RecordingSymbolPredictor,
    _cell_corners,
    _corners,
    _deferred_source,
    _fixture,
)


def test_legacy_snapshot_has_the_prechange_golden_fingerprint():
    # Golden read from the unchanged snapshot module in HEAD1181797c, not
    # recalculated from the implementation under test.
    old = bootstrap_symbol_model_snapshot()
    assert (
        old.inference_fingerprint
        == "7adba5cf42e10d85979ff607fe7a5d3d62401f61d9cb823cbba39ecd29390153"
    )
    payload = old.to_payload()
    assert "cropPolicyVersion" not in payload
    assert SymbolModelJobSnapshot.from_payload(payload).to_payload() == payload
    assert old.crop_padding_fraction == 0.08
    new = old.with_full_cell_crops()
    assert new.crop_padding_fraction == 0
    assert new.to_payload()["cropPolicyVersion"] == FULL
    assert new.inference_fingerprint != old.inference_fingerprint
    assert replace(new, crop_policy_version=None) == old
    assert SymbolModelJobSnapshot.from_payload(new.to_payload()) == new


@pytest.mark.parametrize("policy", ["future", "", False, 0.08, ["full-cell-v2"]])
def test_unknown_snapshot_policy_cannot_be_used_or_silently_downgraded(policy):
    payload = bootstrap_symbol_model_snapshot().to_payload()
    payload["cropPolicyVersion"] = policy
    with pytest.raises(ValueError):
        SymbolModelJobSnapshot.from_payload(payload)


def test_policy_is_part_of_the_human_command_and_rejects_an_unknown_value():
    values = dict(
        corners=_corners(),
        corrected_by="owner",
        expected_geometry_revision=0,
        expected_resolution_revision=0,
    )
    old = validate_image_review_geometry_command(**values)
    full = validate_image_review_geometry_command(**values, crop_policy_version=FULL)
    assert old.command_sha256 != full.command_sha256
    with pytest.raises(ImageReviewConflictError, match="unsupported"):
        validate_image_review_geometry_command(**values, crop_policy_version="future")


def test_full_policy_preserves_the_cas_guard_and_never_mutates_stored_context(tmp_path):
    _, stored = _fixture(tmp_path)
    stored = replace(
        stored, render_configuration=replace(stored.render_configuration, padding_fraction=0.08)
    )
    prepared = bind_manual_crop_policy(stored, FULL)
    _require_same_context(stored, prepared)
    assert stored.render_configuration.padding_fraction == 0.08
    assert prepared.render_configuration.padding_fraction == 0
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError

    with pytest.raises(ImageGridReviewError, match="changed"):
        _require_same_context(replace(stored, geometry_revision=1), prepared)


def test_pending_preview_prediction_and_save_bind_identical_full_cells(tmp_path):
    class Predictor(RecordingSymbolPredictor):
        def predict_rendered_cells(self, cells, snapshot):
            assert snapshot.crop_padding_fraction == 0
            assert snapshot.crop_policy_version == FULL
            return super().predict_rendered_cells(cells, snapshot)

    predictor = Predictor()
    service, repo, contexts = _deferred_source(tmp_path, predictor=predictor)
    context = contexts[5]
    context = replace(
        context,
        render_configuration=replace(
            context.render_configuration, padding_fraction=0.08, output_width=64, output_height=64
        ),
    )
    repo.contexts[context.target_id] = context
    values = dict(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        pending_geometry_id=context.pending_geometry_id,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
        crop_policy_version=FULL,
    )
    preview = service.preview_pending_slot(**values)
    assert len(preview.cells) == 15
    service.preview_pending_slot_symbols(**values)
    saved = service.save_pending_slot(
        **values, idempotency_key=uuid4(), actor="owner", created_at=datetime.now(UTC)
    )
    prepared = repo.saved[-1]
    assert prepared.context.render_configuration.padding_fraction == 0
    assert prepared.context.manual_crop_policy_version == FULL
    assert prepared.virtual_render_spec["cropPolicyVersion"] == FULL
    assert prepared.virtual_render_spec["symbolModelSnapshot"]["cropPolicyVersion"] == FULL
    assert (
        SymbolModelJobSnapshot.from_payload(
            prepared.context.pending_symbol_model
        ).crop_padding_fraction
        == 0
    )
    assert [cell.crop_checksum_sha256 for cell in preview.cells] == [
        cell.crop_checksum_sha256 for cell in saved.revisions[0].cells
    ]
    assert context.render_configuration.padding_fraction == 0.08
    assert (
        SymbolModelJobSnapshot.from_payload(context.pending_symbol_model).crop_padding_fraction
        == 0.08
    )
    assert len(predictor.calls) == 2


def test_snapshot_tampering_with_policy_does_not_reuse_the_legacy_fingerprint():
    payload = bootstrap_symbol_model_snapshot().to_payload()
    payload["cropPolicyVersion"] = FULL
    with pytest.raises(ValueError, match="fingerprint changed"):
        SymbolModelJobSnapshot.from_payload(payload)


def test_legacy_proposal_payload_omits_only_the_new_optional_policy():
    from game_predictor_api.schemas.grid_geometry_proposals import ProposalAcceptCommand

    old = dict(
        idempotencyKey=str(uuid4()),
        expectedProposalRevision=1,
        expectedGeometryRevision=2,
        expectedResolutionRevision=0,
        mode="model",
        originalCandidateSha256="a" * 64,
        geometry=None,
    )
    assert ProposalAcceptCommand.model_validate(old).to_command_payload() == old
    new = ProposalAcceptCommand.model_validate({**old, "cropPolicyVersion": FULL})
    assert new.to_command_payload() == {**old, "cropPolicyVersion": FULL}


@pytest.mark.parametrize("full", [False, True])
def test_a_pinned_job_does_not_borrow_the_crop_of_another_manual_revision(full):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )
    from game_predictor_worker.images.pipeline_contract import (
        CellAssetRolloutMode,
        GeometryPipelineRolloutSnapshot,
        GeometryRolloutMode,
    )
    from game_predictor_worker.images.virtual_cell_extraction import VirtualCellRenderer

    model = bootstrap_symbol_model_snapshot()
    if full:
        model = model.with_full_cell_crops()
    rollout = GeometryPipelineRolloutSnapshot(
        geometry_mode=GeometryRolloutMode.STRUCTURED_DEFAULT,
        cell_asset_mode=CellAssetRolloutMode.VIRTUAL_DEFAULT,
        rollout_revision=0,
        geometry_engine_version="test",
        virtual_renderer_version=VirtualCellRenderer.version,
        preprocessing_version="rgb-v1",
    )
    job = SimpleNamespace(
        input_payload={
            "symbol_model": model.to_payload(),
            "image_geometry_rollout": rollout.to_payload(),
        }
    )
    session = Mock()
    configuration = SqlAlchemyVirtualGridGeometryRepository(session)._pending_render_configuration(
        source_image_id=uuid4(), import_job_id=uuid4(), job=job
    )
    assert configuration.padding_fraction == (0 if full else 0.08)
    assert configuration.output_width == model.input_size
    session.scalar.assert_not_called()


def test_legacy_job_without_rollout_keeps_its_pinned_inset_when_a_neighbor_has_full_cells():
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import Mock

    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )
    from test_virtual_grid_geometry_repository import _RENDER_SPEC

    spec = deepcopy(_RENDER_SPEC)
    spec["configuration"]["paddingFraction"] = 0.0
    session = Mock()
    session.scalar.return_value = spec
    model = bootstrap_symbol_model_snapshot()
    configuration = SqlAlchemyVirtualGridGeometryRepository(session)._pending_render_configuration(
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        job=SimpleNamespace(input_payload={"symbol_model": model.to_payload()}),
    )
    assert configuration.padding_fraction == 0.08
    assert configuration.output_width == spec["configuration"]["outputWidth"]
