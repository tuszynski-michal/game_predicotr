"""Shadow slot assignment, replay, integrity and bounded CPU lifecycle without user data."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    grid_engine_manifest,
    grid_engine_profile_for,
)
from game_predictor_api.domain.grid_shadow import GridShadowError, shadow_digest
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_worker.geometry_core import inference, preprocessing, settings
from game_predictor_worker.geometry_core.bounded_runtime import (
    CPUShadowRunner,
    GeometryRuntimeError,
)
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.images.grid_shadow_handler import (
    GridShadowHandler,
    build_shadow_output,
    cell_visibility,
)
from game_predictor_worker.imports.validation_dispatch import ValidationJobDispatchHandler
from game_predictor_worker.jobs.runtime import JobHandlerError
from pydantic import ValidationError


def quad(position=0, y=5):
    x = 5 + position * 60
    return np.array([[x, y], [x + 50, y], [x + 50, y + 30], [x, y + 30]], np.float32)


def detection(position=0, y=5):
    value = quad(position, y)
    return BoardDetection(1.0, value, nodes=grid_from_quad(value), fit_residual=0.0, fit_inliers=24)


def source(count=3):
    checksum = "a" * 64
    binding = {
        "source_image_id": str(uuid4()),
        "checksum_sha256": checksum,
        "normalized_pixel_checksum_sha256": "b" * 64,
        "relative_path": f"originals/aa/{checksum}.jpg",
        "width": 550,
        "height": 80,
        "sequence_range_start": 100,
        "sequence_range_end": 99 + count,
        "active_board_slots": list(range(count)),
        "baseline_slots": [
            {
                "position_index": index,
                "sequence_number": 100 + index,
                "grid_rows": 3,
                "grid_columns": 5,
                "geometry": {
                    "symbolGridQuad": [{"x": float(x), "y": float(y)} for x, y in quad(index)]
                },
            }
            for index in range(count)
        ],
    }
    binding["bindings_sha256"] = shadow_digest(binding)
    return binding


def model():
    version = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current
    return {
        "profile": version.profile.value,
        "version": version.version,
        "manifest_checksum_sha256": shadow_digest(grid_engine_manifest(version)),
        "bundle_checksum_sha256": next(
            item.sha256 for item in version.files if item.name == "bundle.json"
        ),
        "weights_sha256": version.weights_sha256,
        "files": [
            {"name": item.name, "sha256": item.sha256, "size_bytes": item.size_bytes}
            for item in version.files
        ],
    }


def job(binding):
    payload = {
        "schema_version": 1,
        "validation_kind": "grid_geometry_shadow_v3",
        "sources": [binding],
        "model": model(),
    }
    payload["input_digest_sha256"] = shadow_digest(payload)
    return replace(
        create_job(JobType.VALIDATE, game_id=uuid4(), input_payload=payload),
        status=JobStatus.PROCESSING,
        lease_owner="test",
        lease_token=uuid4(),
    )


class Repository:
    def __init__(self, binding):
        self.binding = binding
        self.result = None
        self.publishes = 0
        self.lease_lost = False

    def pin_source(self, *_args):
        return self.binding

    def get_result_for_source(self, *_args):
        return self.result

    def publish_result(self, **values):
        if self.lease_lost:
            raise GridShadowError("GRID_SHADOW_LEASE_LOST", "Lost lease")
        self.publishes += 1
        value = SimpleNamespace(
            source_binding=values["pinned_source"],
            model_binding=values["model"],
            output=values["output"],
        )
        if self.result is None:
            self.result = value
        else:
            assert self.result.output == value.output
        return self.result


class Sessions:
    @contextmanager
    def begin(self):
        yield object()


class ModelStore:
    def require(self, _version):
        return Path("unused-bundle")


class Loader:
    def __init__(self, binding):
        self.binding = binding
        self.paths = []

    def load(self, path, **_kwargs):
        self.paths.append(path)
        return SimpleNamespace(
            source=SimpleNamespace(
                width=self.binding["width"],
                height=self.binding["height"],
                normalized_pixel_checksum_sha256=self.binding["normalized_pixel_checksum_sha256"],
            ),
            rgb=np.zeros((80, 550, 3), np.uint8),
        )

    def clear(self):
        pass


class Runner:
    def __init__(self):
        self.calls = 0

    def run(self, *_args, **kwargs):
        kwargs["heartbeat"]()
        self.calls += 1
        return [detection(index) for index in range(3)]


class Context:
    def __init__(self, value):
        self.job = value
        self.lease_token = value.lease_token
        self.fail_checkpoint = False
        self.checkpoints = []

    def heartbeat(self):
        pass

    def checkpoint(self, **values):
        if self.fail_checkpoint:
            raise RuntimeError("response lost after publication")
        self.checkpoints.append(values)


def handler(tmp_path, binding, *, enabled=True):
    repository, runner, loader = Repository(binding), Runner(), Loader(binding)
    value = GridShadowHandler(
        Sessions(),
        tmp_path,
        enabled=enabled,
        repository_factory=lambda _session: repository,
        model_store=ModelStore(),
        source_loader=loader,
        runner=runner,
    )
    return value, repository, runner, loader


def test_missing_middle_preserves_slots_and_extra_never_becomes_active():
    binding = source(5)
    output = build_shadow_output(
        binding,
        [detection(0), detection(2), detection(3), detection(4), detection(7)],
        calibrated=True,
    )
    assert [slot["sequenceNumber"] for slot in output["slots"]] == [100, 101, 102, 103, 104]
    assert output["slots"][1]["state"] == "missing"
    assert output["slots"][2]["neuralNodes24"][0]["x"] == 125
    assert len(output["unassignedDetections"]) == 1
    assert all(slot["state"] != "complete" for slot in output["slots"])


def test_five_expected_with_six_detections_and_mumie_always_manual():
    output = build_shadow_output(
        source(5), [detection(index) for index in range(6)], calibrated=False
    )
    assert len(output["slots"]) == 5
    assert len(output["unassignedDetections"]) == 1
    assert all(
        slot["neuralNodes24"] is not None and len(slot["neuralNodes24"]) == 24
        for slot in output["slots"]
    )
    assert all("NEURAL_GRID_GATE_UNCALIBRATED" in slot["reasonCodes"] for slot in output["slots"])


def test_no_reference_does_not_assign_by_reading_order():
    binding = source(1)
    binding["baseline_slots"][0]["geometry"] = {"reviewDraftQuad": []}
    output = build_shadow_output(binding, [detection()], calibrated=False)
    assert output["slots"][0]["neuralNodes24"] is None
    assert output["slots"][0]["cellVisibility"] == ["unknown"] * 15
    assert len(output["unassignedDetections"]) == 1


def test_partial_and_outside_visibility_is_geometric():
    nodes = grid_from_quad(quad(y=-15))
    visibility = cell_visibility(nodes, 550, 80)
    assert visibility[:5] == ["outside"] * 5
    assert visibility[5:10] == ["partial"] * 5
    assert visibility[10:] == ["full"] * 5


def test_replay_after_lost_checkpoint_uses_same_result_without_inference(tmp_path):
    binding = source()
    value, repository, runner, loader = handler(tmp_path, binding)
    work = job(binding)
    context = Context(work)
    context.fail_checkpoint = True
    with pytest.raises(RuntimeError, match="response lost"):
        value(context, work)
    original = repository.result
    context.fail_checkpoint = False
    # A new handler, the same durable repository, no re-inference.
    resumed = GridShadowHandler(
        Sessions(),
        tmp_path,
        enabled=True,
        repository_factory=lambda _session: repository,
        model_store=ModelStore(),
        source_loader=loader,
        runner=runner,
    )
    resumed(context, work)
    assert repository.result is original
    assert runner.calls == 1
    assert context.checkpoints[-1]["current"] == 1
    assert loader.paths[0] == tmp_path / "data" / binding["relative_path"]


def test_off_topology_model_drift_stale_and_lease_fail_closed(tmp_path):
    binding = source()
    value, repository, runner, _loader = handler(tmp_path, binding, enabled=False)
    work = job(binding)
    with pytest.raises(JobHandlerError, match="disabled"):
        value(Context(work), work)
    assert runner.calls == repository.publishes == 0
    value, repository, runner, _loader = handler(tmp_path, binding)
    malformed = copy.deepcopy(binding)
    malformed["baseline_slots"][0]["grid_columns"] = 3
    malformed.pop("bindings_sha256")
    malformed["bindings_sha256"] = shadow_digest(malformed)
    work = job(malformed)
    with pytest.raises(JobHandlerError) as error:
        value(Context(work), work)
    assert error.value.code == "GRID_SHADOW_TOPOLOGY_UNSUPPORTED"
    work = job(binding)
    work.input_payload["model"]["weights_sha256"] = "d" * 64
    work.input_payload.pop("input_digest_sha256")
    work.input_payload["input_digest_sha256"] = shadow_digest(work.input_payload)
    with pytest.raises(JobHandlerError) as error:
        value(Context(work), work)
    assert error.value.code == "GRID_SHADOW_MODEL_BINDING_INVALID"
    work = job(binding)
    repository.binding = {**binding, "bindings_sha256": "stale"}
    with pytest.raises(JobHandlerError) as error:
        value(Context(work), work)
    assert error.value.code == "GRID_SHADOW_SOURCE_STALE"
    repository.binding = binding
    repository.lease_lost = True
    with pytest.raises(JobHandlerError) as error:
        value(Context(work), work)
    assert error.value.code == "GRID_SHADOW_LEASE_LOST"
    assert repository.result is None


def test_old_validation_dispatch_unchanged_new_kind_optional():
    calls = []
    old = ValidationJobDispatchHandler(
        lambda *_: calls.append("layout"),
        lambda *_: calls.append("page"),
        lambda *_: calls.append("guard"),
    )
    work = job(source())
    for kind in (
        "layout_import",
        "page_geometry_preflight",
        "image_geometry_guard_report_reconstruction",
    ):
        old(None, replace(work, input_payload={"validation_kind": kind}))
    assert calls == ["layout", "page", "guard"]
    with pytest.raises(JobHandlerError):
        old(None, work)
    dispatch = ValidationJobDispatchHandler(
        lambda *_: None, lambda *_: None, lambda *_: None, lambda *_: calls.append("shadow")
    )
    dispatch(None, work)
    assert calls[-1] == "shadow"


def slow_factory(_bundle, **_kwargs):
    time.sleep(20)
    return object()


class QuickEngine:
    def analyse(self, _rgb):
        return []


def quick_factory(_bundle, **_kwargs):
    return QuickEngine()


def test_bounded_cpu_child_returns_empty_detection_cleanly(tmp_path):
    raw = b"{}"
    (tmp_path / "bundle.json").write_bytes(raw)
    result = CPUShadowRunner(factory=quick_factory).run(
        tmp_path,
        hashlib.sha256(raw).hexdigest(),
        np.zeros((2, 2, 3), np.uint8),
        heartbeat=lambda: None,
        max_seconds=10,
    )
    assert result == []


def test_deadline_stops_slow_cpu_child_and_reaps_it(tmp_path):
    raw = b"{}"
    (tmp_path / "bundle.json").write_bytes(raw)
    before = {process.pid for process in multiprocessing.active_children()}
    start = time.monotonic()
    with pytest.raises(GeometryRuntimeError) as error:
        CPUShadowRunner(factory=slow_factory).run(
            tmp_path,
            hashlib.sha256(raw).hexdigest(),
            np.zeros((2, 2, 3), np.uint8),
            heartbeat=lambda: None,
            max_seconds=2,
        )
    assert error.value.code == "GRID_SHADOW_SOURCE_TIME_LIMIT"
    assert time.monotonic() - start < 6
    assert {process.pid for process in multiprocessing.active_children()} == before


def test_cancel_signal_stops_cpu_child_and_reaps_it(tmp_path):
    raw = b"{}"
    (tmp_path / "bundle.json").write_bytes(raw)
    before = {process.pid for process in multiprocessing.active_children()}

    def cancelled():
        raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        CPUShadowRunner(factory=slow_factory).run(
            tmp_path,
            hashlib.sha256(raw).hexdigest(),
            np.zeros((2, 2, 3), np.uint8),
            heartbeat=cancelled,
            max_seconds=10,
        )
    assert {process.pid for process in multiprocessing.active_children()} == before


def test_handler_timeout_never_publishes_and_releases_pixels(tmp_path):
    binding = source()
    repository, loader = Repository(binding), Loader(binding)
    clears = []
    loader.clear = lambda: clears.append(True)

    class TimeoutRunner:
        def run(self, *_args, **_kwargs):
            raise GeometryRuntimeError("GRID_SHADOW_SOURCE_TIME_LIMIT", "Deadline")

    value = GridShadowHandler(
        Sessions(),
        tmp_path,
        enabled=True,
        repository_factory=lambda _session: repository,
        model_store=ModelStore(),
        source_loader=loader,
        runner=TimeoutRunner(),
    )
    work = job(binding)
    with pytest.raises(JobHandlerError) as error:
        value(Context(work), work)
    assert error.value.code == "GRID_SHADOW_SOURCE_TIME_LIMIT"
    assert repository.publishes == 0
    assert clears


def test_neutral_imports_have_no_lab_training_storage_or_torch():
    for path in Path(inference.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules += [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not any(
            any(part in value for part in ("vision_lab", "storage", "torch", "training"))
            for value in modules
        )


@pytest.mark.parametrize(
    "preset,key",
    [
        (settings.BoardPreset, "coordinate_loss_weight"),
        (settings.BoardPreset, "visibility_loss_weight"),
        (settings.ScreenPreset, "offset_loss_weight"),
        (settings.ScreenPreset, "offset_scale"),
    ],
)
def test_finite_settings_preserve_lab_validation(preset, key):
    from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset

    data = load_preset("A")[0]
    value = data.board.model_dump() if preset is settings.BoardPreset else data.screen.model_dump()
    value[key] = float("inf")
    with pytest.raises(ValidationError):
        preset.model_validate(value)


def test_lab_reuses_exact_neutral_preprocessing_and_decoder():
    from game_predictor_worker.vision_lab import neural_grid_data, neural_grid_inference

    assert neural_grid_data.screen_input is preprocessing.screen_input
    assert neural_grid_inference.decode_screen is inference.decode_screen
    assert neural_grid_inference.fit_grid is inference.fit_grid


def test_lab_loader_still_validates_entire_training_preset(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab import neural_grid_inference as lab_inference

    (tmp_path / "bundle.json").write_text(json.dumps({"preset": {"unexpected": True}}), "utf-8")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("CPU model loading ran before complete preset validation")

    monkeypatch.setattr(lab_inference, "core_onnx_engine", forbidden)
    with pytest.raises(ValidationError):
        lab_inference.onnx_engine(tmp_path)


def test_onnx_loader_uses_exact_verified_graph_bytes(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset

    graphs = {"screen.onnx": b"screen-graph", "board.onnx": b"board-graph"}
    preset = load_preset("A")[0].model_dump(mode="json")
    document = {
        "preset": preset,
        "weights_sha256": "c" * 64,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in graphs.items()},
    }
    raw = json.dumps(document).encode("utf-8")
    (tmp_path / "bundle.json").write_bytes(raw)
    for name, content in graphs.items():
        (tmp_path / name).write_bytes(content)
    loaded = []

    def session(content, options, providers):
        loaded.append((content, providers, options.intra_op_num_threads))
        return object()

    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        SimpleNamespace(SessionOptions=SimpleNamespace, InferenceSession=session),
    )
    value = inference.onnx_engine(
        tmp_path, threads=2, expected_bundle_sha256=hashlib.sha256(raw).hexdigest()
    )
    assert value.model_version == "neural-grid-v1:A:" + "c" * 12
    assert loaded == [
        (b"screen-graph", ["CPUExecutionProvider"], 2),
        (b"board-graph", ["CPUExecutionProvider"], 2),
    ]
    with pytest.raises(ValueError, match="BUNDLE_CHECKSUM_MISMATCH"):
        inference.onnx_engine(tmp_path, expected_bundle_sha256="f" * 64)


class FileRepository(Repository):
    def __init__(self, directory, binding):
        super().__init__(binding)
        self.path = directory / "result.json"
        if self.path.exists():
            data = json.loads(self.path.read_text("utf-8"))
            self.result = SimpleNamespace(**data)

    def publish_result(self, **values):
        was_missing = self.result is None
        result = super().publish_result(**values)
        if was_missing:
            result.id = str(uuid4())
            self.path.write_text(json.dumps(vars(result), sort_keys=True), "utf-8")
        return result


class FileRunner(Runner):
    def __init__(self, directory):
        super().__init__()
        self.path = directory / "inference-count.txt"

    def run(self, *args, **kwargs):
        count = int(self.path.read_text("utf-8")) if self.path.exists() else 0
        self.path.write_text(str(count + 1), "utf-8")
        return super().run(*args, **kwargs)


def restart_process(directory, phase):
    pin = directory / "input.json"
    if phase == "first":
        binding = source()
        work = job(binding)
        pin.write_text(
            json.dumps(
                {
                    "binding": binding,
                    "job_id": str(work.id),
                    "game_id": str(work.game_id),
                    "lease_token": str(work.lease_token),
                }
            ),
            "utf-8",
        )
    else:
        saved = json.loads(pin.read_text("utf-8"))
        binding = saved["binding"]
        work = replace(
            job(binding),
            id=UUID(saved["job_id"]),
            game_id=UUID(saved["game_id"]),
            lease_token=UUID(saved["lease_token"]),
        )
    repository = FileRepository(directory, binding)
    value = GridShadowHandler(
        Sessions(),
        directory,
        enabled=True,
        repository_factory=lambda _session: repository,
        model_store=ModelStore(),
        source_loader=Loader(binding),
        runner=FileRunner(directory),
    )
    context = Context(work)
    context.fail_checkpoint = phase == "first"
    if phase == "first":
        with pytest.raises(RuntimeError, match="response lost"):
            value(context, work)
    else:
        original_id = repository.result.id
        original_output = shadow_digest(repository.result.output)
        value(context, work)
        assert repository.result.id == original_id
        assert shadow_digest(repository.result.output) == original_output
        assert (directory / "inference-count.txt").read_text("utf-8") == "1"
        (directory / "recovered.json").write_text(
            json.dumps({"id": original_id, "outputChecksum": original_output, "inferCount": 1}),
            "utf-8",
        )


def test_restart_in_new_process_recovers_persisted_result_without_inference(tmp_path):
    workspace = Path(__file__).resolve().parents[3]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [
            str(workspace / "services" / "api" / "src"),
            str(workspace / "services" / "worker" / "src"),
        ]
    )
    for phase in ("first", "second"):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--restart-proof",
                str(tmp_path),
                phase,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr + result.stdout
    persisted = json.loads((tmp_path / "result.json").read_text("utf-8"))
    recovered = json.loads((tmp_path / "recovered.json").read_text("utf-8"))
    assert persisted["id"] == recovered["id"]
    assert shadow_digest(persisted["output"]) == recovered["outputChecksum"]
    assert recovered["inferCount"] == 1


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--restart-proof":
    restart_process(Path(sys.argv[2]), sys.argv[3])
