"""Reconstruct saved neural inputs or read bounded metadata; never run inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_POLICY,
    neural_auto_crop_blockers,
)
from game_predictor_api.domain.neural_grid_proposal import lattice_cell_quads, lattice_visibility
from game_predictor_worker.geometry_core.input_diagnostics import (
    DiagnosticUse,
    InputDiagnostic,
    ModelPin,
    NodeObservation,
    Point,
    SourcePin,
    array_sha256,
    decode_record,
    diagnostic_uses,
    digest,
    encode_record,
    input_stages,
    reconstruct_input,
)
from game_predictor_worker.geometry_core.settings import BoardPreset, ScreenPreset
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from PIL import Image


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("DIAGNOSTIC_JSON_SIZE_LIMIT")
    result = json.loads(path.read_bytes())
    if not isinstance(result, dict):
        raise ValueError("DIAGNOSTIC_JSON_OBJECT_REQUIRED")
    return result


def write_json(path: Path, value: object) -> None:
    """Publish a flushed complete file exclusively, including concurrent writers.

    Windows rename is create-only; elsewhere use the existing symbol_store
    hard-link pattern. Reject identical existing outputs too. No power-cut claim.
    """
    data = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".input-diagnostic-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish_capture(staging: Path, output: Path) -> None:
    """Flush all capture files before Windows' no-replace directory rename.

    A crash before rename leaves staging, never a published partial capture.
    Windows directory fsync and physical power-cut durability are not promised.
    """
    if os.name != "nt":
        raise ValueError("DIAGNOSTIC_DIRECTORY_PUBLICATION_REQUIRES_WINDOWS")
    for path in staging.iterdir():
        with path.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    os.rename(staging, output)  # Windows rejects an existing destination, even an empty dir.


def associate_saved(
    inputs: dict[str, Any],
    base: dict[str, Any],
    candidate: dict[str, Any],
    source_id: str,
    sequence: int,
    position: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prove a stored domain binding and exact geometry; never use detection ordinal."""
    sources = [s for s in inputs["photos"] if s["id"] == source_id]
    boards = [
        b
        for b in inputs["boards"]
        if b["source_image_id"] == source_id
        and b["sequence_number"] == sequence
        and b["position_index"] == position
    ]
    if len(sources) != 1 or len(boards) != 1:
        raise ValueError("DIAGNOSTIC_SOURCE_SEQUENCE_AMBIGUOUS")
    source, board = sources[0], boards[0]
    geometry = board["board_geometry"]
    binding = geometry.get("neuralProposalBinding") or {}
    confirmed = binding.get("confirmedRange") or {}
    start, end = confirmed.get("sequenceRangeStart"), confirmed.get("sequenceRangeEnd")
    if (
        type(start) is not int
        or type(end) is not int
        or not start <= sequence <= end
        or sequence != start + position
        or geometry.get("attestedRangeStart") != start
        or geometry.get("attestedRangeEnd") != end
        or binding.get("sourceChecksumSha256") != source["checksum_sha256"]
        or binding.get("sourceWidth") != source["oriented_width"]
        or binding.get("sourceHeight") != source["oriented_height"]
        or binding.get("gameId") != inputs["gameId"]
        or [a for a in binding.get("assignments", []) if a.get("positionIndex") == position]
        != [{"detectionId": geometry.get("detectionId"), "positionIndex": position}]
    ):
        raise ValueError("DIAGNOSTIC_SEQUENCE_BINDING_MISMATCH")
    expected = [[node["x"], node["y"]] for node in geometry["latticeNodes"]]
    for saved in (base, candidate):
        if (
            saved.get("status") != "ok"
            or saved.get("sourceId") != source_id
            or saved.get("sourceChecksum") != source["checksum_sha256"]
            or (saved.get("width"), saved.get("height"))
            != (source["oriented_width"], source["oriented_height"])
        ):
            raise ValueError("DIAGNOSTIC_SAVED_SOURCE_MISMATCH")
    matches = [d for d in base["detections"] if d.get("nodes") == expected]
    if len(matches) != 1:
        raise ValueError("DIAGNOSTIC_SAVED_BASE_GEOMETRY_AMBIGUOUS")
    baseline = matches[0]
    matches = [d for d in candidate["detections"] if d["screenQuad"] == baseline["screenQuad"]]
    if len(matches) != 1:
        raise ValueError("DIAGNOSTIC_DETECTOR_CORRESPONDENCE_UNAVAILABLE")
    return source, board, baseline, matches[0]


