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
``proposals`` (CPU ONNX, create-only), ``serve`` (127.0.0.1:8105), ``status``,
``export`` (create-only list of complete photos with checksums) and ``close-finished``
(TASK-0825: preview, or with ``--apply`` close, the photos whose boards are all accepted).

TASK-0825 additions: a photo closes automatically when the operator accepts its last
board (``completion_readiness``); fine-tune iterations publish further proposal sets
(generation >= 1) that the page shows for the photos they cover; ``--games`` limits the
queue (the fine-tune round works on Mumie only; other games' data stay untouched).
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
from dataclasses import dataclass, field
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


QUEUE_ITEM_KEYS: Final = (
    "source_id",
    "sha256",
    "game",
    "game_id",
    "game_name",
    "filename",
    "training_set_files",
    "existing_boards",
    "queue_index",
)


def generate_proposals(
    catalog: Catalog,
    state: AnnotationState,
    training_root: Path | None,
    bundle: Path,
    output_root: Path,
    *,
    threads: int = 4,
    log: Callable[[str], None] = print,
    engine: Any | None = None,
    items: Sequence[Mapping[str, Any]] | None = None,
    generation: int = 0,
    supersedes: str | None = None,
    model: Mapping[str, Any] | None = None,
) -> Path:
    """Run the ONNX bundle on CPU over the queue and publish a create-only artifact.

    ``engine`` (anything with ``analyse(rgb)`` and ``model_version``) replaces the bundle's
    ONNX engine in tests; the bundle manifest still binds the artifact identity.

    Generation 0 is the base set over the whole queue (TASK-0824). A later generation
    (TASK-0825 fine-tune iteration) covers only the given queue ``items`` (the photos that
    were still incomplete), names the set it supersedes and the model that produced it,
    and prefixes its proposal identifiers with its own set so that decisions recorded
    against an earlier set keep their provenance.
    """

    if generation < 0 or (generation == 0) != (items is None and supersedes is None):
        raise ValueError("ASSISTED_PROPOSALS_GENERATION_INVALID")
    if items is None:
        if training_root is None:
            raise ValueError("ASSISTED_TRAINING_FOLDER_MISSING")
        queue = build_queue(catalog, state, training_set_files(training_root))
    else:
        queue = [{key: item[key] for key in QUEUE_ITEM_KEYS} for item in items]
    bundle_info = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    identity: dict[str, Any] = {
        "format": PROPOSALS_FORMAT,
        "snapshot_id": store_snapshot_id(catalog),
        "bundle_files": bundle_info["files"],
        "weights_sha256": bundle_info["weights_sha256"],
        "preset_fingerprint": bundle_info.get("preset_fingerprint"),
        "items": [[item["source_id"], item["sha256"]] for item in queue],
    }
    if generation:
        identity.update(generation=generation, supersedes=supersedes, model=dict(model or {}))
    set_id = digest(identity)
    prefix = f"g{generation}-{set_id[:8]}." if generation else ""
    reject_links(output_root)
    target = output_root / set_id
    if target.exists():
        raise ValueError(f"ASSISTED_PROPOSALS_EXIST:{target}")
    if engine is None:
        from .neural_grid_inference import onnx_engine

        engine = onnx_engine(bundle, threads=threads)
    started = time.perf_counter()
    for number, item in enumerate(queue, 1):
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
                "proposal_id": f"{source.id[:16]}.{prefix}{len(proposals)}",
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
            log(f"{number}/{len(queue)} photos, {time.perf_counter() - started:.1f} s")
    payload = {
        **identity,
        "items": queue,
        "proposal_set_id": set_id,
        "decision_reference": "D-490",
        "task": "TASK-0825" if generation else "TASK-0824",
        "bundle": {
            "directory": str(bundle),
            "model_version": engine.model_version,
            "run_id": bundle_info.get("provenance", {}).get("run_id"),
        },
        "catalog_snapshot": catalog.root.name if catalog.root else None,
        "training_set_root": None if training_root is None else str(training_root),
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
    # Merged view (TASK-0825): the set that owns each proposal and the generation chain.
    set_by_id: dict[str, str] = field(default_factory=dict)
    generation: int = 0
    sets: tuple[str, ...] = ()

    def owner(self, proposal_id: str) -> str:
        return self.set_by_id.get(proposal_id, self.set_id)


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
    generation = int(payload.get("generation", 0))
    return ProposalSet(
        root,
        root.name,
        payload,
        items,
        by_source,
        by_id,
        {proposal_id: root.name for proposal_id in by_id},
        generation,
        (root.name,),
    )


def proposal_set_directories(root: Path) -> list[Path]:
    """One set directory, or every published set below a proposals root."""

    reject_links(root)
    if (root / PROPOSALS_FILE).is_file():
        return [root]
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / PROPOSALS_FILE).is_file()
    )


