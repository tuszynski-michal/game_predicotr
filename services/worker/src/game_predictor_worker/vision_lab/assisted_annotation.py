"""Assisted complete-photo annotation for Mumie, Blazing and Gang (D-490, TASK-0824).

The run-1 ``neural_grid`` network proposes board grids once, into an immutable proposal
artifact next to the lab data. A small loopback page shows every proposal over the photo;
only an explicit operator action turns one into a label, written through the existing
``AnnotationStore`` (lock, CAS revision, receipts, history) as a full human-approved
geometry plus an ``AssistedBoard`` record of its origin. A photo is complete only with a
confirmed board count and an accepted grid for every board (D-484); the completion is
bound to the board revisions, so any later geometry change reopens the photo.

Reels and Treasure are holdouts (D-490): neither the queue, the proposal generator, the
page nor the store mutation accepts a source outside the three workflow games.

Commands (``python -m game_predictor_worker.vision_lab.assisted_annotation``):
``proposals`` (CPU ONNX, create-only), ``serve`` (127.0.0.1:8105), ``status`` and
``export`` (create-only list of complete photos with checksums).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .annotation_contracts import (
    AnnotationRequest,
    AnnotationState,
    AssistedBoard,
    AssistedOrigin,
    AssistedPhoto,
    AssistedRequest,
    GeometryAnnotation,
    PhotoReviewRequest,
)
from .annotations import (
    AnnotationStore,
    active_time,
    annotation_key,
    digest,
    read_checked,
    write_atomic,
)
from .catalog import Catalog, InvalidImageError, encode
from .contracts import Point, Source, Topology
from .photo_review import apply_photo_review, board_revisions, photo_accepted
from .snapshot import canonical, reject_links

WORKFLOW_GAMES: Final = ("mumie", "blazing", "gang")
# Catalog game names per workflow game: the lab snapshot names and the source folder names.
GAME_NAMES: Final[Mapping[str, tuple[str, ...]]] = {
    "mumie": ("mumie wybrane", "mumie"),
    "blazing": ("blazing zd", "blazing"),
    "gang": ("gang zd", "gang"),
}
# D-490: final_test (Reels) and unseen_game (Treasure) stay untouched.
HOLDOUT_MARKERS: Final = ("reels", "tresure", "treasure")
MAX_BOARD_INDEX: Final = 8
CORNER_NODES: Final = (0, 5, 23, 18)
PROPOSALS_FORMAT: Final = "lab-assisted-proposals-v1"
PROPOSALS_FILE: Final = "proposals.json"
EXPORT_FORMAT: Final = "lab-assisted-complete-photos-v1"
EXPORT_ROWS: Final = "complete-photos.jsonl"
EXPORT_MANIFEST: Final = "manifest.json"
BOARD_LEVEL: Final = "lab_human"
DEFAULT_PORT: Final = 8105
IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png"})

Annotate = Callable[[AnnotationState, AnnotationRequest, str], None]


# --- game guard ------------------------------------------------------------------------------


def workflow_game(source: Source) -> str:
    """The workflow game of a catalog source, or an error for every other game."""

    name = source.game_name.strip().lower()
    if any(marker in name for marker in HOLDOUT_MARKERS):
        raise ValueError("ASSISTED_HOLDOUT_FORBIDDEN")
    for key, names in GAME_NAMES.items():
        if name in names:
            return key
    raise ValueError("ASSISTED_GAME_FORBIDDEN")


def in_workflow(source: Source) -> bool:
    try:
        workflow_game(source)
    except ValueError:
        return False
    return True


# --- store rules -----------------------------------------------------------------------------


def source_rows(state: AnnotationState, source_id: str) -> dict[int, GeometryAnnotation]:
    return {a.board_index: a for a in state.annotations.values() if a.source_id == source_id}


def owned_board(
    record: AssistedPhoto | None, annotation: GeometryAnnotation | None
) -> AssistedBoard | None:
    """The workflow record of a slot while it still describes the stored annotation."""

    if record is None or annotation is None:
        return None
    board = record.boards.get(str(annotation.board_index))
    return board if board is not None and board.annotation_revision == annotation.revision else None


def photo_complete(state: AnnotationState, source: Source) -> bool:
    record = state.assisted_photos.get(source.id)
    if (
        record is None
        or record.confirmed_board_count is None
        or record.source_sha256 != source.sha256
        or not record.completed_board_revisions
        or record.completed_board_revisions != board_revisions(state, source.id)
    ):
        return False
    present = [a for a in source_rows(state, source.id).values() if a.presence == "present"]
    return (
        len(present) == record.confirmed_board_count
        and all(a.full_approved and a.topology.columns == 5 for a in present)
        and photo_accepted(state, source)
    )


def _board_request(
    request: AssistedRequest, state: AnnotationState, annotation: GeometryAnnotation, action: str
) -> AnnotationRequest:
    return AnnotationRequest(
        request_id=request.request_id,
        expected_revision=state.revision,
        actor=request.actor,
        annotation=annotation,
        action=action,  # type: ignore[arg-type]
        reviewed_all_nodes=action == "approve_full",
        activity_intervals_ms=request.activity_intervals_ms,
        correction_count=request.correction_count,
    )


def apply_assisted(
    state: AnnotationState,
    catalog: Catalog,
    request: AssistedRequest,
    now: str,
    annotate: Annotate,
) -> tuple[int | None, bool]:
    """Apply one operator decision; returns the written board slot and a D-450 review flag."""

    source = catalog.sources.get(request.source_id)
    if source is None:
        raise ValueError("SOURCE_NOT_FOUND")
    workflow_game(source)
    if request.source_sha256 != source.sha256:
        raise ValueError("ASSISTED_SOURCE_CHANGED")
    record = state.assisted_photos.get(source.id) or AssistedPhoto(
        source_id=source.id, source_sha256=source.sha256
    )
    if record.source_sha256 != source.sha256:
        raise ValueError("ASSISTED_SOURCE_CHANGED")
    record = record.model_copy(deep=True)
    elapsed = active_time(request.activity_intervals_ms)
    written: int | None = None
    reviewed = False
    action = request.action
    if action in ("accept_board", "revoke_board", "remove_board"):
        index = request.board_index
        if index is None:
            raise ValueError("ASSISTED_BOARD_INDEX_REQUIRED")
        current = state.annotations.get(annotation_key(source.id, index))
        if request.expected_board_revision != (current.revision if current else 0):
            raise ValueError("ASSISTED_BOARD_REVISION_CONFLICT")
        owner = owned_board(record, current)
        if current is not None and owner is None:
            raise ValueError("ASSISTED_EXISTING_BOARD_LOCKED")
        topology = Topology(columns=5)
        if action == "accept_board":
            origin = request.origin
            if origin is None or len(request.nodes) != 24:
                raise ValueError("ASSISTED_GEOMETRY_REQUIRED")
            proposal = (request.proposal_set_id, request.proposal_id, request.proposal_sha256)
            if origin == "manual":
                if any(proposal) or request.max_corner_shift_px:
                    raise ValueError("ASSISTED_MANUAL_HAS_PROPOSAL")
            elif not all(proposal) or not re.fullmatch(r"[0-9a-f]{64}", request.proposal_sha256):
                raise ValueError("ASSISTED_PROPOSAL_REQUIRED")
            elif origin == "proposal_unchanged" and request.max_corner_shift_px:
                raise ValueError("ASSISTED_UNCHANGED_PROPOSAL_MOVED")
            if request.proposal_id and any(
                slot != str(index)
                and board.proposal_id == request.proposal_id
                and board.status != "removed"
                and owned_board(record, state.annotations.get(annotation_key(source.id, int(slot))))
                for slot, board in record.boards.items()
            ):
                raise ValueError("ASSISTED_PROPOSAL_ALREADY_USED")
            nodes = [Point(x=p.x, y=p.y, provenance="human") for p in request.nodes]
            annotation = GeometryAnnotation(
                source_id=source.id,
                board_index=index,
                topology=topology,
                corners=[nodes[i].model_copy() for i in CORNER_NODES],
                nodes=nodes,
            )
            annotate(state, _board_request(request, state, annotation, "approve_full"), now)
            status: Literal["accepted", "revoked", "removed"] = "accepted"
            board_origin: AssistedOrigin = origin
            shift = request.max_corner_shift_px
            proposal_fields = {
                "proposal_set_id": request.proposal_set_id,
                "proposal_id": request.proposal_id,
                "proposal_sha256": request.proposal_sha256,
            }
            if request.proposal_id in record.dismissed_proposal_ids:
                record.dismissed_proposal_ids.remove(request.proposal_id)
        else:
            if owner is None or current is None:
                raise ValueError("ASSISTED_BOARD_NOT_FOUND")
            if action == "revoke_board":
                if owner.status != "accepted" or not current.full_approved:
                    raise ValueError("ASSISTED_BOARD_NOT_ACCEPTED")
                annotation = current.model_copy(deep=True)
                annotate(state, _board_request(request, state, annotation, "draft"), now)
                status = "revoked"
            else:
                if owner.status == "removed":
                    raise ValueError("ASSISTED_BOARD_ALREADY_REMOVED")
                annotation = GeometryAnnotation(
                    source_id=source.id, board_index=index, topology=topology, presence="absent"
                )
                annotate(state, _board_request(request, state, annotation, "draft"), now)
                status = "removed"
                if owner.proposal_id and owner.proposal_id not in record.dismissed_proposal_ids:
                    record.dismissed_proposal_ids.append(owner.proposal_id)
            board_origin = owner.origin
            shift = owner.max_corner_shift_px
            proposal_fields = {
                "proposal_set_id": owner.proposal_set_id,
                "proposal_id": owner.proposal_id,
                "proposal_sha256": owner.proposal_sha256,
            }
        record.boards[str(index)] = AssistedBoard(
            board_index=index,
            status=status,
            origin=board_origin,
            annotation_revision=state.annotations[annotation_key(source.id, index)].revision,
            max_corner_shift_px=shift,
            actor=request.actor,
            decided_at=now,
            **proposal_fields,
        )
        written = index
    elif action in ("dismiss_proposal", "restore_proposal"):
        if not request.proposal_id:
            raise ValueError("ASSISTED_PROPOSAL_REQUIRED")
        dismissed = request.proposal_id in record.dismissed_proposal_ids
        if (action == "dismiss_proposal") == dismissed:
            raise ValueError("ASSISTED_PROPOSAL_STATE_UNCHANGED")
        if action == "dismiss_proposal":
            record.dismissed_proposal_ids.append(request.proposal_id)
        else:
            record.dismissed_proposal_ids.remove(request.proposal_id)
    else:  # complete_photo
        count = request.confirmed_board_count
        if count is None:
            raise ValueError("ASSISTED_BOARD_COUNT_REQUIRED")
        revisions = board_revisions(state, source.id)
        if request.expected_board_revisions != revisions:
            raise ValueError("ASSISTED_PHOTO_GEOMETRY_CHANGED")
        present = [a for a in source_rows(state, source.id).values() if a.presence == "present"]
        if any(not a.full_approved for a in present):
            raise ValueError("ASSISTED_BOARD_NOT_ACCEPTED")
        if any(a.topology.columns != 5 for a in present):
            raise ValueError("ASSISTED_TOPOLOGY_UNSUPPORTED")
        if len(present) != count:
            raise ValueError("ASSISTED_BOARD_COUNT_MISMATCH")
        if photo_complete(state, source):
            raise ValueError("ASSISTED_PHOTO_ALREADY_COMPLETE")
        if not photo_accepted(state, source):
            apply_photo_review(
                state,
                source,
                PhotoReviewRequest(
                    request_id=request.request_id,
                    expected_revision=state.revision,
                    actor=request.actor,
                    action="accept",
                    source_id=source.id,
                    source_sha256=source.sha256,
                    expected_board_revisions=revisions,
                ),
                now,
            )
            reviewed = True
        record.confirmed_board_count = count
        record.completed_board_revisions = revisions
        record.completed_at = now
    record.active_ms += elapsed
    record.actor, record.decided_at = request.actor, now
    state.assisted_photos[source.id] = record
    return written, reviewed


# --- queue and proposals ---------------------------------------------------------------------


def natural_key(text: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def training_set_files(root: Path) -> dict[str, list[tuple[str, str]]]:
    """``(relative path, SHA-256)`` of the three workflow folders only; holdouts unread."""

    reject_links(root)
    result: dict[str, list[tuple[str, str]]] = {}
    for key in WORKFLOW_GAMES:
        folder = root / key
        reject_links(folder)
        if not folder.is_dir():
            raise ValueError(f"ASSISTED_TRAINING_FOLDER_MISSING:{key}")
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
            key=lambda p: natural_key(p.name),
        )
        result[key] = [(f"{key}/{p.name}", file_sha256(p)) for p in files]
    return result


def store_snapshot_id(catalog: Catalog) -> str:
    return digest([s.model_dump() for s in catalog.sources.values()])


def build_queue(
    catalog: Catalog, state: AnnotationState, files: Mapping[str, Sequence[tuple[str, str]]]
) -> list[dict[str, Any]]:
    """Mumie, then Blazing, then Gang: the source-folder photos, then annotated lab photos.

    Source identifiers and families come from the lab catalog; a SHA-256 shared by two
    catalog entries resolves to the annotated one, else to the first by file name.
    """

    if set(files) - set(WORKFLOW_GAMES):
        raise ValueError("ASSISTED_GAME_FORBIDDEN")
    annotated = {a.source_id for a in state.annotations.values()}
    by_sha: dict[str, list[Source]] = {}
    for source in catalog.sources.values():
        if in_workflow(source):
            by_sha.setdefault(source.sha256, []).append(source)
    items: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}

    def add(source: Source, key: str, relative: str | None) -> None:
        if source.sha256 in seen:
            if relative:
                seen[source.sha256]["training_set_files"].append(relative)
            return
        item = {
            "source_id": source.id,
            "sha256": source.sha256,
            "game": key,
            "game_id": source.game_id,
            "game_name": source.game_name,
            "filename": source.filename,
            "training_set_files": [relative] if relative else [],
            "existing_boards": sum(
                a.source_id == source.id and a.presence == "present"
                for a in state.annotations.values()
            ),
        }
        seen[source.sha256] = item
        items.append(item)

    for key in WORKFLOW_GAMES:
        for relative, sha in files.get(key, ()):
            candidates = [s for s in by_sha.get(sha, []) if workflow_game(s) == key]
            if not candidates:
                raise ValueError(f"ASSISTED_SOURCE_NOT_IN_CATALOG:{relative}")
            chosen = min(candidates, key=lambda s: (s.id not in annotated, s.filename, s.id))
            add(chosen, key, relative)
        extra = sorted(
            (
                s
                for s in catalog.sources.values()
                if s.id in annotated and in_workflow(s) and workflow_game(s) == key
            ),
            key=lambda s: (natural_key(s.filename), s.id),
        )
        for source in extra:
            add(source, key, None)
    for index, item in enumerate(items):
        item["queue_index"] = index
    return items


def proposal_digest(proposal: Mapping[str, Any]) -> str:
    return digest(
        {
            "proposal_id": proposal["proposal_id"],
            "source_id": proposal["source_id"],
            "source_sha256": proposal["source_sha256"],
            "nodes": proposal["nodes"],
        }
    )


def generate_proposals(
    catalog: Catalog,
    state: AnnotationState,
    training_root: Path,
    bundle: Path,
    output_root: Path,
    *,
    threads: int = 4,
    log: Callable[[str], None] = print,
    engine: Any | None = None,
) -> Path:
    """Run the ONNX bundle on CPU over the queue and publish a create-only artifact.

    ``engine`` (anything with ``analyse(rgb)`` and ``model_version``) replaces the bundle's
    ONNX engine in tests; the bundle manifest still binds the artifact identity.
    """

    items = build_queue(catalog, state, training_set_files(training_root))
    bundle_info = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    identity = {
        "format": PROPOSALS_FORMAT,
        "snapshot_id": store_snapshot_id(catalog),
        "bundle_files": bundle_info["files"],
        "weights_sha256": bundle_info["weights_sha256"],
        "preset_fingerprint": bundle_info.get("preset_fingerprint"),
        "items": [[item["source_id"], item["sha256"]] for item in items],
    }
    set_id = digest(identity)
    reject_links(output_root)
    target = output_root / set_id
    if target.exists():
        raise ValueError(f"ASSISTED_PROPOSALS_EXIST:{target}")
    if engine is None:
        from .neural_grid_inference import onnx_engine

        engine = onnx_engine(bundle, threads=threads)
    started = time.perf_counter()
    for number, item in enumerate(items, 1):
        source = catalog.sources[item["source_id"]]
        workflow_game(source)
        begin = time.perf_counter()
        try:
            image = catalog.image(source)
        except InvalidImageError as error:
            item.update(status="invalid_image", reasons=[str(error)], proposals=[])
            continue
        item["width"], item["height"] = image.size
        detections = engine.analyse(np.asarray(image, dtype=np.uint8))
        proposals: list[dict[str, Any]] = []
        for detection in detections:
            if detection.nodes is None:
                continue
            proposal: dict[str, Any] = {
                "proposal_id": f"{source.id[:16]}.{len(proposals)}",
                "source_id": source.id,
                "source_sha256": source.sha256,
                "rank": len(proposals),
                "score": round(float(detection.score), 4),
                "nodes": [[round(float(x), 3), round(float(y), 3)] for x, y in detection.nodes],
                "fit_residual": None
                if detection.fit_residual is None or not np.isfinite(detection.fit_residual)
                else round(float(detection.fit_residual), 5),
                "fit_inliers": detection.fit_inliers,
                "reasons": list(detection.reasons),
            }
            proposal["sha256"] = proposal_digest(proposal)
            proposals.append(proposal)
        item.update(
            status="detected" if proposals else "no_board",
            reasons=[],
            proposals=proposals,
            seconds=round(time.perf_counter() - begin, 3),
        )
        if number % 25 == 0:
            log(f"{number}/{len(items)} photos, {time.perf_counter() - started:.1f} s")
    payload = {
        **identity,
        "items": items,
        "proposal_set_id": set_id,
        "decision_reference": "D-490",
        "task": "TASK-0824",
        "bundle": {
            "directory": str(bundle),
            "model_version": engine.model_version,
            "run_id": bundle_info.get("provenance", {}).get("run_id"),
        },
        "catalog_snapshot": catalog.root.name if catalog.root else None,
        "training_set_root": str(training_root),
        "threads": threads,
        "provider": "CPUExecutionProvider",
        "created_at": datetime.now(UTC).isoformat(),
        "seconds": round(time.perf_counter() - started, 1),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".proposals-", dir=output_root))
    try:
        write_atomic(stage / PROPOSALS_FILE, payload)
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    log(f"published {target}")
    return target


@dataclass(frozen=True, slots=True)
class ProposalSet:
    root: Path
    set_id: str
    payload: dict[str, Any]
    items: list[dict[str, Any]]
    by_source: dict[str, dict[str, Any]]
    by_id: dict[str, dict[str, Any]]


def load_proposals(root: Path, catalog: Catalog) -> ProposalSet:
    payload = read_checked(root / PROPOSALS_FILE)
    if payload.get("format") != PROPOSALS_FORMAT or payload.get("proposal_set_id") != root.name:
        raise ValueError("ASSISTED_PROPOSALS_INVALID")
    if payload.get("snapshot_id") != store_snapshot_id(catalog):
        raise ValueError("ASSISTED_PROPOSALS_SNAPSHOT_MISMATCH")
    items = list(payload["items"])
    by_source: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        source = catalog.sources.get(item["source_id"])
        if source is None or source.sha256 != item["sha256"]:
            raise ValueError("ASSISTED_PROPOSALS_SOURCE_MISMATCH")
        workflow_game(source)
        by_source[source.id] = item
        for proposal in item.get("proposals", []):
            if proposal["source_id"] != source.id or proposal["sha256"] != proposal_digest(
                proposal
            ):
                raise ValueError("ASSISTED_PROPOSALS_INTEGRITY_ERROR")
            by_id[proposal["proposal_id"]] = proposal
    return ProposalSet(root, root.name, payload, items, by_source, by_id)


# --- geometry from operator input ------------------------------------------------------------


def projective_nodes(corners: Sequence[Sequence[float]]) -> list[list[float]]:
    """The 24 nodes of the projective 5 x 3 grid spanned by TL, TR, BR, BL."""

    from .neural_grid_data import grid_from_quad, quad_is_usable

    quad = np.asarray(corners, dtype=np.float32).reshape(4, 2)
    if not quad_is_usable(quad):
        raise ValueError("ASSISTED_QUAD_INVALID")
    return [[float(x), float(y)] for x, y in grid_from_quad(quad)]


class Decision(BaseModel):
    """The page's request; the server resolves geometry and provenance from it."""

    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    action: Literal[
        "accept_board",
        "revoke_board",
        "remove_board",
        "dismiss_proposal",
        "restore_proposal",
        "complete_photo",
    ]
    source_id: str
    board_index: int | None = Field(default=None, ge=0, le=MAX_BOARD_INDEX)
    expected_board_revision: int = Field(default=0, ge=0)
    origin: Literal["proposal_unchanged", "proposal_corrected", "manual"] | None = None
    proposal_id: str = Field(default="", max_length=200)
    corners: list[list[float]] = Field(default_factory=list, max_length=4)
    confirmed_board_count: int | None = Field(default=None, ge=1, le=9)
    expected_board_revisions: dict[str, int] = Field(default_factory=dict)
    activity_intervals_ms: list[int] = Field(default_factory=list, max_length=10000)
    correction_count: int = Field(default=0, ge=0, le=10000)


