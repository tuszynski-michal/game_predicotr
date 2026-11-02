"""Both correction preflight and training must locate the same CUDA interpreter."""

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest
from game_predictor_api.application.grid_correction_learning import LEARNING_KIND
from game_predictor_worker import cli
from game_predictor_worker.images import grid_training_handler
from game_predictor_worker.images.grid_correction_learning_handler import (
    GridCorrectionLearningJobHandler,
)
from game_predictor_worker.training_core.grid_training_admission import RuntimeFacts


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv(cli.GRID_TRAINING_PYTHON_ENV, raising=False)
    monkeypatch.setattr(
        cli, "__file__", str(tmp_path / "services/worker/src/game_predictor_worker/cli.py")
    )
    return tmp_path


def make_python(checkout: Path, relative: str = "Scripts/python.exe") -> Path:
    python = checkout / ".venv-vision-lab" / relative
    python.parent.mkdir(parents=True, exist_ok=True)
    python.touch()
    return python


@pytest.mark.parametrize("relative", ["Scripts/python.exe", "bin/python"])
def test_factory_locates_checkout_cuda_without_process_environment(
    checkout: Path, relative: str
) -> None:
    python = make_python(checkout, relative)
    handler = cli._grid_training_handler(None, None, checkout / "artifacts")  # noqa: SLF001
    assert handler.python == python
    assert str(checkout / "services/worker/src") in handler.pythonpath
    assert handler.repository_root == checkout


def test_explicit_interpreter_wins_over_available_checkout_cuda(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_python(checkout)
    explicit = checkout / "custom environment/python.exe"
    monkeypatch.setenv(cli.GRID_TRAINING_PYTHON_ENV, str(explicit))
    handler = cli._grid_training_handler(None, None, checkout / "artifacts")  # noqa: SLF001
    assert handler.python == explicit


def test_invalid_explicit_interpreter_fails_instead_of_using_checkout_cuda(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_python(checkout)
    explicit = checkout / "missing/python.exe"
    monkeypatch.setenv(cli.GRID_TRAINING_PYTHON_ENV, str(explicit))
    calls = []

    def missing(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        raise FileNotFoundError("Explicit operator configuration is missing.")

    monkeypatch.setattr(grid_training_handler.subprocess, "run", missing)
    handler = cli._grid_training_handler(None, None, checkout / "artifacts")  # noqa: SLF001
    facts = handler.probe()
    assert calls[0][0] == str(explicit)
    assert not facts.cuda_available
    assert facts.probe_error == "GRID_TRAINING_PROBE_FAILED"


def test_missing_configuration_does_not_fall_back_to_the_general_cpu_python(checkout: Path) -> None:
    handler = cli._grid_training_handler(None, None, checkout / "artifacts")  # noqa: SLF001
    assert handler.python is None
    facts = handler.probe()
    assert not facts.cuda_available
    assert facts.probe_error == "GRID_TRAINING_PYTHON_UNSET"


def test_correction_parent_probes_the_discovered_cuda_interpreter(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = make_python(checkout)
    expected = RuntimeFacts(
        True, "2.12.1+cu130", "0.27.1+cu130", "13.0", "test GPU", 6_439_305_216, 5_500_000_000
    )
    calls = []

    def probe(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, json.dumps(asdict(expected)).encode())

    monkeypatch.setattr(grid_training_handler.subprocess, "run", probe)
    workflow = cli._grid_correction_learning_handler(None, None, checkout / "artifacts")  # noqa: SLF001
    learning = workflow.handlers[LEARNING_KIND]
    assert isinstance(learning, GridCorrectionLearningJobHandler)
    assert learning.probe() == expected
    arguments, options = calls[0]
    assert arguments == [str(python), "-m", grid_training_handler.CHILD_MODULE, "--probe"]
    assert options["cwd"] == checkout
    assert options["timeout"] == grid_training_handler.PROBE_TIMEOUT_SECONDS
