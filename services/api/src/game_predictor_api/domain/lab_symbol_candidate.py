"""Immutable lab-origin symbol candidates; no cohort or human approval is manufactured."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from .symbol_model_snapshots import LAB_RGB_SYMBOL_MODEL_VERSION

CANDIDATE_FORMAT = "lab-symbol-candidate-v1"
MUMIE_ELIGIBILITY_ID = "5b6af3ef03d77ff7dbc3e7c2f45f0586f92d24088b5871316acc4aadf044ac7c"
MUMIE_R2_ONNX_SHA256 = "e4f9b2610407be8724fe0b5f26a5efa595b7b575af8434b73c19a39e04737095"
MUMIE_R2_DATASET_ID = "8adaaaf621e5506c5618559ec433f06f4eed13b75465d394ae2af0be3717f40d"
MUMIE_CLASS_LABELS = ("10", "J", "Q", "K", "A", "Ra", "Sarkofag", "Mumia", "Faraon", "Sfinks")
MUMIE_CLASS_CODES = ("10", "J", "Q", "K", "A", "RA", "SARKOFAG", "MUMIA", "FARAON", "SFINKS")
_FILES = ("model.onnx", "classes.json", "calibration.json", "eligibility.json", "origin.json")
_MAX_BYTES = 64 * 1024 * 1024


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _reject_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("LAB_CANDIDATE_LINK_UNSUPPORTED")
        if not item.exists():
            continue
        info = item.lstat()
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024
        ):
            raise ValueError("LAB_CANDIDATE_LINK_UNSUPPORTED")


def _read(path: Path) -> bytes:
    _reject_links(path)
    with path.open("rb") as stream:
        content = stream.read(_MAX_BYTES + 1)
    if len(content) > _MAX_BYTES:
        raise ValueError("LAB_CANDIDATE_ARTIFACT_TOO_LARGE")
    return content


def _eligibility(content: bytes) -> dict[str, object]:
    envelope = json.loads(content)
    if not isinstance(envelope, dict):
        raise ValueError("LAB_CANDIDATE_ELIGIBILITY_DRIFT")
    payload = envelope.get("payload")
    if (
        not isinstance(payload, dict)
        or envelope.get("sha256") != MUMIE_ELIGIBILITY_ID
        or digest(payload) != MUMIE_ELIGIBILITY_ID
        or payload.get("classes") != list(MUMIE_CLASS_LABELS)
    ):
        raise ValueError("LAB_CANDIDATE_ELIGIBILITY_DRIFT")
    # The exact accepted digest binds all source reports, gates and calibration.
    # Preparing this package additionally performs original live pin/semantic checks.
    return payload


@dataclass(frozen=True, slots=True)
class LabSymbolCandidate:
    fingerprint: str
    manifest_relative_path: str
    manifest_sha256: str
    game_id: UUID
    manifest: Mapping[str, object]


def prepare_mumie_candidate(
    artifact_root: Path,
    *,
    game_id: UUID,
    onnx_content: bytes,
    eligibility_content: bytes,
) -> LabSymbolCandidate:
    """Publish bytes already qualified by the CLI's original-source preflight."""
    _eligibility(eligibility_content)
    if hashlib.sha256(onnx_content).hexdigest() != MUMIE_R2_ONNX_SHA256:
        raise ValueError("LAB_CANDIDATE_MODEL_DRIFT")
    identity = {
        "format": CANDIDATE_FORMAT,
        "gameId": str(game_id),
        "origin": "lab_import",
        "scope": "mumie_pilot",
        "modelVersion": LAB_RGB_SYMBOL_MODEL_VERSION,
        "preprocessingVersion": "rgb96-bilinear-antialias64-float32-v1",
        "renderVersion": "source-direct-full-quad-rgb96-v1",
        "paddingFraction": 0.0,
        "cropSize": 96,
        "inputSize": 64,
        "classCodes": list(MUMIE_CLASS_CODES),
        "temperature": 1.05,
        "onnxSha256": MUMIE_R2_ONNX_SHA256,
        "eligibilityId": MUMIE_ELIGIBILITY_ID,
        "datasetId": MUMIE_R2_DATASET_ID,
        "developmentOrigins": {"human": 283, "ai_visual_assessment": 44},
        "populationAccuracy": None,
        "humanSelectedControls": {"correct": 34, "total": 34},
        "r2CombinedAccepted": False,
        "v5Accepted": False,
    }
    fingerprint = digest(identity)
    relative = Path("models/lab-symbol-candidates") / fingerprint
    root = artifact_root.absolute()
    destination = root / relative
    _reject_links(destination)
    bodies = {
        "model.onnx": onnx_content,
        "classes.json": canonical({"classCodes": list(MUMIE_CLASS_CODES)}),
        "calibration.json": canonical({"temperature": 1.05}),
        "eligibility.json": eligibility_content,
        "origin.json": canonical(identity),
    }
    artifacts = {}
    for key, name in (
        ("onnx", "model.onnx"),
        ("classes", "classes.json"),
        ("calibration", "calibration.json"),
        ("gateReport", "eligibility.json"),
        ("origin", "origin.json"),
    ):
        artifacts[key] = {
            "relativePath": (relative / name).as_posix(),
            "sha256": hashlib.sha256(bodies[name]).hexdigest(),
        }
    manifest = {
        "format": CANDIDATE_FORMAT,
        "candidateFingerprint": fingerprint,
        "identity": identity,
        "modelVersion": LAB_RGB_SYMBOL_MODEL_VERSION,
        "classCodes": list(MUMIE_CLASS_CODES),
        "artifacts": artifacts,
    }
    bodies["manifest.json"] = canonical(manifest)
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        _reject_links(destination.parent)
        stage = destination.parent / (".prepare-" + uuid4().hex)
        stage.mkdir()
        for name, content in bodies.items():
            with (stage / name).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        # A concurrent identical publication is checked below. Keep our own
        # abandoned stage for diagnosis; no recursive cleanup of data.
        with suppress(FileExistsError):
            stage.rename(destination)
    for name, expected in bodies.items():
        if _read(destination / name) != expected:
            raise ValueError("LAB_CANDIDATE_EXISTING_ARTIFACT_DRIFT")
    return load_lab_symbol_candidate(root, fingerprint)


