import json
from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_worker.semi_automatic_selection.v7_draft_catalog import (
    draft_folder,
    pin_draft_folder,
    read_draft,
)
from game_predictor_worker.semi_automatic_selection.v7_draft_export import publish_draft
from test_v7_selection_delivery_api import delivery_fixture


def prepared(tmp_path, reason="estimated_equal_partition"):
    client, repository, service, run, manifest = delivery_fixture(tmp_path)
    target = tmp_path / "output" / "propozycje"
    target.mkdir(parents=True)
    pin_draft_folder(
        service._artifact_root, target, run_id=str(run.id), fingerprint=manifest.source_fingerprint
    )
    publish_draft(
        manifest.source_root,
        target,
        manifest.sources[0],
        start=1,
        end=9,
        metadata={
            "runId": str(run.id),
            "state": "estimated",
            "reason": reason,
        },
    )
    return client, repository, service, run, manifest, target


@pytest.mark.parametrize(
    "reason",
    [
        "estimated_equal_partition",
        "estimated_partition",
        "estimated_prefix",
        "estimated_nearest_available",
    ],
)
def test_range_page_adds_draft_without_changing_sql_status_and_owner_wins(tmp_path, reason):
    client, repository, service, run, _, target = prepared(tmp_path, reason)
    data = client.get(f"/admin/semi-automatic-image-selections/{run.id}/ranges").json()["items"][0]
    assert data["status"] == "missing" and data["v7Review"]["candidate"] is None
    assert data["v7Review"]["draft"]["sourceIndex"] == 0
    assert data["v7Review"]["draft"]["estimated"] is True
    assert data["v7Review"]["draft"]["reason"] == reason
    assert repository.ranges[(run.id, 0)].v7_review.get("draft") is None
    row = repository.ranges[(run.id, 0)]
    repository.ranges[(run.id, 0)] = replace(row, v7_output_owner_operation_id=uuid4())
    assert (
        service.list_ranges(run.id, after_expected_index=None, limit=1)[0].v7_review.get("draft")
        is None
    )
    (target / "seq_1-9.jpg").unlink()
    assert read_draft(target, run_id=str(run.id), start=1, end=9, source_count=1) is None


def test_output_and_child_folder_reopen_after_new_service_and_cancel(tmp_path):
    from game_predictor_api.application.semi_automatic_image_selections import (
        SemiAutomaticImageSelectionService,
    )

    client, repository, service, run, manifest, target = prepared(tmp_path)
    for directory in [target.parent, target]:
        service._output_picker = lambda selected=directory: selected
        data = client.post("/admin/semi-automatic-image-selections/review-folder").json()
        assert data == {"status": "selected", "runId": str(run.id)}
    assert (
        draft_folder(
            service._artifact_root, run_id=str(run.id), fingerprint=manifest.source_fingerprint
        )
        == target
    )
    fresh = SemiAutomaticImageSelectionService(
        repository,
        object(),
        enabled=True,
        artifact_root=service._artifact_root,
        output_picker=lambda: target,
    )
    assert fresh.open_review_folder().id == run.id
    service._output_picker = lambda: None
    assert client.post("/admin/semi-automatic-image-selections/review-folder").json() == {
        "status": "cancelled",
        "runId": None,
    }


def test_source_folder_matches_full_path_and_refuses_ambiguity(tmp_path):
    _, repository, service, run, manifest, _ = prepared(tmp_path)
    repository.find_v7_runs_by_source_name = lambda name: (run,)
    service._output_picker = lambda: manifest.source_root
    assert service.open_review_folder().id == run.id
    repository.find_v7_runs_by_source_name = lambda name: (run, run)
    with pytest.raises(Exception, match="unique"):
        service.open_review_folder()


def test_source_folder_prefers_unique_non_cancelled_run_without_removing_old_attempt(tmp_path):
    from game_predictor_api.domain.semi_automatic_image_selections import (
        SemiAutomaticSelectionRunStatus,
    )

    _, repository, service, run, manifest, _ = prepared(tmp_path)
    cancelled = replace(run, id=uuid4(), status=SemiAutomaticSelectionRunStatus.CANCELLED)
    attempts = (cancelled, run)
    repository.find_v7_runs_by_source_name = lambda name: attempts
    service._output_picker = lambda: manifest.source_root
    assert service.open_review_folder().id == run.id
    assert attempts[0] == cancelled
    repository.find_v7_runs_by_source_name = lambda name: (cancelled,)
    assert service.open_review_folder().id == cancelled.id


def test_foreign_marker_source_checksum_and_large_sidecar_fail_explicitly(tmp_path):
    client, _, service, run, _, target = prepared(tmp_path)
    service._output_picker = lambda: target
    marker = target.parent / "_selekcja_v7.json"
    payload = json.loads(marker.read_text())
    payload["sourceFingerprint"] = "f" * 64
    marker.write_text(json.dumps(payload))
    assert client.post("/admin/semi-automatic-image-selections/review-folder").status_code == 409
    sidecar = target / "seq_1-9.jpg.json"
    payload = json.loads(sidecar.read_text())
    payload["sha256"] = "a" * 64
    sidecar.write_text(json.dumps(payload))
    response = client.get(f"/admin/semi-automatic-image-selections/{run.id}/ranges")
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "V7_DRAFT_CATALOG_INVALID"
    )
    sidecar.write_bytes(b" " * 65537)
    assert client.get(f"/admin/semi-automatic-image-selections/{run.id}/ranges").status_code == 409
