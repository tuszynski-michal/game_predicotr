"""TASK-0804 sealed, single-use evaluation of frozen grid engines on held-out sets.

``python -m game_predictor_worker.vision_lab.grid_v3_sealed read --holdout <name>
--confirm-single-read``

The training and calibration guard (``neural_grid_protocol.require_roles``) still refuses
``gold``, ``final_test`` and ``unseen_game``; nothing here weakens it. This module is the
only reader of those roles and it reads them only through a ``SealedRead`` issued by the
ledger (``<output>/sealed/ledger.json``):

* the command requires ``--confirm-single-read``;
* before any label or image is read, the ledger records the read (holdout, every frozen
  model and the gate thresholds) as ``started``; a second read of the same holdout with any
  of the same models is refused (``GRID_V3_SEALED_READ_REPEATED``), also after a crash,
  unless ``--force-reason`` names why (the forced read is recorded too);
* after the evaluation the ledger records the output files and their SHA-256.

Holdouts: ``gold`` (snapshot v2 role, G boards scored, U/S boards known but unscored),
``final_test`` (Reels) and ``unseen_game`` (Treasure) from the frozen D-456 manifest
(partial lab grids, labelled boards only), ``mumie_holdout`` (the four D-490 holdout photos
of the fine-tune iteration 3 snapshot; already used by run 3 for state selection, recorded
for traceability). Training, calibration and fine-tune modules never import this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

from . import grid_v3_comparison as comparison
from .annotations import annotation_key, digest, exclusive, read_checked, write_atomic
from .grid_v3_comparison import EvalPhoto
from .neural_grid_data import (
    ByteImage,
    FloatArray,
    load_samples,
    open_snapshot,
)
from .neural_grid_protocol import COORDINATE_SPACE, RoleForbiddenError
from .snapshot import safe_file

LEDGER_FORMAT: Final = "grid-v3-sealed-reads-v1"
GOLD: Final = "gold"
FINAL_TEST: Final = "final_test"
UNSEEN_GAME: Final = "unseen_game"
MUMIE_HOLDOUT: Final = "mumie_holdout"
SEALED_HOLDOUTS: Final = (GOLD, FINAL_TEST, UNSEEN_GAME, MUMIE_HOLDOUT)
LAB_PARTITIONS: Final = (FINAL_TEST, UNSEEN_GAME)
DATA: Final = comparison.DATA_ROOT
D456_MANIFEST: Final = (
    DATA / "manifests" / "1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0.json"
)
LAB_SNAPSHOT_ID: Final = "0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2"
LAB_CATALOG: Final = DATA / "snapshots" / LAB_SNAPSHOT_ID
LAB_ANNOTATIONS: Final = DATA / "annotations" / LAB_SNAPSHOT_ID
MUMIE_PLAN: Final = comparison.RUNS / "finetune-D" / "iterations" / "03" / "plan.json"
_IMAGE_ID = re.compile(rb'"imageId"\s*:\s*"([^"]+)"')
_KEY: Final = object()


class SealedReadError(RoleForbiddenError):
    """A sealed holdout read that the ledger does not allow."""


@dataclass(frozen=True, slots=True)
class SealedRead:
    """Proof that the ledger recorded this read before any sealed data is opened."""

    holdout: str
    read_id: str
    key: object

    def require(self, holdout: str) -> None:
        if self.key is not _KEY:
            raise SealedReadError("GRID_V3_SEALED_READ_TOKEN_INVALID")
        if self.holdout != holdout:
            raise SealedReadError(f"GRID_V3_SEALED_READ_WRONG_HOLDOUT:{self.holdout}")


def model_keys(identity: Mapping[str, Any], holdout: str) -> dict[str, str]:
    """Frozen model fingerprints a read of ``holdout`` evaluates (the repeat key)."""

    keys = {model: str(item["weights_sha256"]) for model, item in identity["models"].items()}
    if holdout == GOLD:
        keys[comparison.PRODUCTION] = str(identity["originals_sha256"])
        hybrid = identity["hybrid"]
        keys[comparison.HYBRID] = digest(
            {
                "network": keys[hybrid["network"]],
                "thresholds": hybrid["thresholds"],
                "gate": hybrid["gate_version"],
                "originals": identity["originals_sha256"],
            }
        )
    return keys


class SealedLedger:
    """Durable record of every sealed read (``ledger.json`` under a store lock)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "ledger.json"

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"format": LEDGER_FORMAT, "reads": []}
        payload = read_checked(self.path)
        if payload.get("format") != LEDGER_FORMAT:
            raise SealedReadError("GRID_V3_SEALED_LEDGER_FORMAT")
        return payload

    def begin(
        self,
        holdout: str,
        identity: Mapping[str, Any],
        *,
        confirm: bool,
        force_reason: str | None = None,
    ) -> SealedRead:
        if holdout not in SEALED_HOLDOUTS:
            raise SealedReadError(f"GRID_V3_SEALED_HOLDOUT_UNKNOWN:{holdout}")
        if not confirm:
            raise SealedReadError("GRID_V3_SEALED_READ_NOT_CONFIRMED")
        keys = model_keys(identity, holdout)
        self.root.mkdir(parents=True, exist_ok=True)
        with exclusive(self.root):
            ledger = self.read()
            repeated = sorted(
                model
                for entry in ledger["reads"]
                if entry["holdout"] == holdout
                for model, key in entry["model_keys"].items()
                if keys.get(model) == key
            )
            if repeated and not (force_reason and force_reason.strip()):
                raise SealedReadError(
                    f"GRID_V3_SEALED_READ_REPEATED:{holdout}:{','.join(repeated)}"
                )
            read_id = f"{holdout}-{len(ledger['reads']) + 1:03d}"
            ledger["reads"].append(
                {
                    "read_id": read_id,
                    "holdout": holdout,
                    "status": "started",
                    "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model_keys": keys,
                    "identity": identity,
                    "forced": bool(repeated),
                    "force_reason": force_reason if repeated else None,
                    "outputs": {},
                }
            )
            write_atomic(self.path, ledger)
        return SealedRead(holdout, read_id, _KEY)

    def begin_inspection(self, read_id: str, purpose: str) -> SealedRead:
        """Re-open the pixels and labels of a *completed* read for drawing only.

        No model runs and no metric is recomputed; the inspection is recorded with its
        purpose. It never counts as, or replaces, the single evaluation read.
        """

        if not purpose.strip():
            raise SealedReadError("GRID_V3_SEALED_INSPECTION_PURPOSE_REQUIRED")
        with exclusive(self.root):
            ledger = self.read()
            original = next(
                (e for e in ledger["reads"] if e["read_id"] == read_id and "of" not in e), None
            )
            if original is None or original["status"] != "completed":
                raise SealedReadError(f"GRID_V3_SEALED_INSPECTION_WITHOUT_READ:{read_id}")
            inspection_id = f"{read_id}-inspection-{len(ledger['reads']) + 1:03d}"
            ledger["reads"].append(
                {
                    "read_id": inspection_id,
                    "of": read_id,
                    "holdout": original["holdout"],
                    "status": "inspection",
                    "purpose": purpose,
                    "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model_keys": {},
                    "outputs": {},
                }
            )
            write_atomic(self.path, ledger)
        return SealedRead(original["holdout"], inspection_id, _KEY)

    def complete(self, token: SealedRead, outputs: Mapping[str, str]) -> None:
        token.require(token.holdout)
        with exclusive(self.root):
            ledger = self.read()
            entry = next(e for e in ledger["reads"] if e["read_id"] == token.read_id)
            entry.update(
                status="inspected" if "of" in entry else "completed",
                completed_at=datetime.now(UTC).isoformat(timespec="seconds"),
                outputs=dict(outputs),
            )
            write_atomic(self.path, ledger)