def source_pin(path: Path, metadata: dict[str, Any]) -> tuple[SourcePin, Any]:
    frame = CanonicalSourceLoader().load(
        path, expected_source_checksum_sha256=metadata["checksum_sha256"]
    )
    identity = frame.source
    if (
        identity.normalized_pixel_checksum_sha256 != metadata["normalized_pixel_checksum_sha256"]
        or (identity.width, identity.height)
        != (metadata["oriented_width"], metadata["oriented_height"])
        or identity.exif_orientation != metadata["exif_orientation"]
        or identity.normalization_adapter_version != metadata["normalization_adapter_version"]
        or identity.coordinate_space != metadata["coordinate_space"]
    ):
        raise ValueError("DIAGNOSTIC_CANONICAL_SOURCE_MISMATCH")
    return SourcePin(
        source_id=metadata["id"],
        source_sha256=metadata["checksum_sha256"],
        normalized_pixel_sha256=identity.normalized_pixel_checksum_sha256,
        rgb_bytes_sha256=array_sha256(frame.rgb),
        width=identity.width,
        height=identity.height,
        exif_orientation=identity.exif_orientation,
        decoder_version=identity.normalization_adapter_version,
        coordinate_space=identity.coordinate_space,
    ), frame.rgb


def capture(args: argparse.Namespace) -> None:
    inputs = read_json(args.comparison / "inputs.json")
    saved = {
        kind: read_json(args.comparison / kind / f"{args.source}.json")
        for kind in ("base", "candidate")
    }
    source, board, base, candidate = associate_saved(
        inputs, saved["base"], saved["candidate"], args.source, args.sequence, args.position
    )
    original = (args.data_root / source["relative_path"]).resolve()
    if not original.is_relative_to(args.data_root.resolve()):
        raise ValueError("DIAGNOSTIC_SOURCE_PATH_ESCAPE")
    pin, rgb = source_pin(original, source)
    records = {}
    images = {}
    for kind, detection, directory in (
        ("base", base, args.base_bundle),
        ("candidate", candidate, args.candidate_bundle),
    ):
        bundle_path = directory / "bundle.json"
        if hashlib.sha256(bundle_path.read_bytes()).hexdigest() != saved[kind]["bundleSha256"]:
            raise ValueError("DIAGNOSTIC_MODEL_BUNDLE_MISMATCH")
        bundle = read_json(bundle_path)
        preset = bundle["preset"]
        screen_preset = ScreenPreset.model_validate(preset["screen"])
        board_preset = BoardPreset.model_validate(preset["board"])
        quad = cast(
            tuple[Point, Point, Point, Point], tuple(tuple(p) for p in detection["screenQuad"])
        )
        screen, crop, canvas_pixels, crop_pixels = input_stages(
            rgb,
            pin,
            quad,
            screen_preset,
            board_preset,
        )
        nodes = detection.get("nodes")
        domain_nodes = None if nodes is None else [{"x": p[0], "y": p[1]} for p in nodes]
        visibility = (
            lattice_visibility(
                lattice_cell_quads(domain_nodes, width=pin.width, height=pin.height),
                width=pin.width,
                height=pin.height,
            )
            if nodes
            else []
        )
        geometry = board["board_geometry"]
        blockers = neural_auto_crop_blockers(
            policy=NEURAL_AUTO_CROP_POLICY,
            detection={
                "latticeNodes": domain_nodes,
                "cellVisibility": visibility,
                "structurallyValid": detection["structurallyValid"],
                "reasonCodes": detection["reasons"],
                "detectionId": geometry["detectionId"] if kind == "base" else None,
            },
            binding=geometry["neuralProposalBinding"] if kind == "base" else None,
            position=args.position,
            width=pin.width,
            height=pin.height,
        )
        record = InputDiagnostic(
            opencv_version=cv2.__version__,
            source=pin,
            model=ModelPin(
                version_id=saved[kind]["versionId"],
                bundle_sha256=saved[kind]["bundleSha256"],
                preset_sha256=digest(preset),
                preprocessing_version=preset["preprocessing_version"],
            ),
            archived_preset=preset,
            sequence_number=args.sequence,
            position_index=args.position,
            association_basis="exact_saved_nodes_then_unique_equal_detector_quad",
            screen_quad=quad,
            screen_preset=screen_preset,
            board_preset=board_preset,
            screen=screen,
            board=crop,
            raw_nodes=NodeObservation(nodes=None, unavailable_reason="NOT_ARCHIVED"),
            fitted_nodes=NodeObservation(
                nodes=nodes, unavailable_reason=None if nodes else "NOT_ARCHIVED"
            ),
            reason_codes=detection["reasons"],
            historical_disposition=geometry.get("structuredDisposition")
            if kind == "base"
            else None,
            current_policy=NEURAL_AUTO_CROP_POLICY,
            current_policy_blockers=list(blockers),
            current_policy_verdict="blocked" if blockers else "unavailable",
            diagnostic_use=DiagnosticUse(
                source_id=pin.source_id,
                source_sha256=pin.source_sha256,
                normalized_pixel_sha256=pin.normalized_pixel_sha256,
            ),
        )
        reconstruct_input(record, rgb)
        records[kind] = record
        images[kind] = (canvas_pixels, crop_pixels)
    if args.output.exists():
        raise ValueError("DIAGNOSTIC_OUTPUT_ALREADY_EXISTS")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only after both records and their pixels pass replay. An interrupted
    # write leaves a recognizable staging directory, never a completed report.
    staging = Path(tempfile.mkdtemp(prefix=".input-diagnostic-", dir=args.output.parent))
    for kind, record in records.items():
        write_json(staging / f"{kind}.json", encode_record(record))
        for stage, pixels in zip(("screen", "board"), images[kind], strict=True):
            Image.fromarray(pixels).save(staging / f"{kind}-{stage}.png")
            tensor = pixels.transpose(2, 0, 1).astype("<f4")
            np.save(
                staging / f"{kind}-{stage}.npy",
                tensor[None] if stage == "screen" else tensor,
                allow_pickle=False,
            )
    write_json(
        staging / "report.json",
        {
            "schemaVersion": "full-board-diagnostic-report-v1",
            "sourcePath": str(original),
            "sequenceNumber": args.sequence,
            "records": {kind: encode_record(record)["sha256"] for kind, record in records.items()},
            "diagnosticUse": diagnostic_uses(records.values()),
            "limitations": [
                "No new inference. Raw nodes and a bound human GT are unavailable.",
                "Policy projection cannot authorize acceptance; "
                "immutable proposals are not verified.",
                "Candidate lacks an archived sequence binding; the same unique detector quad "
                "is a diagnostic correspondence only.",
                "Board tensor is the exact CHW sample before runtime stacking, "
                "not a historical full batch.",
                "T4 must enforce diagnostic source/copy/group exclusion; "
                "this report does not change the ledger.",
            ],
        },
    )
    publish_capture(staging, args.output)
    print(f"Saved input diagnostics: {args.output}")


