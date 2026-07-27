from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from shutil import copytree
from typing import Any, cast
from uuid import UUID

import pytest
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_worker.payouts.readiness import PayoutCompletenessFacts
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotError,
    ProductionSnapshotGenerator,
    ProductionSnapshotSpec,
    SnapshotArtifact,
    SnapshotArtifactError,
    SnapshotGameSelection,
    SnapshotGameSource,
    SnapshotLayout,
    SnapshotSymbol,
    validate_snapshot_artifact,
)
from game_predictor_worker.snapshots.integrity import file_sha256

DATASET_ID = UUID("10000000-0000-0000-0000-000000000001")
RULES_ID = UUID("20000000-0000-0000-0000-000000000001")
GAME_ID = UUID("30000000-0000-0000-0000-000000000001")
SELECTION = SnapshotGameSelection(DATASET_ID, RULES_ID, "payout-v2")
CREATED_AT = datetime(2026, 7, 27, 23, 15, tzinfo=UTC)
SOURCE = SnapshotGameSource(
    game_id=GAME_ID,
    game_code="alpha",
    game_name="Alpha Game",
    dataset_version_id=DATASET_ID,
    dataset_version=9,
    rules_version_id=RULES_ID,
    rules_version=7,
    algorithm_version="payout-v2",
    rows=1,
    columns=2,
    spin_cost=10,
    signature_cell_width=2,
    layout_count=3,
    symbols=(
        SnapshotSymbol(1, "S1", "Symbol 1", False, 0, None),
        SnapshotSymbol(2, "S2", "Symbol 2", False, 1, "symbols/s2.png"),
    ),
)
LAYOUTS = (
    SnapshotLayout(1, "0102", 0),
    SnapshotLayout(2, "0102", 20),
    SnapshotLayout(3, "0201", 5),
)


class FakeArtifactRepository:
    def __init__(
        self,
        *,
        layouts: tuple[SnapshotLayout, ...] = LAYOUTS,
    ) -> None:
        self.layouts = layouts

    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None:
        if (
            dataset_version_id,
            rules_version_id,
            algorithm_version,
        ) != (DATASET_ID, RULES_ID, "payout-v2"):
            return None
        return PayoutCompletenessFacts(
            dataset_version_id=DATASET_ID,
            rules_version_id=RULES_ID,
            algorithm_version="payout-v2",
            dataset_game_id=GAME_ID,
            rules_game_id=GAME_ID,
            dataset_status=DatasetVersionStatus.PUBLISHED,
            rules_status=RulesVersionStatus.PUBLISHED,
            dataset_rows=1,
            dataset_columns=2,
            rules_rows=1,
            rules_columns=2,
            layout_count=3,
            payout_count=3,
            missing_payout_count=0,
            missing_sequence_numbers=(),
            missing_sequences_truncated=False,
            missing_audit_count=0,
        )

    def load_snapshot_game(
        self,
        selection: SnapshotGameSelection,
    ) -> SnapshotGameSource | None:
        return SOURCE if selection == SELECTION else None

    def list_snapshot_layout_batch(
        self,
        selection: SnapshotGameSelection,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[SnapshotLayout]:
        if selection != SELECTION:
            return ()
        return tuple(
            layout
            for layout in self.layouts
            if layout.sequence_number > after_sequence_number
        )[:limit]


def _spec() -> ProductionSnapshotSpec:
    return ProductionSnapshotSpec(
        release_version="release-1.0",
        created_at=CREATED_AT,
        games=(SELECTION,),
    )


def _publish(
    tmp_path: Path,
    *,
    repository: FakeArtifactRepository | None = None,
) -> SnapshotArtifact:
    publisher = ProductionSnapshotArtifactPublisher(
        ProductionSnapshotGenerator(repository or FakeArtifactRepository()),
        tmp_path / "artifacts",
    )
    return publisher.publish(_spec())


def _read_manifest(artifact: SnapshotArtifact) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(artifact.manifest_path.read_text(encoding="utf-8")),
    )