def merge_proposal_sets(
    sets: Sequence[ProposalSet], games: Sequence[str] = WORKFLOW_GAMES
) -> ProposalSet:
    """The page's view: base queue order, newest proposals per photo, provenance per set.

    Exactly one base set (generation 0) defines the queue; later generations (fine-tune
    iterations) replace the proposals of the photos they cover. Every proposal keeps the
    identifier of the set it came from, so accepted boards keep their own provenance.
    """

    if not sets or set(games) - set(WORKFLOW_GAMES):
        raise ValueError("ASSISTED_PROPOSALS_INVALID")
    bases = [s for s in sets if s.generation == 0]
    if len(bases) != 1:
        raise ValueError("ASSISTED_PROPOSALS_BASE_AMBIGUOUS")
    later = sorted((s for s in sets if s.generation > 0), key=lambda s: s.generation)
    if len({s.generation for s in later}) != len(later):
        raise ValueError("ASSISTED_PROPOSALS_GENERATION_CONFLICT")
    ordered = [bases[0], *later]
    newest: dict[str, tuple[ProposalSet, dict[str, Any]]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    set_by_id: dict[str, str] = {}
    for proposal_set in ordered:
        for item in proposal_set.items:
            if item["source_id"] not in bases[0].by_source:
                raise ValueError("ASSISTED_PROPOSALS_SOURCE_MISMATCH")
            newest[item["source_id"]] = (proposal_set, item)
        for proposal_id, proposal in proposal_set.by_id.items():
            if proposal_id in by_id:
                raise ValueError("ASSISTED_PROPOSALS_ID_CONFLICT")
            by_id[proposal_id] = proposal
            set_by_id[proposal_id] = proposal_set.set_id
    items: list[dict[str, Any]] = []
    for base_item in bases[0].items:
        if base_item["game"] not in games:
            continue
        owner, item = newest[base_item["source_id"]]
        items.append(
            {
                **item,
                "queue_index": len(items),
                "training_set_files": base_item["training_set_files"],
                "proposal_set_id": owner.set_id,
                "proposal_generation": owner.generation,
            }
        )
    return ProposalSet(
        root=bases[0].root,
        set_id=ordered[-1].set_id,
        payload=bases[0].payload,
        items=items,
        by_source={item["source_id"]: item for item in items},
        by_id=by_id,
        set_by_id=set_by_id,
        generation=ordered[-1].generation,
        sets=tuple(s.set_id for s in ordered),
    )


def open_proposals(
    root: Path, catalog: Catalog, games: Sequence[str] = WORKFLOW_GAMES
) -> ProposalSet:
    return merge_proposal_sets(
        [load_proposals(path, catalog) for path in proposal_set_directories(root)], games
    )


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
    # TASK-0825: after an accepted board, close the photo when every board is accepted.
    # The page sends it only when it holds no unsaved new or moved board.
    auto_complete: bool = False


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
        proposal_set_id=proposals.owner(decision.proposal_id) if with_proposal else "",
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
        "proposal_set_id": item.get("proposal_set_id", proposals.set_id),
        "proposal_generation": item.get("proposal_generation", 0),
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
    visible = {item["game"] for item in proposals.items}
    games: dict[str, dict[str, int]] = {
        key: {"total": 0, "complete": 0, "started": 0} for key in WORKFLOW_GAMES if key in visible
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
        "proposal_generation": proposals.generation,
        "hidden_games": [key for key in WORKFLOW_GAMES if key not in visible],
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


# --- automatic completion (TASK-0825) ----------------------------------------------------------


def completion_readiness(
    state: AnnotationState, catalog: Catalog, proposals: ProposalSet, source_id: str
) -> tuple[int | None, str]:
    """Board count the photo would be completed with, or ``None`` and the reason.

    The operator rule of D-490: a photo closes when the operator has accepted all of its
    boards — every present board is fully accepted (no revoked acceptance, no draft),
    every proposal shown for the photo is dismissed, used or covered by a saved board, and
    at least one board was accepted in this workflow (a photo of earlier lab work alone is
    not the operator's decision). The board count is the number of accepted boards.
    """

    source = catalog.sources.get(source_id)
    if source is None or source_id not in proposals.by_source:
        return None, "ASSISTED_SOURCE_NOT_IN_QUEUE"
    if photo_complete(state, source):
        return None, "ASSISTED_PHOTO_ALREADY_COMPLETE"
    record = state.assisted_photos.get(source_id)
    present = [a for a in source_rows(state, source_id).values() if a.presence == "present"]
    if not present:
        return None, "ASSISTED_NO_BOARD"
    if len(present) > MAX_BOARD_INDEX + 1:
        return None, "ASSISTED_BOARD_COUNT_MISMATCH"
    if any(not a.full_approved for a in present):
        return None, "ASSISTED_BOARD_NOT_ACCEPTED"
    if any(a.topology.columns != 5 for a in present):
        return None, "ASSISTED_TOPOLOGY_UNSUPPORTED"
    owned = [owned_board(record, a) for a in present]
    if not any(board is not None and board.status == "accepted" for board in owned):
        return None, "ASSISTED_NO_WORKFLOW_ACCEPTANCE"
    view = photo_view(state, catalog, proposals, source_id)
    if any(
        not p["dismissed"] and p["used_by"] is None and p["covered_by"] is None
        for p in view["proposals"]
    ):
        return None, "ASSISTED_PROPOSAL_UNDECIDED"
    review = state.photo_reviews.get(source_id)
    if review is not None and any(
        issue.status == "needs_correction" for issue in review.issues.values()
    ):
        return None, "PHOTO_CORRECTIONS_REQUIRED"
    return len(present), "ready"


def completion_request(
    state: AnnotationState,
    source: Source,
    count: int,
    request_id: str,
    actor: str,
) -> AssistedRequest:
    return AssistedRequest(
        request_id=request_id,
        expected_revision=state.revision,
        actor=actor,
        action="complete_photo",
        source_id=source.id,
        source_sha256=source.sha256,
        confirmed_board_count=count,
        expected_board_revisions=board_revisions(state, source.id),
    )


def close_request_id(source_id: str, revisions: Mapping[str, int]) -> str:
    """Deterministic per photo and geometry: a retried close never completes twice."""

    return f"close-{digest([source_id, dict(revisions)])[:40]}"


def close_finished_photos(
    store: AnnotationStore,
    catalog: Catalog,
    proposals: ProposalSet,
    *,
    apply: bool,
    actor: str = "operator-auto-close",
    read: Callable[[], AnnotationState] | None = None,
) -> list[dict[str, Any]]:
    """One-off closing of photos that already satisfy the automatic-completion rule.

    The preview (``apply=False``) writes nothing. Applying writes one ``complete_photo``
    decision per ready photo through ``AnnotationStore.mutate``; every photo is re-checked
    on the current state first, so concurrent operator work is never overwritten.
    """

    reader = read or store.read
    results: list[dict[str, Any]] = []
    state = reader()
    for item in proposals.items:
        source_id = item["source_id"]
        source = catalog.sources[source_id]
        count, reason = completion_readiness(state, catalog, proposals, source_id)
        row: dict[str, Any] = {
            "queue_index": item["queue_index"],
            "source_id": source_id,
            "filename": item["filename"],
            "boards": count,
            "status": "ready" if count is not None else "skipped",
            "reason": reason,
        }
        if count is None:
            if reason not in ("ASSISTED_PHOTO_ALREADY_COMPLETE", "ASSISTED_NO_BOARD"):
                results.append(row)
            continue
        attempt = 0
        while apply and row["status"] == "ready" and count is not None:
            attempt += 1
            request = completion_request(
                state,
                source,
                count,
                close_request_id(source_id, board_revisions(state, source_id)),
                actor,
            )
            try:
                state = store.mutate(request)
                row["status"] = "closed" if photo_complete(state, source) else "failed"
            except ValueError as error:
                code = str(error)
                if attempt >= 40 or code not in (
                    "ANNOTATION_STORE_BUSY",
                    "ANNOTATION_REVISION_CONFLICT",
                ):
                    row.update(status="failed", reason=code)
                    break
                time.sleep(0.25 if code == "ANNOTATION_STORE_BUSY" else 0)
                state = reader()  # concurrent operator work: re-check on the current state
                count, reason = completion_readiness(state, catalog, proposals, source_id)
                if count is None:
                    row.update(status="skipped", reason=reason)
                row["boards"] = count
        results.append(row)
    return results


def read_store_state(
    root: Path, catalog: Catalog, timeout_seconds: float = 10.0
) -> AnnotationState:
    """Read the store without holding its lock while parsing (the page keeps writing).

    The bytes are copied under a short, bounded lock (the writer retries for 3 s) and
    parsed after release; the integrity envelope and the snapshot binding are checked.
    """

    from .annotations import exclusive_bounded

    path = root / "state.json"
    with exclusive_bounded(root, timeout_seconds):
        reject_links(path)
        data = path.read_bytes() if path.exists() else None
    if data is None:
        return AnnotationState(snapshot_id=store_snapshot_id(catalog))
    try:
        envelope = json.loads(data)
        payload = envelope["payload"]
        if not isinstance(payload, dict) or envelope["sha256"] != digest(payload):
            raise ValueError("ANNOTATION_INTEGRITY_ERROR")
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("ANNOTATION_INTEGRITY_ERROR") from error
    state = AnnotationState.model_validate(payload["state"])
    if state.snapshot_id != store_snapshot_id(catalog):
        raise ValueError("ANNOTATION_SNAPSHOT_CONFLICT")
    return state


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
                    "proposalSetId": owner.proposal_set_id if owner else "",
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
    catalog: Catalog,
    state: AnnotationState,
    proposals: ProposalSet,
    output_root: Path,
    games: Sequence[str] | None = None,
) -> Path:
    """Create-only ``<output>/<export_id>`` with the rows and a checksummed manifest.

    ``games`` limits the rows to the given workflow games (the fine-tune iteration exports
    Mumie only); the default keeps every complete photo.
    """

    rows = [
        row
        for row in export_rows(catalog, state, proposals)
        if games is None or row["gameKey"] in games
    ]
    data = b"".join(canonical(row) + b"\n" for row in rows)
    rows_sha = hashlib.sha256(data).hexdigest()
    per_game: dict[str, dict[str, int]] = {}
    for row in rows:
        summary = per_game.setdefault(row["gameKey"], {"photos": 0, "boards": 0})
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
        "games": per_game,
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
            # Content-addressed: the same rows and roles give the same directory; a
            # retried iteration reuses it, anything else is a conflict.
            if (target / "manifest.json").read_bytes() != canonical(manifest):
                raise ValueError("ASSISTED_READER_SNAPSHOT_EXISTS")
            return target
        os.replace(stage, target)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


# --- loopback page ---------------------------------------------------------------------------


class Workspace:
    """One store, the proposal sets, serialized access, a state cache keyed by file stat.

    ``proposals_root`` is one set directory or the directory holding every set; in the
    latter case a newly published set (a fine-tune iteration) is picked up on the next
    queue or photo request without a restart. ``games`` limits the queue and counters.
    """

    def __init__(
        self,
        catalog: Catalog,
        annotation_root: Path,
        proposals_root: Path,
        actor: str = "operator",
        games: Sequence[str] = WORKFLOW_GAMES,
    ) -> None:
        self.catalog = catalog
        self.store = AnnotationStore(annotation_root, catalog)
        self.proposals_root = proposals_root
        self.games = tuple(games)
        self.actor = actor
        self.lock = threading.Lock()
        self._sets: dict[str, ProposalSet] = {}
        self.proposals = self._load_sets()
        self._cached: tuple[tuple[int, int], AnnotationState] | None = None
        self._images: OrderedDict[str, bytes] = OrderedDict()

    def _load_sets(self) -> ProposalSet:
        directories = proposal_set_directories(self.proposals_root)
        loaded = {
            path.name: self._sets.get(path.name) or load_proposals(path, self.catalog)
            for path in directories
        }
        merged = merge_proposal_sets(list(loaded.values()), self.games)
        self._sets = loaded
        return merged

    def refresh_proposals(self) -> ProposalSet:
        """Pick up a newly published proposal set (cheap directory listing otherwise)."""

        with self.lock:
            names = {p.name for p in proposal_set_directories(self.proposals_root)}
            if names != set(self._sets):
                self.proposals = self._load_sets()
            return self.proposals

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
        return self.decide_with_auto(decision)[0]

    def decide_with_auto(self, decision: Decision) -> tuple[AnnotationState, bool]:
        """Apply the decision; after an accepted board, close the photo if it is finished.

        The automatic completion is a second store decision with a derived request id.
        It only runs when every board is accepted (``completion_readiness``); a failure
        leaves the accepted board saved and the photo open for the explicit ``C``.
        """

        proposals = self.proposals
        request = store_request(decision, proposals, self.catalog, self.actor)
        with self.lock:
            state = self._retry(lambda: self.store.mutate(request))
            self._cached = None
            if not (decision.auto_complete and decision.action == "accept_board"):
                return state, False
            count, _ = completion_readiness(state, self.catalog, proposals, decision.source_id)
            if count is None:
                return state, False
            completion = completion_request(
                state,
                self.catalog.sources[decision.source_id],
                count,
                f"{decision.request_id}-auto"
                if len(decision.request_id) <= 95
                else f"auto-{digest(decision.request_id)[:48]}",
                self.actor,
            )
            try:
                state = self._retry(lambda: self.store.mutate(completion))
            except ValueError:
                return state, False
            return state, photo_complete(state, self.catalog.sources[decision.source_id])

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
            proposals = workspace.refresh_proposals()
            return queue_view(workspace.state(), workspace.catalog, proposals)
        except ValueError as error:
            raise conflict(error) from error

    @application.get("/api/photos/{queue_index}")
    def photo(queue_index: int) -> dict[str, Any]:
        try:
            proposals = workspace.refresh_proposals()
        except ValueError as error:
            raise conflict(error) from error
        items = proposals.items
        if not 0 <= queue_index < len(items):
            raise HTTPException(404, "PHOTO_NOT_FOUND")
        try:
            return photo_view(
                workspace.state(),
                workspace.catalog,
                proposals,
                items[queue_index]["source_id"],
            )
        except ValueError as error:
            raise conflict(error) from error

    @application.post("/api/decisions")
    def decide(body: Decision) -> dict[str, Any]:
        try:
            state, completed = workspace.decide_with_auto(body)
            view = photo_view(state, workspace.catalog, workspace.proposals, body.source_id)
            return {**view, "auto_completed": completed}
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("proposals", "serve", "status", "export", "close-finished"):
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
            command.add_argument(
                "--games",
                nargs="+",
                choices=WORKFLOW_GAMES,
                default=list(WORKFLOW_GAMES),
                help="games in the queue and counters (TASK-0825: mumie)",
            )
        if name == "serve":
            command.add_argument("--port", type=int, default=DEFAULT_PORT)
            command.add_argument("--actor", default="operator")
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
        if name == "close-finished":
            command.add_argument(
                "--apply", action="store_true", help="write; without it only a preview"
            )
            command.add_argument("--actor", default="operator-auto-close")
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
    if arguments.command == "serve":
        import uvicorn

        workspace = Workspace(
            catalog, arguments.annotations, arguments.proposals, arguments.actor, arguments.games
        )
        print(f"http://127.0.0.1:{arguments.port}", flush=True)
        uvicorn.run(
            create_app(workspace, arguments.port),
            host="127.0.0.1",
            port=arguments.port,
            log_level="warning",
        )
        return
    proposals = open_proposals(arguments.proposals, catalog, arguments.games)
    if arguments.command == "close-finished":
        results = close_finished_photos(
            store,
            catalog,
            proposals,
            apply=arguments.apply,
            actor=arguments.actor,
            read=lambda: read_store_state(arguments.annotations, catalog),
        )
        summary: dict[str, int] = {}
        for row in results:
            summary[row["status"]] = summary.get(row["status"], 0) + 1
        json.dump(
            {"apply": arguments.apply, "summary": summary, "photos": results},
            sys.stdout,
            indent=2,
        )
        print()
        return
    state = read_store_state(arguments.annotations, catalog)
    if arguments.command == "status":
        summary = queue_view(state, catalog, proposals)
        summary.pop("items")
        json.dump(summary, sys.stdout, indent=2)
        print()
        return
    games = None if set(arguments.games) == set(WORKFLOW_GAMES) else arguments.games
    target = write_export(catalog, state, proposals, arguments.output, games)
    print(target)


if __name__ == "__main__":
    main()
