from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.application.jobs import ImageGeometryRolloutJobReference, JobService
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
from game_predictor_api.schemas.geometry_qualification import (
    AutomaticFrameGeometryProposalPayload,
    AutomaticPartialGeometryProposalPayload,
)
from game_predictor_api.schemas.image_imports import BrowserImageImportStart
from game_predictor_api.schemas.jobs import ImageGeometryRolloutJobSnapshotPayload
from game_predictor_worker.images import lateral_partial_contract as contract
from game_predictor_worker.images.lateral_partial_contract import (
    GeometryEngineVariant,
    LateralPartialGeometrySnapshot,
)
from game_predictor_worker.images.partial_grid_learning import (
    PartialGridPattern,
    PartialGridTrainingProfile,
)
from game_predictor_worker.images.pipeline_contract import GeometryPipelineRolloutSnapshot
from pydantic import ValidationError
from test_image_imports_api import _client
from test_jobs_domain import MemoryJobRepository

VARIANT = GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES


def test_reprocess_http_variant_reaches_closed_gate_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "LATERAL_PARTIAL_RELEASED", False)
    client, _game_id = _client(tmp_path, None)
    source = uuid4()
    with client:
        response = client.post(
            f"/api/v1/admin/image-imports/{source}/reprocess",
            params={"geometryEngineVariant": VARIANT.value},
            headers={"X-Admin-Target": f"image-import:{source}:reprocess"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED"


def test_per_run_snapshot_does_not_mutate_game_policy() -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    reference = ImageGeometryRolloutJobReference(
        geometry_mode="structured_lattice_v3", cell_asset_mode="virtual_default", revision=12
    )
    repository.image_geometry_rollout = reference
    service = JobService(repository)
    payload: dict[str, object] = {}
    fingerprint = service._pin_image_geometry_rollout(
        game_id=game_id,
        input_payload=payload,
        effective_fingerprint="a" * 64,
        symbol_model=bootstrap_symbol_model_snapshot(),
        geometry_engine_variant=VARIANT,
    )
    original = json.dumps(payload, sort_keys=True)
    repository.image_geometry_rollout = None
    snapshot = GeometryPipelineRolloutSnapshot.from_payload(payload["image_geometry_rollout"])
    assert snapshot.rollout_revision == 12
    assert snapshot.lateral_partial_geometry == LateralPartialGeometrySnapshot()
    assert fingerprint != "a" * 64
    assert json.dumps(payload, sort_keys=True) == original
    wire = ImageGeometryRolloutJobSnapshotPayload.model_validate(snapshot.to_payload())
    assert wire.model_dump(mode="json", by_alias=True, exclude_none=True) == snapshot.to_payload()
    assert not repository.items


def test_new_run_pins_separate_partial_training_profile() -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_lattice_v3",
        cell_asset_mode="virtual_default",
        revision=12,
    )
    profile = PartialGridTrainingProfile(
        (PartialGridPattern((0, 5, 10), sample_count=3, source_count=3),), 3
    )
    resolver = SimpleNamespace(partial_grid_training_profile=lambda **_: profile.to_payload())
    service = JobService(repository, page_geometry_override_snapshot_resolver=resolver)
    payload: dict[str, object] = {}
    service._pin_image_geometry_rollout(
        game_id=game_id,
        input_payload=payload,
        effective_fingerprint="a" * 64,
        symbol_model=bootstrap_symbol_model_snapshot(),
        geometry_engine_variant=VARIANT,
    )
    snapshot = GeometryPipelineRolloutSnapshot.from_payload(payload["image_geometry_rollout"])
    assert snapshot.lateral_partial_geometry is not None
    assert snapshot.lateral_partial_geometry.training_profile == profile
    assert snapshot.lateral_partial_geometry.to_payload()["schemaVersion"].endswith("v2")
    assert snapshot.lateral_partial_geometry.frame_support_review is False


def test_create_service_gate_precedes_files_and_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contract, "LATERAL_PARTIAL_RELEASED", False)
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    with pytest.raises(JobError) as error:
        JobService(repository).create_image_import_job(
            game_id=game_id,
            selection_id=uuid4(),
            source_directory=tmp_path / "not-created",
            source_display_name="v4",
            pipeline_fingerprint="a" * 64,
            geometry_engine_variant=VARIANT,
        )
    assert error.value.code == "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED"
    assert not repository.items


@pytest.mark.parametrize(
    "variant,status,code",
    [(VARIANT.value, 409, "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED"), ("unknown-v4", 422, None)],
)
def test_http_gate_precedes_staging_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    status: int,
    code: str | None,
) -> None:
    monkeypatch.setattr(contract, "LATERAL_PARTIAL_RELEASED", False)
    client, game_id = _client(tmp_path, None)
    with client:
        response = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{uuid4()}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": "a" * 64,
                "preflightChecksumSha256": "b" * 64,
                "geometryEngineVariant": variant,
            },
        )
    assert response.status_code == status
    if code:
        assert response.json()["code"] == code