def store_request(
    decision: Decision, proposals: ProposalSet, catalog: Catalog, actor: str
) -> AssistedRequest:
    item = proposals.by_source.get(decision.source_id)
    if item is None:
        raise ValueError("ASSISTED_SOURCE_NOT_IN_QUEUE")
    source = catalog.sources[decision.source_id]
    workflow_game(source)
    proposal: dict[str, Any] | None = None
    if decision.proposal_id:
        proposal = proposals.by_id.get(decision.proposal_id)
        if proposal is None or proposal["source_id"] != source.id:
            raise ValueError("ASSISTED_PROPOSAL_NOT_FOUND")
    nodes: list[list[float]] = []
    shift = 0.0
    if decision.action == "accept_board":
        if decision.origin is None:
            raise ValueError("ASSISTED_ORIGIN_REQUIRED")
        if decision.origin == "manual" and proposal is not None:
            raise ValueError("ASSISTED_MANUAL_HAS_PROPOSAL")
        if decision.origin != "manual" and proposal is None:
            raise ValueError("ASSISTED_PROPOSAL_REQUIRED")
        if decision.origin == "proposal_unchanged":
            assert proposal is not None
            if decision.corners:
                raise ValueError("ASSISTED_UNCHANGED_PROPOSAL_MOVED")
            nodes = [list(map(float, node)) for node in proposal["nodes"]]
        else:
            if len(decision.corners) != 4 or any(len(c) != 2 for c in decision.corners):
                raise ValueError("ASSISTED_CORNERS_REQUIRED")
            nodes = projective_nodes(decision.corners)
            if proposal is not None:
                shift = max(
                    float(np.hypot(c[0] - proposal["nodes"][i][0], c[1] - proposal["nodes"][i][1]))
                    for c, i in zip(decision.corners, CORNER_NODES, strict=True)
                )
    elif decision.corners or decision.origin is not None:
        raise ValueError("ASSISTED_GEOMETRY_UNEXPECTED")
    if decision.action in ("dismiss_proposal", "restore_proposal") and proposal is None:
        raise ValueError("ASSISTED_PROPOSAL_REQUIRED")
    with_proposal = proposal is not None and decision.action in (
        "accept_board",
        "dismiss_proposal",
        "restore_proposal",
    )
    return AssistedRequest(
        request_id=decision.request_id,
        expected_revision=decision.expected_revision,
        actor=actor,
        action=decision.action,
        source_id=source.id,
        source_sha256=source.sha256,
        board_index=decision.board_index,
        expected_board_revision=decision.expected_board_revision,
        origin=decision.origin,
        proposal_set_id=proposals.set_id if with_proposal else "",
        proposal_id=decision.proposal_id if with_proposal else "",
        proposal_sha256=proposal["sha256"] if with_proposal and proposal else "",
        max_corner_shift_px=round(shift, 3),
        nodes=[Point(x=x, y=y, provenance="human") for x, y in nodes],
        confirmed_board_count=decision.confirmed_board_count,
        expected_board_revisions=decision.expected_board_revisions,
        activity_intervals_ms=decision.activity_intervals_ms,
        correction_count=decision.correction_count,
    )


