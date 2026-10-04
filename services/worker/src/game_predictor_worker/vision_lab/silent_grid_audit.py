"""TASK-0831 audit of silent grid errors: saved 777 grids against the ``neural_grid`` network.

``python -m game_predictor_worker.vision_lab.silent_grid_audit <command> --audit <dir>``

saved     compact the read-only geometry export (``scripts/vision_lab_geometry_export.py``,
          ``candidates.jsonl``) into ``saved.jsonl``: one line per photo with every live
          board, its label level, symbol signals and the identifiers of the correction tools
infer     run the frozen run-1 model on every photo of ``saved.jsonl``; one line per photo in
          ``network.jsonl``; resumable (a torn last line is cut, finished photos are
          skipped), bounded by ``--max-seconds`` and a ``STOP`` file, progress in
          ``infer-status.json``
parity    the same photos through ONNX Runtime CPU and the torch runner (node deviation)
compare   classify every saved board against the network boards of its photo
          (``boards.jsonl``, ``summary.json``, ``suspects.json``)
render    comparison images (saved grid red, network grid green) for the ranking
refs      attach to every suspect one current symbol-cell review id (the id the existing
          ``Zła siatka`` action takes) from a TSV produced by a separate read-only query;
          this module never connects to the database
board-ids the recognized board ids of the suspects, one per line (input of that query)

The audit never writes the database and never reads a sealed role through the lab: the
photos and grids come from the production export only. Classification is symmetric — a
disagreement says one of the two grids is wrong, not which one; that needs inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from .neural_grid_data import LATTICE, ByteImage, FloatArray, transform_points
from .neural_grid_metrics import MAX_NME, MAX_NODE_ERROR, board_errors, hungarian, quad_iou

AUDIT_VERSION: Final = "silent-grid-audit-v1"
DATA_ROOT: Final = Path(
    os.environ.get(
        "VISION_LAB_DATA_ROOT", str(Path.home() / "Documents" / "game_predictor_vision_data")
    )
)
RUN1_BUNDLE: Final = (
    DATA_ROOT
    / "neural-grid-runs"
    / "43933ac8d7d443c8b9079630a83de2e6"
    / "exports"
    / "2cd19738367121e6-round3"
)
SNAPSHOT_V2_SPLIT: Final = (
    DATA_ROOT
    / "production-geometry-snapshots"
    / "286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59"
    / "split.json"
)
GAME_777: Final = "bfc4f949-5c14-4850-b02a-db99610bcfa5"
REVIEWER_ORIGIN: Final = "http://127.0.0.1:3001"

# D-483 tolerance (unchanged) decides "within tolerance".
MATCH_MIN_IOU: Final = 0.5
# Pairs considered for a period shift or an overlap: a one-row shift has IoU 0.5, a two-row
# shift 0.2, a two-column shift 0.43.
OVERLAP_MIN_IOU: Final = 0.1
# A saved grid is a period shift of a network grid when the network lattice moved by whole
# cells reproduces it: NME <= 0.03 and max node error <= 0.08 of the saved diagonal (looser
# than D-483 because the moved lattice is an extrapolation), and at most half of the
# unshifted NME.
SHIFT_MAX_NME: Final = 0.03
SHIFT_MAX_NODE_ERROR: Final = 0.08
SHIFTS: Final = tuple((dc, dr) for dr in range(-2, 3) for dc in range(-2, 3))
NEAR_TOLERANCE_NME: Final = 0.04
NEAR_TOLERANCE_MAX: Final = 0.10

WITHIN = "within_tolerance"
COLUMN_SHIFT = "column_shift"
ROW_SHIFT = "row_shift"
DIAGONAL_SHIFT = "diagonal_shift"
SCALE_ROTATION = "scale_rotation"
SAVED_ONLY = "saved_only"
NETWORK_ONLY = "network_only"
CLASSES: Final = (
    COLUMN_SHIFT,
    ROW_SHIFT,
    DIAGONAL_SHIFT,
    SCALE_ROTATION,
    SAVED_ONLY,
    NETWORK_ONLY,
    WITHIN,
)
SHIFT_CLASSES: Final = (COLUMN_SHIFT, ROW_SHIFT, DIAGONAL_SHIFT)

_SAVED: Final = "saved.jsonl"
_NETWORK: Final = "network.jsonl"
_STATUS: Final = "infer-status.json"
_STOP: Final = "STOP"


# --- small file helpers -----------------------------------------------------------------------


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def dumps_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def write_json_atomic(path: Path, value: Any) -> str:
    data = json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def repair_jsonl(path: Path) -> set[str]:
    """Cut a torn last line (interrupted append) and return the finished ``imageId`` set."""

    if not path.exists():
        return set()
    data = path.read_bytes()
    complete, _, torn = data.rpartition(b"\n")
    if torn:
        with path.open("r+b") as stream:
            stream.truncate(len(complete) + 1 if complete else 0)
            stream.flush()
            os.fsync(stream.fileno())
    done = set()
    for line in complete.split(b"\n") if complete else []:
        if line.strip():
            done.add(str(json.loads(line)["imageId"]))
    return done


# --- saved grids ------------------------------------------------------------------------------


def compact_board(row: Mapping[str, Any]) -> dict[str, Any]:
    label = row["label"]
    signals = row["symbolSignals"]
    return {
        "recognizedBoardId": row["recognizedBoardId"],
        "positionIndex": int(row["positionIndex"]),
        "sequenceNumber": row["sequenceNumber"],
        "level": label["level"],
        "basis": label["basis"],
        "approvalActor": label["approvalActor"],
        "geometryRevision": label["geometryRevision"],
        "quadSource": row["geometry"]["quadSource"],
        "nodes": row["geometry"]["nodes"],
        "cells": int(signals["cells"]),
        "humanDecidedCells": int(signals["humanDecidedCells"]),
        "pageRow": row["difficulty"].get("pageRow"),
        "pageColumn": row["difficulty"].get("pageColumn"),
    }


def compact_saved(candidates: Path, output: Path, roles: Mapping[str, str]) -> dict[str, Any]:
    """``candidates.jsonl`` (rows grouped by photo) -> one line per photo in ``saved.jsonl``."""

    if output.exists():
        raise ValueError("SILENT_GRID_SAVED_EXISTS")
    temporary = output.with_name(f".{output.name}.tmp")
    seen: set[str] = set()
    photos = boards = 0
    levels: Counter[str] = Counter()
    current: dict[str, Any] | None = None
    with temporary.open("wb") as stream:

        def flush(photo: dict[str, Any] | None) -> None:
            nonlocal photos
            if photo is not None:
                photo["boards"].sort(key=lambda b: b["positionIndex"])
                stream.write(dumps_line(photo))
                photos += 1

        for row in iter_jsonl(candidates):
            image_id = str(row["sourceImageId"])
            if current is None or current["imageId"] != image_id:
                if image_id in seen:
                    raise ValueError("SILENT_GRID_CANDIDATES_NOT_GROUPED")
                flush(current)
                seen.add(image_id)
                current = {
                    "imageId": image_id,
                    "gameId": row["gameId"],
                    "importJobId": row["importJobId"],
                    "sha256": row["sourceChecksumSha256"],
                    "relativePath": row["sourceRelativePath"],
                    "width": int(row["orientedWidth"]),
                    "height": int(row["orientedHeight"]),
                    "expectedBoards": int(row["expectedBoardsOnImage"]),
                    "family": row["family"].get("sourceDisplayName"),
                    "familyId": row["family"].get("familyId"),
                    "snapshotRole": roles.get(image_id),
                    "boards": [],
                }
            current["boards"].append(compact_board(row))
            boards += 1
            levels[row["label"]["level"]] += 1
        flush(current)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    return {"photos": photos, "boards": boards, "levels": dict(sorted(levels.items()))}


def snapshot_roles(split: Path = SNAPSHOT_V2_SPLIT) -> dict[str, str]:
    """Role of each photo in snapshot v2 (ids only; no sample or label is opened)."""

    if not split.exists():
        return {}
    document = json.loads(split.read_text(encoding="utf-8"))
    return {str(row[0]): str(row[1]) for row in document["selection"]}


# --- network inference ------------------------------------------------------------------------


def bundle_identity(bundle: Path) -> dict[str, Any]:
    document = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    return {
        "bundle": str(bundle),
        "weights_sha256": document["weights_sha256"],
        "files": document["files"],
        "provenance": document.get("provenance"),
        "preset_fingerprint": document.get("preset_fingerprint"),
    }


def build_engine(bundle: Path, runner: str, threads: int) -> Any:
    """``onnx`` = the exported CPU graphs; ``torch-cuda`` = the bundle's ``weights.pt`` on GPU.

    Both run the same ``NeuralGridEngine`` decoding; the weights are checksum-bound to the
    bundle (parity of the two runners is measured by the ``parity`` command).
    """

    if runner == "onnx":
        from .neural_grid_inference import onnx_engine

        return onnx_engine(bundle, threads=threads)
    import torch

    from .neural_grid_model import NeuralGridNetwork
    from .neural_grid_protocol import Preset
    from .neural_grid_training import torch_engine

    document = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    content = (bundle / "weights.pt").read_bytes()
    if hashlib.sha256(content).hexdigest() != document["weights_sha256"]:
        raise ValueError("SILENT_GRID_WEIGHTS_CHECKSUM_MISMATCH")
    preset = Preset.model_validate(document["preset"])
    network = NeuralGridNetwork(preset.board.stride)
    network.load_state_dict(torch.load(io.BytesIO(content), map_location="cpu", weights_only=True))
    device = "cuda" if runner == "torch-cuda" else "cpu"
    network = network.to(device).eval()
    torch.set_num_threads(threads)
    return torch_engine(network, preset, device)


def source_path(artifact_root: Path, relative: str) -> Path:
    path = (artifact_root / "data" / relative).resolve()
    if not path.is_relative_to((artifact_root / "data").resolve()):
        raise ValueError("SILENT_GRID_SOURCE_PATH_ESCAPES_ROOT")
    return path


def load_photo(artifact_root: Path, photo: Mapping[str, Any]) -> ByteImage:
    """Checksum-verified RGB in exif-normalized orientation (as the export coordinates)."""

    path = source_path(artifact_root, str(photo["relativePath"]))
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != photo["sha256"]:
        raise ValueError("SOURCE_CHECKSUM_MISMATCH")
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (photo["height"], photo["width"]):
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)  # applies the EXIF orientation
    if bgr is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    if bgr.shape[:2] != (photo["height"], photo["width"]):
        raise ValueError("ORIENTED_SIZE_MISMATCH")
    return np.ascontiguousarray(bgr[:, :, ::-1])


def network_boards_record(engine: Any, rgb: ByteImage) -> list[dict[str, Any]]:
    boards = []
    for detection in engine.analyse(rgb):
        nodes = detection.nodes
        boards.append(
            {
                "nodes": None
                if nodes is None
                else [[round(float(x), 2), round(float(y), 2)] for x, y in nodes],
                "score": round(float(detection.score), 4),
                "fitInliers": int(detection.fit_inliers),
                "fitResidual": None
                if detection.fit_residual is None or not np.isfinite(detection.fit_residual)
                else round(float(detection.fit_residual), 6),
                "reasons": list(detection.reasons),
            }
        )
    return boards


def prefetched(
    items: Sequence[dict[str, Any]], load: Callable[[dict[str, Any]], ByteImage], workers: int
) -> Iterator[tuple[dict[str, Any], ByteImage | Exception]]:
    """Decode ahead in threads (bounded window), yield in order."""

    def task(item: dict[str, Any]) -> ByteImage | Exception:
        try:
            return load(item)
        except (OSError, ValueError) as error:
            return error

    with ThreadPoolExecutor(max_workers=workers) as pool:
        window: deque[tuple[dict[str, Any], Future[ByteImage | Exception]]] = deque()
        iterator = iter(items)
        for item in iterator:
            window.append((item, pool.submit(task, item)))
            if len(window) >= workers * 4:
                break
        while window:
            item, future = window.popleft()
            nxt = next(iterator, None)
            if nxt is not None:
                window.append((nxt, pool.submit(task, nxt)))
            yield item, future.result()


@dataclass(slots=True)
class InferStatus:
    path: Path
    total: int
    done_before: int
    started: float = field(default_factory=time.perf_counter)
    done: int = 0
    errors: int = 0
    runner: str = ""
    state: str = "running"

    def write(self) -> None:
        elapsed = time.perf_counter() - self.started
        rate = self.done / elapsed if elapsed > 0 else 0.0
        remaining = self.total - self.done_before - self.done
        write_json_atomic(
            self.path,
            {
                "state": self.state,
                "pid": os.getpid(),
                "runner": self.runner,
                "updatedAt": now(),
                "total": self.total,
                "doneBeforeThisProcess": self.done_before,
                "doneThisProcess": self.done,
                "errorsThisProcess": self.errors,
                "remaining": remaining,
                "photosPerSecond": rate,
                "etaSeconds": remaining / rate if rate > 0 else None,
            },
        )


def run_inference(
    audit: Path,
    artifact_root: Path,
    *,
    bundle: Path,
    runner: str,
    threads: int,
    decode_workers: int,
    max_seconds: float,
    limit: int | None = None,
    shard: int = 0,
    shards: int = 1,
) -> dict[str, Any]:
    if not 0 <= shard < shards:
        raise ValueError("SILENT_GRID_SHARD_INVALID")
    photos = list(iter_jsonl(audit / _SAVED))
    if limit is not None:
        photos = photos[:limit]
    photos = photos[shard::shards]
    output = audit / (_NETWORK if shards == 1 else f"network-{shard}-of-{shards}.jsonl")
    done = repair_jsonl(output)
    todo = [photo for photo in photos if photo["imageId"] not in done]
    identity_path = audit / "network-identity.json"
    identity = {**bundle_identity(bundle), "runner": runner, "auditVersion": AUDIT_VERSION}
    if identity_path.exists():
        previous = json.loads(identity_path.read_text(encoding="utf-8"))
        if previous["weights_sha256"] != identity["weights_sha256"]:
            raise ValueError("SILENT_GRID_MODEL_CHANGED_BETWEEN_PARTS")
        if previous["runner"] != runner:
            raise ValueError("SILENT_GRID_RUNNER_CHANGED_BETWEEN_PARTS")
    else:
        write_json_atomic(identity_path, identity)
    status_name = _STATUS if shards == 1 else f"infer-status-{shard}-of-{shards}.json"
    status = InferStatus(
        audit / status_name, len(photos), len(done & {p["imageId"] for p in photos})
    )
    status.runner = runner
    status.write()
    if not todo:
        status.state = "complete"
        status.write()
        return {"todo": 0, "done": len(done)}
    engine = build_engine(bundle, runner, threads)
    deadline = time.perf_counter() + max_seconds
    stop_file = audit / _STOP
    with output.open("ab") as stream:
        for photo, rgb in prefetched(
            todo, lambda item: load_photo(artifact_root, item), decode_workers
        ):
            started = time.perf_counter()
            record: dict[str, Any] = {"imageId": photo["imageId"], "error": None}
            if isinstance(rgb, Exception):
                record.update(boards=[], seconds=None, error=str(rgb))
                status.errors += 1
            else:
                record["boards"] = network_boards_record(engine, rgb)
                record["seconds"] = round(time.perf_counter() - started, 4)
            stream.write(dumps_line(record))
            status.done += 1
            if status.done % 200 == 0:
                stream.flush()
                os.fsync(stream.fileno())
                status.write()
                if time.perf_counter() > deadline or stop_file.exists():
                    status.state = "stopped"
                    break
        stream.flush()
        os.fsync(stream.fileno())
    remaining = len(photos) - len(repair_jsonl(output) & {p["imageId"] for p in photos})
    status.state = "complete" if remaining == 0 else "stopped"
    status.write()
    return {"processed": status.done, "errors": status.errors, "remaining": remaining}


def run_parity(
    audit: Path, artifact_root: Path, *, bundle: Path, photos: int, threads: int
) -> dict[str, Any]:
    """Max node deviation (px) between the ONNX CPU and torch CUDA runners."""

    items = list(iter_jsonl(audit / _SAVED))
    step = max(1, len(items) // photos)
    sample = items[::step][:photos]
    onnx = build_engine(bundle, "onnx", threads)
    cuda = build_engine(bundle, "torch-cuda", threads)
    deviations: list[float] = []
    count_mismatch = 0
    for photo in sample:
        rgb = load_photo(artifact_root, photo)
        left = [d.nodes for d in onnx.analyse(rgb) if d.nodes is not None]
        right = [d.nodes for d in cuda.analyse(rgb) if d.nodes is not None]
        if len(left) != len(right):
            count_mismatch += 1
            continue
        for a, b in zip(left, right, strict=True):
            deviations.append(float(np.abs(np.asarray(a) - np.asarray(b)).max()))
    return {
        "photos": len(sample),
        "boards": len(deviations),
        "photosWithDifferentBoardCount": count_mismatch,
        "maxNodeDeviationPx": max(deviations) if deviations else None,
        "p99NodeDeviationPx": float(np.percentile(deviations, 99)) if deviations else None,
    }


# --- comparison -------------------------------------------------------------------------------


def corners_of(nodes: NDArray[Any]) -> NDArray[Any]:
    return np.asarray(nodes, np.float32)[[0, 5, 23, 18]]


def lattice_matrix(nodes: NDArray[Any]) -> NDArray[np.float64] | None:
    matrix, _ = cv2.findHomography(LATTICE, np.asarray(nodes, np.float32), 0)
    return None if matrix is None else np.asarray(matrix, np.float64)


@dataclass(frozen=True, slots=True)
class PairEvidence:
    network: int
    iou: float
    nme: float
    max_error: float
    shift: tuple[int, int]
    shift_nme: float
    shift_max_error: float

    @property
    def within(self) -> bool:
        return self.nme <= MAX_NME and self.max_error <= MAX_NODE_ERROR

    @property
    def is_shift(self) -> bool:
        return (
            self.shift != (0, 0)
            and self.shift_nme <= SHIFT_MAX_NME
            and self.shift_max_error <= SHIFT_MAX_NODE_ERROR
            and self.shift_nme <= 0.5 * self.nme
        )


def pair_evidence(
    saved: FloatArray, network: FloatArray, index: int, iou: float, search: bool = True
) -> PairEvidence:
    """Unshifted errors and the best whole-cell shift of the network lattice to the saved grid
    (``search=False`` keeps only the unshifted errors)."""

    nme, max_error = board_errors(network, saved)
    best = ((0, 0), nme, max_error)
    matrix = lattice_matrix(network) if search else None
    if matrix is not None:
        for dc, dr in SHIFTS:
            if (dc, dr) == (0, 0):
                continue
            moved = transform_points(LATTICE + np.array([dc, dr], np.float32), matrix)
            if not np.isfinite(moved).all():
                continue
            shift_nme, shift_max = board_errors(moved, saved)
            if shift_nme < best[1]:
                best = ((dc, dr), shift_nme, shift_max)
    return PairEvidence(index, iou, nme, max_error, best[0], best[1], best[2])


def shift_class(shift: tuple[int, int]) -> str:
    dc, dr = shift
    if dr == 0:
        return COLUMN_SHIFT
    if dc == 0:
        return ROW_SHIFT
    return DIAGONAL_SHIFT


def geometry_descriptors(saved: FloatArray, network: FloatArray) -> dict[str, Any]:
    """Scale ratio (network / saved, sqrt of quad areas), top-edge angle difference, centre
    offset in saved cell widths and heights — to describe a scale/rotation disagreement."""

    a = corners_of(saved).astype(np.float64)
    b = corners_of(network).astype(np.float64)
    area_a = abs(float(cv2.contourArea(a.astype(np.float32))))
    area_b = abs(float(cv2.contourArea(b.astype(np.float32))))
    angle_a = np.degrees(np.arctan2(a[1, 1] - a[0, 1], a[1, 0] - a[0, 0]))
    angle_b = np.degrees(np.arctan2(b[1, 1] - b[0, 1], b[1, 0] - b[0, 0]))
    cell_w = float(np.linalg.norm(a[1] - a[0])) / 5
    cell_h = float(np.linalg.norm(a[3] - a[0])) / 3
    offset = b.mean(axis=0) - a.mean(axis=0)
    return {
        "scaleRatio": float(np.sqrt(area_b / area_a)) if area_a > 0 else float("nan"),
        "angleDifferenceDeg": float((angle_b - angle_a + 180) % 360 - 180),
        "centreOffsetCells": [
            float(offset[0] / max(cell_w, 1e-6)),
            float(offset[1] / max(cell_h, 1e-6)),
        ],
    }


def compare_photo(
    saved_nodes: Sequence[FloatArray], network_nodes: Sequence[FloatArray | None]
) -> tuple[list[dict[str, Any]], list[int]]:
    """Per saved board: class and evidence; plus the network boards that explain nothing.

    D-483 matching first (Hungarian on quad IoU >= 0.5). A saved board within the D-483
    tolerance of its match is ``within_tolerance``. Otherwise every network board overlapping
    it (IoU >= 0.1) is tried with whole-cell lattice shifts; a reproducing shift gives a
    shift class, an IoU >= 0.5 match without one is ``scale_rotation`` and no overlapping
    network board at all is ``saved_only``. A network board that is neither matched nor the
    partner of a saved board is ``network_only``.
    """

    networks = [
        (i, np.asarray(n, np.float32)) for i, n in enumerate(network_nodes) if n is not None
    ]
    ious = np.zeros((len(saved_nodes), len(networks)))
    boxes = [_box(n) for _, n in networks]
    for s, saved in enumerate(saved_nodes):
        box = _box(saved)
        for k, (_, network) in enumerate(networks):
            if _boxes_overlap(box, boxes[k]):
                ious[s, k] = quad_iou(corners_of(network), corners_of(saved))
    cost = np.where(ious >= MATCH_MIN_IOU, 1.0 - ious, 1e9)
    matched = {s: k for s, k in hungarian(cost) if ious[s, k] >= MATCH_MIN_IOU}
    partners: set[int] = set()
    results: list[dict[str, Any]] = []
    for s, saved in enumerate(saved_nodes):
        saved = np.asarray(saved, np.float32)
        match = None
        if s in matched:
            index, network = networks[matched[s]]
            match = pair_evidence(saved, network, index, float(ious[s, matched[s]]), search=False)
        evidence: list[PairEvidence] = []
        if match is None or not match.within:
            for k, (index, network) in enumerate(networks):
                if ious[s, k] >= OVERLAP_MIN_IOU or matched.get(s) == k:
                    evidence.append(pair_evidence(saved, network, index, float(ious[s, k])))
            if match is not None:
                match = next(e for e in evidence if e.network == match.network)
        result: dict[str, Any] = {
            "saved": s,
            "matchedNetwork": None if match is None else match.network,
        }
        chosen: PairEvidence | None = None
        if match is not None and match.within:
            result["class"] = WITHIN
            chosen = match
        else:
            shifts = [e for e in evidence if e.is_shift]
            if shifts:
                chosen = min(shifts, key=lambda e: e.shift_nme)
                result["class"] = shift_class(chosen.shift)
            elif match is not None:
                chosen = match
                result["class"] = SCALE_ROTATION
            elif evidence:
                chosen = max(evidence, key=lambda e: e.iou)
                result["class"] = SCALE_ROTATION
            else:
                result["class"] = SAVED_ONLY
        if chosen is not None:
            partners.add(chosen.network)
            result.update(
                partner=chosen.network,
                iou=chosen.iou,
                nme=chosen.nme,
                maxError=chosen.max_error,
                shift=list(chosen.shift),
                shiftNme=chosen.shift_nme,
                shiftMaxError=chosen.shift_max_error,
            )
            if result["class"] == SCALE_ROTATION:
                result["nearTolerance"] = bool(
                    chosen.nme <= NEAR_TOLERANCE_NME and chosen.max_error <= NEAR_TOLERANCE_MAX
                )
                result["matchedD483"] = match is not None
                result.update(
                    geometry_descriptors(saved, networks_by_index(networks)[chosen.network])
                )
        nearest = max((float(v) for v in ious[s]), default=0.0)
        result["maxIou"] = nearest
        results.append(result)
    matched_networks = {networks[k][0] for k in matched.values()}
    unexplained = [i for i, _ in networks if i not in partners and i not in matched_networks]
    return results, unexplained


def _box(nodes: NDArray[Any]) -> tuple[float, float, float, float]:
    points = np.asarray(nodes, np.float32).reshape(-1, 2)
    low, high = points.min(axis=0), points.max(axis=0)
    return float(low[0]), float(low[1]), float(high[0]), float(high[1])


def _boxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def networks_by_index(networks: Iterable[tuple[int, FloatArray]]) -> dict[int, FloatArray]:
    return dict(networks)


class NetworkOutputs:
    """Random access to the network lines of every ``network*.jsonl`` part (one per shard)."""

    def __init__(self, audit: Path) -> None:
        self.paths = sorted(audit.glob("network*.jsonl"))
        self.offsets: dict[str, tuple[int, int]] = {}
        for number, path in enumerate(self.paths):
            with path.open("rb") as stream:
                position = stream.tell()
                for line in iter(stream.readline, b""):
                    if line.strip():
                        image_id = str(json.loads(line)["imageId"])
                        if image_id in self.offsets:
                            raise ValueError("SILENT_GRID_NETWORK_DUPLICATE_PHOTO")
                        self.offsets[image_id] = (number, position)
                    position = stream.tell()
        self.streams = [path.open("rb") for path in self.paths]

    def get(self, image_id: str) -> dict[str, Any] | None:
        found = self.offsets.get(image_id)
        if found is None:
            return None
        stream = self.streams[found[0]]
        stream.seek(found[1])
        value: dict[str, Any] = json.loads(stream.readline())
        return value

    def close(self) -> None:
        for stream in self.streams:
            stream.close()


def severity(row: Mapping[str, Any]) -> float:
    """Ranking key: the unshifted NME between the saved grid and its network partner."""

    value = row.get("nme")
    return float(value) if value is not None else 0.0


def run_compare(audit: Path) -> dict[str, Any]:
    outputs = NetworkOutputs(audit)
    identity = json.loads((audit / "network-identity.json").read_text(encoding="utf-8"))
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    photo_counts: Counter[str] = Counter()
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    near_tolerance: Counter[str] = Counter()
    human_on: Counter[str] = Counter()
    boards_with_human: Counter[str] = Counter()
    nme_within: list[float] = []
    skipped: list[dict[str, Any]] = []
    photos_compared = 0
    rows_out = audit / "boards.jsonl"
    temporary = rows_out.with_name(f".{rows_out.name}.tmp")
    with temporary.open("wb") as out:
        for photo in iter_jsonl(audit / _SAVED):
            record = outputs.get(photo["imageId"])
            if record is None:
                skipped.append({"imageId": photo["imageId"], "reason": "NOT_INFERRED"})
                continue
            if record["error"]:
                skipped.append({"imageId": photo["imageId"], "reason": record["error"]})
                continue
            photos_compared += 1
            saved_nodes = [np.asarray(b["nodes"], np.float32) for b in photo["boards"]]
            network_nodes = [
                None if b["nodes"] is None else np.asarray(b["nodes"], np.float32)
                for b in record["boards"]
            ]
            results, unexplained = compare_photo(saved_nodes, network_nodes)
            photo_classes: set[str] = set()
            for result in results:
                board = photo["boards"][result["saved"]]
                level = board["level"]
                klass = result["class"]
                counts[klass][level] += 1
                by_role[klass][photo.get("snapshotRole") or "none"] += 1
                photo_classes.add(klass)
                if klass == WITHIN:
                    nme_within.append(float(result["nme"]))
                    continue
                if klass == SCALE_ROTATION and result.get("nearTolerance"):
                    near_tolerance[level] += 1
                human_on[klass] += board["humanDecidedCells"]
                boards_with_human[klass] += 1 if board["humanDecidedCells"] else 0
                out.write(
                    dumps_line(
                        {
                            **{k: v for k, v in result.items()},
                            "imageId": photo["imageId"],
                            "importJobId": photo["importJobId"],
                            "sha256": photo["sha256"],
                            "family": photo["family"],
                            "snapshotRole": photo.get("snapshotRole"),
                            "board": {k: v for k, v in board.items() if k != "nodes"},
                            "savedNodes": board["nodes"],
                            "networkNodes": None
                            if result.get("partner") is None
                            else record["boards"][result["partner"]]["nodes"],
                        }
                    )
                )
            for index in unexplained:
                counts[NETWORK_ONLY]["-"] += 1
                by_role[NETWORK_ONLY][photo.get("snapshotRole") or "none"] += 1
                photo_classes.add(NETWORK_ONLY)
                out.write(
                    dumps_line(
                        {
                            "class": NETWORK_ONLY,
                            "imageId": photo["imageId"],
                            "importJobId": photo["importJobId"],
                            "sha256": photo["sha256"],
                            "family": photo["family"],
                            "snapshotRole": photo.get("snapshotRole"),
                            "network": index,
                            "networkNodes": record["boards"][index]["nodes"],
                            "networkReasons": record["boards"][index]["reasons"],
                            "networkScore": record["boards"][index]["score"],
                        }
                    )
                )
            for klass in photo_classes:
                photo_counts[klass] += 1
            if photo_classes <= {WITHIN}:
                photo_counts["all_within_tolerance"] += 1
        out.flush()
        os.fsync(out.fileno())
    outputs.close()
    os.replace(temporary, rows_out)
    summary = {
        "auditVersion": AUDIT_VERSION,
        "createdAt": now(),
        "network": identity,
        "thresholds": {
            "matchMinIou": MATCH_MIN_IOU,
            "overlapMinIou": OVERLAP_MIN_IOU,
            "withinToleranceMaxNme": MAX_NME,
            "withinToleranceMaxNodeError": MAX_NODE_ERROR,
            "shiftMaxNme": SHIFT_MAX_NME,
            "shiftMaxNodeError": SHIFT_MAX_NODE_ERROR,
            "shiftAtMostHalfOfUnshiftedNme": True,
            "shifts": [list(s) for s in SHIFTS],
            "nearToleranceNme": NEAR_TOLERANCE_NME,
            "nearToleranceMax": NEAR_TOLERANCE_MAX,
        },
        "photosCompared": photos_compared,
        "photosSkipped": skipped,
        "boardsByClassAndLevel": {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
        "boardsByClassAndSnapshotRole": {
            k: dict(sorted(v.items())) for k, v in sorted(by_role.items())
        },
        "photosByClass": dict(sorted(photo_counts.items())),
        "scaleRotationNearToleranceByLevel": dict(sorted(near_tolerance.items())),
        "humanDecidedCellsByClass": dict(sorted(human_on.items())),
        "boardsWithHumanDecidedCellsByClass": dict(sorted(boards_with_human.items())),
        "withinToleranceNme": {
            "median": float(np.median(nme_within)) if nme_within else None,
            "p95": float(np.percentile(nme_within, 95)) if nme_within else None,
            "p99": float(np.percentile(nme_within, 99)) if nme_within else None,
        },
    }
    write_json_atomic(audit / "summary.json", summary)
    return summary


def correction_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    board = row.get("board") or {}
    return {
        "gameId": GAME_777,
        "importJobId": row["importJobId"],
        "sourceImageId": row["imageId"],
        "recognizedBoardId": board.get("recognizedBoardId"),
        "positionIndex": board.get("positionIndex"),
        "sequenceNumber": board.get("sequenceNumber"),
        "reviewerCorrectionQueue": (
            f"{REVIEWER_ORIGIN}/?mode=local&gameId={GAME_777}&importJobId={row['importJobId']}"
        ),
        "gridReviewApi": (
            f"/api/v1/games/{GAME_777}/grid-reviews?view=correction"
            f"&importJobId={row['importJobId']}&sourceImageId={row['imageId']}"
        ),
    }


def rank_suspects(audit: Path) -> dict[str, Any]:
    """``suspects.json``: every saved board outside tolerance, largest disagreement first,
    shift classes and ``scale_rotation`` in one ranking; ``saved_only`` and
    ``network_only`` in their own lists (no partner, no NME)."""

    paired: list[dict[str, Any]] = []
    saved_only: list[dict[str, Any]] = []
    network_only: list[dict[str, Any]] = []
    for row in iter_jsonl(audit / "boards.jsonl"):
        klass = row["class"]
        if klass == NETWORK_ONLY:
            network_only.append(row)
        elif klass == SAVED_ONLY:
            saved_only.append(row)
        else:
            paired.append(row)
    paired.sort(key=lambda r: (-severity(r), r["imageId"], r["saved"]))
    saved_only.sort(key=lambda r: (r["imageId"], r["saved"]))
    network_only.sort(key=lambda r: (r["imageId"], r["network"]))

    def entry(rank: int, row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
        board = row.get("board") or {}
        position = board.get("positionIndex", row.get("network"))
        return {
            "rank": rank,
            "itemId": f"{prefix}{rank:05d}",
            "class": row["class"],
            "imageId": row["imageId"],
            "level": board.get("level"),
            "basis": board.get("basis"),
            "snapshotRole": row.get("snapshotRole"),
            "family": row.get("family"),
            "nme": row.get("nme"),
            "maxError": row.get("maxError"),
            "iou": row.get("iou"),
            "maxIou": row.get("maxIou"),
            "shift": row.get("shift"),
            "shiftNme": row.get("shiftNme"),
            "nearTolerance": row.get("nearTolerance"),
            "scaleRatio": row.get("scaleRatio"),
            "angleDifferenceDeg": row.get("angleDifferenceDeg"),
            "centreOffsetCells": row.get("centreOffsetCells"),
            "cells": board.get("cells"),
            "humanDecidedCells": board.get("humanDecidedCells"),
            "positionIndex": position,
            "savedIndex": row.get("saved"),
            "networkIndex": row.get("network", row.get("partner")),
            "correction": correction_reference(row) if board else None,
        }

    document = {
        "auditVersion": AUDIT_VERSION,
        "createdAt": now(),
        "ranking": "unshifted NME between saved grid and network partner, descending",
        "paired": [entry(i + 1, r, "p") for i, r in enumerate(paired)],
        "savedOnly": [entry(i + 1, r, "s") for i, r in enumerate(saved_only)],
        "networkOnly": [entry(i + 1, r, "n") for i, r in enumerate(network_only)],
    }
    write_json_atomic(audit / "suspects.json", document)
    return {
        "paired": len(paired),
        "savedOnly": len(saved_only),
        "networkOnly": len(network_only),
    }


# --- rendering --------------------------------------------------------------------------------

RED: Final = (40, 40, 230)  # BGR
GREEN: Final = (60, 200, 60)
DIM_RED: Final = (90, 90, 160)
DIM_GREEN: Final = (90, 150, 90)


def draw_grid(image: Any, nodes: Any, colour: tuple[int, int, int], width: int) -> None:
    points = np.asarray(nodes, np.float64).reshape(4, 6, 2)
    lines = [points[r] for r in range(4)] + [points[:, c] for c in range(6)]
    for line in lines:
        cv2.polylines(
            image,
            [np.round(line).astype(np.int32).reshape(-1, 1, 2)],
            False,
            colour,
            width,
            cv2.LINE_AA,
        )


def render_case(
    rgb: ByteImage,
    focus_saved: Any | None,
    focus_network: Any | None,
    others_saved: Sequence[Any],
    others_network: Sequence[Any],
    header: Sequence[str],
    long_side: int = 1100,
) -> NDArray[np.uint8]:
    """Crop around the focus boards (+60% margin): saved red, network green, others dimmed."""

    focus = [
        np.asarray(n, np.float64).reshape(24, 2)
        for n in (focus_saved, focus_network)
        if n is not None
    ]
    points = np.concatenate(focus)
    low, high = points.min(axis=0), points.max(axis=0)
    size = high - low
    margin = np.maximum(size * 0.6, 40)
    height, width = rgb.shape[:2]
    x0, y0 = np.maximum(low - margin, 0).astype(int)
    x1, y1 = np.minimum(high + margin, [width, height]).astype(int)
    scale = long_side / max(x1 - x0, y1 - y0)
    crop = cv2.resize(
        np.ascontiguousarray(rgb[y0:y1, x0:x1, ::-1]),
        (max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )

    def local(nodes: Any) -> NDArray[np.float64]:
        moved = (np.asarray(nodes, np.float64).reshape(24, 2) - [x0, y0]) * scale
        return np.asarray(moved, np.float64)

    for nodes in others_saved:
        draw_grid(crop, local(nodes), DIM_RED, 1)
    for nodes in others_network:
        draw_grid(crop, local(nodes), DIM_GREEN, 1)
    if focus_network is not None:
        draw_grid(crop, local(focus_network), GREEN, 2)
    if focus_saved is not None:
        draw_grid(crop, local(focus_saved), RED, 2)
    band = np.full((22 * len(header) + 8, crop.shape[1], 3), 24, np.uint8)
    for i, text in enumerate(header):
        cv2.putText(
            band,
            text,
            (8, 20 + 22 * i),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )
    return np.concatenate([band, crop], axis=0)


def run_render(
    audit: Path, artifact_root: Path, *, top: int, saved_only: int, network_only: int
) -> dict[str, Any]:
    suspects = json.loads((audit / "suspects.json").read_text(encoding="utf-8"))
    rows = {
        (r["imageId"], r.get("saved"), r.get("network")): r
        for r in iter_jsonl(audit / "boards.jsonl")
    }
    selected: list[dict[str, Any]] = []
    for item in suspects["paired"]:
        if item["rank"] <= top or item["class"] in SHIFT_CLASSES:
            selected.append(item)
    selected += suspects["savedOnly"][:saved_only]
    selected += suspects["networkOnly"][:network_only]
    photos_needed = {item["imageId"] for item in selected}
    photos = {p["imageId"]: p for p in iter_jsonl(audit / _SAVED) if p["imageId"] in photos_needed}
    outputs = NetworkOutputs(audit)
    directory = audit / "cases"
    directory.mkdir(exist_ok=True)
    written = 0
    try:
        for item in selected:
            target = directory / f"{item['itemId']}.jpg"
            if target.exists():
                continue
            photo = photos[item["imageId"]]
            record = outputs.get(item["imageId"])
            assert record is not None
            if item["class"] == NETWORK_ONLY:
                row = rows[(item["imageId"], None, item["networkIndex"])]
            else:
                row = rows[(item["imageId"], item["savedIndex"], None)]
            focus_saved = row.get("savedNodes")
            focus_network = row.get("networkNodes")
            others_saved = [b["nodes"] for b in photo["boards"] if b["nodes"] != focus_saved]
            others_network = [
                b["nodes"]
                for b in record["boards"]
                if b["nodes"] is not None and b["nodes"] != focus_network
            ]
            rgb = load_photo(artifact_root, photo)
            shift = item.get("shift")
            sequence = (item.get("correction") or {}).get("sequenceNumber")
            header = [
                f"{item['itemId']}  {item['class']}  level {item['level'] or '-'}  "
                f"seq {sequence}  pos {item['positionIndex']}",
                f"NME {fmt(item.get('nme'))}  max {fmt(item.get('maxError'))}  "
                f"IoU {fmt(item.get('iou'))}  shift {shift} -> NME {fmt(item.get('shiftNme'))}  "
                f"human cells {item.get('humanDecidedCells')}",
                "red = saved (production)   green = network run 1",
            ]
            image = render_case(
                rgb, focus_saved, focus_network, others_saved, others_network, header
            )
            cv2.imwrite(str(target), image, [cv2.IMWRITE_JPEG_QUALITY, 88])
            written += 1
    finally:
        outputs.close()
    write_json_atomic(
        audit / "cases.json",
        {"items": [{**item, "image": f"cases/{item['itemId']}.jpg"} for item in selected]},
    )
    return {"selected": len(selected), "written": written}


def fmt(value: Any) -> str:
    return "-" if value is None else f"{float(value):.3f}"


def suspect_board_ids(audit: Path) -> list[str]:
    suspects = json.loads((audit / "suspects.json").read_text(encoding="utf-8"))
    ids = {
        item["correction"]["recognizedBoardId"]
        for key in ("paired", "savedOnly")
        for item in suspects[key]
        if item.get("correction")
    }
    return sorted(ids)


def attach_cell_refs(audit: Path, tsv: Path) -> dict[str, Any]:
    """TSV ``recognized_board_id, cell_review_id, cell_index, review_state, geometry_revision``
    (current cells only) -> ``correction.gridIssueCellReviewId`` (lowest cell index)."""

    first: dict[str, tuple[int, str, int | None]] = {}
    for line in tsv.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 5 or not parts[2].isdigit():
            continue
        board, cell, index = parts[0], parts[1], int(parts[2])
        revision = int(parts[4]) if parts[4] else None
        if board not in first or index < first[board][0]:
            first[board] = (index, cell, revision)
    suspects = json.loads((audit / "suspects.json").read_text(encoding="utf-8"))
    attached = 0
    for key in ("paired", "savedOnly"):
        for item in suspects[key]:
            reference = item.get("correction")
            if not reference:
                continue
            found = first.get(str(reference["recognizedBoardId"]))
            reference["gridIssueCellReviewId"] = None if found is None else found[1]
            reference["gridIssueCellIndex"] = None if found is None else found[0]
            reference["currentGeometryRevision"] = None if found is None else found[2]
            attached += found is not None
    suspects["cellRefsSource"] = {"file": tsv.name, "sha256": file_sha256(tsv)}
    write_json_atomic(audit / "suspects.json", suspects)
    return {"attached": attached, "boards": len(first)}


# --- CLI --------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
    root = argparse.ArgumentParser(prog="silent_grid_audit")
    commands = root.add_subparsers(dest="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        item = commands.add_parser(name)
        item.add_argument("--audit", type=Path, required=True)
        item.add_argument(
            "--artifact-root",
            type=Path,
            default=Path(os.environ.get("GAME_PREDICTOR_ARTIFACT_ROOT", "artifacts")),
        )
        item.add_argument("--bundle", type=Path, default=RUN1_BUNDLE)
        item.add_argument("--threads", type=int, default=4)
        return item

    saved = add("saved")
    saved.add_argument("--candidates", type=Path, required=True)
    infer = add("infer")
    infer.add_argument(
        "--runner", choices=("onnx", "torch-cuda", "torch-cpu"), default="torch-cuda"
    )
    infer.add_argument("--decode-workers", type=int, default=6)
    infer.add_argument("--max-seconds", type=float, default=540.0)
    infer.add_argument("--limit", type=int)
    infer.add_argument("--shard", type=int, default=0)
    infer.add_argument("--shards", type=int, default=1)
    parity = add("parity")
    parity.add_argument("--photos", type=int, default=24)
    add("compare")
    render = add("render")
    render.add_argument("--top", type=int, default=200)
    render.add_argument("--saved-only", type=int, default=60)
    render.add_argument("--network-only", type=int, default=60)
    refs = add("refs")
    refs.add_argument("--tsv", type=Path, required=True)
    add("board-ids")
    args = root.parse_args(argv)
    audit: Path = args.audit
    audit.mkdir(parents=True, exist_ok=True)
    if args.command == "saved":
        result: Any = compact_saved(args.candidates, audit / _SAVED, snapshot_roles())
    elif args.command == "infer":
        result = run_inference(
            audit,
            args.artifact_root,
            bundle=args.bundle,
            runner=args.runner,
            threads=args.threads,
            decode_workers=args.decode_workers,
            max_seconds=args.max_seconds,
            limit=args.limit,
            shard=args.shard,
            shards=args.shards,
        )
    elif args.command == "parity":
        result = run_parity(
            audit, args.artifact_root, bundle=args.bundle, photos=args.photos, threads=args.threads
        )
        write_json_atomic(audit / "parity.json", result)
    elif args.command == "compare":
        result = {"summary": run_compare(audit)["boardsByClassAndLevel"], **rank_suspects(audit)}
    elif args.command == "refs":
        result = attach_cell_refs(audit, args.tsv)
    elif args.command == "board-ids":
        ids = suspect_board_ids(audit)
        (audit / "suspect-board-ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
        result = {"boards": len(ids)}
    else:
        result = run_render(
            audit,
            args.artifact_root,
            top=args.top,
            saved_only=args.saved_only,
            network_only=args.network_only,
        )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
