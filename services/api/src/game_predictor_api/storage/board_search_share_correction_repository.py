"""One-transaction share writer and indexed correction-history reads (D-492)."""

from __future__ import annotations

import hmac
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import String, and_, distinct, exists, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from game_predictor_api.application.access_credentials import hash_access_token
from game_predictor_api.application.board_search_share_access import BoardSearchShareContext
from game_predictor_api.application.board_search_share_corrections import (
    CorrectionStatus,
    ShareCellCorrectionCommand,
    ShareCellCorrectionReceipt,
    ShareCorrectionBoard,
    ShareCorrectionChange,
    ShareCorrectionDetail,
    ShareCorrectionPage,
    correction_fingerprint,
    share_board_version,
    share_cell_version,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.domain.board_search import BoardSearchAssetMode
from game_predictor_api.domain.board_search_board_detail import BoardSearchBoardCell
from game_predictor_api.domain.board_search_share_queries import (
    decode_query_log_cursor,
    encode_query_log_cursor,
)
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.image_review_repository import acquire_image_review_sequence_locks
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    enter_cell_decision,
)
from game_predictor_api.storage.models import (
    BoardSearchShareQueryEventModel,
    BoardSearchShareSessionModel,
    GameModel,
    ImageSymbolReviewCellModel,
    SymbolModel,
)


def pattern_fingerprint(pattern: list[str]) -> str:
    return correction_fingerprint(sorted(pattern))


def _conflict(message: str) -> BoardSearchShareConflictError:
    return BoardSearchShareConflictError("BOARD_SEARCH_SHARE_CORRECTION_CONFLICT", message)


def _missing() -> BoardSearchShareNotFoundError:
    return BoardSearchShareNotFoundError(
        "BOARD_SEARCH_SHARE_CORRECTION_NOT_FOUND", "This correction or share link does not exist."
    )