# --- views -----------------------------------------------------------------------------------


def _inside(point: Sequence[float], quad: Sequence[Sequence[float]]) -> bool:
    import cv2

    contour = np.asarray(quad, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False) >= 0


def photo_status(state: AnnotationState, source: Source) -> str:
    if photo_complete(state, source):
        return "complete"
    if source.id in state.assisted_photos or any(
        a.source_id == source.id for a in state.annotations.values()
    ):
        return "started"
    return "new"


def photo_view(
    state: AnnotationState, catalog: Catalog, proposals: ProposalSet, source_id: str
) -> dict[str, Any]:
    item = proposals.by_source[source_id]
    source = catalog.sources[source_id]
    record = state.assisted_photos.get(source_id)
    boards = []
    used: dict[str, int] = {}
    present_quads: list[tuple[int, list[list[float]]]] = []
    for index, annotation in sorted(source_rows(state, source_id).items()):
        owner = owned_board(record, annotation)
        nodes = [[p.x, p.y] for p in annotation.nodes]
        if owner is not None and owner.proposal_id and owner.status != "removed":
            used[owner.proposal_id] = index
        if annotation.presence == "present" and nodes:
            present_quads.append((index, [nodes[i] for i in CORNER_NODES]))
        boards.append(
            {
                "board_index": index,
                "revision": annotation.revision,
                "presence": annotation.presence,
                "full_approved": annotation.full_approved,
                "nodes": nodes,
                "owner": "workflow" if owner else "lab",
                "status": owner.status
                if owner
                else ("lab_accepted" if annotation.full_approved else "lab_draft"),
                "origin": owner.origin if owner else "existing_lab",
                "proposal_id": owner.proposal_id if owner else "",
                "locked": owner is None,
                "actor": annotation.actor,
            }
        )
    dismissed = set(record.dismissed_proposal_ids) if record else set()
    shown = []
    for proposal in item.get("proposals", []):
        nodes = proposal["nodes"]
        centre = np.mean(np.asarray([nodes[i] for i in CORNER_NODES]), axis=0).tolist()
        covered = next(
            (
                index
                for index, quad in present_quads
                if used.get(proposal["proposal_id"]) != index and _inside(centre, quad)
            ),
            None,
        )
        shown.append(
            {
                "proposal_id": proposal["proposal_id"],
                "rank": proposal["rank"],
                "score": proposal["score"],
                "nodes": nodes,
                "reasons": proposal["reasons"],
                "dismissed": proposal["proposal_id"] in dismissed,
                "used_by": used.get(proposal["proposal_id"]),
                "covered_by": covered,
            }
        )
    review = state.photo_reviews.get(source_id)
    return {
        "queue_index": item["queue_index"],
        "total": len(proposals.items),
        "source_id": source_id,
        "sha256": source.sha256,
        "game": item["game"],
        "filename": source.filename,
        "training_set_files": item["training_set_files"],
        "width": item.get("width"),
        "height": item.get("height"),
        "proposal_status": item.get("status"),
        "revision": state.revision,
        "boards": boards,
        "proposals": shown,
        "board_revisions": board_revisions(state, source_id),
        "complete": photo_complete(state, source),
        "confirmed_board_count": record.confirmed_board_count if record else None,
        "active_ms": record.active_ms if record else 0,
        "photo_review": {
            "accepted": photo_accepted(state, source),
            "rejected": bool(review and review.rejected),
            "issues": len(review.issues) if review else 0,
        },
        "split_stale": state.split_stale,
    }


