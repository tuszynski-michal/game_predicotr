"""Typed symbol decisions, separate from geometry and training eligibility."""

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .contracts import Contract, Point, Topology

Sha = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DictionaryEntry(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_text(self) -> "DictionaryEntry":
        if any(v != v.strip() for v in (self.code, self.display_name)):
            raise ValueError("DICTIONARY_WHITESPACE")
        if self.code.lower() in {"unknown", "unreadable", "grid_issue"}:
            raise ValueError("DICTIONARY_RESERVED_CLASS")
        return self


class CropBinding(Contract):
    snapshot_manifest_id: Sha
    catalog_digest: Sha
    game_id: str
    source_id: str
    source_sha256: Sha
    board_index: int = Field(ge=0, le=100)
    geometry_revision: int = Field(ge=1)
    geometry_digest: Sha
    topology: Topology
    cell_index: int = Field(ge=0, le=14)
    quad: list[Point] = Field(min_length=4, max_length=4)
    renderer_version: Literal["lab-symbol-crop-rgb96-v1"]
    render_spec: dict[str, str]
    render_spec_digest: Sha
    width: Literal[96] = 96
    height: Literal[96] = 96
    pixel_sha256: Sha
    byte_sha256: Sha
    crop_id: Sha


class SymbolMutation(Contract):
    request_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)
    actor: Literal["operator"] = "operator"


class DictionaryDraft(SymbolMutation):
    op: Literal["dictionary_draft"]
    game_id: str
    base_version: int | None = Field(default=None, ge=1)
    entries: list[DictionaryEntry] = Field(max_length=256)


class DictionaryApprove(SymbolMutation):
    op: Literal["dictionary_approve"]
    game_id: str
    version: int = Field(ge=1)
    digest: Sha


class LabelDecide(SymbolMutation):
    op: Literal["label_decide"]
    binding: CropBinding
    dictionary_version: int = Field(ge=1)
    dictionary_digest: Sha
    action: Literal["approve", "unknown", "unreadable", "grid_issue"]
    symbol_id: str | None = None

    @model_validator(mode="after")
    def valid_class(self) -> "LabelDecide":
        if (self.action == "approve") != (self.symbol_id is not None):
            raise ValueError("SYMBOL_ACTION_CLASS_INVALID")
        return self


class LabelWithdraw(SymbolMutation):
    op: Literal["label_withdraw"]
    decision_id: Sha


SymbolRequest = Annotated[
    DictionaryDraft | DictionaryApprove | LabelDecide | LabelWithdraw,
    Field(discriminator="op"),
]


class LabCropRequest(Contract):
    kind: Literal["lab_cell"]
    source_id: str
    board_index: int = Field(ge=0, le=100)
    cell_index: int = Field(ge=0, le=14)
    expected_geometry_revision: int = Field(ge=1)


class DbCropRequest(Contract):
    kind: Literal["db_approved"]
    sample_id: Sha


CropRequest = Annotated[LabCropRequest | DbCropRequest, Field(discriminator="kind")]


class LabelValidity(Contract):
    label_valid: bool = False
    reasons: list[str] = Field(default_factory=list)
    training_blockers: list[str] = Field(default_factory=lambda: ["SYMBOL_SPLIT_NOT_FROZEN"])
    trainable: Literal[False] = False


class SymbolResult(LabelValidity):
    revision: int
    request_id: str
    result_id: str
    replayed: bool = False


class SymbolRow(LabelValidity):
    sample_id: str
    origin: Literal["lab_human_approved", "db_approved"]
    game_id: str
    source_id: str
    board_id: str
    cell_index: int
    symbol_id: str | None = None
    action: str
    metadata: dict[str, Any]


class SymbolPage(Contract):
    items: list[SymbolRow]
    total: int
    revision: int
    read_token: str
    availability: str


class DictionaryView(Contract):
    origin: Literal["lab", "db_snapshot"] = "lab"
    game_id: str
    version: int | None = None
    digest: str
    status: Literal["draft", "approved", "snapshot"]
    approved_at: str | None = None
    active: bool = False
    entries: list[DictionaryEntry] | None = None


class DictionaryPage(Contract):
    items: list[DictionaryView]
    total: int
    revision: int
    read_token: str


class LabCropPreview(Contract):
    kind: Literal["lab_cell"] = "lab_cell"
    binding: CropBinding
    png_base64: str


class DbCropPreview(Contract):
    kind: Literal["db_approved"] = "db_approved"
    origin: Literal["db_approved"] = "db_approved"
    read_only: Literal[True] = True
    sample_id: str
    provenance: dict[str, Any]
    byte_sha256: str
    media_type: str
    crop_bytes_base64: str
    dictionary: DictionaryView
