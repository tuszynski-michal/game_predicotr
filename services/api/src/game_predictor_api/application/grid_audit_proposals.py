"""Read-only queue of the grid-audit proposals (TASK-0840).

The queue lives in an immutable artifact written by
``scripts/import_grid_audit_proposals.py``; its state is derived on every read
from the current geometry revision of each audited board. The service never
writes: the operator saves a correction through the existing geometry path
(``image-reviews/{id}/geometry-revisions``), which gives the board a newer
revision and so removes it from the queue.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.domain.grid_audit_proposals import (
    GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA,
    GridAuditBoardState,
    GridAuditProposalArtifact,
    GridAuditProposalError,
    GridAuditProposalGrid,
    GridAuditProposalItem,
    GridAuditQueueStatus,
    derive_grid_audit_queue_status,
    parse_grid_audit_proposal_document,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewListItem

GRID_AUDIT_PROPOSALS_DIRECTORY = "grid-audit-proposals"
GRID_AUDIT_PROPOSALS_FILE = "proposals.json"
GRID_AUDIT_MANIFEST_FILE = "manifest.json"
MAX_GRID_AUDIT_QUEUE_PAGE_SIZE = 50
MAX_GRID_AUDIT_PROPOSALS_BYTES = 64 * 1024 * 1024


class GridAuditProposalStore(Protocol):
    def load(self, game_id: UUID) -> GridAuditProposalArtifact: ...


class GridAuditBoardReader(Protocol):
    def board_states(
        self, *, game_id: UUID, board_ids: Sequence[UUID]
    ) -> Mapping[UUID, GridAuditBoardState]: ...

    def review_item(
        self, *, game_id: UUID, item: GridAuditProposalItem
    ) -> ImageGridReviewListItem | None: ...


@dataclass(frozen=True, slots=True)
class GridAuditQueueEntry:
    item: GridAuditProposalItem
    status: GridAuditQueueStatus
    current_geometry_revision: int | None


@dataclass(frozen=True, slots=True)
class GridAuditQueueCounts:
    total: int
    open: int
    corrected: int
    stale: int
    removed: int
    no_proposal: int
    open_with_symbol_decisions: int


@dataclass(frozen=True, slots=True)
class GridAuditQueuePage:
    audit_id: str
    created_at: str
    sha256: str
    counts: GridAuditQueueCounts
    items: tuple[GridAuditQueueEntry, ...]
    next_after_ordinal: int | None


@dataclass(frozen=True, slots=True)
class GridAuditProposalView:
    audit_id: str
    entry: GridAuditQueueEntry
    proposal: GridAuditProposalGrid | None
    review_item: ImageGridReviewListItem | None


class GridAuditProposalService:
    def __init__(self, store: GridAuditProposalStore, reader: GridAuditBoardReader) -> None:
        self._store = store
        self._reader = reader

    def queue(self, *, game_id: UUID, after_ordinal: int | None, limit: int) -> GridAuditQueuePage:
        if not 1 <= limit <= MAX_GRID_AUDIT_QUEUE_PAGE_SIZE:
            raise GridAuditProposalError(
                "GRID_AUDIT_QUEUE_PAGE_INVALID",
                "The grid audit queue page limit must be between 1 and 50.",
            )
        artifact = self._store.load(game_id)
        states = self._reader.board_states(
            game_id=game_id,
            board_ids=[item.recognized_board_id for item in artifact.items],
        )
        entries = tuple(
            _entry(item, states.get(item.recognized_board_id)) for item in artifact.items
        )
        statuses = Counter(entry.status for entry in entries)
        open_entries = [entry for entry in entries if entry.status is GridAuditQueueStatus.OPEN]
        following = [
            entry
            for entry in open_entries
            if after_ordinal is None or entry.item.ordinal > after_ordinal
        ]
        page = tuple(following[:limit])
        return GridAuditQueuePage(
            audit_id=artifact.audit_id,
            created_at=artifact.created_at,
            sha256=artifact.sha256,
            counts=GridAuditQueueCounts(
                total=len(entries),
                open=statuses[GridAuditQueueStatus.OPEN],
                corrected=statuses[GridAuditQueueStatus.CORRECTED],
                stale=statuses[GridAuditQueueStatus.STALE],
                removed=statuses[GridAuditQueueStatus.REMOVED],
                no_proposal=statuses[GridAuditQueueStatus.NO_PROPOSAL],
                open_with_symbol_decisions=sum(
                    1 for entry in open_entries if entry.item.human_decided_cells > 0
                ),
            ),
            items=page,
            next_after_ordinal=page[-1].item.ordinal if len(following) > len(page) else None,
        )

    def proposal(self, *, game_id: UUID, item_id: str) -> GridAuditProposalView:
        artifact = self._store.load(game_id)
        item = artifact.item(item_id)
        states = self._reader.board_states(game_id=game_id, board_ids=[item.recognized_board_id])
        entry = _entry(item, states.get(item.recognized_board_id))
        review_item = None
        if entry.status is GridAuditQueueStatus.OPEN:
            review_item = self._reader.review_item(game_id=game_id, item=item)
            if review_item is None:
                entry = GridAuditQueueEntry(item, GridAuditQueueStatus.REMOVED, None)
            elif review_item.geometry_revision != item.audit_geometry_revision:
                # The board changed between the two reads: never pair the old
                # proposal with the new geometry.
                entry = GridAuditQueueEntry(
                    item,
                    GridAuditQueueStatus.CORRECTED
                    if review_item.geometry_revision > item.audit_geometry_revision
                    else GridAuditQueueStatus.STALE,
                    review_item.geometry_revision,
                )
                review_item = None
        return GridAuditProposalView(
            audit_id=artifact.audit_id,
            entry=entry,
            proposal=item.proposal if entry.status is GridAuditQueueStatus.OPEN else None,
            review_item=review_item,
        )


def _entry(item: GridAuditProposalItem, state: GridAuditBoardState | None) -> GridAuditQueueEntry:
    return GridAuditQueueEntry(
        item=item,
        status=derive_grid_audit_queue_status(item, state),
        current_geometry_revision=None if state is None else state.geometry_revision,
    )


class FileGridAuditProposalStore(GridAuditProposalStore):
    """The newest checksum-verified proposal artifact of a game under the artifact root.

    Layout: ``grid-audit-proposals/<gameId>/<auditId>/{manifest.json,proposals.json}``.
    The manifest names the SHA-256 of ``proposals.json``; a mismatch is refused.
    """

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve() / GRID_AUDIT_PROPOSALS_DIRECTORY
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, int, int], GridAuditProposalArtifact] = {}

    def load(self, game_id: UUID) -> GridAuditProposalArtifact:
        directory = self._root / str(game_id)
        manifests = []
        if directory.is_dir():
            for candidate in sorted(directory.iterdir()):
                manifest_path = candidate / GRID_AUDIT_MANIFEST_FILE
                if candidate.is_dir() and manifest_path.is_file():
                    manifests.append((candidate, _read_manifest(manifest_path)))
        if not manifests:
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_NOT_FOUND",
                "No grid audit proposal list was imported for this game.",
            )
        audit_directory, manifest = max(
            manifests, key=lambda pair: (str(pair[1]["createdAt"]), pair[0].name)
        )
        path = (audit_directory / GRID_AUDIT_PROPOSALS_FILE).resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_NOT_FOUND",
                "The grid audit proposal file is missing.",
            )
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None and cached.sha256 == manifest["sha256"]:
            return cached
        if stat.st_size > MAX_GRID_AUDIT_PROPOSALS_BYTES:
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_INVALID", "The grid audit proposal file is too large."
            )
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != manifest["sha256"]:
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_CHECKSUM_MISMATCH",
                "The grid audit proposal file does not match its manifest checksum.",
            )
        try:
            document = json.loads(content)
        except json.JSONDecodeError as error:
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_INVALID", "The grid audit proposal file is not JSON."
            ) from error
        artifact = parse_grid_audit_proposal_document(document, sha256=digest)
        if artifact.game_id != game_id or artifact.audit_id != manifest["auditId"]:
            raise GridAuditProposalError(
                "GRID_AUDIT_PROPOSALS_INVALID",
                "The grid audit proposal file belongs to another game or audit.",
            )
        with self._lock:
            self._cache = {key: artifact}
        return artifact


def _read_manifest(path: Path) -> Mapping[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA
            or not isinstance(manifest.get("sha256"), str)
            or len(manifest["sha256"]) != 64
            or not isinstance(manifest.get("auditId"), str)
            or not isinstance(manifest.get("createdAt"), str)
        ):
            raise ValueError("manifest")
    except (OSError, ValueError) as error:
        raise GridAuditProposalError(
            "GRID_AUDIT_PROPOSALS_INVALID", "The grid audit proposal manifest is malformed."
        ) from error
    return manifest


__all__ = [
    "GRID_AUDIT_MANIFEST_FILE",
    "GRID_AUDIT_PROPOSALS_DIRECTORY",
    "GRID_AUDIT_PROPOSALS_FILE",
    "MAX_GRID_AUDIT_QUEUE_PAGE_SIZE",
    "FileGridAuditProposalStore",
    "GridAuditBoardReader",
    "GridAuditProposalService",
    "GridAuditProposalStore",
    "GridAuditProposalView",
    "GridAuditQueueCounts",
    "GridAuditQueueEntry",
    "GridAuditQueuePage",
]
