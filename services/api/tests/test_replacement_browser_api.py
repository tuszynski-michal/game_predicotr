"""Actual browser requests preserve replacement identity across recovery and replay."""

import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageFolderSelectionService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_sequence_canonical import ImageSequenceCanonicalService
from game_predictor_api.domain.jobs import checkpoint_job, complete_job, start_job
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.source_replacement_admission import selected_replacement_files
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.main import create_app
from game_predictor_api.storage.source_replacement_restore import SourceReplacementRestore
from PIL import Image
from test_image_imports_api import NOW, _MutableBrowserCanonicalRepository
from test_jobs_domain import MemoryJobRepository
from test_source_replacement_admission import selection_fixture


def test_entry_working_and_restore_http_preserve_exact_crop_identity(tmp_path, monkeypatch):
    game, batch, entry, source, job, review, cell = (uuid4() for _ in range(7))
    calls = []

    def working(self, target_game, target_batch, target_entry):
        assert (target_game, target_batch, target_entry) == (game, batch, entry)
        return {
            "game_id": game,
            "batch_id": batch,
            "entry_id": entry,
            "revision": 4,
            "phase": "awaiting_review",
            "source_id": source,
            "import_job_id": job,
            "slots": [
                {
                    "sequence_number": 101,
                    "review_item_id": review,
                    "pending_geometry_id": None,
                    "status": "accepted",
                    "canonical": True,
                }
            ],
            "readability": [
                {
                    "cell_id": cell,
                    "review_item_id": review,
                    "sequence_number": 101,
                    "cell_index": 2,
                    "identity": "fresh-server-pixels",
                    "revision": 7,
                }
            ],
            "ready_to_restore": True,
        }

    def restore(self, target_game, command):
        assert target_game == game
        calls.append(command.model_dump(mode="json", by_alias=True))
        return {
            "game_id": game,
            "batch_id": batch,
            "entry_id": entry,
            "revision": 5,
            "phase": "restored",
            "source_id": source,
        }

    monkeypatch.setattr(SourceReplacementRestore, "working", working)
    monkeypatch.setattr(SourceReplacementRestore, "restore", restore)
    service = SimpleNamespace(replacement_plans=SimpleNamespace(session=None))
    app = create_app(
        ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)}),
        cleanup_service_dependency=lambda: service,
    )
    route = f"/api/v1/admin/games/{game}/board-sources/{batch}/entries/{entry}"
    command = {
        "batchId": str(batch),
        "entryId": str(entry),
        "expectedRevision": 4,
        "confirmed": True,
        "actor": "local-admin",
        "idempotencyKey": str(uuid4()),
        "readability": [
            {
                "cellId": str(cell),
                "identity": "fresh-server-pixels",
                "revision": 7,
                "readable": True,
            }
        ],
    }
    with TestClient(app) as api:
        response = api.get(route + "/working")
        assert response.status_code == 200, response.text
        assert response.json()["readability"][0]["identity"] == "fresh-server-pixels"
        assert response.json()["slots"][0]["reviewItemId"] == str(review)
        mismatch = api.post(route + "/restore", json={**command, "entryId": str(uuid4())})
        assert mismatch.status_code == 409, mismatch.text
        assert not calls
        false = api.post(route + "/restore", json={**command, "confirmed": False})
        assert false.status_code == 422, false.text
        result = api.post(route + "/restore", json=command)
        assert result.status_code == 200, result.text
        assert result.json()["phase"] == "restored"
        assert calls == [command]


