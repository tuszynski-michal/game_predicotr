import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.managed_reprocess_evidence import (
    ManagedReprocessEvidenceError,
    resolve_managed_browser_selection,
    resolve_managed_page_source,
)
from game_predictor_api.application.page_geometry_overrides import PageGeometryOverrideService
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.image_sequence_canonical import (
    BrowserSequenceManifest,
    BrowserSequenceSource,
    ImageSequenceCanonicalService,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobType,
    create_job,
    request_job_cancellation,
)
from game_predictor_api.domain.neural_grid_proposal import (
    build_neural_source_binding,
    proposal_checksum_sha256,
)
from game_predictor_api.schemas.image_imports import BrowserPageGeometryOverrideCreate
from game_predictor_api.schemas.neural_grid_proposals import (
    NeuralSourceBindingPayload,
    NeuralSourceProposalPayload,
)
from PIL import Image
from test_jobs_domain import MemoryJobRepository
from test_managed_reprocess_evidence import (
    _completed_preflight,
    _terminal_import,
    _write_managed_manifest,
)
from test_neural_grid_proposal import proposal
from test_page_geometry_overrides import MemoryPageGeometryOverrideRepository


class ReceiptedRepository(MemoryPageGeometryOverrideRepository):
    def get_by_decision_checksum(self, **pins):
        return next(
            (
                value
                for value in self.values
                if value.game_id == pins["game_id"]
                and value.source_checksum_sha256 == pins["source_checksum_sha256"]
                and value.decision_checksum_sha256 == pins["decision_checksum_sha256"]
            ),
            None,
        )


def binding(value, assignments=None):
    return build_neural_source_binding(
        value,
        confirmed_range=AttestedSequenceRange(101, 105),
        assignments=assignments
        if assignments is not None
        else [
            {"detectionId": "a", "positionIndex": 0},
            {"detectionId": "b", "positionIndex": 1},
            {"detectionId": "c", "positionIndex": 3},
            {"detectionId": "d", "positionIndex": 4},
        ],
    )


def save(service, value, selected, expected=0):
    return service.save_neural_binding(
        game_id=UUID(value["gameId"]),
        source_checksum_sha256=value["sourceChecksumSha256"],
        image_width=value["sourceWidth"],
        image_height=value["sourceHeight"],
        proposal=value,
        binding=selected,
        actor="local-owner",
        expected_override_revision=expected,
    )


def test_binding_keeps_missing_middle_and_stores_no_fictitious_quads():
    value = proposal(4)
    repository = ReceiptedRepository()
    service = PageGeometryOverrideService(repository)
    result, created = save(service, value, binding(value))
    assert created and result.final_quads == ()
    assert result.neural_proposal_binding["missingPositionIndexes"] == [2]
    snapshot = service.snapshot(game_id=result.game_id)[result.source_checksum_sha256]
    assert snapshot["expectedBoardCount"] == 5
    assert snapshot["neuralProposalBinding"]["assignments"][-1]["positionIndex"] == 4


def test_response_lost_replay_after_later_revision_returns_original_receipt():
    value = proposal(4)
    repository = ReceiptedRepository()
    first_service = PageGeometryOverrideService(repository)
    selected = binding(value)
    first, _ = save(first_service, value, selected)
    second_binding = binding(value, [{"detectionId": "a", "positionIndex": 0}])
    second, _ = save(first_service, value, second_binding, 1)
    fresh_service = PageGeometryOverrideService(repository)
    replay, created = save(fresh_service, value, selected, 0)
    assert replay.id == first.id and not created and len(repository.values) == 2
    assert (
        repository.get_current(
            game_id=second.game_id,
            source_checksum_sha256=second.source_checksum_sha256,
        ).id
        == second.id
    )


def test_new_binding_rejects_stale_cas_and_wrong_source_before_append():
    value = proposal(4)
    repository = ReceiptedRepository()
    service = PageGeometryOverrideService(repository)
    save(service, value, binding(value))
    with pytest.raises(JobConflictError, match="changed"):
        save(service, value, binding(value, []), 0)
    tampered = deepcopy(binding(value))
    tampered["sourceChecksumSha256"] = "b" * 64
    with pytest.raises(JobConflictError):
        save(service, value, tampered, 1)
    assert len(repository.values) == 1