def load_lab_symbol_candidate(artifact_root: Path, fingerprint: str) -> LabSymbolCandidate:
    """Fail closed on path, identity, manifest and every managed artifact."""
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("LAB_CANDIDATE_FINGERPRINT_INVALID")
    relative = Path("models/lab-symbol-candidates") / fingerprint
    root = artifact_root.absolute()
    directory = root / relative
    content = _read(directory / "manifest.json")
    manifest = json.loads(content)
    if not isinstance(manifest, dict):
        raise ValueError("LAB_CANDIDATE_MANIFEST_DRIFT")
    identity = manifest.get("identity")
    if (
        set(manifest)
        != {"format", "candidateFingerprint", "identity", "modelVersion", "classCodes", "artifacts"}
        or not isinstance(identity, dict)
        or set(identity)
        != {
            "format",
            "gameId",
            "origin",
            "scope",
            "modelVersion",
            "preprocessingVersion",
            "renderVersion",
            "paddingFraction",
            "cropSize",
            "inputSize",
            "classCodes",
            "temperature",
            "onnxSha256",
            "eligibilityId",
            "datasetId",
            "developmentOrigins",
            "populationAccuracy",
            "humanSelectedControls",
            "r2CombinedAccepted",
            "v5Accepted",
        }
        or manifest.get("format") != CANDIDATE_FORMAT
        or manifest.get("candidateFingerprint") != fingerprint
        or digest(identity) != fingerprint
        or manifest.get("modelVersion") != LAB_RGB_SYMBOL_MODEL_VERSION
        or manifest.get("classCodes") != list(MUMIE_CLASS_CODES)
    ):
        raise ValueError("LAB_CANDIDATE_MANIFEST_DRIFT")
    if not isinstance(identity["gameId"], str):
        raise ValueError("LAB_CANDIDATE_GAME_INVALID")
    game_id = UUID(identity["gameId"])
    # Rebuild the exact allowed identity, rather than accepting a resigned
    # manifest with a different calibration, origin, dictionary or gate scope.
    expected_identity = {
        **identity,
        "format": CANDIDATE_FORMAT,
        "origin": "lab_import",
        "scope": "mumie_pilot",
        "modelVersion": LAB_RGB_SYMBOL_MODEL_VERSION,
        "preprocessingVersion": "rgb96-bilinear-antialias64-float32-v1",
        "renderVersion": "source-direct-full-quad-rgb96-v1",
        "paddingFraction": 0.0,
        "cropSize": 96,
        "inputSize": 64,
        "classCodes": list(MUMIE_CLASS_CODES),
        "temperature": 1.05,
        "onnxSha256": MUMIE_R2_ONNX_SHA256,
        "eligibilityId": MUMIE_ELIGIBILITY_ID,
        "datasetId": MUMIE_R2_DATASET_ID,
        "developmentOrigins": {"human": 283, "ai_visual_assessment": 44},
        "populationAccuracy": None,
        "humanSelectedControls": {"correct": 34, "total": 34},
        "r2CombinedAccepted": False,
        "v5Accepted": False,
    }
    if canonical(identity) != canonical(expected_identity):
        raise ValueError("LAB_CANDIDATE_ORIGIN_DRIFT")
    expected_files = {*_FILES, "manifest.json"}
    _reject_links(directory)
    if {p.name for p in directory.iterdir()} != expected_files:
        raise ValueError("LAB_CANDIDATE_INVENTORY_DRIFT")
    artifacts = manifest["artifacts"]
    expected_keys = {"onnx", "classes", "calibration", "gateReport", "origin"}
    if not isinstance(artifacts, dict) or set(artifacts) != expected_keys:
        raise ValueError("LAB_CANDIDATE_INVENTORY_DRIFT")
    for key, name in zip(
        ("onnx", "classes", "calibration", "gateReport", "origin"), _FILES, strict=True
    ):
        body = _read(directory / name)
        expected = {
            "relativePath": (relative / name).as_posix(),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        if artifacts[key] != expected:
            raise ValueError("LAB_CANDIDATE_ARTIFACT_DRIFT")
        if name == "eligibility.json":
            _eligibility(body)
        elif name == "origin.json" and json.loads(body) != identity:
            raise ValueError("LAB_CANDIDATE_ORIGIN_DRIFT")
        elif name == "model.onnx" and expected["sha256"] != MUMIE_R2_ONNX_SHA256:
            raise ValueError("LAB_CANDIDATE_MODEL_DRIFT")
        elif name == "classes.json" and json.loads(body) != {"classCodes": list(MUMIE_CLASS_CODES)}:
            raise ValueError("LAB_CANDIDATE_CLASS_DRIFT")
        elif name == "calibration.json" and json.loads(body) != {"temperature": 1.05}:
            raise ValueError("LAB_CANDIDATE_CALIBRATION_DRIFT")
    return LabSymbolCandidate(
        fingerprint,
        (relative / "manifest.json").as_posix(),
        hashlib.sha256(content).hexdigest(),
        game_id,
        manifest,
    )