class SqlAlchemyBoardSearchShareCorrectionRepository:
    """The caller owns commit/rollback. Never opens an independent audit transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _share(self, session_id: UUID, *, lock: bool = False) -> BoardSearchShareSessionModel:
        statement = select(BoardSearchShareSessionModel).where(
            BoardSearchShareSessionModel.id == session_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self._session.scalar(statement)
        if record is None:
            raise _missing()
        return record

    def _cells(
        self, game_id: UUID, sequence_number: int, *, lock: bool = False
    ) -> tuple[BoardSearchBoardCell, ...]:
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.WRITE)
        repository = SqlAlchemyBoardSearchApproximateWinRepository(self._session)
        mode, document = repository.board_document(game_id=game_id, sequence_number=sequence_number)
        if document is None or mode is not BoardSearchAssetMode.OPERATIONAL_REVIEW:
            raise _missing()
        if lock and document.review_item_id is not None:
            # TASK-0950 (P0-5): ownership lock before the sequence lock.
            enter_cell_decision(
                self._session, game_id=game_id, review_item_id=document.review_item_id
            )
            acquire_image_review_sequence_locks(
                self._session,
                game_id=game_id,
                review_item_id=document.review_item_id,
                requested_sequence_number=sequence_number,
            )
            _mode, document = repository.board_document(
                game_id=game_id, sequence_number=sequence_number
            )
            if document is None:
                raise _missing()
        source = repository.board_view_source(game_id=game_id, document=document)
        if (
            document.status not in {"pending", "accepted", "corrected"}
            or source is None
            or source.current_board_checksum_sha256 != document.board_checksum_sha256
        ):
            raise _conflict("The board reading or its current owner changed; reload the board.")
        cells = repository.board_cells(game_id=game_id, document=document)
        if len(cells) != 15 or {cell.cell_index for cell in cells} != set(range(15)):
            raise _conflict("This board does not have a complete set of current editable cells.")
        return cells

    def correct(
        self,
        context: BoardSearchShareContext,
        access_token: str,
        command: ShareCellCorrectionCommand,
    ) -> ShareCellCorrectionReceipt:
        # Serialize with revoke, rotation, retries and other corrections of this link.
        record = self._share(context.session_id, lock=True)
        now = datetime.now(UTC)
        if (
            record.game_id != context.game_id
            or record.revoked_at is not None
            or record.locked_at is not None
            or record.expires_at <= now
            or record.token_expires_at is None
            or record.token_expires_at <= now
            or record.token_hash is None
            or not hmac.compare_digest(record.token_hash, hash_access_token(access_token))
        ):
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_SHARE_TOKEN_INVALID", "The share access has expired or was stopped."
            )
        model = BoardSearchShareQueryEventModel
        request_checksum = correction_fingerprint(asdict(command))
        existing = self._session.scalar(
            select(model).where(
                model.session_id == context.session_id,
                model.kind == "symbol_correction",
                model.request["operationId"].as_string() == str(command.operation_id),
            )
        )
        if existing is not None:
            if existing.request.get("requestChecksum") != request_checksum:
                raise _conflict("This operation identifier already belongs to another correction.")
            return _receipt(cast(dict[str, Any], existing.result_summary["receipt"]))

        snapshot: dict[str, Any] = {}
        if command.search_context_id is not None:
            event = self._session.scalar(
                select(model).where(
                    model.id == command.search_context_id,
                    model.session_id == context.session_id,
                    model.game_id == context.game_id,
                    model.kind == "search",
                    model.outcome_code == "ok",
                )
            )
            if event is None:
                raise _missing()
            snapshot = dict(event.request)
        if command.start_sequence_number is not None:
            game = self._session.get(GameModel, context.game_id)
            if game is None or command.start_sequence_number > game.expected_layout_count:
                raise _conflict("The starting board is outside this game's sequence.")
            distance = (
                command.sequence_number - command.start_sequence_number
            ) % game.expected_layout_count
            if distance != 0 and (command.spin_count is None or distance > command.spin_count):
                raise _conflict("This board is outside the reported range.")

        cells = self._cells(context.game_id, command.sequence_number, lock=True)
        cell = next((item for item in cells if item.cell_index == command.cell_index), None)
        if cell is None or share_cell_version(context.game_id, command.sequence_number, cell) != (
            command.expected_cell_version
        ):
            raise _conflict(
                "This cell, its owner or its pixels changed; reload before choosing again."
            )
        target_id: UUID | None = None
        if command.target_symbol_code is not None:
            target_id = self._session.scalar(
                select(SymbolModel.id).where(
                    SymbolModel.game_id == context.game_id,
                    SymbolModel.code == command.target_symbol_code,
                    SymbolModel.status == "active",
                )
            )
            if target_id is None:
                raise BoardSearchShareError(
                    "BOARD_SEARCH_SHARE_SYMBOL_INVALID", "Choose an active symbol of this game."
                )
        SqlAlchemySymbolCellReviewMutationRepository(self._session).apply_mutation(
            SymbolCellReviewMutationCommand(
                game_id=context.game_id,
                cell_review_id=cell.cell_review_id,
                action=SymbolCellReviewAction(command.action),
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                target_symbol_id=target_id,
                actor=f"board-search-share:{context.session_id}",
                # Existing cell events reserve operation_id for durable bulk operations.
                # Share idempotency belongs to the share receipt, in this same transaction.
            )
        )
        # An issue can remove the payout projection; the written cell remains
        # the source of the receipt even when no searchable document remains.
        updated = self._session.get(
            ImageSymbolReviewCellModel, cell.cell_review_id, populate_existing=True
        )
        if updated is None:
            raise _conflict("The written cell is no longer current.")
        assigned = (
            self._session.get(SymbolModel, updated.assigned_symbol_id)
            if updated.assigned_symbol_id is not None
            else None
        )
        after = replace(
            cell,
            revision=updated.revision,
            geometry_revision=updated.geometry_revision,
            crop_sample_id=updated.crop_sample_id,
            crop_checksum_sha256=updated.crop_checksum_sha256,
            review_state=updated.review_state,
            quality_issue=updated.quality_issue,
            assigned_symbol_code=assigned.code if assigned is not None else None,
        )
        changed = (cell.assigned_symbol_code, cell.quality_issue, cell.review_state) != (
            after.assigned_symbol_code,
            after.quality_issue,
            after.review_state,
        )
        receipt = ShareCellCorrectionReceipt(
            sequence_number=command.sequence_number,
            cell_index=command.cell_index,
            cell_version=share_cell_version(context.game_id, command.sequence_number, after),
            changed=changed,
        )
        previous_revision = int(
            self._session.scalar(
                select(func.max(model.request["boardRevision"].as_integer())).where(
                    model.session_id == context.session_id,
                    model.kind == "symbol_correction",
                    model.request["sequenceNumber"].as_integer() == command.sequence_number,
                    model.result_summary["changed"].as_boolean().is_(True),
                )
            )
            or 0
        )
        request: dict[str, Any] = {
            "operationId": str(command.operation_id),
            "requestChecksum": request_checksum,
            "sequenceNumber": command.sequence_number,
            "cellIndex": command.cell_index,
            "boardRevision": previous_revision + int(changed),
            "searchContextId": str(command.search_context_id)
            if command.search_context_id
            else None,
            "searchSnapshot": snapshot,
            "patternFingerprint": pattern_fingerprint(snapshot.get("cells", [])),
            "startSequenceNumber": command.start_sequence_number,
            "spinCount": command.spin_count,
            "stakeGrosze": command.stake_grosze,
            "expectedCellVersion": command.expected_cell_version,
        }
        self._session.add(
            model(
                id=uuid4(),
                session_id=context.session_id,
                game_id=context.game_id,
                occurred_at=now,
                kind="symbol_correction",
                request=request,
                result_summary={
                    "changed": changed,
                    "beforeSymbolCode": cell.assigned_symbol_code,
                    "afterSymbolCode": after.assigned_symbol_code,
                    "beforeQualityIssue": cell.quality_issue,
                    "afterQualityIssue": after.quality_issue,
                    "beforeReviewState": cell.review_state,
                    "afterReviewState": after.review_state,
                    "cellReviewId": str(cell.cell_review_id),
                    "geometryRevision": cell.geometry_revision,
                    "cellRevision": after.revision,
                    "receipt": asdict(receipt),
                },
                outcome_code="ok",
            )
        )
        self._session.flush()
        return receipt

    def _boards_statement(self, session_id: UUID, pattern: list[str] | None = None) -> Any:
        model = BoardSearchShareQueryEventModel
        sequence = model.request["sequenceNumber"].as_integer()
        filters = (
            model.session_id == session_id,
            model.kind == "symbol_correction",
            model.result_summary["changed"].as_boolean().is_(True),
        )
        ranked = (
            select(
                model.id,
                model.occurred_at,
                model.request,
                sequence.label("sequence_number"),
                func.row_number()
                .over(
                    partition_by=sequence,
                    order_by=(model.request["boardRevision"].as_integer().desc(), model.id.desc()),
                )
                .label("position"),
            )
            .where(*filters)
            .subquery()
        )
        counts = (
            select(
                sequence.label("sequence_number"),
                func.max(model.request["boardRevision"].as_integer()).label("revision"),
                func.count(distinct(model.request["cellIndex"].as_integer())).label("cell_count"),
            )
            .where(*filters)
            .group_by(sequence)
            .subquery()
        )
        reviewed = exists(
            select(model.id).where(
                model.session_id == session_id,
                model.kind == "correction_review",
                model.request["reviewedThroughId"].as_string() == sql_cast(ranked.c.id, String),
            )
        )
        statement = (
            select(
                ranked.c.id,
                ranked.c.occurred_at,
                ranked.c.request,
                ranked.c.sequence_number,
                counts.c.revision,
                counts.c.cell_count,
                (~reviewed).label("pending"),
            )
            .join(counts, counts.c.sequence_number == ranked.c.sequence_number)
            .where(ranked.c.position == 1)
        )
        if pattern is not None:
            statement = statement.where(
                ranked.c.sequence_number.in_(
                    select(sequence).where(
                        *filters,
                        model.request["patternFingerprint"].as_string()
                        == (pattern_fingerprint(pattern)),
                    )
                )
            )
        return statement

    def list_boards(
        self,
        session_id: UUID,
        *,
        status: CorrectionStatus,
        before: str | None,
        limit: int,
        pattern: list[str] | None,
    ) -> ShareCorrectionPage:
        self._share(session_id)
        _validate_limit(limit)
        statement = self._boards_statement(session_id, pattern).subquery()
        total, pending = self._session.execute(
            select(func.count(), func.count().filter(statement.c.pending.is_(True))).select_from(
                statement
            )
        ).one()
        query = select(statement)
        if status != "all":
            query = query.where(statement.c.pending.is_(status == "pending"))
        if before is not None:
            at, event_id = decode_query_log_cursor(before)
            query = query.where(
                or_(
                    statement.c.occurred_at < at,
                    and_(statement.c.occurred_at == at, statement.c.id < event_id),
                )
            )
        rows = (
            self._session.execute(
                query.order_by(statement.c.occurred_at.desc(), statement.c.id.desc()).limit(
                    limit + 1
                )
            )
            .mappings()
            .all()
        )
        entries = tuple(_board(dict(row)) for row in rows[:limit])
        last = entries[-1] if len(rows) > limit else None
        return ShareCorrectionPage(
            entries=entries,
            total_count=total,
            pending_count=pending,
            next_cursor=None
            if last is None
            else encode_query_log_cursor(last.last_changed_at, last.last_event_id),
        )

    def _board(self, session_id: UUID, sequence_number: int) -> ShareCorrectionBoard:
        statement = self._boards_statement(session_id).subquery()
        row = (
            self._session.execute(
                select(statement).where(statement.c.sequence_number == sequence_number)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise _missing()
        return _board(dict(row))

    def detail(
        self, session_id: UUID, sequence_number: int, *, before: str | None, limit: int
    ) -> ShareCorrectionDetail:
        _validate_limit(limit)
        record = self._share(session_id)
        board = self._board(session_id, sequence_number)
        cells = self._cells(record.game_id, sequence_number)
        model = BoardSearchShareQueryEventModel
        query = select(model).where(
            model.session_id == session_id,
            model.kind == "symbol_correction",
            model.request["sequenceNumber"].as_integer() == sequence_number,
            model.result_summary["changed"].as_boolean().is_(True),
        )
        if board.pending:
            acknowledged = self._session.scalar(
                select(model)
                .where(
                    model.session_id == session_id,
                    model.kind == "correction_review",
                    model.request["sequenceNumber"].as_integer() == sequence_number,
                )
                .order_by(model.request["expectedRevision"].as_integer().desc())
                .limit(1)
            )
            if acknowledged is not None:
                query = query.where(
                    model.request["boardRevision"].as_integer()
                    > int(str(acknowledged.request["expectedRevision"]))
                )
        if before is not None:
            at, event_id = decode_query_log_cursor(before)
            query = query.where(
                or_(model.occurred_at < at, and_(model.occurred_at == at, model.id < event_id))
            )
        rows = tuple(
            self._session.scalars(
                query.order_by(model.occurred_at.desc(), model.id.desc()).limit(limit + 1)
            )
        )
        changes = tuple(
            ShareCorrectionChange(
                id=row.id,
                occurred_at=row.occurred_at,
                cell_index=int(str(row.request["cellIndex"])),
                before_symbol_code=cast(str | None, row.result_summary.get("beforeSymbolCode")),
                after_symbol_code=cast(str | None, row.result_summary.get("afterSymbolCode")),
                before_quality_issue=cast(str | None, row.result_summary.get("beforeQualityIssue")),
                after_quality_issue=cast(str | None, row.result_summary.get("afterQualityIssue")),
                before_review_state=str(row.result_summary["beforeReviewState"]),
                after_review_state=str(row.result_summary["afterReviewState"]),
            )
            for row in rows[:limit]
        )
        last = changes[-1] if len(rows) > limit else None
        return ShareCorrectionDetail(
            board=board,
            board_version=share_board_version(record.game_id, sequence_number, cells),
            changes=changes,
            next_cursor=None
            if last is None
            else encode_query_log_cursor(last.occurred_at, last.id),
        )

    def review(
        self,
        session_id: UUID,
        sequence_number: int,
        *,
        expected_revision: int,
        expected_board_version: str,
    ) -> ShareCorrectionBoard:
        record = self._share(session_id, lock=True)
        cells = self._cells(record.game_id, sequence_number, lock=True)
        board = self._board(session_id, sequence_number)
        if (
            board.revision != expected_revision
            or share_board_version(record.game_id, sequence_number, cells) != expected_board_version
        ):
            raise _conflict("The board changed during review; inspect the latest changes first.")
        if board.pending:
            self._session.add(
                BoardSearchShareQueryEventModel(
                    id=uuid4(),
                    session_id=session_id,
                    game_id=record.game_id,
                    occurred_at=datetime.now(UTC),
                    kind="correction_review",
                    outcome_code="ok",
                    request={
                        "sequenceNumber": sequence_number,
                        "reviewedThroughId": str(board.last_event_id),
                        "expectedRevision": expected_revision,
                        "boardVersion": expected_board_version,
                    },
                    result_summary={},
                )
            )
            self._session.flush()
        return self._board(session_id, sequence_number)


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 50:
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_CORRECTION_LIMIT_INVALID", "Use a page size between 1 and 50."
        )


def _receipt(value: dict[str, Any]) -> ShareCellCorrectionReceipt:
    return ShareCellCorrectionReceipt(
        sequence_number=int(value["sequence_number"]),
        cell_index=int(value["cell_index"]),
        cell_version=str(value["cell_version"]),
        changed=bool(value["changed"]),
    )


def _board(row: dict[str, Any]) -> ShareCorrectionBoard:
    return ShareCorrectionBoard(
        sequence_number=int(row["sequence_number"]),
        revision=int(row["revision"]),
        changed_cell_count=int(row["cell_count"]),
        pending=bool(row["pending"]),
        last_changed_at=row["occurred_at"],
        last_event_id=row["id"],
        stake_grosze=row["request"].get("stakeGrosze"),
        start_sequence_number=row["request"].get("startSequenceNumber"),
    )
