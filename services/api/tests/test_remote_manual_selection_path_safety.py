from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from game_predictor_api.application import (
    remote_manual_selection_path_safety as path_safety_module,
)
from game_predictor_api.application.remote_manual_selection_path_safety import (
    WindowsPathGuard,
    WindowsPathLimits,
    validate_windows_component,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)

LIMITS = WindowsPathLimits(max_component_utf16_units=255, max_path_utf16_units=259)


def _create_directory_reparse(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip("Directory symlinks and junctions are unavailable.")


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "folder/child",
        r"folder\child",
        r"C:\folder",
        r"\\server\share",
        "bad:name",
        "bad*name",
        "bad\x00name",
        "name.",
        "name ",
        "CON",
        "con.txt",
        "COM1.jpg",
        "LPT9",
        "COM¹.txt",
    ],
)
def test_windows_component_rejects_unsafe_and_reserved_names(value: str) -> None:
    with pytest.raises(RemoteManualSelectionError) as error:
        validate_windows_component(value, limits=LIMITS)

    assert error.value.code == "REMOTE_SELECTION_PATH_NAME_INVALID"
    assert not error.value.details


def test_windows_component_normalizes_nfc_and_casefold_key() -> None:
    result = validate_windows_component("Żółć", limits=LIMITS)

    assert result.display_name == "Żółć"
    assert result.normalized_name == "żółć"


def test_windows_component_uses_utf16_filesystem_limit() -> None:
    limits = WindowsPathLimits(max_component_utf16_units=4, max_path_utf16_units=259)

    assert validate_windows_component("abcd", limits=limits).display_name == "abcd"
    with pytest.raises(RemoteManualSelectionError) as error:
        validate_windows_component("abcde", limits=limits)
    assert error.value.code == "REMOTE_SELECTION_PATH_COMPONENT_TOO_LONG"


def test_final_path_length_check_does_not_silently_truncate() -> None:
    limits = WindowsPathLimits(max_component_utf16_units=255, max_path_utf16_units=8)

    with pytest.raises(RemoteManualSelectionError) as error:
        path_safety_module._assert_path_length(Path(r"C:\123456"), limits)

    assert error.value.code == "REMOTE_SELECTION_PATH_TOO_LONG"


@pytest.mark.skipif(os.name != "nt", reason="Win32 final-handle policy")
def test_path_guard_creates_only_direct_children_inside_locked_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    guard = WindowsPathGuard()

    with guard.lock_base(base) as locked:
        collection, collection_created = locked.open_or_create_child(
            locked.bound_base.final_path,
            validate_windows_component("777", limits=locked.bound_base.limits),
        )
        batch, batch_created = locked.open_or_create_child(
            collection,
            validate_windows_component("1-19809", limits=locked.bound_base.limits),
        )

    assert collection_created is True
    assert batch_created is True
    assert batch == base / "777" / "1-19809"


@pytest.mark.skipif(os.name != "nt", reason="Win32 final-handle policy")
def test_path_guard_rejects_case_and_unicode_equivalent_collision(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "Collection").mkdir()

    with (
        WindowsPathGuard().lock_base(base) as locked,
        pytest.raises(RemoteManualSelectionConflictError) as error,
    ):
        locked.open_or_create_child(
            locked.bound_base.final_path,
            validate_windows_component("collection", limits=locked.bound_base.limits),
        )

    assert error.value.code == "REMOTE_SELECTION_PATH_CASE_COLLISION"


@pytest.mark.skipif(os.name != "nt", reason="Win32 final-handle policy")
def test_path_guard_rejects_symlink_in_selected_base_chain(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "base").mkdir()
    link = tmp_path / "linked"
    _create_directory_reparse(target, link)

    with pytest.raises(RemoteManualSelectionError) as failure:
        WindowsPathGuard().inspect_base(link / "base")

    assert failure.value.code == "REMOTE_SELECTION_PATH_UNSAFE"


@pytest.mark.skipif(os.name != "nt", reason="Win32 final-handle policy")
def test_path_guard_rejects_reparse_swap_between_create_and_final_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "base"
    external = tmp_path / "external"
    base.mkdir()
    external.mkdir()
    probe = tmp_path / "symlink-probe"
    _create_directory_reparse(external, probe)
    os.rmdir(probe)

    def replace_created_directory(path: str | bytes | os.PathLike[str]) -> None:
        _create_directory_reparse(external, Path(path))

    with WindowsPathGuard().lock_base(base) as locked:
        monkeypatch.setattr(path_safety_module.os, "mkdir", replace_created_directory)
        with pytest.raises(RemoteManualSelectionError) as failure:
            locked.open_or_create_child(
                locked.bound_base.final_path,
                validate_windows_component("batch", limits=locked.bound_base.limits),
            )

    assert failure.value.code == "REMOTE_SELECTION_PATH_UNSAFE"