def _write_manifest(
    artifact: SnapshotArtifact,
    value: dict[str, Any],
) -> None:
    artifact.manifest_path.write_bytes(
        (
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )


def _refresh_file_checksum(artifact: SnapshotArtifact) -> None:
    manifest = _read_manifest(artifact)
    manifest["snapshotFileSha256"] = file_sha256(artifact.database_path)
    _write_manifest(artifact, manifest)


def _mutate_database(
    artifact: SnapshotArtifact,
    statement: str,
    *,
    ignore_checks: bool = False,
) -> None:
    with closing(sqlite3.connect(artifact.database_path)) as connection:
        if ignore_checks:
            connection.execute("PRAGMA ignore_check_constraints = ON")
        with connection:
            connection.execute(statement)
    _refresh_file_checksum(artifact)


def test_publisher_creates_strict_manifest_and_idempotently_reuses_artifact(
    tmp_path: Path,
) -> None:
    artifact = _publish(tmp_path)
    database_bytes = artifact.database_path.read_bytes()
    manifest_bytes = artifact.manifest_path.read_bytes()
    database_mtime = artifact.database_path.stat().st_mtime_ns
    manifest = artifact.manifest

    retried = _publish(tmp_path)

    assert retried.directory == artifact.directory
    assert retried.database_path.read_bytes() == database_bytes
    assert retried.manifest_path.read_bytes() == manifest_bytes
    assert retried.database_path.stat().st_mtime_ns == database_mtime
    assert artifact.directory == (
        tmp_path
        / "artifacts"
        / "snapshots"
        / "release-1.0"
        / manifest.logical_content_sha256
    )
    assert {path.name for path in artifact.directory.iterdir()} == {
        "manifest.json",
        "snapshot.db",
    }
    assert manifest.manifest_version == 1
    assert manifest.snapshot_schema_version == 2
    assert manifest.game_count == 1
    assert manifest.symbol_count == 2
    assert manifest.layout_count == 3
    assert manifest.games[0].game_id == GAME_ID
    assert manifest.games[0].dataset_version_id == DATASET_ID
    assert manifest.games[0].rules_version_id == RULES_ID
    assert b"fixture" not in manifest_bytes
    assert b"golden" not in manifest_bytes


@pytest.mark.parametrize("field", ["games", "snapshotFileSha256"])
def test_manifest_missing_field_is_rejected(tmp_path: Path, field: str) -> None:
    artifact = _publish(tmp_path)
    manifest = _read_manifest(artifact)
    del manifest[field]
    _write_manifest(artifact, manifest)

    with pytest.raises(SnapshotArtifactError) as error:
        validate_snapshot_artifact(artifact.directory)

    assert error.value.code == "SNAPSHOT_MANIFEST_INVALID"


def test_manifest_extra_field_and_noncanonical_json_are_rejected(
    tmp_path: Path,
) -> None:
    artifact = _publish(tmp_path)
    manifest = _read_manifest(artifact)
    manifest["fixtureVersion"] = "forbidden"
    _write_manifest(artifact, manifest)

    with pytest.raises(SnapshotArtifactError) as extra_error:
        validate_snapshot_artifact(artifact.directory)
    assert extra_error.value.code == "SNAPSHOT_MANIFEST_INVALID"

    del manifest["fixtureVersion"]
    artifact.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True),
        encoding="utf-8",
    )
    with pytest.raises(SnapshotArtifactError) as canonical_error:
        validate_snapshot_artifact(artifact.directory)
    assert canonical_error.value.code == "SNAPSHOT_MANIFEST_NOT_CANONICAL"


