from pathlib import Path

import pytest

from scripts.prepare_legacy_copy_retirement import (
    io_path,
    legacy_values,
    validate_roots,
    verify_files,
)


def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    source, active, output = [tmp_path / name for name in ("old", "active", "backup")]
    source.mkdir()
    active.mkdir()
    return source, active, output


def test_preserves_old_data_without_overwriting_active_checkout(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    for root in (source, active):
        (root / "same").write_bytes(b"same")
    (source / "changed").write_bytes(b"old")
    (active / "changed").write_bytes(b"new")
    (source / "missing").write_bytes(b"only old")
    result = verify_files(source, active, output)
    assert result["complete"]
    assert result["preserved_by_kind"] == {"active_copy": 1, "archive": 2}
    assert (active / "changed").read_bytes() == b"new"
    assert not (active / "missing").exists()
    assert (output / "legacy-files/changed").read_bytes() == b"old"
    assert (output / "legacy-files/missing").read_bytes() == b"only old"


def test_resume_rechecks_changed_active_copy_and_archives_old_version(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    (source / "photo").write_bytes(b"original")
    (active / "photo").write_bytes(b"original")
    assert verify_files(source, active, output)["complete"]
    (active / "photo").write_bytes(b"replaced")
    result = verify_files(source, active, output)
    assert result["complete"]
    assert result["preserved_by_kind"] == {"archive": 1}
    assert (output / "legacy-files/photo").read_bytes() == b"original"
    assert (active / "photo").read_bytes() == b"replaced"


def test_changed_source_does_not_overwrite_existing_archive(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    (source / "photo").write_bytes(b"first")
    assert verify_files(source, active, output)["complete"]
    (source / "photo").write_bytes(b"second")
    result = verify_files(source, active, output)
    assert not result["complete"]
    assert result["verification_errors"]
    assert (output / "legacy-files/photo").read_bytes() == b"first"


def test_refuses_overlapping_roots(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        validate_roots(source, active, source / "backup")
    with pytest.raises(ValueError, match="contain"):
        validate_roots(source, active, active.parent)


def test_reparse_target_cannot_redirect_backup_into_live_data(tmp_path: Path) -> None:
    import subprocess

    source, active, output = roots(tmp_path)
    (source / "folder").mkdir()
    (source / "folder/photo").write_bytes(b"old")
    (active / "elsewhere").mkdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(active / "folder"), str(active / "elsewhere")],
        check=True,
        capture_output=True,
        timeout=10,
    )
    result = verify_files(source, active, output)
    assert not result["complete"]
    assert result["verification_errors"]
    assert not (active / "elsewhere/photo").exists()


def test_nested_environment_is_reproducible_and_legacy_paths_have_boundaries(
    tmp_path: Path,
) -> None:
    source, active, output = roots(tmp_path)
    folder = source / "worktrees/old/.venv"
    folder.mkdir(parents=True)
    (folder / "cache").write_bytes(b"rebuild me")
    assert verify_files(source, active, output)["files"] == 0
    assert list(legacy_values({"a": ["C:/old/a", "C:/older/b"]}, "c:\\old")) == [
        (".a[0]", "C:/old/a")
    ]


def test_long_windows_paths_are_preserved_with_atomic_publication(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    relative = Path("x" * 90) / ("y" * 90) / ("z" * 70) / "photo.jpg"
    original = io_path(source / relative)
    original.parent.mkdir(parents=True)
    original.write_bytes(b"long-path original")
    result = verify_files(source, active, output)
    assert result["complete"]
    assert io_path(output / "legacy-files" / relative).read_bytes() == b"long-path original"


def test_cached_inventory_requires_fresh_pass_and_cannot_hide_new_files(tmp_path: Path) -> None:
    source, active, output = roots(tmp_path)
    (source / "first").write_bytes(b"first")
    assert verify_files(source, active, output)["complete"]
    (source / "new-after-inventory").write_bytes(b"new")
    cached = verify_files(source, active, output, resume_inventory=True)
    assert not cached["complete"]
    assert cached["ready_for_fresh_inventory"]
    final = verify_files(source, active, output)
    assert final["complete"]
    assert final["files"] == 2
    assert (output / "legacy-files/new-after-inventory").read_bytes() == b"new"