def replay(args: argparse.Namespace) -> None:
    record = decode_record(read_json(args.record))
    frame = CanonicalSourceLoader().load(
        args.original, expected_source_checksum_sha256=record.source.source_sha256
    )
    if (
        frame.source.normalized_pixel_checksum_sha256 != record.source.normalized_pixel_sha256
        or frame.source.exif_orientation != record.source.exif_orientation
        or frame.source.normalization_adapter_version != record.source.decoder_version
        or frame.source.coordinate_space != record.source.coordinate_space
    ):
        raise ValueError("DIAGNOSTIC_CANONICAL_SOURCE_MISMATCH")
    reconstruct_input(record, frame.rgb)
    print("Replay verified: RGB and float32 tensor hashes match both stages.")


def readiness(args: argparse.Namespace) -> None:
    from game_predictor_api.config import get_settings
    from game_predictor_api.storage.database import create_maintenance_database_engine
    from game_predictor_api.storage.grid_diagnostic_readiness import read_readiness

    engine = create_maintenance_database_engine(get_settings())
    try:
        result = read_readiness(
            engine,
            args.game,
            args.artifact_root,
            max_sources=args.max_sources,
            after_source_id=args.after_source,
            timeout_seconds=args.timeout,
        )
        if args.output.exists():
            raise ValueError("DIAGNOSTIC_OUTPUT_ALREADY_EXISTS")
        write_json(args.output, result)
        print(f"Readiness {result['status']}: {result['qualifiedHumanBoards']} human boards.")
    finally:
        engine.dispose()


