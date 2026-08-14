from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

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


def test_job_error_reads_nested_api_contract() -> None:
    monitor = _monitor_module()

    assert monitor._job_error(
        {
            "error": {
                "code": "IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT",
                "message": "Projection conflict.",
            }
        }
    ) == (
        "IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT",
        "Projection conflict.",
    )
    assert monitor._job_error({"error": None}) == (None, None)


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
    assert saved["schemaVersion"] == 3
    assert saved["exportCursor"] == -1


def test_progressive_export_advances_cursor_without_rescanning_old_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    calls: list[int] = []
    pages = {
        -1: {
            "items": [
                {
                    "groupOrder": 0,
                    "id": "group-0",
                    "rangeStart": 1,
                    "rangeEnd": 9,
                    "status": "auto_selected",
                },
                {
                    "groupOrder": 1,
                    "id": "group-1",
                    "rangeStart": None,
                    "rangeEnd": None,
                    "status": "manual_required",
                },
            ],
            "nextAfterGroupOrder": None,
        },
        1: {
            "items": [
                {
                    "groupOrder": 2,
                    "id": "group-2",
                    "rangeStart": 10,
                    "rangeEnd": 18,
                    "status": "auto_selected",
                }
            ],
            "nextAfterGroupOrder": None,
        },
        2: {"items": [], "nextAfterGroupOrder": None},
    }

    class _Response:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            pass

    class _Client:
        def get(self, path: str) -> _Response:
            return _Response(path.encode("ascii"))

    def request_json(
        _client: object,
        _method: str,
        _path: str,
        *,
        params: dict[str, Any],
        **_: object,
    ) -> dict[str, Any]:
        after = int(params["afterGroupOrder"])
        calls.append(after)
        return pages[after]

    monkeypatch.setattr(monitor, "_request_json", request_json)
    saved_orders: set[int] = set()

    saved, cursor = monitor._save_ready_groups(
        _Client(),
        "run",
        tmp_path,
        saved_orders,
        after_group_order=-1,
    )
    saved_again, cursor = monitor._save_ready_groups(
        _Client(),
        "run",
        tmp_path,
        saved_orders,
        after_group_order=cursor,
    )
    saved_last, cursor = monitor._save_ready_groups(
        _Client(),
        "run",
        tmp_path,
        saved_orders,
        after_group_order=cursor,
    )

    assert (saved, saved_again, saved_last) == (1, 1, 0)
    assert cursor == 2
    assert calls == [-1, 1, 2]
    assert saved_orders == {0, 2}
    assert (tmp_path / "seq_1-9.jpg").is_file()
    assert (tmp_path / "seq_10-18.jpg").is_file()


def test_progressive_export_reads_one_bounded_page_while_run_is_growing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    calls: list[int] = []

    class _Client:
        def get(self, _path: str) -> object:
            raise AssertionError("No selected file is expected for a manual group.")

    def request_json(
        _client: object,
        _method: str,
        _path: str,
        *,
        params: dict[str, Any],
        **_: object,
    ) -> dict[str, Any]:
        calls.append(int(params["afterGroupOrder"]))
        return {
            "items": [
                {
                    "groupOrder": 99,
                    "id": "group-99",
                    "rangeStart": None,
                    "rangeEnd": None,
                    "status": "manual_required",
                }
            ],
            "nextAfterGroupOrder": 99,
        }

    monkeypatch.setattr(monitor, "_request_json", request_json)

    saved, cursor = monitor._save_ready_groups(
        _Client(),
        "run",
        tmp_path,
        set(),
        after_group_order=-1,
    )

    assert saved == 0
    assert cursor == 99
    assert calls == [-1]


def test_terminal_export_drains_every_remaining_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    calls: list[int] = []

    def save_page(
        _client: object,
        _run_id: str,
        _output_root: Path,
        saved_orders: set[int],
        *,
        after_group_order: int,
    ) -> tuple[int, int]:
        calls.append(after_group_order)
        if after_group_order == 99:
            saved_orders.add(150)
            return 1, 199
        if after_group_order == 199:
            saved_orders.add(250)
            return 1, 250
        return 0, after_group_order

    monkeypatch.setattr(monitor, "_save_ready_groups", save_page)
    saved_orders = {5}

    saved, cursor = monitor._drain_ready_groups(
        object(),
        "run",
        tmp_path,
        saved_orders,
        after_group_order=99,
    )

    assert saved == 2
    assert cursor == 250
    assert calls == [99, 199, 250]
    assert saved_orders == {5, 150, 250}


