from __future__ import annotations

from pathlib import Path

import pytest
from game_predictor_worker.snapshot import (
    SnapshotValidationError,
    generate_snapshot,
    validate_snapshot,
)


def test_generate_and_validate_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "m1-spike.db"
    manifest_path = tmp_path / "manifest.json"

    generated = generate_snapshot(database_path, manifest_path)
    validated = validate_snapshot(database_path, manifest_path)

    assert validated == generated
    assert generated["recordCount"] == 3
    assert len(generated["snapshotFileSha256"]) == 64
    assert len(generated["logicalContentSha256"]) == 64


def test_generation_is_byte_deterministic(tmp_path: Path) -> None:
    database_path = tmp_path / "m1-spike.db"
    manifest_path = tmp_path / "manifest.json"

    first = generate_snapshot(database_path, manifest_path)
    first_bytes = database_path.read_bytes()
    second = generate_snapshot(database_path, manifest_path)

    assert database_path.read_bytes() == first_bytes
    assert second == first


def test_validation_rejects_changed_file(tmp_path: Path) -> None:
    database_path = tmp_path / "m1-spike.db"
    manifest_path = tmp_path / "manifest.json"
    generate_snapshot(database_path, manifest_path)

    with database_path.open("ab") as file:
        file.write(b"changed")

    with pytest.raises(SnapshotValidationError, match="checksum"):
        validate_snapshot(database_path, manifest_path)