# --- sealed loaders ---------------------------------------------------------------------------


def load_gold(token: SealedRead, snapshot: Path = comparison.SNAPSHOT_V2) -> list[EvalPhoto]:
    """Gold photos of snapshot v2: G boards scored; U/S boards known, not scored.

    The photo metric applies only to photos whose every board is G and whose stored boards
    cover the expected boards; photos without a G board (a SHA twin) are not returned.
    """

    token.require(GOLD)
    info = open_snapshot(snapshot)
    split = json.loads(safe_file(snapshot, "split.json").read_bytes())
    roles = {str(row[0]): (str(row[1]), str(row[2]), str(row[3])) for row in split["selection"]}
    digest_samples = hashlib.sha256()
    photos: list[EvalPhoto] = []
    with safe_file(snapshot, "samples.jsonl").open("rb") as stream:
        for line in stream:
            digest_samples.update(line)
            match = _IMAGE_ID.search(line)
            if match is None:
                continue
            image_id = match.group(1).decode()
            role, checksum, suffix = roles.get(image_id, ("", "", ""))
            if role != GOLD:
                continue
            row = json.loads(line)
            if row["role"] != GOLD or row["coordinateSpace"] != COORDINATE_SPACE:
                raise SealedReadError("GRID_V3_GOLD_ROW_INVALID")
            relative = f"images/{checksum[:2]}/{checksum}{suffix}"
            if row["imagePath"] != relative or info.files.get(relative) != checksum:
                raise SealedReadError("GRID_V3_GOLD_IMAGE_NOT_REGISTERED")
            boards = row["boards"]
            labels = tuple(np.asarray(b["nodes"], np.float32).reshape(24, 2) for b in boards)
            targets = tuple(i for i, b in enumerate(boards) if b.get("evaluationTarget"))
            if not targets:
                continue
            complete = int(row["expectedBoardsOnImage"]) == len(boards)
            all_gold = len(targets) == len(boards)
            path = safe_file(snapshot, relative)
            photos.append(
                EvalPhoto(
                    image_id=image_id,
                    group="seen" if row["familySeenInTraining"] else "unseen",
                    load=_snapshot_reader(
                        path, int(row["orientedWidth"]), int(row["orientedHeight"])
                    ),
                    labels=labels,
                    targets=targets,
                    labels_complete=complete,
                    photo_metric=complete and all_gold,
                    meta={
                        "sha256": checksum,
                        "family": row["familyId"],
                        "family_seen_in_training": row["familySeenInTraining"],
                        "gold_basis": row.get("goldBasis"),
                        "levels": [b["level"] for b in boards],
                        "bases": [b.get("basis") for b in boards],
                        "positions": [b.get("positionIndex") for b in boards],
                        "all_gold": all_gold,
                    },
                )
            )
    if digest_samples.hexdigest() != info.files.get("samples.jsonl"):
        raise SealedReadError("SNAPSHOT_CHECKSUM_MISMATCH")
    photos.sort(key=lambda p: p.image_id)
    return photos


