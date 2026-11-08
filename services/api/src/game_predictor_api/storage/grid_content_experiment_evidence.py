"""Bind an exported experiment proof to actual files, sealed run and frozen TRAIN data."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_content_experiment_evidence import (
    POLICY,
    require_content_experiment_evidence,
)
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.storage.grid_content_bundle import read_content_bundle
from game_predictor_api.storage.grid_engine_model_store import file_sha256


def read_json(root: Path, path: Path, limit: int | None = None) -> Any:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("CONTENT_EXPERIMENT_RECEIPT_PATH_INVALID")
    return read_content_bundle(path, limit=limit)


def inspect_content_experiment(
    root: Path, payload: Mapping[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    proof = require_content_experiment_evidence(bundle)
    directory = root / payload["managedDirectory"]
    provenance = bundle["provenance"]
    run_id = str(UUID(provenance["runId"]))
    run = root / "grid-training" / "runs" / run_id
    sealed = read_json(root, run / "spec.json", 2 * 1024 * 1024)
    spec = sealed["payload"]
    if (
        sealed["sha256"] != digest(spec)
        or spec.get("format") != "grid-training-spec-v1"
        or spec["jobId"] != run_id
        or spec["preset"]["fingerprint"] != provenance["trainingPresetFingerprint"]
        or spec["base"]["weightsSha256"] != proof["plan"]["baseWeightsSha256"]
        or spec.get("contentExperiment") != proof["plan"]
        or spec.get("contentExperimentInputs") != proof["inputs"]
    ):
        raise ValueError("CONTENT_EXPERIMENT_SPEC_CHANGED")
    receipt = read_json(root, directory / "training-base" / "receipt.json", 65536)["payload"]
    original = Path(receipt["sources"]["bundle.json"])
    if not original.resolve().is_relative_to(run.resolve()) or read_json(root, original) != bundle:
        raise ValueError("CONTENT_EXPERIMENT_EXPORT_CHANGED")
    from game_predictor_worker.images.grid_cohort_dataset import (
        GridBoardDataset,
        GridCohortSnapshot,
    )
    from game_predictor_worker.images.grid_content_experiment_data import verify_inputs

    from game_predictor_api.domain.grid_visibility_contract import require_output_contract

    require_output_contract(bundle, spec.get("gridOutputContract"), require_expected=True)
    pins = spec["joint"]["cohorts"] if spec.get("joint") else [spec["cohort"]]
    snapshots = [GridCohortSnapshot(root, p["manifestPath"], p["manifestSha256"]) for p in pins]
    verify_inputs(proof["plan"], proof["inputs"], snapshots)
    head_reference = False
    for snapshot in snapshots:
        game = snapshot.manifest["gameId"]
        members = set()
        for source, _ in GridBoardDataset(snapshot, "TRAIN").indexed():
            # Actual frame validates copied bytes, dimensions and normalized pixel identity.
            snapshot.frame(source, "TRAIN")
            if proof["selectedArm"] == "R3":
                from game_predictor_worker.images.grid_cell_content_reference import (
                    frozen_content_reference,
                )

                for target in source["targets"]:
                    reference = frozen_content_reference(UUID(game), source, target)
                    head_reference |= (
                        reference is not None
                        and reference.humanApproved
                        and any(
                            cell.state == "visible" and cell.quad is not None
                            for cell in reference.cells
                        )
                    )
            members.add(
                digest(
                    {
                        "gameId": game,
                        "sourceId": source["sourceId"],
                        "sourceSha256": source["sourceIdentity"]["checksum_sha256"],
                        "cohortSha256": snapshot.manifest_sha256,
                    }
                )
            )
        for stage in proof["exposure"]["games"].get(game, {}).values():
            if not set(stage["sources"]) <= members:
                raise ValueError("CONTENT_EXPERIMENT_EXPOSURE_SOURCE_CHANGED")
    if proof["selectedArm"] == "R3" and not head_reference:
        raise ValueError("CONTENT_EXPERIMENT_APPROVED_HEAD_REFERENCE_REQUIRED")
    graphs = bundle["contentRescue"]["parity"]["graphs"]
    declared = {f["name"]: f["sha256"] for f in payload["files"]}
    if set(declared) != {*graphs, "bundle.json", "preset.json"} or any(
        declared[name] != sha or file_sha256(directory / name) != sha
        for name, sha in graphs.items()
    ):
        raise ValueError("CONTENT_EXPERIMENT_GRAPH_CHANGED")
    import onnx

    for name in graphs:
        graph = onnx.load(str(directory / name), load_external_data=False)
        if any(item.data_location == onnx.TensorProto.EXTERNAL for item in graph.graph.initializer):
            raise ValueError("CONTENT_EXPERIMENT_GRAPH_EXTERNAL_DATA")
        incoming = graph.graph.input
        if len(incoming) != 1 or incoming[0].type.tensor_type.elem_type != onnx.TensorProto.FLOAT:
            raise ValueError("CONTENT_EXPERIMENT_GRAPH_INPUT_INVALID")
        dims = incoming[0].type.tensor_type.shape.dim
        if len(dims) != 4 or dims[1].dim_value != 3:
            raise ValueError("CONTENT_EXPERIMENT_GRAPH_INPUT_INVALID")
        expected_names = {
            "screen.onnx": ("pixels", {"heat", "offsets"}),
            "board.onnx": ("crops", {"nodes", "peak", "visibility"}),
            "content.onnx": ("crops", {"content_quads", "local_visibility"}),
        }
        input_name, output_names = expected_names[name]
        if (
            incoming[0].name != input_name
            or {out.name for out in graph.graph.output} != output_names
        ):
            raise ValueError("CONTENT_EXPERIMENT_GRAPH_OUTPUT_INVALID")
        if name == "screen.onnx" or proof["selectedArm"] in ("R2", "R3"):
            if not dims[2].dim_param or not dims[3].dim_param:
                raise ValueError("CONTENT_EXPERIMENT_DYNAMIC_RASTER_REQUIRED")
        elif (dims[2].dim_value, dims[3].dim_value) != (192, 320):
            raise ValueError("CONTENT_EXPERIMENT_BASELINE_RASTER_CHANGED")
    return proof


def content_rescue_pin(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    game_id: str,
    publication_evidence: Mapping[str, Any],
) -> dict[str, Any] | None:
    proof = require_content_experiment_evidence(bundle)
    if game_id not in {p["gameId"] for p in proof["plan"]["cohorts"]}:
        raise ValueError("CONTENT_EXPERIMENT_GAME_NOT_EVALUATED")
    rescue = bundle["contentRescue"]
    if rescue["selectedPath"] is None:
        return None
    from game_predictor_worker.geometry_core.rescue import GridRescueVariantV2

    variant = GridRescueVariantV2.model_validate(rescue["variant"])
    return {
        "policyVersion": POLICY,
        "variantId": variant.sha256,
        "variant": rescue["variant"],
        "selectedPath": "combined",
        "bundleSha256": next(f["sha256"] for f in payload["files"] if f["name"] == "bundle.json"),
        "proofSha256": rescue["sha256"],
        "publicationEvidenceSha256": digest(publication_evidence),
    }