def test_typed_proposal_roundtrip_preserves_all_floating_points():
    value = proposal(4)
    assert (
        NeuralSourceProposalPayload.model_validate(value).model_dump(
            mode="json",
            by_alias=True,
        )
        == value
    )


def test_empty_quads_require_complete_pinned_neural_binding():
    value = proposal(4)
    body = {
        "gameId": value["gameId"],
        "sourceChecksumSha256": value["sourceChecksumSha256"],
        "imageWidth": 500,
        "imageHeight": 300,
        "actor": "local-owner",
        "finalQuads": [],
    }
    with pytest.raises(ValueError):
        BrowserPageGeometryOverrideCreate.model_validate(body)
    parsed = BrowserPageGeometryOverrideCreate.model_validate(
        {
            **body,
            "neuralProposalBinding": binding(value),
            "geometryPreflightJobId": str(uuid4()),
            "geometryManifestChecksumSha256": "d" * 64,
            "expectedOverrideRevision": 0,
        }
    )
    assert parsed.final_quads == []


@pytest.mark.parametrize("field", ["assignment", "missing", "range", "width"])
@pytest.mark.parametrize("bad", [True, "1"])
def test_neural_binding_dto_never_coerces_slot_or_range_identity(field, bad):
    selected = binding(proposal(4))
    if field == "assignment":
        selected["assignments"][0]["positionIndex"] = bad
    elif field == "missing":
        selected["missingPositionIndexes"][0] = bad
    elif field == "range":
        selected["confirmedRange"]["sequenceRangeStart"] = bad
    else:
        selected["sourceWidth"] = bad
    with pytest.raises(ValueError):
        NeuralSourceBindingPayload.model_validate(selected)


class CanonicalRepository:
    def __init__(self, pilot=True, maximum=500000):
        self.pilot, self.maximum = pilot, maximum

    def canonical_numbers(self, _game_id):
        return set()

    def canonical_source_checksums(self, _game_id):
        return {}

    def expected_layout_count(self, _game_id):
        return self.maximum

    def uses_neural_grid_pilot(self, _game_id):
        return self.pilot


def manifest(start=101, end=105):
    return BrowserSequenceManifest(
        (
            BrowserSequenceSource(
                0,
                f"seq_{start}-{end}.jpg",
                "00000001.jpg",
                1,
                "a" * 64,
                (start, end),
            ),
        ),
        (),
        "b" * 64,
    )


def test_neural_short_range_is_allowed_but_777_legacy_gate_is_unchanged():
    result = ImageSequenceCanonicalService(CanonicalRepository()).preflight(
        game_id=uuid4(),
        manifest=manifest(),
    )
    assert result.new_sequence_count == 5 and result.first_unresolved_sequence == 101
    with pytest.raises(JobConflictError) as error:
        ImageSequenceCanonicalService(CanonicalRepository(False)).preflight(
            game_id=uuid4(),
            manifest=manifest(),
        )
    assert error.value.code == "IMAGE_SEQUENCE_PREFLIGHT_SHORT_RANGE_NOT_TERMINAL"


def test_unbound_outbound_source_has_no_invented_canonical_position_or_silent_cap():
    service = ImageSequenceCanonicalService(CanonicalRepository())
    original = service.preflight(game_id=uuid4(), manifest=manifest(499996, 500004))
    assert original.last_unresolved_sequence == 500004
    assert "IMAGE_SEQUENCE_CONFIRMED_RANGE_REQUIRED" in original.warnings
    pending = service.preflight(
        game_id=uuid4(),
        manifest=manifest(499996, 500004),
        confirmed_ranges={"a" * 64: None},
    )
    assert pending.new_sequence_count == 0 and pending.first_unresolved_sequence is None
    confirmed = service.preflight(
        game_id=uuid4(),
        manifest=manifest(499996, 500004),
        confirmed_ranges={"a" * 64: (499996, 500000)},
    )
    assert confirmed.new_sequence_count == 5 and confirmed.last_unresolved_sequence == 500000