def queue_view(state: AnnotationState, catalog: Catalog, proposals: ProposalSet) -> dict[str, Any]:
    rows = []
    games: dict[str, dict[str, int]] = {
        key: {"total": 0, "complete": 0, "started": 0} for key in WORKFLOW_GAMES
    }
    durations: list[tuple[str, int]] = []
    for item in proposals.items:
        source = catalog.sources[item["source_id"]]
        status = photo_status(state, source)
        record = state.assisted_photos.get(source.id)
        active = record.active_ms if record else 0
        games[item["game"]]["total"] += 1
        if status != "new":
            games[item["game"]][status] += 1
        if status == "complete" and record is not None:
            durations.append((record.completed_at, active))
        rows.append(
            {
                "i": item["queue_index"],
                "source_id": source.id,
                "game": item["game"],
                "status": status,
                "proposals": len(item.get("proposals", [])),
                "active_ms": active,
            }
        )
    durations.sort()
    first = [ms for _, ms in durations[:10]]
    return {
        "proposal_set_id": proposals.set_id,
        "revision": state.revision,
        "items": rows,
        "games": games,
        "complete": sum(g["complete"] for g in games.values()),
        "total": len(rows),
        "timing": {
            "complete_photos": len(durations),
            "mean_active_ms": int(sum(ms for _, ms in durations) / len(durations))
            if durations
            else None,
            "first_ten_mean_active_ms": int(sum(first) / len(first)) if first else None,
        },
        "split_stale": state.split_stale,
    }


