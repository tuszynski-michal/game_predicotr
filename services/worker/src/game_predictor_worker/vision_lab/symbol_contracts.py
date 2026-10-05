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


class BatchLabelDecide(SymbolMutation):
    op: Literal["batch_label_decide"]
    reference_id: Sha
    case_id: Sha
    action: Literal["approve", "unreadable", "grid_issue"]
    symbol_id: str | None = None

    @model_validator(mode="after")
    def valid_class(self) -> "BatchLabelDecide":
        if (self.action == "approve") != (self.symbol_id is not None):
            raise ValueError("SYMBOL_ACTION_CLASS_INVALID")
        return self


class LabelWithdraw(SymbolMutation):
    op: Literal["label_withdraw"]
    decision_id: Sha


class BoardCellDecision(Contract):
    binding: CropBinding
    action: Literal["approve", "unknown", "unreadable", "grid_issue"]
    symbol_id: str | None = None

    @model_validator(mode="after")
    def valid_class(self) -> "BoardCellDecision":
        if (self.action == "approve") != (self.symbol_id is not None):
            raise ValueError("SYMBOL_ACTION_CLASS_INVALID")
        return self


class LabelBoardDecide(SymbolMutation):
    op: Literal["label_board_decide"]
    dictionary_version: int = Field(ge=1)
    dictionary_digest: Sha
    cells: list[BoardCellDecision] = Field(min_length=9, max_length=15)

    @model_validator(mode="after")
    def complete_board(self) -> "LabelBoardDecide":
        first = self.cells[0].binding
        count = first.topology.columns * first.topology.rows
        if [c.binding.cell_index for c in self.cells] != list(range(count)):
            raise ValueError("SYMBOL_BOARD_CELLS_INVALID")
        fields = (
            "source_id",
            "game_id",
            "board_index",
            "topology",
            "geometry_revision",
            "geometry_digest",
        )
        if any(
            any(getattr(c.binding, key) != getattr(first, key) for key in fields)
            for c in self.cells
        ):
            raise ValueError("SYMBOL_BOARD_BINDING_MIXED")
        return self


class LabelCellsDecide(SymbolMutation):
    op: Literal["label_cells_decide"]
    dictionary_version: int = Field(ge=1)
    dictionary_digest: Sha
    symbol_id: str
    bindings: list[CropBinding] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def distinct_cells(self) -> "LabelCellsDecide":
        first = self.bindings[0]
        keys = [(b.source_id, b.board_index, b.cell_index) for b in self.bindings]
        if any(b.game_id != first.game_id for b in self.bindings) or keys != sorted(set(keys)):
            raise ValueError("SYMBOL_QUEUE_BINDINGS_INVALID")
        return self


SymbolRequest = Annotated[
    DictionaryDraft
    | DictionaryApprove
    | LabelDecide
    | LabelWithdraw
    | LabelBoardDecide
    | LabelCellsDecide
    | BatchLabelDecide,
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


class LabBoardRequest(Contract):
    kind: Literal["lab_board"]
    source_id: str
    board_index: int = Field(ge=0, le=100)
    expected_geometry_revision: int = Field(ge=1)


class LabQueueRequest(Contract):
    kind: Literal["lab_queue"]
    game_id: str
    view: Literal["pending", "assigned"] = "pending"
    symbol_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=2000)
    read_token: str | None = None


class BatchQueueRequest(Contract):
    kind: Literal["batch_queue"]


CropRequest = Annotated[
    LabCropRequest | DbCropRequest | LabBoardRequest | LabQueueRequest | BatchQueueRequest,
    Field(discriminator="kind"),
]


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
    decision_ids: list[Sha] = Field(default_factory=list)


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


class BoardCellPreview(Contract):
    binding: CropBinding
    png_base64: str
    current: SymbolRow | None = None


class LabBoardPreview(Contract):
    kind: Literal["lab_board"] = "lab_board"
    revision: int
    dictionary: DictionaryView | None = None
    topology: Topology
    board_png_base64: str
    width: int = Field(ge=1, le=960)
    height: int = Field(ge=1, le=960)
    nodes: list[Point]
    cells: list[BoardCellPreview] = Field(min_length=9, max_length=15)


class LabQueueItem(Contract):
    binding: CropBinding
    png_base64: str
    status: Literal["unassigned", "requires_review", "assigned"]
    reason: str | None = None


class LabQueuePreview(Contract):
    kind: Literal["lab_queue"] = "lab_queue"
    items: list[LabQueueItem]
    total: int
    revision: int
    read_token: str


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


class BatchCasePreview(Contract):
    case_id: Sha
    filename: str
    board: int = Field(ge=1, le=9)
    field: int = Field(ge=1, le=15)
    category: str
    png_base64: str
    pixel_sha256: Sha
    photo_url: str
    action: Literal["approve", "unreadable", "grid_issue"] | None = None
    symbol_id: str | None = None
    decision_id: Sha | None = None


class BatchQueuePreview(Contract):
    kind: Literal["batch_queue"] = "batch_queue"
    reference_id: Sha
    revision: int
    dictionary: DictionaryView
    items: list[BatchCasePreview] = Field(min_length=1, max_length=100)
    trainable: Literal[False] = False
