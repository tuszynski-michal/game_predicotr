import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.legacy_job_path_migration import (
    CONTRACT,
    apply,
    manifest_inventory,
    target_directory,
    validate_after_payloads,
    validate_current_row,
    verify_input_receipts,
    verify_worker,
)
from scripts.prepare_legacy_copy_retirement import verify_files


def plan_for(tmp_path: Path, *, different: bool = False) -> dict:
    source, destination, output = [tmp_path / p for p in ("source", "active", "receipt")]
    for root in (source, destination):
        folder = root / "imports/browser-selections/selection"
        folder.mkdir(parents=True)
        (folder / "photo.jpg").write_bytes(b"original")
    if different:
        (destination / "imports/browser-selections/selection/photo.jpg").write_bytes(b"different")
    assert verify_files(source, destination, output)["complete"]
    return {
        "contract": CONTRACT,
        "source": str(source),
        "destination": str(destination),
        "files_summary": str(output / "files-summary.json"),
        "jobs": [{"after": str(destination / "imports/browser-selections/selection")}],
    }


def test_input_receipt_is_usable_without_old_c_file(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    (Path(plan["source"]) / "imports/browser-selections/selection/photo.jpg").unlink()
    verify_input_receipts(plan)


def test_input_changed_after_preview_blocks_migration(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    (Path(plan["destination"]) / "imports/browser-selections/selection/photo.jpg").write_bytes(
        b"replacement"
    )
    with pytest.raises(ValueError, match="changed"):
        verify_input_receipts(plan)


def test_archive_is_not_mistaken_for_an_operational_source(tmp_path: Path) -> None:
    plan = plan_for(tmp_path, different=True)
    with pytest.raises(ValueError, match="recovery"):
        verify_input_receipts(plan)


def test_equal_size_and_restored_timestamp_cannot_hide_changed_input(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    path = Path(plan["destination"]) / "imports/browser-selections/selection/photo.jpg"
    before = path.stat()
    path.write_bytes(b"modified")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ValueError, match="checksum changed"):
        verify_input_receipts(plan)


def test_approval_is_bound_to_exact_preview_bytes(tmp_path: Path) -> None:
    path = tmp_path / "preview.json"
    path.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        apply(path, digest)


def test_unfinished_preservation_blocks_apply_before_connection(tmp_path: Path) -> None:
    path = tmp_path / "preview.json"
    path.write_text(
        json.dumps({"contract": CONTRACT, "blockers": ["incomplete"], "files_ready": False}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blockers"):
        apply(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_new_status_or_revision_blocks_atomic_update() -> None:
    before = {"id": "id", "status": "waiting_for_review", "updated_at": "before"}
    validate_current_row(before, dict(before))
    for changed in (
        {**before, "status": "processing"},
        {**before, "updated_at": "after"},
        {**before, "status": "created"},
    ):
        with pytest.raises(ValueError, match="changed"):
            validate_current_row(before, changed)


def test_windows_relocation_preserves_suffix_and_rejects_another_prefix() -> None:
    assert target_directory("C:/old/imports/abc", "c:\\old", "D:/new") == str(
        Path("D:/new/imports/abc")
    )
    with pytest.raises(ValueError):
        target_directory("C:/older/imports/abc", "C:/old", "D:/new")
    with pytest.raises(ValueError, match="traversal"):
        target_directory("C:/old/../outside", "C:/old", "D:/new")


def relocation_plan() -> dict:
    before = {
        "id": str(uuid4()),
        "game_id": str(uuid4()),
        "job_type": "import",
        "status": "waiting_for_review",
        "input_payload": {"source_directory": "C:/old/imports/abc", "keep": 7},
    }
    after = target_directory(before["input_payload"]["source_directory"], "C:/old", "D:/new")
    return {
        "source": "C:/old",
        "destination": "D:/new",
        "jobs": [
            {
                "before": before,
                "after": after,
                "after_payload": {
                    **before["input_payload"],
                    "source_directory": after,
                    "source_directory_relocation": {
                        "contract_version": 1,
                        "previous": "C:/old/imports/abc",
                        "current": after,
                    },
                },
            }
        ],
    }


def test_apply_rejects_unrelated_payload_change_even_with_recomputed_sha(tmp_path: Path) -> None:
    plan = relocation_plan()
    validate_after_payloads(plan)
    plan.update(contract=CONTRACT, blockers=[], files_ready=True)
    plan["jobs"][0]["after_payload"]["keep"] = 8
    path = tmp_path / "preview.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="permitted"):
        apply(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_missing_or_different_manifest_blocks_worker_verification(tmp_path: Path) -> None:
    plan = relocation_plan()
    root = tmp_path / "artifacts"
    root.mkdir()
    with pytest.raises(ValueError, match="missing"):
        manifest_inventory(plan["jobs"], root)
    path = root / "data/originals/manifests" / (plan["jobs"][0]["before"]["id"] + ".json")
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    plan.update(artifact_root=str(root), manifests=manifest_inventory(plan["jobs"], root))
    path.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="inventory changed"):
        verify_worker(plan)
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_worker(plan)
