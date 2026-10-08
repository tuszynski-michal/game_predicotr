"""Atomic slot, receipt and retained journal operations under live ancestry locks."""

from collections.abc import Callable
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.board_search_share_queries import (
    decode_query_log_cursor,
    encode_query_log_cursor,
)
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import ManagementCommand, ManagementError
from game_predictor_api.domain.management_stakes import MANAGEMENT_STAKES
from game_predictor_api.schemas.board_search_approximate_win import ApproximateWinResponse
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCellCorrectionResponse,
    BoardSearchSharePublicBoardDetailResponse,
)
from game_predictor_api.schemas.management_stakes import (
    ManagementClearCommand,
    ManagementCorrectionCommand,
    ManagementJournalEntry,
    ManagementJournalResponse,
    ManagementRefreshCommand,
    ManagementRefreshResponse,
    ManagementResultResponse,
    ManagementSaveCommand,
    ManagementSearchCommand,
    ManagementSearchResponse,
    ManagementStakeListResponse,
    ManagementStakeResponse,
)
from game_predictor_api.storage.management_game_adapter import SqlAlchemyManagementGameAdapter
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementOperationModel,
    ManagementPointModel,
    now,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_result_snapshots import expand_result, pin_values
from game_predictor_api.storage.management_stake_models import (
    ManagementResultVersionModel,
    ManagementSearchContextModel,
    ManagementStakeSlotModel,
)
from game_predictor_api.storage.models import GameModel