def test_confirmed_range_still_checks_game_boundary():
    with pytest.raises(JobConflictError) as error:
        ImageSequenceCanonicalService(CanonicalRepository()).preflight(
            game_id=uuid4(),
            manifest=manifest(499996, 500004),
            confirmed_ranges={"a" * 64: (499996, 500001)},
        )
    assert error.value.code == "IMAGE_SEQUENCE_PREFLIGHT_OUT_OF_BOUNDS"


@pytest.mark.parametrize("source_drift", [None, "before_decode", "during_decode"])
def test_source_binding_http_and_reopened_queue_keep_exact_proposal(
    tmp_path: Path, monkeypatch, source_drift
):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (500, 300)).save(source)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    value = proposal(4)
    value["sourceChecksumSha256"] = source_sha
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    selected = binding(value)
    game_id, upload_id = UUID(value["gameId"]), UUID(value["sourceSelectionId"])
    manifest = {
        "schemaVersion": 5,
        "version": "page-geometry-preflight-v13-neural-mumie-pilot",
        "gameId": str(game_id),
        "sourceSelectionId": str(upload_id),
        "sourceManifestChecksumSha256": "b" * 64,
        "neuralGridProposal": value["engineSnapshot"],
        "registeredSourceCount": 0,
        "reviewRequiredSourceCount": 1,
        "skippedHumanResolvedSourceCount": 0,
        "entries": {
            source_sha: {
                "sourceRelativePath": "seq_101-105.jpg",
                "imageWidth": 500,
                "imageHeight": 300,
                "status": "slot_binding_required",
                "reasonCode": "count_mismatch",
                "neuralProposal": value,
                "neuralProposalBinding": None,
            }
        },
    }
    relative = "data/page-geometry-manifests/test.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    content = json.dumps(manifest).encode()
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    job = _completed_preflight(
        game_id,
        selection_id=upload_id,
        source_manifest_sha256="b" * 64,
        geometry_checksum=checksum,
        geometry_relative_path=relative,
    )
    job = replace(
        job,
        input_payload={
            **job.input_payload,
            "preflight_policy_version": manifest["version"],
            "neural_grid_proposal": value["engineSnapshot"],
        },
    )
    jobs = SimpleNamespace(
        get_job=lambda _id: job,
        get_image_import_by_source_selection=lambda **_: None,
    )
    ready = SimpleNamespace(
        upload=SimpleNamespace(path=tmp_path),
        manifest=SimpleNamespace(
            files=[
                SimpleNamespace(
                    checksum_sha256=source_sha,
                    stored_file_name="source.jpg",
                    relative_path="seq_101-105.jpg",
                )
            ]
        ),
    )
    browser = SimpleNamespace(bind_ready_game=lambda *_: ready)
    repository = ReceiptedRepository()

    def new_client():
        app = FastAPI()
        app.include_router(
            create_image_imports_router(
                browser_selection_service_dependency=lambda: browser,
                job_service_dependency=lambda: jobs,
                iterative_import_service_dependency=lambda: None,
                page_geometry_override_service_dependency=lambda: PageGeometryOverrideService(
                    repository
                ),
                image_sequence_canonical_service_dependency=lambda: None,
                image_import_geometry_guard_service_dependency=lambda: None,
                artifact_root=tmp_path,
            )
        )
        return TestClient(app)

    client = new_client()
    endpoint = f"/admin/image-imports/browser-selections/{upload_id}/page-geometry-overrides"
    body = {
        "gameId": str(game_id),
        "sourceChecksumSha256": source_sha,
        "imageWidth": 500,
        "imageHeight": 300,
        "actor": "local-owner",
        "finalQuads": [],
        "neuralProposalBinding": selected,
        "geometryPreflightJobId": str(job.id),
        "geometryManifestChecksumSha256": checksum,
        "expectedOverrideRevision": 0,
    }
    if source_drift is not None:
        if source_drift == "before_decode":
            Image.new("RGB", (500, 300), "red").save(source)
        else:
            original_open = Image.open

            def drifting_open(*args, **kwargs):
                Image.new("RGB", (500, 300), "red").save(source)
                return original_open(*args, **kwargs)

            monkeypatch.setattr(Image, "open", drifting_open)
        with pytest.raises(JobConflictError) as caught:
            client.post(endpoint, json=body)
        assert caught.value.code == "NEURAL_SOURCE_PROPOSAL_STALE"
        assert repository.values == []
        return
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 201, saved.text
    assert saved.json()["neuralProposalBinding"]["missingPositionIndexes"] == [2]
    reopened = new_client()
    replay = reopened.post(endpoint, json=body)
    assert replay.status_code == 201 and not replay.json()["created"]
    assert replay.json()["id"] == saved.json()["id"]
    listing = reopened.get(
        f"/admin/image-imports/browser-selections/{upload_id}/geometry-preflights/{job.id}/review-sources",
        params={"game_id": str(game_id)},
    )
    assert listing.status_code == 200, listing.text
    entry = listing.json()["sources"][0]
    assert entry["neuralProposal"] == value
    assert entry["neuralProposalBinding"] == selected
    assert entry["existingOverrideRevision"] == 1 and entry["expectedBoardCount"] == 5
    assert entry["geometryOrigin"] == "manual_override"
    # A game-wide override of the same photo from another selection cannot attest
    # the range or proposal currently shown in this immutable source queue.
    other = deepcopy(value)
    other["sourceSelectionId"] = str(uuid4())
    other["proposalChecksumSha256"] = proposal_checksum_sha256(other)
    save(PageGeometryOverrideService(repository), other, binding(other), 1)
    refreshed = reopened.get(
        f"/admin/image-imports/browser-selections/{upload_id}/geometry-preflights/{job.id}/review-sources",
        params={"game_id": str(game_id)},
    )
    assert refreshed.status_code == 200, refreshed.text
    entry = refreshed.json()["sources"][0]
    assert entry["geometryOrigin"] == "automatic"
    assert entry["existingOverrideRevision"] == 2
    assert entry["neuralProposalBinding"] is None


