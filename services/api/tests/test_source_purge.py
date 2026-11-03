from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.cleanup import ManagedCleanupArtifactStore
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from test_cleanup_api import FakeCleanupService


def test_only_source_owned_thumbnail_pairs_enter_purge(tmp_path):
    import json

    game, cell, other = uuid4(), uuid4(), uuid4()
    cache = tmp_path / "data/working/virtual-cell-preview-cache-v1"
    cache.mkdir(parents=True)
    for key, owners in (("a", [cell]), ("b", [cell, other]), ("c", [other])):
        (cache / (key * 64 + ".json")).write_text(
            json.dumps(
                {"gameId": str(game), "tiles": [{"cellReviewId": str(owner)} for owner in owners]}
            )
        )
        (cache / (key * 64 + ".webp")).write_bytes(b"thumbnail")
    store = ManagedCleanupArtifactStore(tmp_path)
    paths, shared = store.source_preview_paths(game, [cell])
    assert len(paths) == 2 and shared == 1
    assert all("a" * 64 in path for path in paths)
    store.quarantine("f" * 64, paths)
    assert store.finalize("f" * 64)
    assert not (cache / ("a" * 64 + ".webp")).exists()
    assert (cache / ("b" * 64 + ".webp")).exists()
    assert (cache / ("c" * 64 + ".webp")).exists()


def test_recovery_keeps_foreign_replacement_and_reports_no_freed_bytes(tmp_path):
    @contextmanager
    def guard(key, paths):
        yield False

    store = ManagedCleanupArtifactStore(tmp_path, operation_retention_guard=guard)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"old")
    purge = {"quarantineKey": "a" * 64, "fileProof": store.file_proof(("photo.jpg",))}
    store.quarantine(purge["quarantineKey"], ("photo.jpg",))
    store.restore(purge["quarantineKey"])
    photo.write_bytes(b"foreign")
    assert store.purge_status(purge) == "recovery_required"
    assert store.recover_purge(purge) == "recovery_required"
    assert photo.read_bytes() == b"foreign"
    photo.write_bytes(b"old")
    assert store.recover_purge(purge) == "finalized"
    assert not photo.exists()


def test_http_physical_preview_and_confirmed_execute_preserve_command():
    service = FakeCleanupService()
    batch, entry, source, key = (uuid4() for _ in range(4))
    request = dict(
        mode="replace_delete_source",
        action="purge",
        batchId=str(batch),
        entryId=str(entry),
        expectedRevision=1,
    )

    class Physical:
        def preview(self, game, command):
            assert command.model_dump(mode="json", by_alias=True) == request
            return dict(
                game_id=game,
                batch_id=batch,
                entry_id=entry,
                revision=1,
                preview_token="a" * 64,
                source_ids=[source],
                sequence_numbers=[31, 32],
                file_count=3,
                missing_file_count=0,
                shared_file_count=1,
                bytes_to_delete=99,
                retained_metadata={"source_tombstones": 1},
                record_counts={"boards": 2},
            )

        def execute(self, game, command):
            assert command.idempotency_key == key and command.confirmed
            return dict(
                game_id=game,
                batch_id=batch,
                entry_id=entry,
                revision=2,
                phase="gap_open",
                scope_digest="b" * 64,
                purge=dict(
                    operationType="source_replacement_purge",
                    sourceIds=[source],
                    fileCount=3,
                    bytesToDelete=99,
                    sharedFileCount=1,
                    missingFileCount=0,
                    retainedMetadata={"source_tombstones": 1},
                    command=command,
                    fileStatus="pending",
                ),
            )

    service.physical_sources = Physical()
    with TestClient(
        create_app(ApiSettings.from_environment({}), cleanup_service_dependency=lambda: service)
    ) as client:
        prefix = f"/api/v1/admin/games/{service.game_id}"
        response = client.post(prefix + "/board-source-cleanup-preview", json=request)
        assert response.status_code == 200, response.text
        assert response.json()["sequenceNumbers"] == [31, 32]
        command = dict(request, previewToken="a" * 64, idempotencyKey=str(key), confirmed=True)
        response = client.request("DELETE", prefix + "/board-sources", json=command)
        assert response.status_code == 200, response.text
        assert response.json()["purge"]["command"] == command
        assert response.json()["purge"]["deletedBytes"] == 0