# --- export ----------------------------------------------------------------------------------


def _reading_order(boards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .neural_grid_inference import BoardDetection, reading_order

    detections = [
        BoardDetection(
            score=float(i), screen_quad=np.asarray(b["quad"], dtype=np.float32).reshape(4, 2)
        )
        for i, b in enumerate(boards)
    ]
    return [boards[int(d.score)] for d in reading_order(detections)]


def export_rows(
    catalog: Catalog, state: AnnotationState, proposals: ProposalSet
) -> list[dict[str, Any]]:
    """Complete photos in queue order: photo -> boards -> 24 nodes with provenance."""

    rows = []
    order = {item["source_id"]: item["queue_index"] for item in proposals.items}
    complete = sorted(
        (sid for sid in state.assisted_photos if photo_complete(state, catalog.sources[sid])),
        key=lambda sid: (order.get(sid, len(order)), sid),
    )
    for source_id in complete:
        source = catalog.sources[source_id]
        game = workflow_game(source)
        record = state.assisted_photos[source_id]
        image = catalog.image(source)
        boards = []
        for index, annotation in sorted(source_rows(state, source_id).items()):
            if annotation.presence != "present":
                continue
            owner = owned_board(record, annotation)
            nodes = [[p.x, p.y] for p in annotation.nodes]
            boards.append(
                {
                    "boardIndex": index,
                    "nodes": nodes,
                    "quad": [nodes[i] for i in CORNER_NODES],
                    "topology": annotation.topology.model_dump(),
                    "unavailableCellIndices": [],
                    "level": BOARD_LEVEL,
                    "origin": owner.origin if owner else "existing_lab",
                    "proposalId": owner.proposal_id if owner else "",
                    "proposalSha256": owner.proposal_sha256 if owner else "",
                    "maxCornerShiftPx": owner.max_corner_shift_px if owner else None,
                    "annotationRevision": annotation.revision,
                    "geometrySha256": annotation.geometry_sha256,
                    "actor": annotation.actor,
                    "decidedAt": annotation.decided_at,
                }
            )
        ordered = _reading_order(boards)
        for rank, board in enumerate(ordered):
            board["readingOrder"] = rank
        family = state.families.get(source_id)
        item = proposals.by_source.get(source_id, {})
        rows.append(
            {
                "schemaVersion": EXPORT_FORMAT,
                "imageId": source_id,
                "gameKey": game,
                "gameId": source.game_id,
                "gameName": source.game_name,
                "filename": source.filename,
                "trainingSetFiles": item.get("training_set_files", []),
                "sourceChecksumSha256": source.sha256,
                "labImagePath": f"images/{source.sha256}.img",
                "suffix": (Path(source.filename).suffix.lower() or ".jpg"),
                "coordinateSpace": "exif-normalized-rgb-pixels-v1",
                "orientedWidth": image.size[0],
                "orientedHeight": image.size[1],
                "familyId": family.family_id if family else source.family_candidate,
                "familyCandidate": source.family_candidate,
                "familyProvenance": family.provenance if family else "catalog_candidate",
                "confirmedBoardCount": record.confirmed_board_count,
                "completedAt": record.completed_at,
                "activeMs": record.active_ms,
                "boardRevisions": record.completed_board_revisions,
                "boards": ordered,
            }
        )
    return rows


def write_export(
    catalog: Catalog, state: AnnotationState, proposals: ProposalSet, output_root: Path
) -> Path:
    """Create-only ``<output>/<export_id>`` with the rows and a checksummed manifest."""

    rows = export_rows(catalog, state, proposals)
    data = b"".join(canonical(row) + b"\n" for row in rows)
    rows_sha = hashlib.sha256(data).hexdigest()
    games: dict[str, dict[str, int]] = {}
    for row in rows:
        summary = games.setdefault(row["gameKey"], {"photos": 0, "boards": 0})
        summary["photos"] += 1
        summary["boards"] += len(row["boards"])
    manifest = {
        "format": EXPORT_FORMAT,
        "decision_reference": "D-490",
        "snapshot_id": store_snapshot_id(catalog),
        "catalog_snapshot": catalog.root.name if catalog.root else None,
        "store_revision": state.revision,
        "proposal_set_id": proposals.set_id,
        "photos": len(rows),
        "boards": sum(len(row["boards"]) for row in rows),
        "games": games,
        "files": {EXPORT_ROWS: rows_sha},
    }
    export_id = digest(manifest)
    reject_links(output_root)
    target = output_root / export_id
    if target.exists():
        existing = json.loads((target / EXPORT_MANIFEST).read_bytes())
        if (
            existing != {**manifest, "export_id": export_id}
            or file_sha256(target / EXPORT_ROWS) != rows_sha
        ):
            raise ValueError("ASSISTED_EXPORT_CONFLICT")
        return target
    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".export-", dir=output_root))
    try:
        (stage / EXPORT_ROWS).write_bytes(data)
        (stage / EXPORT_MANIFEST).write_bytes(canonical({**manifest, "export_id": export_id}))
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def read_export(root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((root / EXPORT_MANIFEST).read_bytes())
    if manifest.get("format") != EXPORT_FORMAT:
        raise ValueError("ASSISTED_EXPORT_FORMAT_UNSUPPORTED")
    if file_sha256(root / EXPORT_ROWS) != manifest["files"][EXPORT_ROWS]:
        raise ValueError("ASSISTED_EXPORT_CHECKSUM_MISMATCH")
    with (root / EXPORT_ROWS).open("rb") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_reader_snapshot(
    rows: Iterable[Mapping[str, Any]],
    catalog: Catalog,
    output_root: Path,
    roles: Mapping[str, str],
) -> Path:
    """Adapter: a ``production-geometry-snapshot-v1`` directory that ``load_samples`` reads.

    Only rows whose ``imageId`` has a role are written; images are copied after a
    SHA-256 check. Role assignment (training versus held-out evaluation) is the caller's.
    """

    from .neural_grid_protocol import COORDINATE_SPACE, SNAPSHOT_FORMAT, SNAPSHOT_POLICY

    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".reader-", dir=output_root))
    try:
        files: dict[str, str] = {}
        records = []
        selection = []
        for row in rows:
            role = roles.get(str(row["imageId"]))
            if role is None:
                continue
            source = catalog.sources[str(row["imageId"])]
            data = catalog.paths[source.asset_id].read_bytes()
            sha = str(row["sourceChecksumSha256"])
            if hashlib.sha256(data).hexdigest() != sha or source.sha256 != sha:
                raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
            suffix = str(row["suffix"])
            relative = f"images/{sha[:2]}/{sha}{suffix}"
            if relative not in files:
                (stage / relative).parent.mkdir(parents=True, exist_ok=True)
                (stage / relative).write_bytes(data)
                files[relative] = sha
            records.append(
                {
                    "schemaVersion": "production-geometry-sample-v1",
                    "imageId": row["imageId"],
                    "role": role,
                    "imageLevel": BOARD_LEVEL,
                    "sourceChecksumSha256": sha,
                    "imagePath": relative,
                    "coordinateSpace": COORDINATE_SPACE,
                    "orientedWidth": row["orientedWidth"],
                    "orientedHeight": row["orientedHeight"],
                    "familyId": row["familyId"],
                    "gameKey": row["gameKey"],
                    "boards": [
                        {
                            "nodes": board["nodes"],
                            "quad": board["quad"],
                            "unavailableCellIndices": board["unavailableCellIndices"],
                            "level": board["level"],
                            "origin": board["origin"],
                            "positionIndex": board["boardIndex"],
                        }
                        for board in row["boards"]
                    ],
                }
            )
            selection.append([row["imageId"], role, sha, suffix])
        records.sort(key=lambda r: str(r["imageId"]))
        samples = b"".join(canonical(r) + b"\n" for r in records)
        (stage / "samples.jsonl").write_bytes(samples)
        files["samples.jsonl"] = hashlib.sha256(samples).hexdigest()
        split = canonical(
            {
                "selectionColumns": ["imageId", "role", "sourceChecksumSha256", "suffix"],
                "selection": sorted(selection),
                "samplesSha256": files["samples.jsonl"],
                "source": EXPORT_FORMAT,
            }
        )
        (stage / "split.json").write_bytes(split)
        files["split.json"] = hashlib.sha256(split).hexdigest()
        snapshot_id = digest({"files": files, "source": EXPORT_FORMAT})
        manifest = {
            "format": SNAPSHOT_FORMAT,
            "snapshotId": snapshot_id,
            "policy": {"policyVersion": SNAPSHOT_POLICY, "source": EXPORT_FORMAT},
            "files": files,
        }
        (stage / "manifest.json").write_bytes(canonical(manifest))
        target = output_root / snapshot_id
        if target.exists():
            raise ValueError("ASSISTED_READER_SNAPSHOT_EXISTS")
        os.replace(stage, target)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