def _snapshot_reader(path: Path, width: int, height: int) -> Any:
    def load() -> ByteImage:
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("IMAGE_DECODE_FAILED")
        if bgr.shape[:2] != (height, width):
            raise ValueError("ORIENTED_SIZE_MISMATCH")
        return np.ascontiguousarray(bgr[:, :, ::-1])

    return load


def load_lab_holdout(
    token: SealedRead,
    partition: str,
    manifest: Path = D456_MANIFEST,
    catalog_root: Path = LAB_CATALOG,
    annotations_root: Path = LAB_ANNOTATIONS,
) -> tuple[list[EvalPhoto], dict[str, Any]]:
    """Labelled boards of one D-456 holdout partition (frozen manifest, partial grids).

    The frozen D-456 manifest is the label source (its digest is its file name); every
    target is checked against the lab catalog (image SHA-256) and compared with the current
    annotation store, read from a byte copy under a short bounded lock (never written).
    """

    token.require(partition)
    if partition not in LAB_PARTITIONS:
        raise SealedReadError(f"GRID_V3_LAB_PARTITION_UNKNOWN:{partition}")
    return _lab_partition(partition, manifest, catalog_root, annotations_root, token)


def _lab_partition(
    partition: str,
    manifest: Path,
    catalog_root: Path,
    annotations_root: Path,
    token: SealedRead | None = None,
) -> tuple[list[EvalPhoto], dict[str, Any]]:
    """D-456 partition loader; a holdout partition needs its sealed-read token."""

    if partition in LAB_PARTITIONS:
        if token is None:
            raise SealedReadError("GRID_V3_SEALED_READ_TOKEN_REQUIRED")
        token.require(partition)
    from .assisted_annotation import read_store_state
    from .catalog import Catalog

    payload = read_checked(manifest)
    if digest(payload) != manifest.stem:
        raise SealedReadError("GRID_V3_D456_MANIFEST_DIGEST_MISMATCH")
    if (
        payload.get("decision_reference") != "D-456"
        or payload.get("status") != "frozen"
        or payload.get("snapshot_manifest_id") != catalog_root.name
    ):
        raise SealedReadError("GRID_V3_D456_MANIFEST_BINDING_MISMATCH")
    targets = [t for t in payload["targets"] if t["partition"] == partition]
    catalog = Catalog(catalog_root)
    state = read_store_state(annotations_root, catalog)
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for target in targets:
        topology = target["topology"]
        if topology.get("columns") != 5 or topology.get("rows") != 3 or len(target["nodes"]) != 24:
            raise SealedReadError("GRID_V3_LAB_TARGET_NOT_5X3")
        source = catalog.sources[target["source_id"]]
        if source.sha256 != target["source_sha256"]:
            raise SealedReadError("GRID_V3_LAB_SOURCE_CHANGED")
        by_source.setdefault(target["source_id"], []).append(target)
    unchanged = changed = 0
    extra: list[str] = []
    for source_id, items in by_source.items():
        frozen = {int(t["board_index"]) for t in items}
        for t in items:
            current = state.annotations.get(annotation_key(source_id, int(t["board_index"])))
            if current is not None and current.geometry_sha256 == t["geometry_sha256"]:
                unchanged += 1
            else:
                changed += 1
        for key, annotation in state.annotations.items():
            if (
                annotation.source_id == source_id
                and annotation.board_index not in frozen
                and annotation.presence == "present"
                and len(annotation.nodes) == 24
            ):
                extra.append(key)
    photos = []
    for source_id, items in sorted(by_source.items()):
        source = catalog.sources[source_id]
        items = sorted(items, key=lambda t: int(t["board_index"]))
        labels = tuple(
            np.asarray([[p["x"], p["y"]] for p in t["nodes"]], np.float32) for t in items
        )
        photos.append(
            EvalPhoto(
                image_id=source_id,
                group=source.game_name,
                load=_catalog_reader(catalog, source),
                labels=labels,
                targets=tuple(range(len(labels))),
                labels_complete=False,
                photo_metric=False,
                meta={
                    "sha256": source.sha256,
                    "game": source.game_name,
                    "filename": source.filename,
                    "board_indices": [int(t["board_index"]) for t in items],
                },
            )
        )
    provenance = {
        "manifest": str(manifest),
        "manifest_digest": manifest.stem,
        "partition": partition,
        "targets": len(targets),
        "photos": len(photos),
        "store_revision": state.revision,
        "targets_unchanged_in_store": unchanged,
        "targets_changed_or_missing_in_store": changed,
        "store_boards_not_in_frozen_targets": len(extra),
        "games": sorted({p.group for p in photos}),
    }
    return photos, provenance