def test_managed_source_survives_absent_staging_and_rejects_cross_game_and_byte_drift(tmp_path):
    game_id, selection_id = uuid4(), uuid4()
    content = b"immutable-original"
    source_sha = hashlib.sha256(content).hexdigest()
    source_job = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    _write_managed_manifest(tmp_path, source_job, source_checksum=source_sha)
    path = tmp_path / f"data/originals/{source_sha[:2]}/{source_sha}.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    pins = {
        "artifact_root": tmp_path,
        "game_id": game_id,
        "selection_id": selection_id,
        "source_checksum_sha256": source_sha,
    }
    recovered_path, logical_name = resolve_managed_page_source(source_job, **pins)
    assert recovered_path == path and logical_name == "seq_1-9.jpg"
    ready = resolve_managed_browser_selection(
        source_job,
        artifact_root=tmp_path,
        game_id=game_id,
        selection_id=selection_id,
    )
    assert ready.upload.game_id == game_id and ready.manifest.checksum_sha256 == "b" * 64
    assert ready.upload.path / ready.manifest.files[0].stored_file_name == path
    with pytest.raises(ManagedReprocessEvidenceError):
        resolve_managed_page_source(source_job, **{**pins, "game_id": uuid4()})
    path.write_bytes(b"changed")
    with pytest.raises(ManagedReprocessEvidenceError):
        resolve_managed_page_source(source_job, **pins)


