"""The operational CLI must preserve source identity and the pinned API contract."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "mumie_import_cli", SCRIPTS / "run_mumie_image_import.py"
)
assert spec is not None and spec.loader is not None
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_same_count_and_size_changed_pixels_block_resume(tmp_path):
    (tmp_path / "seq_10-18.jpg").write_bytes(b"first")
    report = {}
    assert cli.bind_input(tmp_path, report) == [tmp_path / "seq_10-18.jpg"]
    assert cli.bind_input(tmp_path, report) == [tmp_path / "seq_10-18.jpg"]
    (tmp_path / "seq_10-18.jpg").write_bytes(b"other")
    with pytest.raises(ValueError, match="IMPORT_INPUT_CHANGED"):
        cli.bind_input(tmp_path, report)


def test_existing_game_wrong_profile_is_not_mutated():
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            json=[
                {"id": "m", "code": "mumie", "shapeGeometryConfiguration": "requires_clarification"}
            ],
        )

    with (
        httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="MUMIE_GAME_PROFILE_CONFLICT"),
    ):
        cli.ensure_game(client, {})
    assert calls == ["GET"]


def test_start_pins_virtual_mode_and_blocks_review_required():
    report = {"gameId": "m", "geometryJobId": "g"}
    preflight = {
        "manifestChecksumSha256": "a" * 64,
        "preflightChecksumSha256": "b" * 64,
        "gridProfileInferenceFingerprint": "c" * 64,
    }
    job = {
        "progress": {
            "pageGeometryPreflight": {
                "geometryManifestChecksumSha256": "d" * 64,
                "reviewRequiredSourceCount": 0,
            }
        }
    }
    payload = cli.start_payload(report, preflight, job)
    assert payload["boardCellProcessingMode"] == "structured_lattice_v3"
    assert payload["gridProfileInferenceFingerprint"] == "c" * 64
    assert payload["symbolModelInferenceFingerprint"] is None
    job["progress"]["pageGeometryPreflight"]["reviewRequiredSourceCount"] = 1
    with pytest.raises(ValueError, match="GEOMETRY_REVIEW_REQUIRED"):
        cli.start_payload(report, preflight, job)
    job["progress"]["pageGeometryPreflight"].pop("reviewRequiredSourceCount")
    job["progress"]["review"] = 225
    with pytest.raises(ValueError, match="GEOMETRY_REVIEW_REQUIRED"):
        cli.start_payload(report, preflight, job)


def test_unknown_staging_creation_is_not_repeated(tmp_path):
    (tmp_path / "seq_10-18.jpg").write_bytes(b"jpeg")
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200, json=[{"id": "m", "code": "mumie", "shapeGeometryConfiguration": cli.PROFILE}]
        )

    with (
        httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="UPLOAD_CREATION_OUTCOME_UNKNOWN"),
    ):
        cli.upload(client, tmp_path, tmp_path / "report.json", {"uploadCreationPending": True})
    assert calls == ["GET"]


def test_preflight_requests_bind_game_scope_before_job_reads(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.params.get("gameId"))
        if request.method == "POST":
            return httpx.Response(200, json={"job": {"id": "g"}})
        return httpx.Response(200, json={"status": "queued"})

    report = {"gameId": "m", "uploadId": "u"}
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        cli.advance(client, tmp_path / "report.json", report)
    assert seen == ["m", "m"]
    assert report["geometryJobId"] == "g"
