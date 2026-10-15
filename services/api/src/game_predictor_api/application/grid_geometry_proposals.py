"""Durable human commands for pinned model geometry candidates."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProposalCommandOutcome:
    """A committed command receipt, separate from today's applicability."""

    status: int
    receipt: dict[str, Any]
    current: dict[str, Any] | None


class GridGeometryProposalRepository(Protocol):
    def list_proposals(
        self, game_id: UUID, import_job_id: UUID, review_item_id: UUID
    ) -> dict[str, Any]: ...

    def get_proposal(
        self, game_id: UUID, import_job_id: UUID, review_item_id: UUID, proposal_id: UUID
    ) -> dict[str, Any]: ...

    def command(
        self,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        proposal_id: UUID | None,
        kind: str,
        payload: dict[str, Any],
        actor: str,
    ) -> ProposalCommandOutcome: ...


class GridGeometryProposalService:
    def __init__(self, repository: GridGeometryProposalRepository) -> None:
        self.repository = repository

    def command(
        self,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        proposal_id: UUID | None,
        kind: str,
        payload: dict[str, Any],
        actor: str,
    ) -> ProposalCommandOutcome:
        return self.repository.command(
            game_id, import_job_id, review_item_id, proposal_id, kind, payload, actor
        )