def test_managed_source_selection_survives_new_inflight_run_and_new_service(tmp_path):
    value = proposal(4)
    game_id, selection_id = UUID(value["gameId"]), UUID(value["sourceSelectionId"])
    source = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    source = replace(
        source,
        input_payload={
            **source.input_payload,
            "neural_grid_proposal": value["engineSnapshot"],
        },
    )
    _write_managed_manifest(tmp_path, source, source_checksum="a" * 64)
    newer = create_job(
        JobType.IMPORT,
        game_id=game_id,
        input_payload={
            **source.input_payload,
            "managed_source_job_id": str(source.id),
        },
    )
    repository = MemoryJobRepository(game_id)
    repository.add_job(source)
    repository.add_job(newer)
    fresh = JobService(repository, artifact_root=tmp_path)
    found = fresh.get_managed_neural_import_by_source_selection(
        game_id=game_id,
        source_selection_id=selection_id,
    )
    assert found is not None and found.id == source.id
    assert (
        fresh.get_managed_neural_import_by_source_selection(
            game_id=game_id,
            source_selection_id=uuid4(),
        )
        is None
    )


def test_all_unbound_neural_sources_start_and_replay_without_invented_boards(tmp_path, monkeypatch):
    from game_predictor_api.application.image_imports import (
        BrowserImageUpload,
        BrowserReadySelection,
        ImageSelectionPurpose,
    )
    from game_predictor_api.application.jobs import _baseline_grid_profile_snapshot
    from test_managed_reprocess_evidence import NOW

    value = proposal(4)
    game_id, selection_id = UUID(value["gameId"]), UUID(value["sourceSelectionId"])
    source_sha = value["sourceChecksumSha256"]
    content = {
        "schemaVersion": 5,
        "version": "page-geometry-preflight-v13-neural-mumie-pilot",
        "gameId": str(game_id),
        "sourceSelectionId": str(selection_id),
        "sourceManifestChecksumSha256": "b" * 64,
        "neuralGridProposal": value["engineSnapshot"],
        "pageRegistrationProfile": {},
        "sourceCount": 1,
        "registeredSourceCount": 0,
        "reviewRequiredSourceCount": 1,
        "skippedHumanResolvedSourceCount": 0,
        "entries": {
            source_sha: {
                "sourceRelativePath": "seq_101-105.jpg",
                "imageWidth": 500,
                "imageHeight": 300,
                "status": "slot_binding_required",
                "reasonCode": "count_mismatch",
                "neuralProposal": value,
                "neuralProposalBinding": None,
            }
        },
    }
    raw = json.dumps(content).encode()
    checksum = hashlib.sha256(raw).hexdigest()
    relative = "data/page-geometry-manifests/source-only.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    job = _completed_preflight(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        geometry_checksum=checksum,
        geometry_relative_path=relative,
    )
    job = replace(
        job,
        input_payload={
            **job.input_payload,
            "preflight_policy_version": content["version"],
            "neural_grid_proposal": value["engineSnapshot"],
        },
        checkpoint_payload={**job.checkpoint_payload, "review_required_source_count": 1},
    )
    repository = MemoryJobRepository(game_id)
    repository.add_job(job)
    grid = SimpleNamespace(
        uses_neural_grid_pilot=lambda **_: True,
        resolve=lambda **_: _baseline_grid_profile_snapshot(),
    )
    monkeypatch.setattr(
        "game_predictor_api.application.jobs.ManagedGridEngineModelStore.require",
        lambda *_: None,
    )
    jobs = JobService(repository, artifact_root=tmp_path, grid_profile_snapshot_resolver=grid)
    assert (
        jobs.get_page_geometry_preflight_by_source_selection(
            game_id=game_id,
            source_selection_id=selection_id,
            source_manifest_sha256="b" * 64,
            geometry_engine_variant=None,
        )
        is not None
    ), job.input_payload
    ready = BrowserReadySelection(
        BrowserImageUpload(
            upload_id=selection_id,
            path=tmp_path,
            display_name="source-only",
            purpose=ImageSelectionPurpose.LAYOUT_IMPORT,
            game_id=game_id,
            expected_file_count=1,
            expected_total_bytes=1,
            created_at=NOW,
            uploaded_indexes={0},
            uploaded_files={},
        ),
        BrowserSequenceManifest(
            (
                BrowserSequenceSource(
                    0,
                    "seq_101-105.jpg",
                    "source.jpg",
                    1,
                    source_sha,
                    (101, 105),
                ),
            ),
            (),
            "b" * 64,
        ),
        NOW,
        None,
    )
    browser = SimpleNamespace(
        get_ready=lambda *_: ready,
        require_current_ready=lambda *_: ready,
        mark_in_use=lambda *_, **__: None,
    )
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            browser_selection_service_dependency=lambda: browser,
            job_service_dependency=lambda: jobs,
            iterative_import_service_dependency=lambda: None,
            page_geometry_override_service_dependency=lambda: None,
            image_sequence_canonical_service_dependency=lambda: ImageSequenceCanonicalService(
                CanonicalRepository()
            ),
            image_import_geometry_guard_service_dependency=lambda: None,
            artifact_root=tmp_path,
        )
    )
    client = TestClient(app)
    prefix = f"/admin/image-imports/browser-selections/{selection_id}"
    report = client.post(prefix + "/preflight", json={"gameId": str(game_id)})
    assert report.status_code == 200, report.text
    preflight = report.json()
    assert preflight["geometryPreflightJob"] is not None, preflight
    assert preflight["geometryPreflightArtifactReady"] is True, preflight
    assert preflight["newSequenceCount"] == 0, json.dumps(preflight)
    assert preflight["geometryPreflightArtifactReady"] is True
    command = {
        "gameId": str(game_id),
        "manifestChecksumSha256": "b" * 64,
        "preflightChecksumSha256": preflight["preflightChecksumSha256"],
        "geometryPreflightJobId": str(job.id),
        "geometryManifestChecksumSha256": checksum,
        "startMode": "rerun_current_models",
    }
    started = client.post(prefix + "/start", json=command)
    assert started.status_code == 201, started.text
    assert started.json()["created"] is True
    frozen = repository.get_job(UUID(started.json()["job"]["id"]))
    assert frozen.input_payload["neural_grid_proposal"] == value["engineSnapshot"]
    replay = client.post(prefix + "/start", json=command)
    assert replay.status_code == 201, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["job"]["id"] == started.json()["job"]["id"]
    assert len([job for job in repository.items.values() if job.job_type is JobType.IMPORT]) == 1
    # A new immutable binding descriptor must not race an active sibling run.
    content["entries"][source_sha]["neuralProposalBinding"] = binding(value)
    content["entries"][source_sha]["status"] = "review_required"
    updated_raw = json.dumps(content).encode()
    updated_sha = hashlib.sha256(updated_raw).hexdigest()
    updated_relative = "data/page-geometry-manifests/bound.json"
    (tmp_path / updated_relative).write_bytes(updated_raw)
    updated_job = _completed_preflight(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        geometry_checksum=updated_sha,
        geometry_relative_path=updated_relative,
    )
    updated_job = replace(
        updated_job,
        input_payload=job.input_payload,
        checkpoint_payload={**updated_job.checkpoint_payload, "review_required_source_count": 1},
    )
    repository.add_job(updated_job)
    updated_report = client.post(prefix + "/preflight", json={"gameId": str(game_id)})
    assert updated_report.status_code == 200, updated_report.text
    assert updated_report.json()["newSequenceCount"] == 5
    updated_command = {
        **command,
        "preflightChecksumSha256": updated_report.json()["preflightChecksumSha256"],
        "geometryPreflightJobId": str(updated_job.id),
        "geometryManifestChecksumSha256": updated_sha,
    }
    with pytest.raises(JobConflictError) as caught:
        client.post(prefix + "/start", json=updated_command)
    assert caught.value.code == "NEURAL_GRID_IMPORT_RUN_IN_PROGRESS"
    repository.save_job(request_job_cancellation(frozen))
    fresh_run = client.post(prefix + "/start", json=updated_command)
    assert fresh_run.status_code == 201, fresh_run.text
    assert fresh_run.json()["created"] is True
    assert fresh_run.json()["job"]["id"] != started.json()["job"]["id"]
    assert len([job for job in repository.items.values() if job.job_type is JobType.IMPORT]) == 2