class AdmissionRepository(MemoryJobRepository):
    closed = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preview_flags: list[bool] = []

    def validate_replacement_staging(
        self, *, game_id, selection, manifest, upload_id, preview=False
    ):
        self.preview_flags.append(preview)
        if self.closed:
            raise SourceReplacementError("SOURCE_REPLACEMENT_ADMISSION_CLOSED", "Already restored")
        assert game_id == self.game_id
        if selection is None:
            raise SourceReplacementError("SOURCE_REPLACEMENT_RESERVED", "Open replacement entry")
        files = selected_replacement_files(selection, game_id)
        assert len(manifest.files) == len(files) == 1
        assert manifest.files[0].checksum_sha256 == files[0]["checksumSha256"]
        assert manifest.files[0].sequence_range == (files[0]["rangeStart"], files[0]["rangeEnd"])
        return {
            "schemaVersion": "source-replacement-staging-v1",
            "gameId": str(game_id),
            "batchId": selection["request"]["batchId"],
            "uploadId": str(upload_id),
            "manifestChecksumSha256": manifest.checksum_sha256,
            "selectionDigest": digest(
                {"selection": selection, "manifest": manifest.checksum_sha256}
            ),
            "files": files,
        }


def test_replacement_browser_restart_full_geometry_start_and_exact_closed_replay(tmp_path: Path):
    game, selection = selection_fixture()
    image = BytesIO()
    Image.new("RGB", (32, 24), (100, 50, 20)).save(image, "JPEG")
    content = image.getvalue()
    selection["files"][0]["checksumSha256"] = hashlib.sha256(content).hexdigest()
    repository = AdmissionRepository(game)

    class Resolver:
        def resolve(self, *, game_id):
            assert game_id == game
            return bootstrap_symbol_model_snapshot()

        def resolve_unclassified_cold_start(self, *, game_id):
            return None

    jobs = JobService(
        repository, symbol_model_snapshot_resolver=Resolver(), artifact_root=tmp_path / "artifacts"
    )
    canonical = ImageSequenceCanonicalService(_MutableBrowserCanonicalRepository({101, 102}))

    def client():
        folders = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
        browser = BrowserImageSelectionService(
            folders, tmp_path / "imports", max_bytes=1024 * 1024, clock=lambda: NOW
        )
        return TestClient(
            create_app(
                ApiSettings.from_environment(
                    {
                        "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                        "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                    }
                ),
                job_service_dependency=lambda: jobs,
                image_folder_selection_service_dependency=lambda: folders,
                browser_image_selection_service_dependency=lambda: browser,
                image_sequence_canonical_service_dependency=lambda: canonical,
                page_geometry_override_service_dependency=lambda: None,
            )
        )

    root = "/api/v1/admin/image-imports/browser-selections"
    command = {
        "displayName": "seq_101-102.jpg",
        "gameId": str(game),
        "expectedFileCount": 1,
        "expectedTotalBytes": len(content),
        "idempotencyKey": str(uuid4()),
        "replacementSelection": selection,
    }
    with client() as api:
        created = api.post(root, json=command)
        assert created.status_code == 201, created.text
        upload = created.json()["uploadId"]
        response = api.put(
            f"{root}/{upload}/files/0",
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "seq_101-102.jpg",
            },
        )
        assert response.status_code == 200, response.text
    # New service instance, same durable key and partial upload. No browser memory is reused.
    with client() as api:
        replay = api.post(root, json=command)
        assert replay.status_code == 201, replay.text
        assert replay.json()["uploadId"] == upload
        conflict = api.post(root, json={**command, "expectedTotalBytes": len(content) + 1})
        assert conflict.status_code == 409
        assert api.post(f"{root}/{upload}/finalize").status_code == 200
    state_path = tmp_path / "imports" / "browser-selections" / upload / "_upload_state.json"
    assert state_path.resolve().is_relative_to(tmp_path.resolve())
    # Simulate state loss; the finalized manifest remains the durable recovery source.
    state_path.unlink()
    with client() as api:
        ready = api.get(root).json()
        assert ready[0]["replacementSelection"] == selection
        changed = deepcopy(selection)
        changed["files"][0]["operationId"] = "another"
        refused = api.post(
            f"{root}/{upload}/preflight",
            json={"gameId": str(game), "replacementSelection": changed},
        )
        assert refused.status_code == 409
        report_response = api.post(f"{root}/{upload}/preflight", json={"gameId": str(game)})
        assert report_response.status_code == 200, report_response.text
        # The report asks the repository for a read-only preview check (TASK-1190).
        assert repository.preview_flags[-1] is True
        report = report_response.json()
        assert report["replacementSelection"] == selection
        assert (
            report["newSequenceCount"],
            report["reusedSequenceCount"],
            report["skippedSourceCount"],
        ) == (2, 0, 0)
        geometry = api.post(
            f"{root}/{upload}/geometry-preflight",
            json={"gameId": str(game), "replacementSelection": selection},
        )
        assert geometry.status_code == 201, geometry.text
        job = repository.get_job(UUID(geometry.json()["job"]["id"]))
        assert "source_replacement" not in job.input_payload
        assert job.input_payload.get("canonical_sequence_numbers") in (None, [])
        manifest = {
            "gameId": str(game),
            "sourceSelectionId": upload,
            "sourceManifestChecksumSha256": report["manifestChecksumSha256"],
            "lateralPartialGeometry": job.input_payload["lateral_partial_geometry"],
            "entries": {},
            "registeredSourceCount": 1,
            "reviewRequiredSourceCount": 0,
            "skippedHumanResolvedSourceCount": 0,
        }
        data = json.dumps(manifest, sort_keys=True).encode()
        sha = hashlib.sha256(data).hexdigest()
        relative = f"data/page-geometry-manifests/{sha}.json"
        path = tmp_path / "artifacts" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        lease = uuid4()
        running = start_job(
            job,
            worker_version="test",
            worker_id="test",
            lease_token=lease,
            lease_expires_at=NOW + timedelta(minutes=5),
            started_at=NOW,
        )
        running = checkpoint_job(
            running,
            lease_token=lease,
            checkpoint_payload={
                "schema_version": 1,
                "complete": True,
                "geometry_manifest_checksum_sha256": sha,
                "geometry_manifest_relative_path": relative,
                "review_required_source_count": 0,
            },
            stage="page_geometry_manifest_ready",
            current=1,
            total=1,
            success_count=1,
            failure_count=0,
            review_count=0,
            updated_at=NOW + timedelta(seconds=1),
        )
        repository.add_job(
            complete_job(running, lease_token=lease, finished_at=NOW + timedelta(seconds=2))
        )
        start = {
            "gameId": str(game),
            "manifestChecksumSha256": report["manifestChecksumSha256"],
            "preflightChecksumSha256": report["preflightChecksumSha256"],
            "geometryPreflightJobId": str(job.id),
            "geometryManifestChecksumSha256": sha,
            "replacementSelection": selection,
        }
        started = api.post(f"{root}/{upload}/start", json=start)
        assert started.status_code == 201, started.text
        # Admission of the import keeps the exclusive ownership lock.
        assert repository.preview_flags and not any(repository.preview_flags[-2:]), (
            repository.preview_flags
        )
        result = started.json()
        imported = repository.get_job(UUID(result["job"]["id"]))
        pin = imported.input_payload["source_replacement"]
        assert pin["startReceipt"]["preflight"] == result["preflight"]
        assert imported.input_payload.get("canonical_sequence_numbers") in (None, [])
    repository.closed = True
    # Exact receipt replay must not access staging after retention moved it away.
    staged = tmp_path / "imports" / "browser-selections" / upload
    assert staged.resolve().is_relative_to(tmp_path.resolve())
    staged.rename(staged.with_name("removed-after-import"))
    with client() as api:
        replay = api.post(f"{root}/{upload}/start", json=start)
        assert replay.status_code == 201, replay.text
        assert replay.json()["created"] is False
        assert replay.json()["job"]["id"] == result["job"]["id"]
        assert replay.json()["preflight"] == result["preflight"]
        different = api.post(
            f"{root}/{upload}/start", json={**start, "preflightChecksumSha256": "f" * 64}
        )
        assert different.status_code == 409
        assert different.json()["code"] == "SOURCE_REPLACEMENT_START_CONFLICT"
        assert len(repository.items) == 2