def test_wrong_directory_and_extra_file_are_rejected(tmp_path: Path) -> None:
    artifact = _publish(tmp_path)
    wrong_directory = tmp_path / "wrong"
    copytree(artifact.directory, wrong_directory)

    with pytest.raises(SnapshotArtifactError) as layout_error:
        validate_snapshot_artifact(wrong_directory)
    assert layout_error.value.code == "SNAPSHOT_ARTIFACT_LAYOUT_INVALID"

    (artifact.directory / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(SnapshotArtifactError) as extra_error:
        validate_snapshot_artifact(artifact.directory)
    assert extra_error.value.code == "SNAPSHOT_ARTIFACT_LAYOUT_INVALID"


def test_changed_database_file_is_rejected_by_physical_checksum(
    tmp_path: Path,
) -> None:
    artifact = _publish(tmp_path)
    with artifact.database_path.open("ab") as file:
        file.write(b"changed")

    with pytest.raises(SnapshotArtifactError) as error:
        validate_snapshot_artifact(artifact.directory)

    assert error.value.code == "SNAPSHOT_FILE_CHECKSUM_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("PRAGMA user_version = 99", "SNAPSHOT_SCHEMA_UNSUPPORTED"),
        (
            "DROP INDEX idx_layouts_game_signature",
            "SNAPSHOT_SIGNATURE_INDEX_INVALID",
        ),
        ("CREATE TABLE forbidden_admin_data(id INTEGER)", "SNAPSHOT_SCHEMA_INVALID"),
    ],
)
def test_schema_and_index_corruption_are_rejected(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    artifact = _publish(tmp_path)
    _mutate_database(artifact, mutation)

    with pytest.raises(SnapshotArtifactError) as error:
        validate_snapshot_artifact(artifact.directory)

    assert error.value.code == code


def test_metadata_and_manifest_count_mismatch_are_rejected(tmp_path: Path) -> None:
    artifact = _publish(tmp_path)
    _mutate_database(
        artifact,
        "UPDATE metadata SET value = '2' WHERE key = 'layout_count'",
    )

    with pytest.raises(SnapshotArtifactError) as metadata_error:
        validate_snapshot_artifact(artifact.directory)
    assert metadata_error.value.code == "SNAPSHOT_METADATA_MISMATCH"

    artifact = _publish(tmp_path / "second")
    manifest = _read_manifest(artifact)
    manifest["layoutCount"] = 2
    manifest["games"][0]["layoutCount"] = 2
    _write_manifest(artifact, manifest)
    with pytest.raises(SnapshotArtifactError) as count_error:
        validate_snapshot_artifact(artifact.directory)
    assert count_error.value.code == "SNAPSHOT_METADATA_MISMATCH"


def test_sequence_gap_and_foreign_key_violation_are_rejected(tmp_path: Path) -> None:
    artifact = _publish(tmp_path)
    _mutate_database(
        artifact,
        "DELETE FROM layouts WHERE game_id = 1 AND sequence_number = 2",
    )

    with pytest.raises(SnapshotArtifactError) as sequence_error:
        validate_snapshot_artifact(artifact.directory)
    assert sequence_error.value.code == "SNAPSHOT_SEQUENCE_INVALID"

    artifact = _publish(tmp_path / "second")
    _mutate_database(
        artifact,
        "UPDATE layouts SET game_id = 999 WHERE game_id = 1 AND sequence_number = 1",
    )
    with pytest.raises(SnapshotArtifactError) as foreign_key_error:
        validate_snapshot_artifact(artifact.directory)
    assert foreign_key_error.value.code == "SNAPSHOT_FOREIGN_KEY_INVALID"


@pytest.mark.parametrize(
    ("signature", "code"),
    [
        ("9901", "SNAPSHOT_SYMBOL_REFERENCE_INVALID"),
        ("01", "SNAPSHOT_SIGNATURE_INVALID"),
    ],
)
def test_unknown_symbol_and_malformed_signature_are_rejected(
    tmp_path: Path,
    signature: str,
    code: str,
) -> None:
    artifact = _publish(tmp_path)
    _mutate_database(
        artifact,
        f"UPDATE layouts SET signature = '{signature}' "
        "WHERE game_id = 1 AND sequence_number = 3",
    )

    with pytest.raises(SnapshotArtifactError) as error:
        validate_snapshot_artifact(artifact.directory)

    assert error.value.code == code


def test_invalid_payout_and_valid_content_change_are_rejected(tmp_path: Path) -> None:
    artifact = _publish(tmp_path)
    _mutate_database(
        artifact,
        "UPDATE layouts SET payout = -1 WHERE game_id = 1 AND sequence_number = 3",
        ignore_checks=True,
    )
    with pytest.raises(SnapshotArtifactError) as payout_error:
        validate_snapshot_artifact(artifact.directory)
    assert payout_error.value.code in {
        "SNAPSHOT_DATABASE_CORRUPT",
        "SNAPSHOT_LAYOUT_INVALID",
    }

    artifact = _publish(tmp_path / "second")
    _mutate_database(
        artifact,
        "UPDATE layouts SET payout = payout + 1 "
        "WHERE game_id = 1 AND sequence_number = 3",
    )
    with pytest.raises(SnapshotArtifactError) as logical_error:
        validate_snapshot_artifact(artifact.directory)
    assert logical_error.value.code == "SNAPSHOT_LOGICAL_CHECKSUM_MISMATCH"


def test_corrupt_existing_artifact_causes_collision_without_overwrite(
    tmp_path: Path,
) -> None:
    artifact = _publish(tmp_path)
    with artifact.database_path.open("ab") as file:
        file.write(b"corrupt")
    corrupt_bytes = artifact.database_path.read_bytes()
    publisher = ProductionSnapshotArtifactPublisher(
        ProductionSnapshotGenerator(FakeArtifactRepository()),
        tmp_path / "artifacts",
    )

    with pytest.raises(SnapshotArtifactError) as error:
        publisher.publish(_spec())

    assert error.value.code == "SNAPSHOT_ARTIFACT_COLLISION"
    assert artifact.database_path.read_bytes() == corrupt_bytes


def test_generation_failure_cleans_staging_and_publishes_no_artifact(
    tmp_path: Path,
) -> None:
    repository = FakeArtifactRepository(
        layouts=(
            SnapshotLayout(1, "0102", 0),
            SnapshotLayout(3, "0201", 5),
        )
    )
    publisher = ProductionSnapshotArtifactPublisher(
        ProductionSnapshotGenerator(repository),
        tmp_path / "artifacts",
    )

    with pytest.raises(ProductionSnapshotError):
        publisher.publish(_spec())

    artifact_root = tmp_path / "artifacts"
    assert not (artifact_root / "snapshots").exists()
    assert list((artifact_root / ".staging").iterdir()) == []
