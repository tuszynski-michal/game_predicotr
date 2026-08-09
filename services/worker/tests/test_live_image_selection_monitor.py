from argparse import Namespace
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


def test_existing_rerun_writes_resumable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    output = tmp_path / "selected"
    output.mkdir()
    report = tmp_path / "run.json"
    requests: list[tuple[str, str]] = []

    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def request_json(
        _client: object,
        method: str,
        path: str,
        **_: object,
    ) -> dict[str, object]:
        requests.append((method, path))
        return {
            "created": True,
            "run": {"id": "new-run", "job": {"id": "new-job"}},
        }

    monkeypatch.setattr(monitor.httpx, "Client", _Client)
    monkeypatch.setattr(monitor, "_request_json", request_json)
    monkeypatch.setattr(monitor, "_resume_existing", lambda _options: 17)

    result = monitor._start_existing_rerun(
        Namespace(
            api_base_url="http://127.0.0.1:8000",
            output=output,
            report=report,
            rerun_id="source-run",
        )
    )

    saved = monitor.json.loads(report.read_text(encoding="utf-8"))
    assert result == 17
    assert requests == [
        ("POST", "/api/v1/admin/image-selections/source-run/rerun"),
    ]
    assert saved["runId"] == "new-run"
    assert saved["jobId"] == "new-job"
    assert saved["savedOutputFiles"] == 0