# --- loopback page ---------------------------------------------------------------------------


class Workspace:
    """One store, one proposal set, serialized access, a state cache keyed by file stat."""

    def __init__(
        self,
        catalog: Catalog,
        annotation_root: Path,
        proposals_root: Path,
        actor: str = "operator",
    ) -> None:
        self.catalog = catalog
        self.store = AnnotationStore(annotation_root, catalog)
        self.proposals = load_proposals(proposals_root, catalog)
        self.actor = actor
        self.lock = threading.Lock()
        self._cached: tuple[tuple[int, int], AnnotationState] | None = None
        self._images: OrderedDict[str, bytes] = OrderedDict()

    def _stat(self) -> tuple[int, int]:
        path = self.store.root / "state.json"
        try:
            info = path.stat()
        except FileNotFoundError:
            return (0, 0)
        return (info.st_mtime_ns, info.st_size)

    def _retry(self, operation: Callable[[], AnnotationState]) -> AnnotationState:
        deadline = time.monotonic() + 3.0
        while True:
            try:
                return operation()
            except ValueError as error:
                if str(error) != "ANNOTATION_STORE_BUSY" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    def state(self) -> AnnotationState:
        with self.lock:
            stat = self._stat()
            if self._cached is not None and self._cached[0] == stat:
                return self._cached[1]
            state = self._retry(self.store.read)
            self._cached = (stat, state)
            return state

    def decide(self, decision: Decision) -> AnnotationState:
        request = store_request(decision, self.proposals, self.catalog, self.actor)
        with self.lock:
            state = self._retry(lambda: self.store.mutate(request))
            self._cached = None
            return state

    def image(self, source_id: str) -> bytes:
        if source_id not in self.proposals.by_source:
            raise KeyError(source_id)
        with self.lock:
            if source_id in self._images:
                self._images.move_to_end(source_id)
                return self._images[source_id]
        data = encode(self.catalog.image(self.catalog.sources[source_id]))
        with self.lock:
            self._images[source_id] = data
            while len(self._images) > 12:
                self._images.popitem(last=False)
        return data


