"""Bounded read-only snapshots and transaction-owned pilot reconciliation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from PIL import Image, ImageOps
from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.partial_board_reconciliation import (
    MAX_AUDIT_BOARDS,
    PILOT_SEQUENCES,
    RECEIPT_SCHEMA,
    ReconciliationError,
    blocked_board,
    build_manifest,
    digest,
    human_decisions,
    json_value,
    manifest_board,
    validate_manifest,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageSymbolReviewStateModel,
    PartialBoardReconciliationReceiptModel,
)
from game_predictor_api.storage.symbol_cell_source_visibility import (
    current_source_visibilities,
    pinned_visibility_geometry,
)


class PartialBoardReconciliationRepository:
    def __init__(self, session: Session, *, source_roots: Sequence[Path]) -> None:
        self.session = session
        self.source_roots = tuple(root.resolve() for root in source_roots)
        self.router = GameStorageRouter()

    def _execute(self, sql: str, **parameters: Any) -> Any:
        # Explicit connection execution preserves the read route: the session's
        # generic textual-SQL event conservatively treats unknown SQL as writes.
        return self.session.connection().execute(text(sql), parameters)

    def _table(self, game_id: UUID, name: str) -> str:
        location = self.router.bind(self.session, game_id, intent=GameStorageIntent.READ)
        return self.router.qualified_game_table(location, name)

    def preview(self, game_id: UUID) -> dict[str, Any]:
        location = self.router.bind(self.session, game_id, intent=GameStorageIntent.READ)
        boards = []
        for number in PILOT_SEQUENCES:
            try:
                boards.append(self.snapshot_board(game_id, number))
            except (ReconciliationError, ValueError, OSError) as error:
                boards.append(
                    blocked_board(
                        number, getattr(error, "code", "RECONCILIATION_SOURCE_INVALID"), str(error)
                    )
                )
        return build_manifest(
            game_id=game_id, boards=boards, storage_generation=location.generation
        )

    def audit_page(
        self, game_id: UUID, *, after_sequence: int = 0, limit: int = 25
    ) -> dict[str, Any]:
        if not 1 <= limit <= MAX_AUDIT_BOARDS or after_sequence < 0:
            raise ReconciliationError(
                "RECONCILIATION_AUDIT_BOUND_INVALID", "Audit page is out of bounds."
            )
        table = self._table(game_id, "image_review_items")
        numbers = list(
            self._execute(
                f"SELECT DISTINCT sequence_number FROM {table} WHERE game_id=:game_id "
                "AND status IN ('pending','accepted','corrected') AND sequence_number>:after "
                "ORDER BY sequence_number LIMIT :limit",
                game_id=game_id,
                after=after_sequence,
                limit=limit,
            ).scalars()
        )
        rows = []
        for number in numbers:
            try:
                rows.append(self.snapshot_board(game_id, number))
            except (ReconciliationError, ValueError, OSError) as error:
                rows.append(
                    blocked_board(
                        number, getattr(error, "code", "RECONCILIATION_SOURCE_INVALID"), str(error)
                    )
                )
        return {
            "gameId": str(game_id),
            "boards": rows,
            "nextAfterSequence": numbers[-1] if len(numbers) == limit else None,
        }

    def snapshot_board(
        self, game_id: UUID, sequence_number: int, *, lock: bool = False
    ) -> dict[str, Any]:
        r = self._table(game_id, "image_review_items")
        b = self._table(game_id, "recognized_boards")
        s = self._table(game_id, "source_images")
        base = (
            f"FROM {r} r JOIN {b} b ON b.game_id=r.game_id AND b.id=r.recognized_board_id "
            f"JOIN {s} s ON s.game_id=b.game_id AND s.id=b.source_image_id "
            "WHERE r.game_id=:game_id AND r.sequence_number=:number "
            "AND r.status IN ('pending','accepted','corrected')"
        )
        params = {"game_id": game_id, "number": sequence_number}
        if lock:
            self._execute("SELECT s.id " + base + " FOR UPDATE OF s", **params).all()
        rows = (
            self._execute(
                "SELECT to_jsonb(r) AS owner, to_jsonb(b) AS board, to_jsonb(s) AS source "
                + base
                + " LIMIT 2"
                + (" FOR UPDATE OF r,b" if lock else ""),
                **params,
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            raise ReconciliationError(
                "RECONCILIATION_OWNER_CONFLICT", "Expected exactly one current owner."
            )
        owner, board, source = (dict(rows[0][name]) for name in ("owner", "board", "source"))
        if (
            board.get("sequence_number") != sequence_number
            or owner["import_job_id"] != source["import_job_id"]
        ):
            raise ReconciliationError(
                "RECONCILIATION_OWNER_CONFLICT", "Board ownership provenance disagrees."
            )
        if (board.get("grid_rows") or 3, board.get("grid_columns") or 5) != (3, 5):
            raise ReconciliationError(
                "RECONCILIATION_TOPOLOGY_INVALID", "Pilot requires fifteen cells."
            )
        source_geometry = None
        if board["asset_mode"] == "virtual_source":
            table = self._table(game_id, "image_source_geometry_revisions")
            source_geometry = self._execute(
                f"SELECT to_jsonb(g) FROM {table} g WHERE game_id=:game_id AND id=:id",
                game_id=game_id,
                id=board.get("source_geometry_revision_id"),
            ).scalar_one_or_none()
        manual_geometry = None
        if board["geometry_revision"] > 0:
            table = self._table(game_id, "image_board_geometry_revisions")
            manual_geometry = self._execute(
                f"SELECT to_jsonb(g) FROM {table} g WHERE game_id=:game_id "
                "AND recognized_board_id=:id AND revision=:revision",
                game_id=game_id,
                id=board["id"],
                revision=board["geometry_revision"],
            ).scalar_one_or_none()
            if manual_geometry is None or manual_geometry["review_item_id"] != owner["id"]:
                raise ReconciliationError(
                    "RECONCILIATION_GEOMETRY_CONFLICT",
                    "Current manual revision is missing or belongs to another owner.",
                )
        geometry = pinned_visibility_geometry(
            board=board,
            source=source,
            source_geometry=source_geometry,
            manual_geometry=manual_geometry,
        )
        if geometry is None:
            raise ReconciliationError(
                "RECONCILIATION_GEOMETRY_MISSING", "Visibility requires source geometry."
            )
        width = source.get("oriented_width") or source["width"]
        height = source.get("oriented_height") or source["height"]
        self._verify_source(source, width=width, height=height)
        visibility = current_source_visibilities(
            geometry=geometry, width=width, height=height, topology=BoardTopology(rows=3, columns=5)
        )
        cells = self._cells(game_id, sequence_number, lock=lock)
        if any(cell["review_item_id"] != owner["id"] for cell in cells):
            raise ReconciliationError(
                "RECONCILIATION_CELL_OWNER_CONFLICT", "Existing cells belong to a different owner."
            )
        indices = [cell["cell_index"] for cell in cells]
        if len(indices) != len(set(indices)) or any(index not in range(15) for index in indices):
            raise ReconciliationError(
                "RECONCILIATION_CELL_CONFLICT", "Existing logical positions are invalid."
            )
        # D-467: the board's current render manifest replaces the former cell
        # observations in the guard.  The immutable row is pinned by its
        # checksum and provenance; no manifest means no renderable cells.
        manifest_table = self._table(game_id, "board_render_manifests")
        render_manifest = self._execute(
            "SELECT jsonb_build_object('geometryRevision', m.geometry_revision, "
            "'sourceGeometryRevisionId', m.source_geometry_revision_id, "
            "'extractorVersion', m.extractor_version, "
            "'manifestChecksumSha256', m.manifest_checksum_sha256, "
            "'cellCount', jsonb_array_length(m.cells->'cells')) "
            f"FROM {manifest_table} m WHERE game_id=:game_id "
            "AND recognized_board_id=:id AND geometry_revision=:revision",
            game_id=game_id,
            id=board["id"],
            revision=board["geometry_revision"],
        ).scalar_one_or_none()
        if render_manifest is not None and render_manifest["cellCount"] > 15:
            raise ReconciliationError(
                "RECONCILIATION_CELL_CONFLICT", "Source has more than fifteen rendered cells."
            )
        prediction_table = self._table(game_id, "image_symbol_prediction_revisions")
        predictions = self._execute(
            f"SELECT to_jsonb(p) FROM {prediction_table} p "
            "WHERE game_id=:game_id AND review_item_id=:id "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            game_id=game_id,
            id=owner["id"],
        ).scalar_one_or_none()
        queue = self._execute(
            f"SELECT to_jsonb(q) FROM {self._table(game_id, 'image_review_queue_items')} q "
            "WHERE game_id=:game_id AND review_item_id=:id",
            game_id=game_id,
            id=owner["id"],
        ).scalar_one_or_none()
        if queue is None:
            raise ReconciliationError(
                "RECONCILIATION_QUEUE_MISSING", "Owner has no operational queue entry."
            )
        guard = json_value(
            {
                "sequence_number": sequence_number,
                "owner": owner,
                "board": board,
                "source": source,
                "sourceGeometry": source_geometry,
                "manualGeometry": manual_geometry,
                "cells": cells,
                "renderManifest": render_manifest,
                "prediction": predictions,
                "queue": queue,
            }
        )
        return {
            "sequenceNumber": sequence_number,
            "status": "ready",
            "guard": guard,
            "guardSha256": digest(guard),
            "humanSha256": digest(human_decisions(cells)),
            "existingIndices": indices,
            "missingIndices": [index for index in range(15) if index not in indices],
            "sourceVisibility": list(visibility),
        }

    def _cells(
        self, game_id: UUID, sequence_number: int, *, lock: bool = False
    ) -> list[dict[str, Any]]:
        # D-467 S7: the row has no render specification since migration 0136
        # (TASK-0793); TASK-0792 already excluded it, so the guard is unchanged.
        rows = self._execute(
            f"SELECT to_jsonb(c) FROM {self._table(game_id, 'image_symbol_review_cells')} c "
            "WHERE game_id=:game_id AND sequence_number=:number ORDER BY cell_index LIMIT 16"
            + (" FOR UPDATE" if lock else ""),
            game_id=game_id,
            number=sequence_number,
        ).scalars()
        # This also works on 0125: a missing new column means unknown, never outside.
        return [dict(row) | {"source_visibility": row.get("source_visibility")} for row in rows]

    def _verify_source(self, source: Mapping[str, Any], *, width: int, height: int) -> None:
        relative = PurePosixPath(source["relative_path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ReconciliationError(
                "RECONCILIATION_SOURCE_PATH_INVALID", "Source path is unsafe."
            )
        for root in self.source_roots:
            path = root.joinpath(*relative.parts).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            before = path.stat()
            with path.open("rb") as handle:
                checksum = hashlib.file_digest(handle, "sha256").hexdigest()
                handle.seek(0)
                with Image.open(handle) as image:
                    actual_size = ImageOps.exif_transpose(image).size
            after = path.stat()
            if checksum != source["checksum_sha256"] or (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ReconciliationError(
                    "RECONCILIATION_SOURCE_DRIFT", "Source bytes differ from the recorded checksum."
                )
            if actual_size != (width, height):
                raise ReconciliationError(
                    "RECONCILIATION_SOURCE_DIMENSIONS",
                    "Source dimensions differ from the geometry coordinate space.",
                )
            return
        raise ReconciliationError(
            "RECONCILIATION_SOURCE_MISSING", "Managed source image is unavailable."
        )

    def apply_board(self, manifest: Mapping[str, Any], sequence_number: int) -> dict[str, Any]:
        """Caller MUST commit/rollback this transaction; never commit internally."""
        expected = manifest_board(manifest, sequence_number)
        game_id = UUID(manifest["gameId"])
        self.router.bind(
            self.session,
            game_id,
            intent=GameStorageIntent.WRITE,
            expected_generation=manifest["storageGeneration"],
        )
        self._execute("SET LOCAL lock_timeout = '5s'")
        self._execute("SET LOCAL statement_timeout = '30s'")
        if (
            self._execute(
                "SELECT to_regclass('public.partial_board_reconciliation_receipts')"
            ).scalar_one()
            is None
        ):
            raise ReconciliationError(
                "RECONCILIATION_MIGRATION_REQUIRED", "Migration 0128 is required before apply."
            )
        acquire_image_sequence_locks(
            self.session, game_id=game_id, sequence_numbers={sequence_number}
        )
        identity = (game_id, manifest["previewSha256"], sequence_number)
        receipt = self.session.get(PartialBoardReconciliationReceiptModel, identity)
        if receipt is not None:
            if receipt.guard_sha256 != expected["guardSha256"]:
                raise ReconciliationError(
                    "RECONCILIATION_RECEIPT_CONFLICT", "Receipt input differs from the preview."
                )
            return dict(receipt.result) | {"replayed": True}
        if (
            self._execute(
                "SELECT id FROM public.jobs WHERE game_id=:game_id "
                "AND status IN ('created','processing') LIMIT 1",
                game_id=game_id,
            ).first()
            is not None
        ):
            raise ReconciliationError(
                "RECONCILIATION_ACTIVE_WRITES", "Finish active jobs before reconciliation."
            )
        actual = self.snapshot_board(game_id, sequence_number, lock=True)
        if (
            actual["guardSha256"] != expected["guardSha256"]
            or actual["sourceVisibility"] != expected["sourceVisibility"]
        ):
            raise ReconciliationError(
                "RECONCILIATION_REVISION_CONFLICT",
                "Owner, source, geometry or decisions changed after preview.",
            )
        before_human = human_decisions(actual["guard"]["cells"])
        SymbolCellReviewWriteThroughCoordinator(
            self.session
        ).synchronize_for_backfill_reconciliation(
            game_id=game_id,
            review_item_id=UUID(actual["guard"]["owner"]["id"]),
        )
        self.session.flush()
        state = self.session.get(ImageSymbolReviewStateModel, game_id)
        if state is None or state.status == "failed":
            raise ReconciliationError(
                "RECONCILIATION_PROJECTION_FAILED",
                "Symbol projection reported an integrity failure.",
            )
        cells = self._cells(game_id, sequence_number)
        if [cell["cell_index"] for cell in cells] != list(range(15)) or [
            cell["source_visibility"] for cell in cells
        ] != actual["sourceVisibility"]:
            raise ReconciliationError(
                "RECONCILIATION_PROJECTION_INCOMPLETE",
                "Coordinator did not create all fifteen classified positions.",
            )
        after_human = human_decisions(cells)
        if any(after_human.get(key) != value for key, value in before_human.items()):
            raise ReconciliationError(
                "RECONCILIATION_HUMAN_DECISION_CHANGED",
                "Reconciliation would modify an operator decision.",
            )
        result = {
            "schema": RECEIPT_SCHEMA,
            "sequenceNumber": sequence_number,
            "reviewItemId": actual["guard"]["owner"]["id"],
            "cellCount": len(cells),
            "sourceVisibility": actual["sourceVisibility"],
            "replayed": False,
            "afterSha256": digest(cells),
            "humanSha256": digest(after_human),
        }
        self.session.add(
            PartialBoardReconciliationReceiptModel(
                game_id=game_id,
                preview_sha256=manifest["previewSha256"],
                sequence_number=sequence_number,
                guard_sha256=expected["guardSha256"],
                result=result,
            )
        )
        self.session.flush()
        return result

    def rebuild_counts_batch(
        self, manifest: Mapping[str, Any], *, batch_size: int = 5000
    ) -> dict[str, Any]:
        """One bounded batch, caller-owned transaction, resuming the stored cursor."""
        validate_manifest(manifest)
        if not 1 <= batch_size <= 10000:
            raise ReconciliationError(
                "RECONCILIATION_COUNT_BOUND_INVALID", "Invalid count batch size."
            )
        game_id = UUID(manifest["gameId"])
        self.router.bind(
            self.session,
            game_id,
            intent=GameStorageIntent.WRITE,
            expected_generation=manifest["storageGeneration"],
        )
        self._execute("SET LOCAL lock_timeout = '5s'")
        self._execute("SET LOCAL statement_timeout = '30s'")
        receipts = self._execute(
            "SELECT sequence_number,guard_sha256 FROM public.partial_board_reconciliation_receipts "
            "WHERE game_id=:game_id AND preview_sha256=:sha ORDER BY sequence_number LIMIT 71",
            game_id=game_id,
            sha=manifest["previewSha256"],
        ).all()
        expected = [(row["sequenceNumber"], row.get("guardSha256")) for row in manifest["boards"]]
        if [tuple(row) for row in receipts] != expected:
            raise ReconciliationError(
                "RECONCILIATION_PILOT_INCOMPLETE",
                "All seventy receipts are required before the pilot count rebuild.",
            )
        state = self.session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None:
            raise ReconciliationError(
                "RECONCILIATION_COUNTS_UNINITIALIZED", "Symbol projection is not initialized."
            )
        if state.status not in {"ready", "rebuilding"} or (
            state.status == "rebuilding" and state.count_projection_status != "rebuilding"
        ):
            raise ReconciliationError(
                "RECONCILIATION_PROJECTION_NOT_READY",
                "Symbol projection is not ready for count publication.",
            )
        if state.count_projection_status == "ready" and state.count_projection.get(
            "_semantics"
        ) == {"version": 2}:
            return {"complete": True, "scannedBatch": False, "cursor": None}
        repository = SqlAlchemyImageSymbolReviewRepository(self.session)
        if state.count_projection_status != "rebuilding":
            repository.start_count_rebuild(game_id)
        complete = repository.rebuild_count_projection_next_batch(game_id, batch_size=batch_size)
        return {
            "complete": complete,
            "scannedBatch": True,
            "cursor": None
            if state.count_rebuild_cursor is None
            else str(state.count_rebuild_cursor),
        }
