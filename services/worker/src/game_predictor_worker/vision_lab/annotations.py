"""Atomic, checksummed annotation revisions without application database access."""

import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .annotation_contracts import (
    AnnotationRequest,
    AnnotationState,
    AssistedRequest,
    BackupResult,
    FamilyRequest,
    GeometryQualificationRequest,
    PhotoReviewRequest,
    SplitRequest,
    StoredFamily,
    Timing,
    TimingReport,
)
from .catalog import Catalog
from .contracts import Board, Point, Topology
from .geometry import cell_quads
from .geometry_qualification import apply_qualification, qualification_effective
from .photo_review import apply_photo_review, geometry_changed, photo_accepted
from .snapshot import canonical, reject_links


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def annotation_key(source_id: str, board_index: int) -> str:
    return f"{source_id}:{board_index}"


def interpolate(corners: list[Point], topology: Topology) -> list[Point]:
    if len(corners) != 4:
        raise ValueError("FOUR_CORNERS_REQUIRED")
    result = []
    for row in range(4):
        v = row / 3
        for col in range(topology.columns + 1):
            u = col / topology.columns
            weights = ((1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v)
            result.append(
                Point(
                    x=sum(p.x * w for p, w in zip(corners, weights, strict=True)),
                    y=sum(p.y * w for p, w in zip(corners, weights, strict=True)),
                )
            )
    return result


def active_time(intervals: list[int]) -> int:
    if any(value < 0 or value > 86400000 for value in intervals):
        raise ValueError("ACTIVITY_INTERVAL_INVALID")
    return sum(value for value in intervals if value <= 30000)


@contextmanager
def exclusive(root: Path) -> Iterator[None]:
    reject_links(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".lock"
    reject_links(path)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError("ANNOTATION_STORE_BUSY") from error
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("ANNOTATION_STORE_BUSY") from error
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_bounded(root: Path, timeout_seconds: float = 3.0) -> Iterator[None]:
    """Wait briefly for a concurrent store reader without changing write semantics."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        lock = exclusive(root)
        try:
            lock.__enter__()
            break
        except ValueError as error:
            if str(error) != "ANNOTATION_STORE_BUSY" or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    reject_links(path)
    envelope = canonical({"payload": payload, "sha256": digest(payload)})
    if len(envelope) > 64 * 1024 * 1024:
        raise ValueError("ANNOTATION_STORE_TOO_LARGE")
    descriptor, temporary = tempfile.mkstemp(prefix=".annotation-", dir=path.parent)
    staged = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(envelope)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def read_checked(path: Path) -> dict[str, Any]:
    reject_links(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("ANNOTATION_STORE_TOO_LARGE")
        envelope = json.loads(data)
        payload = envelope["payload"]
        if not isinstance(payload, dict) or envelope["sha256"] != digest(payload):
            raise ValueError("ANNOTATION_INTEGRITY_ERROR")
        return payload
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("ANNOTATION_INTEGRITY_ERROR") from error


SPLIT_REFERENCE_KEY = "unchanged_since_revision"


def _last_full_split(history: list[Any]) -> tuple[int, dict[str, Any]] | None:
    for event in reversed(history):
        split = event.get("split") if isinstance(event, dict) else None
        if isinstance(split, dict) and SPLIT_REFERENCE_KEY not in split:
            return int(event["revision"]), split
    return None


def history_split(history: list[Any], split: dict[str, Any] | None) -> dict[str, Any] | None:
    """Split as recorded in one history event.

    The frozen split is about 0.5 MB; copying it into every event filled the
    64 MB store after about a hundred edits. An event whose split equals the
    last fully recorded one stores a reference (revision and digest) instead.
    """

    if split is None:
        return None
    previous = _last_full_split(history)
    split_digest = digest(split)
    if previous is not None and digest(previous[1]) == split_digest:
        return {SPLIT_REFERENCE_KEY: previous[0], "sha256": split_digest}
    return split


def compact_history_splits(history: list[Any]) -> int:
    """Replace repeated full split copies in existing events by references.

    Returns the number of replaced copies. The first full copy of every
    distinct split stays in place, so each reference resolves to an earlier
    event of the same history.
    """

    replaced = 0
    seen: dict[str, int] = {}
    for event in history:
        split = event.get("split") if isinstance(event, dict) else None
        if not isinstance(split, dict) or SPLIT_REFERENCE_KEY in split:
            continue
        split_digest = digest(split)
        if split_digest in seen:
            event["split"] = {SPLIT_REFERENCE_KEY: seen[split_digest], "sha256": split_digest}
            replaced += 1
        else:
            seen[split_digest] = int(event["revision"])
    return replaced


class AnnotationStore:
    def __init__(self, root: Path, catalog: Catalog) -> None:
        if catalog.root is not None and root.resolve().is_relative_to(catalog.root.resolve()):
            raise ValueError("ANNOTATION_SNAPSHOT_OVERLAP")
        self.root = root
        self.catalog = catalog
        self.snapshot_id = digest([s.model_dump() for s in catalog.sources.values()])

    def _load(self) -> dict[str, Any]:
        path = self.root / "state.json"
        if not path.exists():
            return {
                "state": AnnotationState(snapshot_id=self.snapshot_id).model_dump(),
                "receipts": {},
                "history": [],
            }
        payload = read_checked(path)
        state = AnnotationState.model_validate(payload["state"])
        if state.snapshot_id != self.snapshot_id:
            raise ValueError("ANNOTATION_SNAPSHOT_CONFLICT")
        return payload

    def read(self) -> AnnotationState:
        with exclusive(self.root):
            return self._view(AnnotationState.model_validate(self._load()["state"]))

    def _view(self, state: AnnotationState) -> AnnotationState:
        if state.split and any(
            not photo_accepted(state, self.catalog.sources[source_id])
            for source_id in state.split.assignments
        ):
            state.split_stale = True
        if (
            state.split
            and state.split.purpose == "geometry"
            and any(
                source_id not in state.geometry_qualifications
                or not qualification_effective(state, self.catalog.sources[source_id])
                or digest(state.geometry_qualifications[source_id].model_dump()) != fingerprint
                for source_id, fingerprint in (
                    state.split.geometry_qualification_fingerprints.items()
                )
            )
        ):
            state.split_stale = True
        if state.split and state.split.policy_version in (
            "lab-geometry-cohort-split-v1",
            "lab-geometry-cohort-777-targets-v2",
        ):
            from .geometry_qualification import geometry_role_eligible
            from .splits import build_components, component_fingerprints

            components = build_components(self.catalog, state)
            cohort = (
                set(state.split.geometry_source_ids)
                if state.split.geometry_source_ids is not None
                else None
            )
            if (
                components != state.split.leakage_components
                or component_fingerprints(self.catalog, state, components)
                != state.split.leakage_component_fingerprints
                or any(
                    not geometry_role_eligible(
                        state, self.catalog.sources[source_id], state.split.policy_version, cohort
                    )
                    for ids in components.values()
                    if any(source_id in state.split.assignments for source_id in ids)
                    for source_id in ids
                    if self.catalog.sources[source_id].role != "data"
                )
            ):
                state.split_stale = True
        if state.split and state.split.policy_version == "lab-geometry-whole-game-pilot-v1":
            from .whole_game_split import pilot_is_current

            if not pilot_is_current(self.catalog, state):
                state.split_stale = True
        return state

    def mutate(
        self,
        request: AnnotationRequest
        | FamilyRequest
        | SplitRequest
        | PhotoReviewRequest
        | GeometryQualificationRequest
        | AssistedRequest,
    ) -> AnnotationState:
        with exclusive(self.root):
            payload = self._load()
            request_data = request.model_dump()
            # Keep receipts from the original SplitRequest retryable after upgrade.
            if isinstance(request, SplitRequest) and request.purpose == "legacy":
                request_data.pop("purpose")
            if isinstance(request, SplitRequest) and request.geometry_source_ids is None:
                request_data.pop("geometry_source_ids")
            if isinstance(request, SplitRequest) and request.geometry_policy is None:
                request_data.pop("geometry_policy")
            if isinstance(request, SplitRequest) and request.game_partitions is None:
                request_data.pop("game_partitions")
            fingerprint = digest(request_data)
            receipt = payload["receipts"].get(request.request_id)
            if receipt is not None:
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError("REQUEST_ID_CONFLICT")
                return self._view(AnnotationState.model_validate(payload["state"]))
            state = self._view(AnnotationState.model_validate(payload["state"]))
            if request.expected_revision != state.revision:
                raise ValueError("ANNOTATION_REVISION_CONFLICT")
            if not request.actor.strip():
                raise ValueError("ACTOR_REQUIRED")
            now = datetime.now(UTC).isoformat()
            assisted_board: int | None = None
            assisted_review = False
            if isinstance(request, AnnotationRequest):
                self._annotate(state, request, now)
            elif isinstance(request, AssistedRequest):
                from .assisted_annotation import apply_assisted

                assisted_board, assisted_review = apply_assisted(
                    state, self.catalog, request, now, self._annotate
                )
            elif isinstance(request, PhotoReviewRequest):
                source = self.catalog.sources.get(request.source_id)
                if source is None:
                    raise ValueError("SOURCE_NOT_FOUND")
                apply_photo_review(state, source, request, now)
            elif isinstance(request, FamilyRequest):
                decision = request.decision
                ids = decision.source_ids + decision.related_source_ids
                if any(source_id not in self.catalog.sources for source_id in ids):
                    raise ValueError("SOURCE_NOT_FOUND")
                if decision.provenance == "777_v2_verified":
                    raise ValueError("777_V2_SIMILARITY_EVIDENCE_NOT_IMPLEMENTED")
                stored = StoredFamily(**decision.model_dump(), actor=request.actor, decided_at=now)
                for source_id in decision.source_ids:
                    state.families[source_id] = stored
                state.split_stale = state.split is not None
            elif isinstance(request, GeometryQualificationRequest):
                apply_qualification(state, self.catalog.sources, request, now)
            else:
                from .splits import freeze_splits

                if state.split is not None:
                    raise ValueError("SPLIT_ALREADY_FROZEN")
                state.split = freeze_splits(self.catalog, state, request)
            state.revision += 1
            payload["state"] = state.model_dump()
            payload["history"].append(
                {
                    "request": request_data,
                    "at": now,
                    "revision": state.revision,
                    "split": history_split(
                        payload["history"], state.split.model_dump() if state.split else None
                    ),
                    "annotation": state.annotations[
                        annotation_key(request.annotation.source_id, request.annotation.board_index)
                    ].model_dump()
                    if isinstance(request, AnnotationRequest)
                    else state.annotations[
                        annotation_key(request.source_id, assisted_board)
                    ].model_dump()
                    if isinstance(request, AssistedRequest) and assisted_board is not None
                    else None,
                    "family": state.families[request.decision.source_ids[0]].model_dump()
                    if isinstance(request, FamilyRequest)
                    else None,
                    **(
                        {"photo_review": state.photo_reviews[request.source_id].model_dump()}
                        if isinstance(request, PhotoReviewRequest)
                        or (isinstance(request, AssistedRequest) and assisted_review)
                        else {}
                    ),
                    **(
                        {"assisted_photo": state.assisted_photos[request.source_id].model_dump()}
                        if isinstance(request, AssistedRequest)
                        else {}
                    ),
                    **(
                        {
                            "geometry_qualifications": {
                                binding.source_id: state.geometry_qualifications[
                                    binding.source_id
                                ].model_dump()
                                for binding in request.bindings
                            }
                        }
                        if isinstance(request, GeometryQualificationRequest)
                        else {}
                    ),
                }
            )
            payload["receipts"][request.request_id] = {"fingerprint": fingerprint}
            write_atomic(self.root / "state.json", payload)
            return state

    def _annotate(self, state: AnnotationState, request: AnnotationRequest, now: str) -> None:
        item = request.annotation.model_copy(deep=True)
        source = self.catalog.sources.get(item.source_id)
        if source is None:
            raise ValueError("SOURCE_NOT_FOUND")
        width, height = self.catalog.image(source).size
        key = annotation_key(source.id, item.board_index)
        previous = state.annotations.get(key)
        if item.presence == "present":
            proposal = interpolate(item.corners, item.topology)
            cell_quads(
                Board(position_index=item.board_index, status="complete", nodes=proposal),
                item.topology,
            )
            if not item.nodes:
                item.nodes = proposal
            cell_quads(
                Board(position_index=item.board_index, status="complete", nodes=item.nodes),
                item.topology,
            )
            indices = [
                0,
                item.topology.columns,
                len(item.nodes) - 1,
                len(item.nodes) - item.topology.columns - 1,
            ]
            if any(
                item.nodes[i].x != p.x or item.nodes[i].y != p.y
                for i, p in zip(indices, item.corners, strict=True)
            ):
                raise ValueError("CORNERS_NODES_MISMATCH")
            if any(p.x < 0 or p.y < 0 or p.x > width - 1 or p.y > height - 1 for p in item.nodes):
                raise ValueError("GEOMETRY_OUTSIDE_SOURCE")
        elif item.nodes or item.corners:
            raise ValueError("OBSERVATION_HAS_GEOMETRY")
        item.location_approved = request.action in {"approve_location", "approve_full"}
        item.full_approved = request.action == "approve_full"
        if item.full_approved and (
            item.presence != "present"
            or not request.reviewed_all_nodes
            or any(p.provenance != "human" for p in item.nodes)
        ):
            raise ValueError("FULL_NODE_REVIEW_REQUIRED")
        item.revision = 1 if previous is None else previous.revision + 1
        item.source_sha256 = source.sha256
        item.actor, item.decided_at = request.actor, now
        item.geometry_sha256 = digest(
            [
                source.sha256,
                item.topology.model_dump(),
                item.presence,
                [(p.x, p.y) for p in item.nodes],
            ]
        )
        state.annotations[key] = item
        geometry_changed(state, source.id, item.board_index, item.revision)
        state.split_stale = state.split is not None
        elapsed = active_time(request.activity_intervals_ms)
        state.timings.append(
            Timing(
                source_id=source.id,
                game_id=source.game_id,
                active_ms=elapsed,
                corrections=request.correction_count,
            )
        )

    def backup(self) -> BackupResult:
        with exclusive(self.root):
            payload = self._load()
            backup_id = digest(payload)
            directory = self.root / "backups"
            reject_links(directory)
            directory.mkdir(exist_ok=True)
            path = directory / f"{backup_id}.json"
            if path.exists():
                if read_checked(path) != payload:
                    raise ValueError("BACKUP_CONFLICT")
            else:
                write_atomic(path, payload)
            return BackupResult(backup_id=backup_id, revision=payload["state"]["revision"])

    def restore(self, backup_id: str, destination: Path) -> "AnnotationStore":
        if len(backup_id) != 64 or any(c not in "0123456789abcdef" for c in backup_id):
            raise ValueError("BACKUP_ID_INVALID")
        reject_links(destination)
        if self.catalog.root is not None and destination.resolve().is_relative_to(
            self.catalog.root.resolve()
        ):
            raise ValueError("ANNOTATION_SNAPSHOT_OVERLAP")
        if destination.exists():
            raise ValueError("RESTORE_REQUIRES_NEW_DESTINATION")
        payload = read_checked(self.root / "backups" / f"{backup_id}.json")
        if digest(payload) != backup_id or payload["state"]["snapshot_id"] != self.snapshot_id:
            raise ValueError("BACKUP_INTEGRITY_ERROR")
        AnnotationState.model_validate(payload["state"])
        destination.mkdir(parents=True, exist_ok=False)
        write_atomic(destination / "state.json", payload)
        return AnnotationStore(destination, self.catalog)

    def timing_report(self) -> list[TimingReport]:
        state = self.read()
        reports = []
        for game_id in sorted({s.game_id for s in self.catalog.sources.values()}):
            totals: dict[str, int] = {}
            for timing in state.timings:
                if timing.game_id == game_id and timing.active_ms > 0:
                    totals[timing.source_id] = totals.get(timing.source_id, 0) + timing.active_ms
            first = list(totals.values())[:10]
            target = min(40, sum(s.game_id == game_id for s in self.catalog.sources.values()))
            reports.append(
                TimingReport(
                    game_id=game_id,
                    measured_sources=len(first),
                    active_ms=sum(first),
                    target_sources=target,
                    estimated_remaining_ms=(
                        int(sum(first) / len(first) * max(0, target - len(totals)))
                        if first
                        else None
                    ),
                )
            )
        return reports