def create_app(workspace: Workspace, port: int = DEFAULT_PORT) -> Any:
    from fastapi import FastAPI, HTTPException, Response
    from fastapi.responses import HTMLResponse

    from .assisted_annotation_page import PAGE
    from .label_review import LoopbackBoundary

    application = FastAPI(
        title="Assisted complete-photo annotation", docs_url=None, redoc_url=None, openapi_url=None
    )
    application.add_middleware(LoopbackBoundary, port=port)

    def conflict(error: ValueError) -> HTTPException:
        return HTTPException(409, str(error))

    @application.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @application.get("/api/queue")
    def queue() -> dict[str, Any]:
        try:
            return queue_view(workspace.state(), workspace.catalog, workspace.proposals)
        except ValueError as error:
            raise conflict(error) from error

    @application.get("/api/photos/{queue_index}")
    def photo(queue_index: int) -> dict[str, Any]:
        items = workspace.proposals.items
        if not 0 <= queue_index < len(items):
            raise HTTPException(404, "PHOTO_NOT_FOUND")
        try:
            return photo_view(
                workspace.state(),
                workspace.catalog,
                workspace.proposals,
                items[queue_index]["source_id"],
            )
        except ValueError as error:
            raise conflict(error) from error

    @application.post("/api/decisions")
    def decide(body: Decision) -> dict[str, Any]:
        try:
            state = workspace.decide(body)
            return photo_view(state, workspace.catalog, workspace.proposals, body.source_id)
        except ValueError as error:
            raise conflict(error) from error

    @application.get("/api/images/{source_id}")
    def image(source_id: str) -> Response:
        try:
            data = workspace.image(source_id)
        except KeyError as error:
            raise HTTPException(404, "IMAGE_NOT_FOUND") from error
        except (InvalidImageError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return Response(
            data, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"}
        )

    return application


# --- command line ----------------------------------------------------------------------------


def _single_proposal_set(root: Path) -> Path:
    if (root / PROPOSALS_FILE).is_file():
        return root
    sets = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if len(sets) != 1:
        raise SystemExit(f"Expected exactly one proposal set in {root}, found {len(sets)}")
    return sets[0]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("proposals", "serve", "status", "export"):
        command = commands.add_parser(name)
        command.add_argument("--snapshot", type=Path, required=True)
        command.add_argument("--annotations", type=Path, required=True)
        if name == "proposals":
            command.add_argument("--training-set", type=Path, required=True)
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--threads", type=int, default=4)
        else:
            command.add_argument(
                "--proposals", type=Path, required=True, help="proposal set or its parent"
            )
        if name == "serve":
            command.add_argument("--port", type=int, default=DEFAULT_PORT)
            command.add_argument("--actor", default="operator")
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    catalog = Catalog(arguments.snapshot)
    store = AnnotationStore(arguments.annotations, catalog)
    if arguments.command == "proposals":
        if not 1 <= arguments.threads <= 4:
            raise SystemExit("--threads must be 1..4 (CPU only)")
        generate_proposals(
            catalog,
            store.read(),
            arguments.training_set,
            arguments.bundle,
            arguments.output,
            threads=arguments.threads,
        )
        return
    proposals_root = _single_proposal_set(arguments.proposals)
    if arguments.command == "serve":
        import uvicorn

        workspace = Workspace(catalog, arguments.annotations, proposals_root, arguments.actor)
        print(f"http://127.0.0.1:{arguments.port}", flush=True)
        uvicorn.run(
            create_app(workspace, arguments.port),
            host="127.0.0.1",
            port=arguments.port,
            log_level="warning",
        )
        return
    proposals = load_proposals(proposals_root, catalog)
    state = store.read()
    if arguments.command == "status":
        summary = queue_view(state, catalog, proposals)
        summary.pop("items")
        json.dump(summary, sys.stdout, indent=2)
        print()
        return
    target = write_export(catalog, state, proposals, arguments.output)
    print(target)


if __name__ == "__main__":
    main()