def _catalog_reader(catalog: Any, source: Any) -> Any:
    def load() -> ByteImage:
        return np.ascontiguousarray(np.asarray(catalog.image(source), dtype=np.uint8))

    return load


def load_mumie_holdout(
    token: SealedRead, plan_path: Path = MUMIE_PLAN
) -> tuple[list[EvalPhoto], dict[str, Any]]:
    """The D-490 Mumie holdout photos as frozen in the fine-tune iteration 3 snapshot."""

    token.require(MUMIE_HOLDOUT)
    return _mumie_photos(plan_path, "development", "holdout_ids", token)


def _mumie_photos(
    plan_path: Path, role: str, ids_key: str, token: SealedRead | None = None
) -> tuple[list[EvalPhoto], dict[str, Any]]:
    """Mumie photos of the iteration snapshot; the holdout ones need their sealed token."""

    if ids_key == "holdout_ids" or role != "training":
        if token is None:
            raise SealedReadError("GRID_V3_SEALED_READ_TOKEN_REQUIRED")
        token.require(MUMIE_HOLDOUT)
    plan = read_checked(plan_path)
    snapshot = Path(plan["snapshot"]["directory"])
    holdout = set(plan[ids_key])
    samples = [s for s in load_samples(snapshot, (role,)) if s.image_id in holdout]
    if {s.image_id for s in samples} != holdout:
        raise SealedReadError("GRID_V3_MUMIE_HOLDOUT_MISMATCH")
    photos = [comparison.photo_from_sample(sample, group="mumie") for sample in samples]
    provenance = {
        "plan": str(plan_path),
        "snapshot": str(snapshot),
        "store_revision": plan["store_revision"],
        "photos": len(photos),
        "note": "used by run 3 (preset E) to select the fine-tune state of every iteration",
    }
    return photos, provenance