def test_terminal_reconciliation_rescans_promoted_groups_and_removes_stale_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    groups = [
        {
            "groupOrder": 0,
            "id": "group-0",
            "rangeStart": 1,
            "rangeEnd": 9,
            "status": "auto_selected",
        },
        {
            "groupOrder": 1,
            "id": "group-1",
            "rangeStart": 10,
            "rangeEnd": 18,
            "status": "manual_required",
        },
        {
            "groupOrder": 2,
            "id": "group-2",
            "rangeStart": 19,
            "rangeEnd": 27,
            "status": "range_confirmed",
        },
        {
            "groupOrder": 3,
            "id": "group-3",
            "rangeStart": 19,
            "rangeEnd": 27,
            "status": "skipped_existing_range",
        },
    ]

    class _Response:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            pass

    class _Client:
        def get(self, path: str) -> _Response:
            return _Response(path.encode("ascii"))

    def request_json(
        _client: object,
        _method: str,
        _path: str,
        *,
        params: dict[str, Any],
        **_: object,
    ) -> dict[str, Any]:
        return {"items": groups if int(params["afterGroupOrder"]) == -1 else []}

    monkeypatch.setattr(monitor, "_request_json", request_json)
    (tmp_path / "seq_1-9.jpg").write_bytes(b"old-owner")
    (tmp_path / "seq_999-1007.jpg").write_bytes(b"stale")
    saved_orders = {99}
    run = {
        "firstSequenceNumber": 1,
        "lastSequenceNumber": 27,
        "sequenceDirection": "ascending",
        "expectedGroupCount": 3,
        "job": {"status": "waiting_for_review"},
    }

    coverage, saved, cursor = monitor._finalize_terminal_run(
        _Client(),
        "run",
        run,
        tmp_path,
        saved_orders,
    )

    assert saved == 2
    assert cursor == 3
    assert coverage["logicalCoverageValid"] is True
    assert coverage["outputCoverageValid"] is True
    assert coverage["expectedLogicalGroups"] == 3
    assert coverage["logicalGroups"] == 3
    assert coverage["duplicateGroups"] == 1
    assert coverage["readyOutputGroups"] == 2
    assert coverage["savedOutputFiles"] == 2
    assert coverage["groupStatusCounts"]["range_confirmed"] == 1
    assert saved_orders == {0, 2}
    assert not (tmp_path / "seq_999-1007.jpg").exists()
    assert (tmp_path / "seq_1-9.jpg").read_bytes().endswith(b"selected-file")
    assert (tmp_path / "seq_19-27.jpg").is_file()


def test_failed_terminal_run_is_a_read_only_invalid_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _monitor_module()
    groups = [
        {
            "groupOrder": 0,
            "id": "group-0",
            "rangeStart": 1,
            "rangeEnd": 9,
            "status": "auto_selected",
        }
    ]

    class _Client:
        def get(self, _path: str) -> object:
            raise AssertionError("A failed run must not repair exported files.")

    def request_json(
        _client: object,
        _method: str,
        _path: str,
        *,
        params: dict[str, Any],
        **_: object,
    ) -> dict[str, Any]:
        return {"items": groups if int(params["afterGroupOrder"]) == -1 else []}

    monkeypatch.setattr(monitor, "_request_json", request_json)
    stale = tmp_path / "seq_1-9.jpg"
    stale.write_bytes(b"preserve-failure-evidence")

    coverage, saved, _cursor = monitor._finalize_terminal_run(
        _Client(),
        "run",
        {
            "firstSequenceNumber": 1,
            "lastSequenceNumber": 9,
            "sequenceDirection": "ascending",
            "expectedGroupCount": 1,
            "job": {"status": "failed"},
        },
        tmp_path,
        set(),
    )

    assert saved == 0
    assert coverage["logicalCoverageValid"] is True
    assert coverage["outputCoverageValid"] is False
    assert stale.read_bytes() == b"preserve-failure-evidence"
