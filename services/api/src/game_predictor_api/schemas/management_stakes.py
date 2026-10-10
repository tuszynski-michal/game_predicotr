"""Backend-owned saved-selection, immutable-result and journal contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.management import ManagementValue
from game_predictor_api.domain.management_stakes import (
    ManagementClearCommand as ManagementClearCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementCorrectionCommand as ManagementCorrectionCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementQueryCell as ManagementQueryCell,
)
from game_predictor_api.domain.management_stakes import (
    ManagementRefreshCommand as ManagementRefreshCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementSaveCommand as ManagementSaveCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementSearchCommand as ManagementSearchCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementStake as ManagementStake,
)
from game_predictor_api.schemas.board_search import BoardSearchResponse
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinResponse,
    ApproximateWinSummaryResponse,
)


class ManagementSearchResponse(ManagementValue):
    search_context_id: UUID
    search: BoardSearchResponse


class ManagementChartPoint(ManagementValue):
    spin_number: int
    balance_credits: int


class ManagementPinnedPoint(ManagementChartPoint):
    available: bool
    required_stake_credits: int | None = None
    machine_cash_credits: int | None = None


class ManagementStakeResponse(ManagementValue):
    machine_id: UUID
    game_id: UUID
    stake_grosze: ManagementStake
    revision: int
    empty: bool
    search_context_id: UUID | None = None
    query: dict[str, object] | None = None
    start_sequence_number: int | None = None
    spin_count: int | None = None
    pinned_spin_positions: tuple[int, ...] = ()
    unavailable_pin_positions: tuple[int, ...] = ()
    result_version_id: UUID | None = None
    start_symbol_codes: tuple[str | None, ...] | None = None
    summary: ApproximateWinSummaryResponse | None = None
    chart_points: tuple[ManagementChartPoint, ...] = Field(default=(), max_length=256)
    pinned_points: tuple[ManagementPinnedPoint, ...] = Field(default=(), max_length=6)
    spin_cost: int | None = None
    saved_at: datetime | None = None
    updated_at: datetime | None = None
    stale_error_code: str | None = None


class ManagementStakeListResponse(ManagementValue):
    slots: tuple[ManagementStakeResponse, ...] = Field(min_length=6, max_length=6)


class ManagementResultResponse(ManagementValue):
    id: UUID
    content_sha256: str
    created_at: datetime
    calculation: ApproximateWinResponse
    start_symbol_codes: tuple[str | None, ...]
    rules_snapshot: dict[str, object]


class ManagementRefreshResponse(ManagementValue):
    slot: ManagementStakeResponse
    changed: bool
    status: Literal["current", "stale", "empty"]
    error_code: str | None = None


class ManagementJournalEntry(ManagementValue):
    id: UUID
    actor: str
    action: str
    point_id: UUID
    machine_id: UUID | None
    game_id: UUID | None
    stake_grosze: int | None
    before_result_id: UUID | None
    after_result_id: UUID | None
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime


class ManagementJournalResponse(ManagementValue):
    entries: tuple[ManagementJournalEntry, ...]
    next_cursor: str | None