# --- comparison images ----------------------------------------------------------------------

_COLORS: Final[Mapping[str, tuple[int, int, int]]] = {
    "label": (40, 200, 40),
    comparison.PRODUCTION: (40, 40, 230),
    "run1": (230, 120, 20),
    "run2": (200, 60, 200),
    "iter3": (20, 180, 230),
    comparison.HYBRID: (0, 0, 0),
}


def _draw_grid(
    image: ByteImage, nodes: FloatArray, color: tuple[int, int, int], width: int
) -> None:
    grid = np.asarray(nodes, np.float32).reshape(4, 6, 2)
    for row in range(4):
        cv2.polylines(image, [np.round(grid[row]).astype(np.int32)], False, color, width)
    for column in range(6):
        cv2.polylines(image, [np.round(grid[:, column]).astype(np.int32)], False, color, width)


def case_image(
    rgb: ByteImage,
    label: FloatArray,
    panels: Sequence[tuple[str, FloatArray | None, str]],
    scale_height: int = 240,
) -> ByteImage:
    """Label (green) and each engine's matched grid on the same crop, 3 panels per row."""

    corners = np.asarray(label, np.float32)[[0, 5, 23, 18]]
    lo, hi = corners.min(axis=0), corners.max(axis=0)
    margin = (hi - lo) * 0.45
    x0, y0 = np.maximum(lo - margin, 0).astype(int)
    x1 = int(min(rgb.shape[1], hi[0] + margin[0]))
    y1 = int(min(rgb.shape[0], hi[1] + margin[1]))
    scale = scale_height / max(1, y1 - y0)
    tiles = []
    for name, nodes, caption in panels:
        tile = np.ascontiguousarray(rgb[:, :, ::-1]).copy()
        _draw_grid(tile, label, _COLORS["label"], 1)
        if nodes is not None:
            _draw_grid(tile, nodes, _COLORS.get(name, (0, 0, 255)), 1)
        region = tile[y0:y1, x0:x1]
        crop = np.asarray(
            cv2.resize(
                region,
                (max(1, int(region.shape[1] * scale)), scale_height),
                interpolation=cv2.INTER_AREA,
            ),
            dtype=np.uint8,
        )
        bar = np.full((22, crop.shape[1], 3), 255, np.uint8)
        cv2.putText(
            bar, f"{name}: {caption}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1
        )
        tiles.append(np.vstack([bar, crop]))
    width = max(t.shape[1] for t in tiles)
    tiles = [
        np.hstack([t, np.full((t.shape[0], width - t.shape[1], 3), 255, np.uint8)]) for t in tiles
    ]
    blank = np.full_like(tiles[0], 255)
    rows = []
    for start in range(0, len(tiles), 3):
        row = tiles[start : start + 3]
        row += [blank] * (3 - len(row))
        rows.append(np.hstack(row))
    return np.vstack(rows)


def _caption(target: Mapping[str, Any]) -> str:
    if not target["matched"]:
        return "missing"
    state = f" {target['state']}" if target.get("state") else ""
    verdict = "ok" if target["correct"] else "WRONG"
    return f"{verdict} nme {target['nme']:.4f} max {target['max_error']:.3f}{state}"


