"""Execute the Windows starter against a fake local API; never create real jobs."""

import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

SOURCE = Path(__file__).parents[1] / "Start-GridCorrectionLearning.ps1"
GAME = "246a1f54-eee8-49d5-b11a-0fde70e5eecd"


def quoted(path):
    return "'" + str(path).replace("'", "''") + "'"


def invoke(
    tmp_path, *, mode=None, saved=None, supported=True, reuse=False, command_file=None, game=GAME
):
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    target = scripts / SOURCE.name
    shutil.copyfile(SOURCE, target)
    runtime = tmp_path / ".runtime"
    runtime.mkdir(exist_ok=True)
    command = command_file or runtime / f"grid-detector-learning-{GAME}.json"
    if saved is not None:
        command.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    trace = tmp_path / ("replay-trace.jsonl" if reuse else "trace.jsonl")
    properties = {"prepareInBackground": {}, "preparationOnly": {}} if supported else {}
    contract = {
        "paths": {
            "/api/v1/admin/games/{game_id}/grid-correction-learning": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Start"}}
                        }
                    }
                }
            }
        },
        "components": {"schemas": {"Start": {"properties": properties}}},
    }
    contract_path = tmp_path / "openapi.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        "$ErrorActionPreference='Stop'\n"
        "function Invoke-RestMethod {\n"
        "param($Method='Get',$Uri,$Headers,$ContentType,$Body,$TimeoutSec)\n"
        "$parsedBody=if ($Body) {$Body | ConvertFrom-Json} else {$null}\n"
        "@{method=$Method;uri=$Uri;body=$parsedBody} | ConvertTo-Json -Depth 20 -Compress | "
        f"Add-Content -Encoding UTF8 {quoted(trace)}\n"
        "if ($Uri -like '*/openapi.json') {return (Get-Content -Raw "
        f"{quoted(contract_path)} | ConvertFrom-Json)}}\n"
        "return @{learningId='11111111-1111-4111-8111-111111111111';status='created'}\n"
        "}\n"
        f"& {quoted(target)} -GameId {game}"
        + (f" -TrainingMode '{mode}'" if mode else "")
        + (f" -CommandFile {quoted(command_file)}" if command_file else "")
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        capture_output=True,
        text=True,
        timeout=25,
    )
    calls = (
        [json.loads(line) for line in trace.read_text(encoding="utf-8-sig").splitlines()]
        if trace.exists()
        else []
    )
    return result, command, calls


@pytest.mark.parametrize("mode", [None, "screen+grid"])
def test_fresh_starter_defaults_to_partial_compatible_grid_mode(tmp_path, mode):
    result, command, calls = invoke(tmp_path, mode=mode)
    assert result.returncode == 0, result.stderr
    saved = json.loads(command.read_text(encoding="utf-8-sig"))
    assert saved["trainingMode"] == (mode or "grid-only")
    assert saved["policyVersion"] == "application-grid-corrections-v4"
    assert saved["prepareInBackground"] is True and saved["preparationOnly"] is False
    assert len([c for c in calls if c["method"] == "Post"]) == 1
    original = command.read_bytes()
    replay, _, repeated = invoke(tmp_path, mode=mode, reuse=True)
    assert replay.returncode == 0, replay.stderr
    assert command.read_bytes() == original
    assert repeated[-1]["body"] == saved


def test_old_detector_command_requires_explicit_replay_and_is_never_rewritten(tmp_path):
    saved = {
        "idempotencyKey": str(uuid4()),
        "trainingMode": "screen+grid",
        "prepareInBackground": True,
        "preparationOnly": False,
        "policyVersion": "application-grid-corrections-v4",
        "validationAssignments": {},
        "historicalCohorts": [],
        "importJobIds": [],
        "exclusions": [],
    }
    result, command, calls = invoke(tmp_path, saved=saved)
    original = command.read_bytes()
    assert result.returncode != 0 and "Saved command uses" in result.stderr
    assert calls == [] and json.loads(original) == saved
    replay, _, calls = invoke(tmp_path, mode="screen+grid", reuse=True)
    assert replay.returncode == 0, replay.stderr
    assert command.read_bytes() == original
    assert calls[-1]["body"] == saved


def test_invalid_saved_key_never_reaches_network(tmp_path):
    result, command, calls = invoke(
        tmp_path, saved={"idempotencyKey": "bad", "trainingMode": "grid-only"}
    )
    assert result.returncode != 0 and "invalid idempotency" in result.stderr
    assert calls == [] and json.loads(command.read_text())["idempotencyKey"] == "bad"


def test_old_api_contract_blocks_training_post(tmp_path):
    result, command, calls = invoke(tmp_path, supported=False)
    assert result.returncode != 0 and "does not support durable" in result.stderr
    assert command.exists()
    assert [c["method"] for c in calls] == ["Get"]


def test_separate_future_command_file_preserves_old_detector_run(tmp_path):
    old = {"idempotencyKey": str(uuid4()), "trainingMode": "screen+grid"}
    rejected, original, _ = invoke(tmp_path, saved=old)
    assert rejected.returncode != 0
    before = original.read_bytes()
    separate = tmp_path / ".runtime" / "new-points.json"
    accepted, command, calls = invoke(tmp_path, command_file=separate, reuse=True)
    assert accepted.returncode == 0, accepted.stderr
    assert command == separate and original.read_bytes() == before
    assert calls[-1]["body"]["trainingMode"] == "grid-only"
    assert calls[-1]["body"]["idempotencyKey"] != old["idempotencyKey"]


def test_custom_command_cannot_be_replayed_for_another_game(tmp_path):
    custom = tmp_path / "custom.json"
    first, command, _ = invoke(tmp_path, command_file=custom)
    assert first.returncode == 0, first.stderr
    before = command.read_bytes()
    rejected, _, calls = invoke(tmp_path, command_file=custom, game=str(uuid4()), reuse=True)
    assert rejected.returncode != 0 and "belongs to another game" in rejected.stderr
    assert calls == [] and command.read_bytes() == before


def test_unbound_existing_custom_file_fails_before_network(tmp_path):
    custom = tmp_path / "custom.json"
    result, _, calls = invoke(
        tmp_path,
        command_file=custom,
        saved={"idempotencyKey": str(uuid4()), "trainingMode": "grid-only"},
    )
    assert result.returncode != 0 and "no game binding" in result.stderr
    assert calls == []