def frozen(args: argparse.Namespace) -> None:
    from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot

    if args.max_sources < 1 or args.output.exists():
        raise ValueError("DIAGNOSTIC_SNAPSHOT_BUDGET_OR_OUTPUT_INVALID")
    snapshot = GridCohortSnapshot(args.artifact_root, args.manifest, args.manifest_sha)
    roles: dict[str, dict[str, int]] = {}
    count, complete = 0, True
    for source in snapshot.sources():
        if count == args.max_sources:
            complete = False
            break
        count += 1
        role = source["role"] or "UNASSIGNED"
        totals = roles.setdefault(
            role, {"photos": 0, "usedPhotos": 0, "humanLabels": 0, "screenEligiblePhotos": 0}
        )
        totals["photos"] += 1
        totals["usedPhotos"] += int(source["used"])
        if source["used"]:
            totals["humanLabels"] += len(source["targets"])
            totals["screenEligiblePhotos"] += int(source["screenEligible"])
    if complete:
        for role, expected in snapshot.manifest["counts"].items():
            actual = roles.get(role, {})
            if expected != {
                "boards": actual.get("humanLabels", 0),
                "photos": actual.get("usedPhotos", 0),
                "fullPhotos": actual.get("screenEligiblePhotos", 0),
            }:
                raise ValueError("DIAGNOSTIC_FROZEN_COUNTS_MISMATCH")
    write_json(
        args.output,
        {
            "schemaVersion": "grid-diagnostic-frozen-readiness-v1",
            "gameId": snapshot.manifest["gameId"],
            "cohortId": snapshot.manifest["cohortId"],
            "manifestPath": args.manifest,
            "manifestSha256": args.manifest_sha,
            "status": "complete" if complete else "partial",
            "populationComplete": complete,
            "maxSources": args.max_sources,
            "sourceCount": count,
            "roles": roles,
            "evidenceTime": "historical_frozen_snapshot",
            "liveEligibility": None,
            "independentGroups": None,
            "diagnosticUse": [],
            "ledgerModified": False,
            "limitations": [
                "Metadata only; no pixels read and no model-design use.",
                "Frozen labels and roles are history, not current admission or independence.",
            ],
        },
    )
    print(f"Frozen readiness {'complete' if complete else 'partial'}: {count} sources.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("capture")
    for flag in ("comparison", "data-root", "base-bundle", "candidate-bundle", "output"):
        collect.add_argument(f"--{flag}", type=Path, required=True)
    collect.add_argument("--source", type=lambda value: str(UUID(value)), required=True)
    collect.add_argument("--sequence", type=int, required=True)
    collect.add_argument("--position", type=int, choices=range(9), required=True)
    check = commands.add_parser("replay")
    check.add_argument("--record", type=Path, required=True)
    check.add_argument("--original", type=Path, required=True)
    ready = commands.add_parser("readiness")
    ready.add_argument("--game", type=UUID, required=True)
    ready.add_argument("--artifact-root", type=Path, required=True)
    ready.add_argument("--max-sources", type=int, default=250)
    ready.add_argument("--after-source", type=UUID)
    ready.add_argument("--timeout", type=float, default=60)
    ready.add_argument("--output", type=Path, required=True)
    history = commands.add_parser("frozen")
    history.add_argument("--artifact-root", type=Path, required=True)
    history.add_argument("--manifest", required=True)
    history.add_argument("--manifest-sha", required=True)
    history.add_argument("--max-sources", type=int, default=5000)
    history.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"capture": capture, "replay": replay, "readiness": readiness, "frozen": frozen}[args.command](
        args
    )


if __name__ == "__main__":
    main()