def write_cases(
    directory: Path,
    photos: Sequence[EvalPhoto],
    per_engine: Mapping[str, Sequence[Mapping[str, Any]]],
    predictions: Mapping[str, Mapping[str, list[tuple[FloatArray, bool]]]],
) -> list[dict[str, Any]]:
    """One comparison image per scored board that any engine got wrong or missed."""

    directory.mkdir(parents=True, exist_ok=False)
    results = {engine: {r["image_id"]: r for r in rows} for engine, rows in per_engine.items()}
    cases = []
    for photo in photos:
        failing: dict[int, dict[str, Mapping[str, Any]]] = {}
        for engine, rows in results.items():
            result = rows.get(photo.image_id)
            if result is None:
                continue
            for target in result["targets"]:
                failing.setdefault(target["label"], {})[engine] = target
        wrong = {
            label: targets
            for label, targets in failing.items()
            if any(not t["correct"] for t in targets.values())
        }
        if not wrong:
            continue
        rgb = photo.load()
        for label, targets in sorted(wrong.items()):
            panels: list[tuple[str, FloatArray | None, str]] = [
                ("label", None, f"{photo.group} board {label}")
            ]
            for engine in comparison.ENGINES:
                if engine not in targets:
                    continue
                target = targets[engine]
                nodes = None
                if target["matched"]:
                    nodes = _matched_nodes(photo, label, predictions[engine][photo.image_id])
                panels.append((engine, nodes, _caption(target)))
            name = f"{photo.image_id[:12]}-{label}.jpg"
            cv2.imwrite(str(directory / name), case_image(rgb, photo.labels[label], panels))
            cases.append(
                {
                    "file": name,
                    "image_id": photo.image_id,
                    "label": label,
                    "group": photo.group,
                    "meta": {
                        k: v
                        for k, v in photo.meta.items()
                        if k in ("family_seen_in_training", "game", "filename")
                    },
                    "position": (photo.meta.get("positions") or [None] * (label + 1))[label]
                    if photo.meta.get("positions")
                    else None,
                    "engines": {
                        engine: {
                            k: t[k] for k in ("matched", "correct", "nme", "max_error", "state")
                        }
                        for engine, t in targets.items()
                    },
                }
            )
    return cases


def _matched_nodes(
    photo: EvalPhoto, label: int, predictions: Sequence[tuple[FloatArray, bool]]
) -> FloatArray | None:
    from .neural_grid_metrics import evaluate_photo

    evaluation = evaluate_photo(photo.image_id, photo.group, list(photo.labels), list(predictions))
    for match in evaluation.matches:
        if match.label == label:
            return predictions[match.prediction][0]
    return None


# --- the sealed read ------------------------------------------------------------------------


