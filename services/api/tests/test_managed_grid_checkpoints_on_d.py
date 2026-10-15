"""TASK-1014: training base publication, receipt and restart regressions."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
import torch
from game_predictor_api.domain.grid_engine_profiles import GridEngineModelError, GridEngineModelFile
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from test_grid_engine_profiles import ROOT, _fake_export, _install_module


def training_export(tmp_path: Path):
    install = _install_module()
    version, source = _fake_export(tmp_path)
    checkpoint = tmp_path / "base.pt"
    torch.save({"schemaVersion": 1, "modelState": {"weight": torch.ones(1)}}, checkpoint)
    torch.save({"weight": torch.ones(1)}, source / "weights.pt")
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    weights_sha = hashlib.sha256((source / "weights.pt").read_bytes()).hexdigest()
    bundle = json.loads((source / "bundle.json").read_text())
    bundle["weights_sha256"] = weights_sha
    bundle["provenance"]["checkpoint_sha256"] = sha
    (source / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    version = replace(
        version,
        checkpoint_sha256=sha,
        weights_sha256=weights_sha,
        checkpoint_size_bytes=checkpoint.stat().st_size,
        weights_size_bytes=(source / "weights.pt").stat().st_size,
        files=tuple(
            GridEngineModelFile(
                file.name,
                hashlib.sha256((source / file.name).read_bytes()).hexdigest(),
                (source / file.name).stat().st_size,
            )
            if file.name == "bundle.json"
            else file
            for file in version.files
        ),
    )
    return install, version, source, checkpoint, tmp_path / "artifacts"


def test_copy_receipt_and_new_process_reads_only_managed_base(tmp_path: Path) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    result = install.install_version(version, source, root, training_checkpoint=checkpoint)
    store = ManagedGridEngineModelStore(root)
    assert result.outcome == "installed"
    assert store.require_training_base(version).read_bytes() == checkpoint.read_bytes()
    before = (store.directory(version) / "manifest.json").read_bytes()
    assert (
        install.install_version(version, source, root, training_checkpoint=checkpoint).outcome
        == "already_installed"
    )
    assert (store.directory(version) / "manifest.json").read_bytes() == before
    version_file = tmp_path / "fixture-version.pickle"
    version_file.write_bytes(pickle.dumps(version))
    # Remove all fixture source artifacts: the child process must use only the managed copy.
    checkpoint.unlink()
    for file in source.iterdir():
        file.unlink()
    code = """