def test_omitted_variant_does_not_serialize_into_old_request() -> None:
    request = BrowserImageImportStart(
        game_id=uuid4(), manifest_checksum_sha256="a" * 64, preflight_checksum_sha256="b" * 64
    )
    assert "geometryEngineVariant" not in request.model_dump(mode="json", by_alias=True)


def test_automatic_partial_provenance_is_not_a_human_decision() -> None:
    raw = {
        "version": "automatic-lateral-partial-proposal-v1",
        "origin": "automatic_proposal",
        "sourceChecksumSha256": "a" * 64,
        "positionIndex": 3,
        "policyVersion": "structured-lattice-v4-lateral-partial-v1",
        "policyChecksumSha256": LateralPartialGeometrySnapshot(
            frame_support_review=False
        ).checksum_sha256,
        "requiresManualConfirmation": True,
        "geometryQualification": {
            "version": "manual-geometry-qualification-v1",
            "completenessStatus": "pending_partial",
            "unavailableCellIndices": [0, 5, 10],
            "excludeFromGeometryTraining": True,
            "exclusionReason": "missing_pixels",
        },
    }
    result = AutomaticPartialGeometryProposalPayload.model_validate(raw)
    assert result.geometry_qualification.to_domain().completeness_status == "pending_partial"
    assert result.requires_manual_confirmation
    for key, value in [
        ("origin", "manual_override"),
        ("requiresManualConfirmation", False),
        ("policyChecksumSha256", "b" * 64),
    ]:
        with pytest.raises(ValidationError):
            AutomaticPartialGeometryProposalPayload.model_validate({**raw, key: value})


def test_learned_automatic_proposal_keeps_manual_confirmation() -> None:
    profile = PartialGridTrainingProfile(
        (PartialGridPattern((0, 5, 10), sample_count=3, source_count=3),), 3
    )
    policy = LateralPartialGeometrySnapshot(
        training_profile=profile, frame_support_review=False
    )
    raw = {
        "version": "automatic-lateral-partial-proposal-v2",
        "origin": "automatic_proposal",
        "sourceChecksumSha256": "a" * 64,
        "positionIndex": 3,
        "policyVersion": policy.policy_version,
        "policyChecksumSha256": policy.checksum_sha256,
        "trainingProfileChecksumSha256": profile.checksum_sha256,
        "requiresManualConfirmation": True,
        "geometryQualification": {
            "version": "manual-geometry-qualification-v2",
            "completenessStatus": "pending_partial",
            "unavailableCellIndices": [0, 5, 10],
            "excludeFromGeometryTraining": True,
            "includeInPartialGridTraining": False,
            "exclusionReason": "missing_pixels",
        },
    }
    proposal = AutomaticPartialGeometryProposalPayload.model_validate(raw)
    assert proposal.requires_manual_confirmation is True
    assert proposal.geometry_qualification.include_in_partial_grid_training is False
    for key, value in (
        ("version", "automatic-lateral-partial-proposal-v1"),
        ("policyVersion", "structured-lattice-v4-lateral-partial-v1"),
    ):
        with pytest.raises(ValidationError):
            AutomaticPartialGeometryProposalPayload.model_validate({**raw, key: value})


def test_frame_proposal_requires_complete_excluded_geometry() -> None:
    policy = LateralPartialGeometrySnapshot(frame_support_review=True)
    raw = {
        "version": "automatic-frame-geometry-proposal-v1",
        "origin": "automatic_proposal",
        "sourceChecksumSha256": "a" * 64,
        "positionIndex": 1,
        "policyVersion": policy.policy_version,
        "policyChecksumSha256": policy.checksum_sha256,
        "requiresManualConfirmation": True,
        "reasonCode": "board_frame_support_incomplete",
        "geometryQualification": {
            "version": "manual-geometry-qualification-v2",
            "completenessStatus": "complete",
            "unavailableCellIndices": [],
            "excludeFromGeometryTraining": True,
            "includeInPartialGridTraining": False,
            "exclusionReason": "manual_exclusion",
        },
    }
    assert AutomaticFrameGeometryProposalPayload.model_validate(raw).requires_manual_confirmation
    with pytest.raises(ValidationError):
        AutomaticFrameGeometryProposalPayload.model_validate(
            {
                **raw,
                "geometryQualification": {
                    **raw["geometryQualification"],
                    "excludeFromGeometryTraining": False,
                    "exclusionReason": None,
                },
            }
        )
