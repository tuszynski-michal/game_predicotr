"""Closed transport commands for durable selected V3 geometry recognition."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from game_predictor_api.schemas.catalog import ApiModel


class GridReinferenceSelector(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    categories: list[Literal["grid_issue", "deferred", "unconfirmed", "all_automatic"]] = Field(
        default=["grid_issue", "deferred"], min_length=1, max_length=4
    )
    import_job_ids: list[UUID] = Field(default_factory=list, max_length=100)
    sequence_start: int | None = Field(default=None, ge=1)
    sequence_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "GridReinferenceSelector":
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Repeated target categories are not allowed.")
        if (self.sequence_start is None) != (self.sequence_end is None):
            raise ValueError("Both sequence bounds are required.")
        if (
            self.sequence_start is not None
            and self.sequence_end is not None
            and self.sequence_end < self.sequence_start
        ):
            raise ValueError("The sequence bounds are reversed.")
        return self


class GridReinferencePrepare(ApiModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    selector: GridReinferenceSelector = Field(default_factory=GridReinferenceSelector)
    model_version_id: UUID | None = None
    execution_scope: Literal["pilot", "broader"] = "pilot"


class GridReinferenceCommand(ApiModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)


class GridReinferenceFreeze(GridReinferenceCommand):
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GridReinferenceStart(GridReinferenceFreeze):
    broad_scope_confirmed: bool = False


class GridReinferencePilotAck(GridReinferenceCommand):
    pilot_operation_id: UUID
    pilot_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GridReinferenceResume(GridReinferenceCommand):
    expected_phase: Literal["prepare", "infer"]


class GridReinferenceResponse(ApiModel):
    game_id: UUID
    operation_id: UUID
    job_id: UUID
    state: Literal[
        "preparing",
        "prepared",
        "frozen",
        "queued",
        "running",
        "cancel_requested",
        "cancelled",
        "failed",
        "completed",
    ]
    phase: Literal["prepare", "infer"]
    revision: int
    manifest_sha256: str | None
    report_sha256: str | None
    source_count: int
    target_count: int
    processed_sources: int
    outcomes: dict[str, int]
    source_status_counts: dict[str, int] = Field(default_factory=dict)
    model_snapshot: dict[str, object]
    runtime_policy: str
    acceptance_policy: str
    membership_captured_at: str | None
    preparation_started_at: str
    preparation_finished_at: str | None
    receipt: dict[str, object] | None = None


class GridReinferenceTargetResponse(ApiModel):
    target_result_id: UUID
    source_image_id: UUID
    position_index: int
    ordinal: int
    snapshot: dict[str, object]
    outcome: str | None
    result: dict[str, object] | None


class GridReinferenceTargetPage(ApiModel):
    items: list[GridReinferenceTargetResponse]
    next_cursor: str | None