import pickle, sys
from pathlib import Path
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_worker.training_core.checkpoint import load_checkpoint
version = pickle.loads(Path(sys.argv[1]).read_bytes())
path = ManagedGridEngineModelStore(Path(sys.argv[2])).require_training_base(version)
value = load_checkpoint(path, version.checkpoint_sha256)
assert value['modelState']['weight'].tolist() == [1.0]
print('managed checkpoint read')
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(ROOT / path) for path in ("services/api/src", "services/worker/src")
        ),
    }
    child = subprocess.run(
        [sys.executable, "-c", code, str(version_file), str(root)],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert child.returncode == 0, child.stderr
    assert "managed checkpoint read" in child.stdout


def test_interrupted_copy_retries_owned_staging_and_verifies_complete_files(tmp_path: Path) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    install.install_version(version, source, root)
    original = install.shutil.copyfile
    copied = []

    def interrupt(src, dest):
        copied.append(Path(dest).name)
        if len(copied) == 2:
            Path(dest).write_bytes(b"partial")
            raise OSError("interrupted copy")
        return original(src, dest)

    with (
        patch.object(install.shutil, "copyfile", side_effect=interrupt),
        pytest.raises(OSError, match="interrupted"),
    ):
        install.install_version(version, source, root, training_checkpoint=checkpoint)
    store = ManagedGridEngineModelStore(root)
    assert not store.training_directory(version).exists()
    staged = store.directory(version) / ".training-base.installing"
    # Same-sized tampering must be copied again, rather than trusted by mtime/size.
    path = staged / "checkpoint.pt"
    path.write_bytes(b"x" * path.stat().st_size)
    install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert store.require_training_base(version).read_bytes() == checkpoint.read_bytes()
    assert not staged.exists()


@pytest.mark.parametrize("foreign", ["training-base", ".training-base.installing"])
def test_foreign_directory_is_never_overwritten(tmp_path: Path, foreign: str) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    install.install_version(version, source, root)
    directory = ManagedGridEngineModelStore(root).directory(version) / foreign
    directory.mkdir()
    sentinel = directory / "foreign.txt"
    sentinel.write_text("untouched")
    with pytest.raises(GridEngineModelError):
        install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert sentinel.read_text() == "untouched"


@pytest.mark.parametrize("name", ["checkpoint.pt", "weights.pt", "receipt.json", "preset.json"])
def test_store_rejects_corruption_and_installer_preserves_it(tmp_path: Path, name: str) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    install.install_version(version, source, root, training_checkpoint=checkpoint)
    store = ManagedGridEngineModelStore(root)
    path = store.training_directory(version) / name
    path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(GridEngineModelError, match="GRID_ENGINE_TRAINING_INVALID"):
        store.require_training_base(version)
    with pytest.raises(GridEngineModelError):
        install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert path.read_bytes() == b"x" * path.stat().st_size


@pytest.mark.parametrize("mutation", ["hash", "size"])
def test_source_mismatch_writes_nothing(tmp_path: Path, mutation: str) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    if mutation == "hash":
        checkpoint.write_bytes(b"x" * checkpoint.stat().st_size)
    else:
        checkpoint.write_bytes(b"small")
    with pytest.raises(GridEngineModelError, match="GRID_ENGINE_SOURCE_CHECKSUM_MISMATCH"):
        install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert not root.exists()


def test_process_crash_releases_os_lock_and_restart_resumes(tmp_path: Path) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    install.install_version(version, source, root)
    fixture = tmp_path / "version.pickle"
    fixture.write_bytes(pickle.dumps(version))
    code = """
import os, pickle, sys
from pathlib import Path
from scripts import install_grid_engine_models as install
version = pickle.loads(Path(sys.argv[1]).read_bytes())
original = install.shutil.copyfile
def crash(source, destination):
    original(source, destination)
    os._exit(23)
install.shutil.copyfile = crash
install.install_version(version, Path(sys.argv[2]), Path(sys.argv[3]),
                        training_checkpoint=Path(sys.argv[4]))
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(ROOT / path) for path in ("services/api/src", "services/worker/src", ".")
        ),
    }
    child = subprocess.run(
        [sys.executable, "-c", code, str(fixture), str(source), str(root), str(checkpoint)],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert child.returncode == 23, child.stderr
    store = ManagedGridEngineModelStore(root)
    assert not store.training_directory(version).exists()
    assert (store.directory(version) / ".training-base.installing/checkpoint.pt.partial").exists()
    result = install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert result.outcome == "installed"
    assert store.require_training_base(version).read_bytes() == checkpoint.read_bytes()


def test_disk_reserve_refuses_before_installing_anything(tmp_path: Path) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    with (
        patch.object(install.shutil, "disk_usage", return_value=usage(10, 9, 1)),
        pytest.raises(GridEngineModelError, match="GRID_ENGINE_SPACE_REQUIRED"),
    ):
        install.install_version(version, source, root, training_checkpoint=checkpoint)
    assert not root.exists()


def test_check_training_cli_reports_failure_and_source_free_success(tmp_path: Path) -> None:
    install, version, source, checkpoint, root = training_export(tmp_path)
    from game_predictor_api.domain.grid_engine_profiles import GRID_ENGINE_PROFILES

    profile = replace(GRID_ENGINE_PROFILES[1], versions=(version,))
    with patch.object(install, "GRID_ENGINE_PROFILES", (profile,)):
        assert install.main(["--artifact-root", str(root), "--check-training"]) == 2
        install.install_version(version, source, root, training_checkpoint=checkpoint)
        checkpoint.unlink()
        assert install.main(["--artifact-root", str(root), "--check-training"]) == 0