def run_read(args: argparse.Namespace) -> dict[str, Any]:
    holdout = args.holdout
    output = args.output / "sealed" / holdout
    if output.exists():
        raise SealedReadError(f"GRID_V3_SEALED_OUTPUT_EXISTS:{output}")
    identity = comparison.frozen_identity()
    with (args.originals / "production-originals.jsonl").open("rb") as stream:
        identity["originals_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    ledger = SealedLedger(args.output / "sealed")
    token = ledger.begin(
        holdout, identity, confirm=args.confirm_single_read, force_reason=args.force_reason
    )
    provenance: dict[str, Any] = {}
    originals: dict[str, dict[str, Any]] = {}
    if holdout == GOLD:
        photos = load_gold(token, args.snapshot)
        originals = comparison.load_originals(args.originals)
    elif holdout == MUMIE_HOLDOUT:
        photos, provenance = load_mumie_holdout(token)
    else:
        photos, provenance = load_lab_holdout(token, holdout)
    outputs, result = evaluate_and_write(
        output,
        photos,
        originals=originals,
        with_production=holdout == GOLD,
        threads=args.threads,
        extra={
            "holdout": holdout,
            "read_id": token.read_id,
            "identity": identity,
            "provenance": provenance,
        },
    )
    ledger.complete(token, outputs)
    return {"output": str(output), "read_id": token.read_id, **result, **outputs}


def evaluate_and_write(
    output: Path,
    photos: Sequence[EvalPhoto],
    *,
    originals: Mapping[str, Mapping[str, Any]],
    with_production: bool,
    threads: int,
    extra: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Every frozen engine on ``photos``: summary, per-photo results, raw outputs, cases."""

    started = time.perf_counter()
    engines = comparison.ENGINES if with_production else comparison.NETWORK_MODELS
    networks = comparison.collect_networks(photos, comparison.NETWORK_MODELS, threads)
    summary, per_engine = comparison.set_report(
        photos,
        originals=originals,
        networks=networks,
        engines=engines,
        group_key=lambda r: str(r["group"]),
    )
    photo_metric = {p.image_id for p in photos if p.photo_metric}
    summary["photo_metric_subset"] = {
        engine: comparison.summarize_results([r for r in rows if r["image_id"] in photo_metric])
        for engine, rows in per_engine.items()
    }
    if not with_production:
        summary["missing_production_original"] = (
            "not applicable: the production engine has no output for these photos"
        )
        summary.pop("engines_on_photos_with_original", None)
    summary.update(extra)
    summary.update(engines_measured=list(engines), wall_seconds=time.perf_counter() - started)
    predictions: dict[str, dict[str, list[tuple[FloatArray, bool]]]] = {
        model: {
            image_id: comparison.predictions_of_network(record["boards"])
            for image_id, record in networks[model].items()
        }
        for model in comparison.NETWORK_MODELS
    }
    if with_production:
        predictions[comparison.PRODUCTION] = {
            p.image_id: comparison.predictions_of_reference(
                comparison.original_reference(originals.get(p.image_id))
            )
            for p in photos
        }
        predictions[comparison.HYBRID] = {
            p.image_id: comparison.predictions_of_decision(
                comparison.hybrid_decision(
                    originals.get(p.image_id),
                    networks[comparison.HYBRID_NETWORK][p.image_id]["boards"],
                )
            )[0]
            for p in photos
            if (originals.get(p.image_id) or {}).get("status") == "present"
        }
    output.mkdir(parents=True, exist_ok=False)
    outputs = {
        "summary.json": comparison.write_json(output / "summary.json", summary),
        "photos.json": comparison.write_json(output / "photos.json", per_engine),
        "networks.json": comparison.write_json(output / "networks.json", networks),
    }
    try:
        cases = write_cases(output / "cases", photos, per_engine, predictions)
    except Exception as error:  # the measurement is written; a drawing error must not lose it
        cases = [{"error": f"{type(error).__name__}: {error}"}]
    outputs["cases.json"] = comparison.write_json(output / "cases.json", cases)
    return outputs, {"cases": len(cases), "photos": len(photos)}


def inspect_gold(args: argparse.Namespace) -> dict[str, Any]:
    """Whole-photo overviews of a completed gold read from its stored outputs (no inference).

    Green: scored G label, yellow: known unscored board (U/S), red: production original,
    cyan: ``neural_grid`` iteration 3 (stored output of the read). Used for the error
    taxonomy, where the cause of a production miss is often elsewhere on the photo.
    """

    read = args.output / "sealed" / GOLD
    networks = json.loads((read / "networks.json").read_text(encoding="utf-8"))
    cases = json.loads((read / "cases.json").read_text(encoding="utf-8"))
    photos_result = json.loads((read / "photos.json").read_text(encoding="utf-8"))
    wanted = {c["image_id"] for c in cases} | {
        r["image_id"] for rows in photos_result.values() for r in rows if r["false_boards"]
    }
    ledger = SealedLedger(args.output / "sealed")
    token = ledger.begin_inspection(args.read_id, args.purpose)
    originals = comparison.load_originals(args.originals)
    photos = [p for p in load_gold(token, args.snapshot) if p.image_id in wanted]
    output = args.output / "sealed" / f"{token.read_id}"
    output.mkdir(parents=True, exist_ok=False)
    for photo in photos:
        image = np.ascontiguousarray(photo.load()[:, :, ::-1]).copy()
        reference = comparison.original_reference(originals.get(photo.image_id))
        for board in reference:
            if board.nodes is not None:
                _draw_grid(image, board.nodes, (40, 40, 230), 2)
        for nodes, _ in comparison.predictions_of_network(
            networks["iter3"][photo.image_id]["boards"]
        ):
            _draw_grid(image, nodes, (230, 200, 20), 1)
        for index, label in enumerate(photo.labels):
            scored = index in photo.targets
            _draw_grid(image, label, (40, 200, 40) if scored else (0, 220, 230), 1)
            centre = np.asarray(label, np.float32).mean(axis=0).astype(int)
            text = f"{index}{'' if scored else 'u'}"
            cv2.putText(
                image,
                text,
                tuple(int(v) for v in centre),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )
        scale = min(1.0, 1400 / image.shape[1])
        if scale < 1.0:
            image = np.asarray(
                cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale))),
                np.uint8,
            )
        cv2.imwrite(str(output / f"{photo.image_id[:12]}.jpg"), image)
    ledger.complete(token, {"overviews": str(len(photos))})
    return {"output": str(output), "photos": len(photos), "inspection": token.read_id}


def rehearse(args: argparse.Namespace) -> dict[str, Any]:
    """The sealed pipeline on development photos only (no ledger, no sealed role).

    Three shapes exercise every path before a holdout is read once: full labels, gold-like
    (complete labels, only some boards scored) and partial lab-like labels.
    """

    photos = comparison.development_photos(args.snapshot)[: args.limit]
    originals = comparison.load_originals(args.originals)
    gold_like = [
        EvalPhoto(
            p.image_id,
            "seen" if index % 2 else "unseen",
            p.load,
            p.labels,
            p.targets[:5] if index % 3 else p.targets,
            True,
            index % 3 == 0,
            {**p.meta, "positions": list(range(len(p.labels)))},
        )
        for index, p in enumerate(photos)
    ]
    partial = [
        EvalPhoto(p.image_id, "partial", p.load, p.labels[:3], (0, 1, 2), False, False, p.meta)
        for p in photos
    ]
    # The same loaders as the lab and Mumie holdouts, on parts that are not held out:
    # the D-456 development partition and the Mumie fine-tune training photos.
    lab, lab_provenance = _lab_partition("development", D456_MANIFEST, LAB_CATALOG, LAB_ANNOTATIONS)
    mumie, _ = _mumie_photos(MUMIE_PLAN, "training", "train_ids")
    result: dict[str, Any] = {"lab_development_provenance": lab_provenance}
    for name, items, production in (
        ("gold-like", gold_like, True),
        ("partial", partial, False),
        ("lab-development", lab[: args.limit], False),
        ("mumie-training", mumie[:4], False),
    ):
        outputs, info = evaluate_and_write(
            args.output / "rehearsal" / name,
            items,
            originals=originals,
            with_production=production,
            threads=args.threads,
            extra={"holdout": f"rehearsal-{name}"},
        )
        result[name] = {**outputs, **info}
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="grid_v3_sealed")
    commands = root.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read")
    read.add_argument("--holdout", choices=SEALED_HOLDOUTS, required=True)
    read.add_argument("--confirm-single-read", action="store_true")
    read.add_argument("--force-reason")
    read.add_argument("--output", type=Path, default=comparison.OUTPUT)
    read.add_argument("--snapshot", type=Path, default=comparison.SNAPSHOT_V2)
    read.add_argument("--originals", type=Path, default=comparison.ORIGINALS)
    read.add_argument("--threads", type=int, default=4)
    commands.add_parser("status").add_argument("--output", type=Path, default=comparison.OUTPUT)
    inspection = commands.add_parser("inspect-gold")
    inspection.add_argument("--read-id", required=True)
    inspection.add_argument("--purpose", required=True)
    inspection.add_argument("--output", type=Path, default=comparison.OUTPUT)
    inspection.add_argument("--snapshot", type=Path, default=comparison.SNAPSHOT_V2)
    inspection.add_argument("--originals", type=Path, default=comparison.ORIGINALS)
    rehearsal = commands.add_parser("rehearse")
    rehearsal.add_argument("--output", type=Path, required=True)
    rehearsal.add_argument("--snapshot", type=Path, default=comparison.SNAPSHOT_V2)
    rehearsal.add_argument("--originals", type=Path, default=comparison.ORIGINALS)
    rehearsal.add_argument("--threads", type=int, default=4)
    rehearsal.add_argument("--limit", type=int, default=24)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "rehearse":
        print(json.dumps(rehearse(args), indent=1))
        return
    if args.command == "inspect-gold":
        print(json.dumps(inspect_gold(args), indent=1))
        return
    if args.command == "status":
        ledger = SealedLedger(args.output / "sealed").read()
        print(
            json.dumps(
                [
                    {k: e.get(k) for k in ("read_id", "holdout", "status", "forced", "model_keys")}
                    for e in ledger["reads"]
                ],
                indent=1,
            )
        )
        return
    print(json.dumps(run_read(args), indent=1))


if __name__ == "__main__":
    main()
