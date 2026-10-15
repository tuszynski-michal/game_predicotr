"""Closed recording commands; clients cannot submit identity attestations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecordingSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source_ids: list[UUID] | None = Field(
        default=None, alias="sourceIds", min_length=1, max_length=200
    )
    import_job_id: UUID | None = Field(default=None, alias="importJobId")

    @model_validator(mode="after")
    def one_selector(self) -> "RecordingSelection":
        if (self.source_ids is None) == (self.import_job_id is None):
            raise ValueError("Choose exact sources or one import, not both.")
        if self.source_ids and len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Source IDs must be unique.")
        return self


class SourceRecordingCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    kind: Literal[
        "prepare", "attach", "complete", "declare", "assign_role", "retract", "alias", "freeze"
    ]
    idempotency_key: UUID = Field(alias="idempotencyKey")
    group_id: UUID | None = Field(default=None, alias="groupId")
    expected_revision: int = Field(default=0, alias="expectedRevision", ge=0)
    family_id: UUID | None = Field(default=None, alias="familyId")
    role: Literal["TRAIN", "VALIDATION", "REGRESSION"] | None = None
    independence_confirmed: bool | None = Field(default=None, alias="independenceConfirmed")
    manifest_id: UUID | None = Field(default=None, alias="manifestId")
    page_index: int | None = Field(default=None, alias="pageIndex", ge=0)
    other_group_id: UUID | None = Field(default=None, alias="otherGroupId")
    base_version_id: UUID | None = Field(default=None, alias="baseVersionId")
    selection: RecordingSelection | None = None

    @model_validator(mode="after")
    def fields_for_kind(self) -> "SourceRecordingCommandRequest":
        if self.kind == "prepare":
            if self.selection is None or self.group_id is not None or self.expected_revision != 0:
                raise ValueError("Preparation requires a selection and revision0.")
        elif self.group_id is None:
            raise ValueError("A recording group is required.")
        if self.kind == "attach" and (self.manifest_id is None or self.page_index is None):
            raise ValueError("Attachment requires a frozen manifest page.")
        if self.kind in {"assign_role", "freeze"} and self.family_id is None:
            raise ValueError("A model family is required.")
        if self.kind == "assign_role" and self.role is None:
            raise ValueError("A role is required.")
        if self.kind == "freeze" and self.base_version_id is None:
            raise ValueError("An exact base version is required.")
        if self.kind == "declare" and self.independence_confirmed is not True:
            raise ValueError("Confirm the recording declaration and partition independence.")
        if self.kind == "alias" and self.other_group_id is None:
            raise ValueError("An authorized second group is required.")
        allowed = {
            "prepare": {"selection"},
            "attach": {"manifest_id", "page_index"},
            "complete": set(),
            "declare": {"independence_confirmed"},
            "assign_role": {"family_id", "role"},
            "retract": set(),
            "alias": {"other_group_id"},
            "freeze": {"family_id", "base_version_id"},
        }[self.kind]
        optional = {
            "selection",
            "manifest_id",
            "page_index",
            "independence_confirmed",
            "family_id",
            "role",
            "other_group_id",
            "base_version_id",
        }
        if any(getattr(self, field) is not None for field in optional - allowed):
            raise ValueError("Fields are not valid for this command kind.")
        return self


class SourceRecordingGroupResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: UUID
    revision: int
    membership_complete: bool = Field(alias="membershipComplete")
    expected_sources: int = Field(alias="expectedSources")
    registered_sources: int = Field(alias="registeredSources")
    manifest_id: UUID = Field(alias="manifestId")
    manifest_sha256: str = Field(alias="manifestSha256")
    page_count: int = Field(alias="pageCount")
    next_page_index: int | None = Field(default=None, alias="nextPageIndex")
    registered_pages: int = Field(default=0, alias="registeredPages")
    created_at: str = Field(default="", alias="createdAt")
    import_job_id: UUID | None = Field(default=None, alias="importJobId")
    declared: bool
    independent: bool
    role: Literal["TRAIN", "VALIDATION", "REGRESSION"] | None
    qualification: Literal["unresolved", "blocked", "eligible"]
    reason_codes: list[str] = Field(alias="reasonCodes")
    resolution_id: UUID | None = Field(default=None, alias="resolutionId")


class SourceRecordingGroupListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    items: list[SourceRecordingGroupResponse]
    next_cursor: UUID | None = Field(default=None, alias="nextCursor")


class SourceRecordingCommandResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    command_kind: str = Field(alias="commandKind")
    idempotency_key: UUID = Field(alias="idempotencyKey")
    group: SourceRecordingGroupResponse
    status_code: int = Field(alias="statusCode")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    resolution_id: UUID | None = Field(default=None, alias="resolutionId")
