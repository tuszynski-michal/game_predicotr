from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


def _monitor_module() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "run_live_image_selection.py"
    spec = spec_from_file_location("run_live_image_selection", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the live image-selection monitor.")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_job_progress_reads_nested_api_contract() -> None:
    monitor = _monitor_module()

    assert monitor._job_progress(
        {
            "progress": {
                "current": 96,
                "total": 32_079,
                "stage": "image_selection:scanning",
                "imageSelection": {
                    "groups": 1,
                    "selected": 1,
                    "manual": 0,
                    "skipped": 0,
                    "errors": 0,
                    "verifications": 3,
                },
            }
        }
    ) == {
        "stage": "image_selection:scanning",
        "current": 96,
        "total": 32_079,
        "groups": 1,
        "selected": 1,
        "manual": 0,
        "skipped": 0,
        "errors": 0,
        "verifications": 3,
    }


def test_job_progress_rejects_response_without_progress() -> None:
    monitor = _monitor_module()

    with pytest.raises(RuntimeError, match="missing progress"):
        monitor._job_progress({"status": "processing"})
