"""Bounded metadata validation and deployment seam tests without operator data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.source_recording_groups import RecordingError, recording_sha256
from game_predictor_api.storage import source_recording_lab_import as importer
from sqlalchemy.engine import Connection


def _write(path: Path, value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _fixture(root: Path, *, photo_only: bool = False, role: str = "Reels") -> tuple[Path, str]:
    identity, recording, source = "a" * 64, "b" * 64, "c" * 64
    group = (
        importer.lab_photo_group_id(identity, source)
        if photo_only
        else importer.lab_group_id(identity, recording)
    )
    provider = {
        "schemaVersion": "recording-ancestor-provider-v1",
        "ancestor": {
            "versionId": str(uuid4()),
            "manifestSha256": "d" * 64,
            "snapshotId": "owned-fixture",
            "cohortId": None,
            "publicationEvidenceSha256": None,
            "historicalReportSha256": None,
            "evaluation": None,
        },
        "complete": not photo_only,
        "recordingIdentityAvailable": not photo_only,
        "recordingGroups": [{"groupId": str(group), "role": role}],
    }
    page = {
        "schemaVersion": "recording-lab-import-page-v1",
        "sources": [
            {
                "sourceRefSha256": source,
                "recordingRefSha256": None if photo_only else recording,
                "byteSha256": "e" * 64,
                "pixelSha256": "f" * 64,
                "pixelAlgorithm": "rgb-uint8-v1",
                "width": 10,
                "height": 20,
            }
        ],
    }
    provider_sha = _write(root / "provider.json", provider)
    descriptor_sha = _write(root / "descriptor.json", {"schemaVersion": "fixture-descriptor"})
    split_sha = _write(root / "split.json", {"schemaVersion": "fixture-split"})
    page_sha = _write(root / "page.json", page)
    manifest = {
        "schemaVersion": "recording-lab-import-v1",
        "providerIdentitySha256": identity,
        "provider": {"path": "provider.json", "sha256": provider_sha},
        "descriptor": {"path": "descriptor.json", "sha256": descriptor_sha},
        "split": {"path": "split.json", "sha256": split_sha},
        "groups": []
        if photo_only
        else [
            {
                "recordingRefSha256": recording,
                "expectedSources": 1,
                "role": role,
                "independenceConfirmed": True,
            }
        ],
        "pages": [{"path": "page.json", "sha256": page_sha}],
    }
    path = root / "manifest.json"
    return path, _write(path, manifest)


class _Result:
    def __init__(self, value: Any):
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def one_or_none(self) -> Any:
        return self.value

    def mappings(self) -> _Result:
        return self

    def all(self) -> Any:
        return self.value


class _Connection:
    def __init__(self, *values: Any):
        self.values = iter(values)
        self.statements: list[tuple[str, Any]] = []

    def execute(self, statement: object, parameters: object = None) -> _Result:
        self.statements.append((str(statement), parameters))
        return _Result(next(self.values))

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append((statement, None))


def test_manifest_binds_actual_metadata_and_stable_opaque_identities(tmp_path: Path) -> None:
    path, checksum = _fixture(tmp_path)
    manifest = importer.read_lab_import_manifest(path, checksum)
    assert manifest.provider_sha256 == recording_sha256(manifest.provider)
    assert importer.read_lab_import_page(manifest, 0)[0]["width"] == 10
    group = importer.lab_group_id("a" * 64, "b" * 64)
    assert group == UUID(manifest.provider["recordingGroups"][0]["groupId"])
    assert group != importer.lab_photo_group_id("a" * 64, "b" * 64)
    assert group != importer.lab_group_id("c" * 64, "b" * 64)


def test_photo_only_metadata_preserves_incomplete_provider_and_source_identity(
    tmp_path: Path,
) -> None:
    path, checksum = _fixture(tmp_path, photo_only=True)
    manifest = importer.read_lab_import_manifest(path, checksum)
    assert manifest.groups == ()
    assert manifest.provider["recordingIdentityAvailable"] is False
    assert importer.read_lab_import_page(manifest, 0)[0]["recordingRefSha256"] is None


def test_train_is_a_valid_distinct_ancestor_role(tmp_path: Path) -> None:
    path, checksum = _fixture(tmp_path, role="TRAIN")
    manifest = importer.read_lab_import_manifest(path, checksum)
    assert manifest.groups[0].role == "TRAIN"


@pytest.mark.parametrize(
    "field,value", [("expectedSources", True), ("independenceConfirmed", "yes"), ("role", [])]
)
def test_group_declaration_is_typed_and_explicit(tmp_path: Path, field: str, value: object) -> None:
    path, _ = _fixture(tmp_path)
    payload = json.loads(path.read_bytes())
    payload["groups"][0][field] = value
    with pytest.raises(RecordingError):
        importer.read_lab_import_manifest(path, _write(path, payload))


def test_import_never_reads_unpinned_descriptor_metadata(tmp_path: Path) -> None:
    path, checksum = _fixture(tmp_path)
    (tmp_path / "descriptor.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RecordingError, match="checksum"):
        importer.read_lab_import_manifest(path, checksum)


def test_metadata_paths_cannot_escape_manifest_directory(tmp_path: Path) -> None:
    path, _ = _fixture(tmp_path)
    payload = json.loads(path.read_bytes())
    payload["descriptor"]["path"] = "../foreign.json"
    with pytest.raises(RecordingError, match="escapes"):
        importer.read_lab_import_manifest(path, _write(path, payload))


def test_unknown_manifest_fields_are_rejected_before_deployment(tmp_path: Path) -> None:
    path, _ = _fixture(tmp_path)
    payload = json.loads(path.read_bytes())
    payload["actor"] = "untrusted"
    with pytest.raises(RecordingError, match="Unknown"):
        importer.read_lab_import_manifest(path, _write(path, payload))


@pytest.mark.parametrize("mutation", ["oversize", "path", "missing_role", "bool_width"])
def test_pages_are_closed_bounded_and_role_mapped(tmp_path: Path, mutation: str) -> None:
    path, checksum = _fixture(tmp_path, photo_only=True)
    manifest = importer.read_lab_import_manifest(path, checksum)
    page = json.loads((tmp_path / "page.json").read_bytes())
    if mutation == "oversize":
        page["sources"] *= 201
    elif mutation == "path":
        page["sources"][0]["path"] = "private-photo.png"
    elif mutation == "bool_width":
        page["sources"][0]["width"] = True
    else:
        manifest = replace(manifest, provider={**manifest.provider, "recordingGroups": []})
    page_sha = _write(tmp_path / "page.json", page)
    manifest = replace(manifest, pages=(importer.MetadataPin(tmp_path / "page.json", page_sha),))
    with pytest.raises(RecordingError):
        importer.read_lab_import_page(manifest, 0)


def test_page_hash_drift_is_rejected(tmp_path: Path) -> None:
    path, checksum = _fixture(tmp_path)
    manifest = importer.read_lab_import_manifest(path, checksum)
    (tmp_path / "page.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RecordingError, match="checksum"):
        importer.read_lab_import_page(manifest, 0)


@pytest.mark.parametrize(
    "role,kind,answers", [("TRAIN", "use", (False, False)), ("Reels", "holdout", (False,))]
)
def test_trusted_train_use_is_never_written_as_holdout(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    kind: str,
    answers: tuple[bool, ...],
) -> None:
    events = []
    monkeypatch.setattr(
        importer,
        "_event",
        lambda connection, event_kind, groups, payload: events.append((event_kind, payload)),
    )
    importer._install_role(cast(Connection, _Connection(*answers)), uuid4(), role, "a" * 64, {})
    assert events == [(kind, {"role": role, "providerSha256": "a" * 64, "ancestor": {}})]
    assert "reportId" not in events[0][1] and "resolutionId" not in events[0][1]


def test_retained_holdout_cannot_become_train(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "_event", lambda *args: pytest.fail("TRAIN must not be recorded"))
    with pytest.raises(RecordingError) as caught:
        importer._install_role(cast(Connection, _Connection(True)), uuid4(), "TRAIN", "a" * 64, {})
    assert caught.value.code == "RECORDING_PROTECTED"


def test_exact_command_replay_and_changed_body_conflict() -> None:
    body, receipt = {"manifestSha256": "a" * 64}, {"eventId": str(uuid4())}
    connection = _Connection((recording_sha256(body), receipt))
    assert (
        importer._replay(cast(Connection, connection), "b" * 64, "lab_import_page", uuid4(), body)
        == receipt
    )
    connection = _Connection(("c" * 64, receipt))
    with pytest.raises(RecordingError) as caught:
        importer._replay(cast(Connection, connection), "b" * 64, "lab_import_page", uuid4(), body)
    assert caught.value.code == "RECORDING_COMMAND_CONFLICT"


def test_final_replay_does_not_read_page_files_or_recheck_membership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, checksum = _fixture(tmp_path)
    manifest = importer.read_lab_import_manifest(path, checksum)
    events = []
    monkeypatch.setattr(importer, "_verify_pins", lambda manifest: events.append("pins"))
    monkeypatch.setattr(importer, "_guard", lambda connection: events.append("locks"))
    monkeypatch.setattr(importer, "_replay", lambda *args: {"eventId": "exact-receipt"})
    monkeypatch.setattr(importer, "read_lab_import_page", lambda *args: pytest.fail("No page I/O"))
    monkeypatch.setattr(importer, "_membership_counts", lambda *args: pytest.fail("Replay first"))
    assert importer.finalize_lab_import(cast(Connection, object()), manifest, uuid4()) == {
        "eventId": "exact-receipt"
    }
    assert events == ["pins", "locks"]


@pytest.mark.parametrize(
    "change,code",
    [
        ("page_count", "RECORDING_LAB_PAGE_MISSING"),
        ("unique_count", "RECORDING_LAB_IMPORT_INVALID"),
        ("actual_count", "RECORDING_LAB_MEMBERSHIP_CONFLICT"),
    ],
)
def test_final_sql_summary_rejects_missing_duplicate_or_extra_members(
    tmp_path: Path,
    change: str,
    code: str,
) -> None:
    path, checksum = _fixture(tmp_path)
    manifest = importer.read_lab_import_manifest(path, checksum)
    row = {
        "group_id": uuid4(),
        "member_count": 1,
        "matched_count": 1,
        "actual_count": 1,
        "page_count": 1,
        "source_count": 1,
        "unique_count": 1,
        change: 0,
    }
    with pytest.raises(RecordingError) as caught:
        importer._membership_counts(cast(Connection, _Connection([row])), manifest)
    assert caught.value.code == code


def test_direct_main_install_rejects_provider_with_arbitrary_ancestor_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, checksum = _fixture(tmp_path)
    provider = importer.read_lab_import_manifest(path, checksum).provider
    provider["ancestor"]["path"] = "never-store-this"
    monkeypatch.setattr(importer, "_guard", lambda connection: None)
    with pytest.raises(RecordingError):
        importer.install_provider_proof(
            cast(Connection, object()), provider, recording_sha256(provider)
        )