class SqlAlchemyManagementStakeRepository:
    def __init__(
        self,
        session: Session,
        *,
        adapter: SqlAlchemyManagementGameAdapter | None = None,
        revalidate: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.metadata = SqlAlchemyManagementRepository(session)
        self.adapter = adapter or SqlAlchemyManagementGameAdapter(session)
        self.revalidate = revalidate or (lambda: None)

    def before_commit(self) -> None:
        """T5 supplies a locked panel-session guard; called immediately before commit."""
        self.session.flush()
        self.revalidate()

    def _target(
        self, machine_id: UUID, game_id: UUID, *, live: bool = True
    ) -> tuple[ManagementPointModel, ManagementMachineModel]:
        self.revalidate()
        point, machine = self.metadata.lock_machine(machine_id)
        assignment = self.session.get(ManagementAssignmentModel, (machine_id, game_id))
        if assignment is None:
            raise ManagementError(
                "MANAGEMENT_ASSIGNMENT_NOT_FOUND", "The game is not assigned to this machine.", 404
            )
        if live:
            self.metadata.require_available(point, machine)
            game = self.session.scalar(
                select(GameModel)
                .where(GameModel.id == game_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            if not assignment.attached or game is None or game.status != GameStatus.ACTIVE:
                raise ManagementError(
                    "MANAGEMENT_GAME_NOT_AVAILABLE",
                    "The assigned game must be active and attached.",
                )
        return point, machine

    def _begin(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementCommand,
        actor: str,
        action: str,
        suffix: str = "",
    ) -> tuple[str, dict[str, object] | None]:
        self.revalidate()
        if stake not in MANAGEMENT_STAKES:
            raise ManagementError(
                "MANAGEMENT_STAKE_INVALID", "Choose one of the six supported stakes.", 422
            )
        checksum, receipt = self.metadata.begin_operation(
            command, actor, action, f"{machine_id}/{game_id}/{stake}{suffix}"
        )
        return checksum, receipt

    def _finish(
        self,
        command: ManagementCommand,
        actor: str,
        checksum: str,
        action: str,
        point_id: UUID,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        response: BaseModel,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        journal: bool = True,
        before_result: UUID | None = None,
        after_result: UUID | None = None,
    ) -> None:
        self.session.add(
            ManagementOperationModel(
                operation_id=command.operation_id,
                actor=actor,
                request_checksum=checksum,
                response=response.model_dump(mode="json", by_alias=True),
                action=action,
                point_id=point_id,
                machine_id=machine_id,
                game_id=game_id,
            )
        )
        self.session.flush()
        if journal:
            self.session.add(
                ManagementJournalModel(
                    operation_id=command.operation_id,
                    actor=actor,
                    action=action,
                    point_id=point_id,
                    machine_id=machine_id,
                    game_id=game_id,
                    stake_grosze=stake,
                    before_result_id=before_result,
                    after_result_id=after_result,
                    before=before,
                    after=after,
                )
            )
        self.session.flush()
        self.revalidate()

    def _slot(self, machine_id: UUID, game_id: UUID, stake: int) -> ManagementStakeSlotModel | None:
        return self.session.get(
            ManagementStakeSlotModel, (machine_id, game_id, stake), populate_existing=True
        )

    def _response(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        slot: ManagementStakeSlotModel | None = None,
    ) -> ManagementStakeResponse:
        if slot is None:
            slot = self._slot(machine_id, game_id, stake)
        values: dict[str, Any] = {
            "machine_id": machine_id,
            "game_id": game_id,
            "stake_grosze": stake,
            "revision": slot.revision if slot else 0,
            "empty": slot is None or slot.result_version_id is None,
        }
        if slot is None:
            return ManagementStakeResponse(**values)
        values.update(
            {
                key: getattr(slot, key)
                for key in (
                    "search_context_id",
                    "start_sequence_number",
                    "spin_count",
                    "pinned_spin_positions",
                    "result_version_id",
                    "saved_at",
                    "updated_at",
                    "stale_error_code",
                    "pinned_points",
                )
            }
        )
        if slot.result_version_id:
            # Only compact metadata is selected. Full numeric rows load on demand.
            summary: dict[str, Any] | None = self.session.scalar(
                select(ManagementResultVersionModel.summary).where(
                    ManagementResultVersionModel.id == slot.result_version_id
                )
            )
            if summary is None:
                raise RuntimeError("Saved management result is missing.")
            values.update(
                summary=summary["summary"],
                start_symbol_codes=summary["startSymbolCodes"],
                chart_points=summary["chartPoints"],
                spin_cost=summary["spinCost"],
                unavailable_pin_positions=[
                    pin for pin in slot.pinned_spin_positions if pin > summary["evaluatedSpinCount"]
                ],
            )
            if any(
                point.get("available")
                and (
                    point.get("requiredStakeCredits") is None
                    or point.get("machineCashCredits") is None
                )
                for point in slot.pinned_points
            ):
                # At most six pins per slot and six slots per list. No GET writes
                # and no current rules: only the already frozen result payload.
                payload = self.session.scalar(
                    select(ManagementResultVersionModel.payload).where(
                        ManagementResultVersionModel.id == slot.result_version_id
                    )
                )
                if payload is None:
                    raise RuntimeError("Saved management result is missing.")
                values["pinned_points"] = pin_values(payload, list(slot.pinned_spin_positions))
            context = self.session.get(ManagementSearchContextModel, slot.search_context_id)
            values["query"] = context.query if context else None
        return ManagementStakeResponse(**values)

    def list_slots(self, machine_id: UUID, game_id: UUID) -> ManagementStakeListResponse:
        self._target(machine_id, game_id, live=False)
        return ManagementStakeListResponse(
            slots=tuple(self._response(machine_id, game_id, stake) for stake in MANAGEMENT_STAKES)
        )

    def slot(self, machine_id: UUID, game_id: UUID, stake: int) -> ManagementStakeResponse:
        self._target(machine_id, game_id, live=False)
        return self._response(machine_id, game_id, stake)

    def search(
        self, machine_id: UUID, game_id: UUID, command: ManagementSearchCommand, actor: str
    ) -> ManagementSearchResponse:
        stake = command.stake_grosze
        checksum, receipt = self._begin(machine_id, game_id, stake, command, actor, "search")
        if receipt is not None:
            return ManagementSearchResponse.model_validate(receipt)
        point, _machine = self._target(machine_id, game_id)
        result = self.adapter.search(game_id, command)
        response = ManagementSearchResponse(search_context_id=command.operation_id, search=result)
        query = command.model_dump(
            mode="json", by_alias=True, exclude={"operation_id", "expected_revision"}
        )
        self._finish(
            command,
            actor,
            checksum,
            "search",
            point.id,
            machine_id,
            game_id,
            stake,
            response,
            {},
            {
                "query": query,
                "searchContextId": str(command.operation_id),
                "resultCount": len(result.results),
                "sequenceNumbers": [row.sequence_number for row in result.results],
            },
        )
        self.session.add(
            ManagementSearchContextModel(
                id=command.operation_id,
                machine_id=machine_id,
                game_id=game_id,
                stake_grosze=stake,
                actor=actor,
                query=query,
                sequence_numbers=[row.sequence_number for row in result.results],
            )
        )
        self.session.flush()
        return response

    def _context(
        self,
        context_id: UUID,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        actor: str,
        allow_saved: bool = False,
    ) -> ManagementSearchContextModel:
        context = self.session.get(ManagementSearchContextModel, context_id)
        saved = self._slot(machine_id, game_id, stake) if allow_saved else None
        restored = saved is not None and saved.search_context_id == context_id
        if (
            context is None
            or (
                context.machine_id,
                context.game_id,
                context.stake_grosze,
            )
            != (machine_id, game_id, stake)
            or (context.actor != actor and not restored)
        ):
            raise ManagementError(
                "MANAGEMENT_SEARCH_CONTEXT_INVALID", "Use this slot's own validated search context."
            )
        return context

    def _version(self, game_id: UUID, start: int, count: int) -> ManagementResultVersionModel:
        digest, payload, summary = self.adapter.snapshot(game_id, start, count)
        # Dedup across machines without races; fixed ordering follows target locks.
        if self.session.get_bind().dialect.name == "postgresql":
            key = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        version = self.session.scalar(
            select(ManagementResultVersionModel).where(
                ManagementResultVersionModel.game_id == game_id,
                ManagementResultVersionModel.content_sha256 == digest,
            )
        )
        if version is None:
            version = ManagementResultVersionModel(
                game_id=game_id, content_sha256=digest, payload=payload, summary=summary
            )
            self.session.add(version)
            self.session.flush()
        return version

    def save(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementSaveCommand,
        actor: str,
    ) -> ManagementStakeResponse:
        checksum, receipt = self._begin(machine_id, game_id, stake, command, actor, "stake.save")
        if receipt is not None:
            return ManagementStakeResponse.model_validate(receipt)
        point, _machine = self._target(machine_id, game_id)
        slot = self._slot(machine_id, game_id, stake)
        self.metadata.require_revision(slot.revision if slot else 0, command.expected_revision)
        context = self._context(
            command.search_context_id,
            machine_id,
            game_id,
            stake,
            actor,
            allow_saved=bool(slot and slot.start_sequence_number == command.start_sequence_number),
        )
        if command.start_sequence_number not in context.sequence_numbers:
            raise ManagementError(
                "MANAGEMENT_START_NOT_SEARCHED", "Choose a board returned by this search."
            )
        before = self._response(machine_id, game_id, stake).model_dump(mode="json", by_alias=True)
        before_result = slot.result_version_id if slot else None
        version = self._version(game_id, command.start_sequence_number, command.spin_count)
        if any(
            pin > cast(int, version.summary["evaluatedSpinCount"])
            for pin in command.pinned_spin_positions
        ):
            raise ManagementError(
                "MANAGEMENT_PIN_UNAVAILABLE", "A pin is outside the evaluated range."
            )
        if slot is None:
            slot = ManagementStakeSlotModel(
                machine_id=machine_id, game_id=game_id, stake_grosze=stake, revision=1
            )
            self.session.add(slot)
        else:
            slot.revision += 1
        slot.search_context_id = context.id
        slot.start_sequence_number, slot.spin_count = (
            command.start_sequence_number,
            command.spin_count,
        )
        slot.pinned_spin_positions = list(command.pinned_spin_positions)
        slot.pinned_points = pin_values(version.payload, slot.pinned_spin_positions)
        slot.result_version_id, slot.stale_error_code = version.id, None
        slot.saved_at = slot.updated_at = now()
        self.session.flush()
        response = self._response(machine_id, game_id, stake, slot)
        self._finish(
            command,
            actor,
            checksum,
            "stake.replace" if before_result else "stake.save",
            point.id,
            machine_id,
            game_id,
            stake,
            response,
            before,
            response.model_dump(mode="json", by_alias=True),
            before_result=before_result,
            after_result=version.id,
        )
        return response

    def clear(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementClearCommand,
        actor: str,
    ) -> ManagementStakeResponse:
        checksum, receipt = self._begin(machine_id, game_id, stake, command, actor, "stake.clear")
        if receipt is not None:
            return ManagementStakeResponse.model_validate(receipt)
        point, _machine = self._target(machine_id, game_id)
        slot = self._slot(machine_id, game_id, stake)
        self.metadata.require_revision(slot.revision if slot else 0, command.expected_revision)
        before = self._response(machine_id, game_id, stake).model_dump(mode="json", by_alias=True)
        before_result = slot.result_version_id if slot else None
        if slot is None:
            slot = ManagementStakeSlotModel(
                machine_id=machine_id, game_id=game_id, stake_grosze=stake, revision=1
            )
            self.session.add(slot)
        else:
            slot.revision += 1
        slot.search_context_id = slot.start_sequence_number = slot.spin_count = (
            slot.result_version_id
        ) = None
        slot.pinned_spin_positions = []
        slot.pinned_points = []
        slot.saved_at = slot.stale_error_code = None
        slot.updated_at = now()
        self.session.flush()
        response = self._response(machine_id, game_id, stake, slot)
        self._finish(
            command,
            actor,
            checksum,
            "stake.clear",
            point.id,
            machine_id,
            game_id,
            stake,
            response,
            before,
            response.model_dump(mode="json", by_alias=True),
            before_result=before_result,
        )
        return response

    def refresh(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementRefreshCommand,
        actor: str,
    ) -> ManagementRefreshResponse:
        checksum, receipt = self._begin(machine_id, game_id, stake, command, actor, "stake.refresh")
        if receipt is not None:
            return ManagementRefreshResponse.model_validate(receipt)
        point, _machine = self._target(machine_id, game_id)
        slot = self._slot(machine_id, game_id, stake)
        self.metadata.require_revision(slot.revision if slot else 0, command.expected_revision)
        before = self._response(machine_id, game_id, stake).model_dump(mode="json", by_alias=True)
        old = slot.result_version_id if slot else None
        changed, error = False, None
        status: Literal["current", "stale", "empty"] = "empty"
        if slot and old:
            assert slot.start_sequence_number is not None and slot.spin_count is not None
            try:
                version = self._version(game_id, slot.start_sequence_number, slot.spin_count)
            except (BoardSearchError, ManagementError) as failure:
                # Known unavailable data is stale; infrastructure/programming errors propagate.
                error = failure.code
                slot.stale_error_code, status = error, "stale"
            else:
                changed = version.id != old
                if changed:
                    slot.result_version_id = version.id
                    slot.revision += 1
                    slot.pinned_points = pin_values(version.payload, slot.pinned_spin_positions)
                slot.stale_error_code, status = None, "current"
            slot.updated_at = now()
            self.session.flush()
        response = ManagementRefreshResponse(
            slot=self._response(machine_id, game_id, stake, slot),
            changed=changed,
            status=status,
            error_code=error,
        )
        self._finish(
            command,
            actor,
            checksum,
            "stake.recalculate",
            point.id,
            machine_id,
            game_id,
            stake,
            response,
            before,
            response.slot.model_dump(mode="json", by_alias=True),
            journal=changed,
            before_result=old,
            after_result=response.slot.result_version_id,
        )
        return response

    def result(self, machine_id: UUID, game_id: UUID, version_id: UUID) -> ManagementResultResponse:
        self._target(machine_id, game_id, live=False)
        owned = self.session.scalar(
            select(ManagementJournalModel.id)
            .where(
                ManagementJournalModel.machine_id == machine_id,
                ManagementJournalModel.game_id == game_id,
                or_(
                    ManagementJournalModel.before_result_id == version_id,
                    ManagementJournalModel.after_result_id == version_id,
                ),
            )
            .limit(1)
        )
        version = self.session.get(ManagementResultVersionModel, version_id) if owned else None
        if version is None or version.game_id != game_id:
            raise ManagementError(
                "MANAGEMENT_RESULT_NOT_FOUND",
                "This saved result does not belong to this machine/game.",
                404,
            )
        return ManagementResultResponse.model_validate(
            dict(
                id=version.id,
                content_sha256=version.content_sha256,
                created_at=version.created_at,
                calculation=expand_result(version.payload),
                start_symbol_codes=version.payload["startSymbolCodes"],
                rules_snapshot=version.payload["rulesSnapshot"],
            )
        )

    def journal(
        self,
        machine_id: UUID,
        *,
        game_id: UUID | None = None,
        stake: int | None = None,
        before: str | None = None,
        limit: int = 20,
    ) -> ManagementJournalResponse:
        self.revalidate()
        point, _machine = self.metadata.lock_machine(machine_id)
        model = ManagementJournalModel
        statement = select(model).where(
            model.point_id == point.id,
            or_(model.machine_id == machine_id, model.machine_id.is_(None)),
        )
        if game_id is not None:
            statement = statement.where(or_(model.game_id == game_id, model.game_id.is_(None)))
        if stake is not None:
            statement = statement.where(
                or_(model.stake_grosze == stake, model.stake_grosze.is_(None))
            )
        if before:
            timestamp, event_id = decode_query_log_cursor(before)
            statement = statement.where(
                or_(
                    model.created_at < timestamp,
                    and_(model.created_at == timestamp, model.id < event_id),
                )
            )
        rows = self.session.scalars(
            statement.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
        ).all()
        entries = tuple(
            ManagementJournalEntry.model_validate(
                {key: getattr(row, key) for key in ManagementJournalEntry.model_fields}
            )
            for row in rows[:limit]
        )
        cursor = (
            encode_query_log_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
            if len(rows) > limit
            else None
        )
        return ManagementJournalResponse(entries=entries, next_cursor=cursor)

    def detail(
        self, machine_id: UUID, game_id: UUID, sequence: int
    ) -> BoardSearchSharePublicBoardDetailResponse:
        self._target(machine_id, game_id)
        return self.adapter.detail(game_id, sequence)

    def preview(
        self, machine_id: UUID, game_id: UUID, start: int, count: int
    ) -> ApproximateWinResponse:
        self._target(machine_id, game_id)
        _digest, payload, _summary = self.adapter.snapshot(game_id, start, count)
        return expand_result(payload)

    def correct(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        sequence: int,
        cell_index: int,
        command: ManagementCorrectionCommand,
        actor: str,
    ) -> BoardSearchShareCellCorrectionResponse:
        checksum, receipt = self._begin(
            machine_id,
            game_id,
            stake,
            command,
            actor,
            "symbol.correct",
            f"/{sequence}/{cell_index}",
        )
        if receipt is not None:
            from game_predictor_api.schemas.board_search_shares import (
                BoardSearchShareCellCorrectionResponse,
            )

            return BoardSearchShareCellCorrectionResponse.model_validate(receipt)
        point, _machine = self._target(machine_id, game_id)
        if command.search_context_id:
            self._context(
                command.search_context_id, machine_id, game_id, stake, actor, allow_saved=True
            )
        response, before, after = self.adapter.correct(
            game_id, sequence, cell_index, command, actor
        )
        meta = {
            "sequenceNumber": sequence,
            "cellIndex": cell_index,
            "searchContextId": str(command.search_context_id)
            if command.search_context_id
            else None,
            "startSequenceNumber": command.start_sequence_number,
            "spinCount": command.spin_count,
        }
        self._finish(
            command,
            actor,
            checksum,
            "symbol.correct",
            point.id,
            machine_id,
            game_id,
            stake,
            response,
            {**meta, **before},
            {**meta, **after, "cellVersion": response.cell_version},
            journal=response.changed,
        )
        return response
