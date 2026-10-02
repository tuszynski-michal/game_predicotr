"""Source-direct preview and persistence boundary for manual virtual geometry."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from PIL import Image

from game_predictor_api.application.image_review_assets import (
    resolve_grid_review_source_asset,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    ImageGeometryContractError,
    NormalizedSourceImage,
    SourceImageBounds,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    canonical_json_bytes,
    derive_virtual_cells,
    resolve_manual_geometry_qualification,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewSourceAsset,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryPoint,
    ValidatedImageReviewGeometryCommand,
    validate_image_review_geometry_command,
)

if TYPE_CHECKING:
    from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
        ManualBoardCellSymbolPredictor,
    )
    from game_predictor_worker.images.virtual_cell_extraction import (
        VirtualCellRender,
    )

VIRTUAL_MANUAL_GEOMETRY_VERSION = "manual-source-geometry-v1"
VIRTUAL_MANUAL_RENDER_MANIFEST_VERSION = "virtual-board-render-manifest-v2-dual-identity-v1"


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryContext:
    game_id: UUID
    import_job_id: UUID
    review_item_id: UUID | None
    recognized_board_id: UUID
    pending_geometry_id: UUID | None
    source_image_id: UUID
    file_execution_key: str
    position_index: int
    sequence_number: int
    source_relative_path: str
    source_checksum_sha256: str
    raw_width: int
    raw_height: int
    oriented_width: int
    oriented_height: int
    exif_orientation: int | None
    normalized_pixel_checksum_sha256: str
    normalization_adapter_version: str
    pipeline_fingerprint: str
    resolution_revision: int
    geometry_revision: int
    topology: BoardTopology
    topology_rules_version_id: UUID
    source_geometry_revision_id: UUID
    source_geometry_revision: int
    sequence_range_start: int
    sequence_range_end: int
    active_board_slots: tuple[int, ...]
    global_initialization: Mapping[str, object] | None
    board_geometries: tuple[Mapping[str, object], ...]
    render_configuration: DirectCellRenderConfiguration
    # Symbol model pinned to the import of a still-deferred slot; its rendered
    # cells are classified with exactly this model (D-467, TASK-0790).
    pending_symbol_model: Mapping[str, object] | None = None
    # Common revision of the 15 current symbol cells of the slot's
    # ``game_id + sequence_number`` when a deferred slot takes over a sequence
    # already owned by another board (TASK-0702 handoff rule, DATA_MODEL).
    sequence_geometry_revision: int | None = None

    @property
    def next_geometry_revision(self) -> int:
        """Revision of the next manual geometry of this slot.

        A deferred slot pins its own source revision, but when it becomes the
        newest owner of a sequence whose current cells are on revision R, the
        logical 3 x 5 board continues from R: the write uses ``max(pinned, R)
        + 1`` so it never reuses a revision of the previous owner.
        """

        floor = self.geometry_revision
        if self.sequence_geometry_revision is not None:
            floor = max(floor, self.sequence_geometry_revision)
        return floor + 1

    @property
    def target_id(self) -> UUID:
        return self.pending_geometry_id or cast(UUID, self.review_item_id)

    @property
    def source_asset(self) -> ImageGridReviewSourceAsset:
        return ImageGridReviewSourceAsset(
            review_item_id=self.target_id,
            source_image_id=self.source_image_id,
            source_relative_path=self.source_relative_path,
            source_checksum_sha256=self.source_checksum_sha256,
            source_width=self.oriented_width,
            source_height=self.oriented_height,
            geometry_revision=self.geometry_revision,
            resolution_revision=self.resolution_revision,
            topology=self.topology,
        )


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryCell:
    cell_index: int
    row_index: int
    column_index: int
    crop_sample_id: str
    crop_checksum_sha256: str
    logical_cell_key: str
    logical_cell_key_v2: str | None
    render_identity_v2_sha256: str | None
    render_spec: Mapping[str, object]
    render_spec_checksum_sha256: str
    rendered_pixel_checksum_sha256: str
    extractor_version: str


@dataclass(frozen=True, slots=True)
class VirtualSlotPrediction:
    """Pinned-model predictions of the rendered cells of a deferred slot."""

    model_iteration_id: str | None
    model_manifest_checksum_sha256: str
    model_version: str
    temperature_applied: float
    cells: tuple[Mapping[str, object], ...]

    def to_cells_prediction(self) -> dict[str, object]:
        return {
            "cells": [dict(cell) for cell in self.cells],
            "modelIterationId": self.model_iteration_id,
            "modelManifestChecksumSha256": self.model_manifest_checksum_sha256,
            "modelVersion": self.model_version,
            "temperatureApplied": self.temperature_applied,
        }


@dataclass(frozen=True, slots=True)
class PreparedVirtualGridGeometry:
    command: ValidatedImageReviewGeometryCommand
    context: VirtualGridGeometryContext
    source_geometry_checksum_sha256: str
    board_geometries: tuple[Mapping[str, object], ...]
    board_geometry: Mapping[str, object]
    virtual_render_spec: Mapping[str, object]
    virtual_render_spec_checksum_sha256: str
    cells: tuple[VirtualGridGeometryCell, ...]
    cropper_version: str
    slot_prediction: VirtualSlotPrediction | None = None


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryPreview:
    contact_sheet_png: bytes
    cells: tuple[VirtualGridGeometryCell, ...]
    cropper_version: str


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryRevision:
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int
    idempotency_key: UUID
    command_sha256: str
    corners: tuple[ImageReviewGeometryPoint, ...]
    source_geometry_revision_id: UUID
    geometry_checksum_sha256: str
    virtual_render_spec_checksum_sha256: str
    cropper_version: str
    cells: tuple[VirtualGridGeometryCell, ...]
    corrected_by: str
    created_at: datetime
    geometry_qualification: GeometryQualification | None = None


@dataclass(frozen=True, slots=True)
class VirtualGridGeometrySaveResult:
    revision: VirtualGridGeometryRevision
    created: bool


@dataclass(frozen=True, slots=True)
class VirtualGridGeometrySourceCommand:
    """One exact board command inside an all-or-nothing source correction."""

    review_item_id: UUID | None
    pending_geometry_id: UUID | None
    expected_geometry_revision: int
    expected_resolution_revision: int
    expected_source_checksum_sha256: str
    expected_source_width: int
    expected_source_height: int
    expected_grid_rows: int
    expected_grid_columns: int
    corners: tuple[ImageReviewGeometryPoint, ...]
    geometry_qualification: GeometryQualification | None = None

    @property
    def target_id(self) -> UUID:
        return self.pending_geometry_id or cast(UUID, self.review_item_id)


@dataclass(frozen=True, slots=True)
class PreparedVirtualGridGeometrySource:
    entries: tuple[PreparedVirtualGridGeometry, ...]
    source_geometry_checksum_sha256: str
    board_geometries: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class VirtualGridGeometrySourceSaveResult:
    revisions: tuple[VirtualGridGeometryRevision, ...]
    created: bool


@dataclass(frozen=True, slots=True)
class LegacyConversionTarget:
    """One ``legacy_file`` board rendered from its current corners (TASK-0791).

    ``context.geometry_revision`` is the board's current revision and
    ``context.sequence_geometry_revision`` the common revision of its
    sequence's current cells, so ``context.next_geometry_revision`` follows
    the TASK-0702 rule ``max(N, R) + 1``.
    """

    context: VirtualGridGeometryContext
    corners: tuple[ImageReviewGeometryPoint, ...]
    geometry_qualification: GeometryQualification | None


class VirtualGridGeometryRepository(Protocol):
    def virtual_geometry_replay(
        self, *, context: VirtualGridGeometryContext, idempotency_key: UUID
    ) -> VirtualGridGeometryRevision | None: ...

    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID | None,
        pending_geometry_id: UUID | None,
    ) -> VirtualGridGeometryContext: ...

    def save_virtual_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySaveResult: ...

    def save_virtual_source_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometrySource,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySourceSaveResult: ...


class VirtualGridGeometryService:
    """Render manual virtual crops once and persist metadata-only provenance."""

    def __init__(
        self,
        repository: VirtualGridGeometryRepository,
        artifact_root: Path,
        *,
        symbol_predictor: ManualBoardCellSymbolPredictor | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = artifact_root.resolve()
        self._symbol_predictor = symbol_predictor

    def preview(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometryPreview:
        prepared, renders = self._prepare(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
            expected_source_width=expected_source_width,
            expected_source_height=expected_source_height,
            expected_grid_rows=expected_grid_rows,
            expected_grid_columns=expected_grid_columns,
            corners=corners,
            actor="local-admin-preview",
            geometry_qualification=geometry_qualification,
        )
        return VirtualGridGeometryPreview(
            contact_sheet_png=_contact_sheet_png(
                renders,
                prepared.context.topology,
                qualification=prepared.command.geometry_qualification,
                configuration=prepared.context.render_configuration,
            ),
            cells=prepared.cells,
            cropper_version=prepared.cropper_version,
        )

    def save(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
        created_at: datetime,
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometrySaveResult:
        replay = self._find_replay(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=(
                VirtualGridGeometrySourceCommand(
                    review_item_id=review_item_id,
                    pending_geometry_id=None,
                    expected_geometry_revision=expected_geometry_revision,
                    expected_resolution_revision=expected_resolution_revision,
                    expected_source_checksum_sha256=expected_source_checksum_sha256,
                    expected_source_width=expected_source_width,
                    expected_source_height=expected_source_height,
                    expected_grid_rows=expected_grid_rows,
                    expected_grid_columns=expected_grid_columns,
                    corners=tuple(corners),
                    geometry_qualification=geometry_qualification,
                ),
            ),
            idempotency_key=idempotency_key,
            actor=actor,
        )
        if replay is not None:
            return VirtualGridGeometrySaveResult(revision=replay[0], created=False)
        prepared, _renders = self._prepare(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
            expected_source_width=expected_source_width,
            expected_source_height=expected_source_height,
            expected_grid_rows=expected_grid_rows,
            expected_grid_columns=expected_grid_columns,
            corners=corners,
            actor=actor,
            geometry_qualification=geometry_qualification,
        )
        return self._repository.save_virtual_geometry_revision(
            prepared=prepared,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def preview_review_item(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometryPreview:
        """Render one current board for the operational Reviewer (TASK-0796).

        The Reviewer command carries only the corners and the two CAS
        revisions; the source identity and topology are the persisted ones,
        exactly as for a deferred slot.  The render is the same as
        :meth:`preview` would produce for the Admin.
        """

        context = self._persisted_review_item_context(
            game_id=game_id, import_job_id=import_job_id, review_item_id=review_item_id
        )
        return self.preview(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=context.source_checksum_sha256,
            expected_source_width=context.oriented_width,
            expected_source_height=context.oriented_height,
            expected_grid_rows=context.topology.rows,
            expected_grid_columns=context.topology.columns,
            corners=corners,
            geometry_qualification=geometry_qualification,
        )

    def save_review_item(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
        created_at: datetime,
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometrySaveResult:
        """Persist one current board's manual geometry for the Reviewer (TASK-0796).

        Delegates to :meth:`save` (replay by ``idempotency_key`` first, then
        the revision CAS and ``save_virtual_geometry_revision``), so the
        board gets a ``virtual_source`` revision with a render manifest.
        """

        context = self._persisted_review_item_context(
            game_id=game_id, import_job_id=import_job_id, review_item_id=review_item_id
        )
        return self.save(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            idempotency_key=idempotency_key,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=context.source_checksum_sha256,
            expected_source_width=context.oriented_width,
            expected_source_height=context.oriented_height,
            expected_grid_rows=context.topology.rows,
            expected_grid_columns=context.topology.columns,
            corners=corners,
            geometry_qualification=geometry_qualification,
            actor=actor,
            created_at=created_at,
        )

    def _persisted_review_item_context(
        self, *, game_id: UUID, import_job_id: UUID, review_item_id: UUID
    ) -> VirtualGridGeometryContext:
        return self._repository.virtual_geometry_context(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            pending_geometry_id=None,
        )

    def save_source(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        commands: Sequence[VirtualGridGeometrySourceCommand],
        idempotency_key: UUID,
        actor: str,
        created_at: datetime,
    ) -> VirtualGridGeometrySourceSaveResult:
        replay = self._find_replay(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=commands,
            idempotency_key=idempotency_key,
            actor=actor,
            complete_source=True,
        )
        if replay is not None:
            return VirtualGridGeometrySourceSaveResult(revisions=replay, created=False)
        prepared, _renders = self._prepare_source(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=commands,
            actor=actor,
        )
        return self._repository.save_virtual_source_geometry_revision(
            prepared=prepared,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def preview_pending_slot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        pending_geometry_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        geometry_qualification: GeometryQualification | None = None,
        actor: str = "local-admin-preview",
    ) -> VirtualGridGeometryPreview:
        """Render one deferred slot from its source, exactly as a save would."""

        command = self._pending_slot_command(
            game_id=game_id,
            import_job_id=import_job_id,
            pending_geometry_id=pending_geometry_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corners=corners,
            geometry_qualification=geometry_qualification,
        )
        prepared, renders = self._prepare_source(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=(command,),
            actor=actor,
            require_complete_source=False,
            predict=False,
        )
        entry = prepared.entries[0]
        return VirtualGridGeometryPreview(
            contact_sheet_png=_contact_sheet_png(
                renders[entry.context.target_id],
                entry.context.topology,
                qualification=entry.command.geometry_qualification,
                configuration=entry.context.render_configuration,
            ),
            cells=entry.cells,
            cropper_version=entry.cropper_version,
        )

    def save_pending_slot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        pending_geometry_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
        created_at: datetime,
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometrySourceSaveResult:
        """Resolve one deferred slot as a ``virtual_source`` board (D-467).

        Unlike :meth:`save_source` the other slots of the source keep their
        current geometry: the new source revision is derived from the latest
        one and only the deferred slot's quad changes.  The repository locks
        and re-checks that exact snapshot, so a concurrent change conflicts.
        """

        command = self._pending_slot_command(
            game_id=game_id,
            import_job_id=import_job_id,
            pending_geometry_id=pending_geometry_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corners=corners,
            geometry_qualification=geometry_qualification,
        )
        replay = self._find_replay(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=(command,),
            idempotency_key=idempotency_key,
            actor=actor,
        )
        if replay is not None:
            return VirtualGridGeometrySourceSaveResult(revisions=replay, created=False)
        prepared, _renders = self._prepare_source(
            game_id=game_id,
            import_job_id=import_job_id,
            commands=(command,),
            actor=actor,
            require_complete_source=False,
        )
        return self._repository.save_virtual_source_geometry_revision(
            prepared=prepared,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def _pending_slot_command(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        pending_geometry_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        geometry_qualification: GeometryQualification | None,
    ) -> VirtualGridGeometrySourceCommand:
        # The deferred item's processing manifest already pins the source
        # checksum; the source identity therefore comes from persistence.
        context = self._repository.virtual_geometry_context(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=None,
            pending_geometry_id=pending_geometry_id,
        )
        return VirtualGridGeometrySourceCommand(
            review_item_id=None,
            pending_geometry_id=pending_geometry_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=context.source_checksum_sha256,
            expected_source_width=context.oriented_width,
            expected_source_height=context.oriented_height,
            expected_grid_rows=context.topology.rows,
            expected_grid_columns=context.topology.columns,
            corners=tuple(corners),
            geometry_qualification=geometry_qualification,
        )

    def _find_replay(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        commands: Sequence[VirtualGridGeometrySourceCommand],
        idempotency_key: UUID,
        actor: str,
        complete_source: bool = False,
    ) -> tuple[VirtualGridGeometryRevision, ...] | None:
        """Recognize a committed request before rendering or rejecting its old CAS token."""
        found: list[tuple[int, VirtualGridGeometryRevision]] = []
        contexts: list[VirtualGridGeometryContext] = []
        for value in commands:
            context = self._repository.virtual_geometry_context(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=value.review_item_id,
                pending_geometry_id=value.pending_geometry_id,
            )
            contexts.append(context)
            prior = self._repository.virtual_geometry_replay(
                context=context, idempotency_key=idempotency_key
            )
            if prior is None:
                continue
            qualification = value.geometry_qualification
            if qualification is not None:
                qualification = resolve_manual_geometry_qualification(
                    quad=SourceQuad(
                        cast(
                            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                            tuple(SourcePoint(x=p.x, y=p.y) for p in value.corners),
                        )
                    ),
                    source=SourceImageBounds(context.oriented_width, context.oriented_height),
                    topology=context.topology,
                    qualification=qualification,
                )
            command = validate_image_review_geometry_command(
                corners=value.corners,
                expected_geometry_revision=value.expected_geometry_revision,
                expected_resolution_revision=value.expected_resolution_revision,
                corrected_by=actor,
                geometry_qualification=qualification,
            )
            _require_expected_context(
                context,
                command=command,
                source_checksum=value.expected_source_checksum_sha256,
                source_width=value.expected_source_width,
                source_height=value.expected_source_height,
                topology=BoardTopology(
                    rows=value.expected_grid_rows, columns=value.expected_grid_columns
                ),
                check_revision=False,
            )
            if prior.command_sha256 != command.command_sha256:
                raise ImageGridReviewError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another command.",
                )
            found.append((context.position_index, prior))
        if not found:
            return None
        if len(found) != len(commands) or len({command.target_id for command in commands}) != len(
            commands
        ):
            raise ImageGridReviewError(
                "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                "A source retry must contain the same complete set of commands.",
            )
        if complete_source and (
            len({context.source_image_id for context in contexts}) != 1
            or len({prior.source_geometry_revision_id for _, prior in found}) != 1
            or len({prior.geometry_checksum_sha256 for _, prior in found}) != 1
            or tuple(sorted(context.position_index for context in contexts))
            != contexts[0].active_board_slots
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "A source retry requires every active slot of the same source.",
            )
        return tuple(prior for _position, prior in sorted(found, key=lambda pair: pair[0]))

    def _prepare_source(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        commands: Sequence[VirtualGridGeometrySourceCommand],
        actor: str,
        require_complete_source: bool = True,
        predict: bool = True,
    ) -> tuple[
        PreparedVirtualGridGeometrySource,
        dict[UUID, tuple[VirtualCellRender, ...]],
    ]:
        """Render every source slot once, then assemble one immutable revision.

        A source image can contain at most nine logical boards.  Loading and
        rendering each board through the single-board API would create sibling
        source-geometry revisions from stale base geometry.  This path validates
        all client identities first, canonicalizes the source once, and produces
        one board-geometries document containing every requested quad.

        ``require_complete_source=False`` is reserved for one deferred slot
        (``save_pending_slot``): it is rendered against the latest source
        revision and the other slots keep their current quads.
        """

        if not commands:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_EMPTY",
                "Manual source geometry requires at least one board command.",
            )
        if len({command.target_id for command in commands}) != len(commands):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_DUPLICATE",
                "Manual source geometry cannot repeat a board command.",
            )

        prepared_inputs: list[
            tuple[
                VirtualGridGeometryContext,
                ValidatedImageReviewGeometryCommand,
                SourceQuad,
            ]
        ] = []
        for source_command in commands:
            command = validate_image_review_geometry_command(
                corners=source_command.corners,
                expected_geometry_revision=source_command.expected_geometry_revision,
                expected_resolution_revision=source_command.expected_resolution_revision,
                corrected_by=actor,
                geometry_qualification=source_command.geometry_qualification,
            )
            context = _bind_current_renderer(
                self._repository.virtual_geometry_context(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    review_item_id=source_command.review_item_id,
                    pending_geometry_id=source_command.pending_geometry_id,
                )
            )
            _require_expected_context(
                context,
                command=command,
                source_checksum=source_command.expected_source_checksum_sha256,
                source_width=source_command.expected_source_width,
                source_height=source_command.expected_source_height,
                topology=BoardTopology(
                    rows=source_command.expected_grid_rows,
                    columns=source_command.expected_grid_columns,
                ),
            )
            quad = SourceQuad(
                corners=cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(SourcePoint(x=point.x, y=point.y) for point in command.corners),
                )
            )
            if command.geometry_qualification is not None:
                qualification = resolve_manual_geometry_qualification(
                    quad=quad,
                    source=SourceImageBounds(context.oriented_width, context.oriented_height),
                    topology=context.topology,
                    qualification=command.geometry_qualification,
                )
                command = validate_image_review_geometry_command(
                    corners=command.corners,
                    expected_geometry_revision=command.expected_geometry_revision,
                    expected_resolution_revision=command.expected_resolution_revision,
                    corrected_by=actor,
                    geometry_qualification=qualification,
                )
            prepared_inputs.append((context, command, quad))

        prepared_inputs.sort(key=lambda value: value[0].position_index)
        base_context = prepared_inputs[0][0]
        _require_source_batch_context(
            base_context=base_context,
            values=prepared_inputs,
        )
        expected_positions = tuple(range(len(base_context.board_geometries)))
        actual_positions = tuple(
            context.position_index for context, _command, _quad in prepared_inputs
        )
        if require_complete_source and actual_positions != expected_positions:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "Manual source geometry requires every active source slot in row-major order.",
            )
        if not require_complete_source and (
            len(prepared_inputs) != 1
            or prepared_inputs[0][0].pending_geometry_id is None
            or prepared_inputs[0][0].review_item_id is not None
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "A partial source correction may contain only one deferred slot.",
            )
        return self._render_source_entries(prepared_inputs, predict=predict)

    def prepare_legacy_conversion(
        self,
        targets: Sequence[LegacyConversionTarget],
        *,
        actor: str,
    ) -> PreparedVirtualGridGeometrySource:
        """Render ``legacy_file`` boards of one source exactly as manual geometry.

        D-467 S6 (TASK-0791): the conversion keeps each board's current corners
        and qualification and renders its cells through the same source loader,
        renderer, render manifest and checksums as a manual virtual geometry
        save.  The caller owns the contexts (they describe a legacy board, which
        the regular context reader refuses) and the persistence.
        """

        if not targets:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_EMPTY",
                "A legacy conversion requires at least one board of the source.",
            )
        prepared_inputs: list[
            tuple[VirtualGridGeometryContext, ValidatedImageReviewGeometryCommand, SourceQuad]
        ] = []
        for target in targets:
            context = _bind_current_renderer(target.context)
            corners = target.corners
            qualification = target.geometry_qualification
            quad = SourceQuad(
                corners=cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(SourcePoint(x=point.x, y=point.y) for point in corners),
                )
            )
            if qualification is not None:
                try:
                    qualification = resolve_manual_geometry_qualification(
                        quad=quad,
                        source=SourceImageBounds(context.oriented_width, context.oriented_height),
                        topology=context.topology,
                        qualification=qualification,
                    )
                except ImageGeometryContractError as error:
                    raise ImageGridReviewError(error.code, str(error)) from error
            command = validate_image_review_geometry_command(
                corners=tuple(corners),
                expected_geometry_revision=context.geometry_revision,
                expected_resolution_revision=context.resolution_revision,
                corrected_by=actor,
                geometry_qualification=qualification,
            )
            prepared_inputs.append((context, command, quad))
        prepared_inputs.sort(key=lambda value: value[0].position_index)
        _require_source_batch_context(base_context=prepared_inputs[0][0], values=prepared_inputs)
        prepared, _renders = self._render_source_entries(prepared_inputs, predict=False)
        return prepared

    def _render_source_entries(
        self,
        prepared_inputs: Sequence[
            tuple[VirtualGridGeometryContext, ValidatedImageReviewGeometryCommand, SourceQuad]
        ],
        *,
        predict: bool,
    ) -> tuple[
        PreparedVirtualGridGeometrySource,
        dict[UUID, tuple[VirtualCellRender, ...]],
    ]:
        """Render validated slots of one source once and assemble the revision."""

        base_context = prepared_inputs[0][0]

        from game_predictor_worker.images.normalization import (
            CanonicalSourceLoader,
            CanonicalSourceLoadError,
        )
        from game_predictor_worker.images.virtual_cell_extraction import (
            VirtualCellExtractionError,
            VirtualCellRenderer,
        )

        source_path = resolve_grid_review_source_asset(
            base_context.source_asset,
            self._artifact_root,
        ).path
        loader = CanonicalSourceLoader()
        rendered_by_item: dict[UUID, tuple[VirtualCellRender, ...]] = {}
        try:
            frame = loader.load(
                source_path,
                expected_source_checksum_sha256=base_context.source_checksum_sha256,
            )
            _require_frame(
                base_context,
                frame.source,
                raw_width=frame.raw_width,
                raw_height=frame.raw_height,
            )
            renderer = VirtualCellRenderer()
            for context, command, quad in prepared_inputs:
                geometry = VirtualBoardGeometry(
                    source=frame.source,
                    source_occurrence=SourceOccurrence(
                        import_job_id=context.import_job_id,
                        file_execution_key=context.file_execution_key,
                    ),
                    slot=ActiveBoardSlot(
                        range_start=context.sequence_range_start,
                        range_end=context.sequence_range_end,
                        position_index=context.position_index,
                        sequence_number=context.sequence_number,
                    ),
                    topology=context.topology,
                    topology_rules_version_id=context.topology_rules_version_id,
                    geometry_revision=context.next_geometry_revision,
                    geometry_version=VIRTUAL_MANUAL_GEOMETRY_VERSION,
                    engine_kind=GeometryEngineKind.MANUAL_V1,
                    symbol_grid_quad=quad,
                    geometry_qualification=command.geometry_qualification,
                )
                rendered_by_item[context.target_id] = tuple(
                    renderer.render(
                        frame,
                        derive_virtual_cells(
                            geometry=geometry,
                            configuration=context.render_configuration,
                        ),
                    )
                )
        except (
            CanonicalSourceLoadError,
            ImageGeometryContractError,
            VirtualCellExtractionError,
        ) as error:
            raise ImageGridReviewError(
                getattr(error, "code", "IMAGE_GRID_REVIEW_VIRTUAL_RENDER_FAILED"),
                str(error),
            ) from error
        finally:
            loader.clear()

        board_geometries = _replace_source_board_geometries(
            base_context,
            tuple((context, quad) for context, _command, quad in prepared_inputs),
            qualifications={
                context.position_index: command.geometry_qualification
                for context, command, _quad in prepared_inputs
            },
        )
        source_geometry_checksum = hashlib.sha256(
            canonical_json_bytes(
                {
                    "activeBoardSlots": list(base_context.active_board_slots),
                    "boardGeometries": list(board_geometries),
                    "engineKind": GeometryEngineKind.MANUAL_V1.value,
                    "engineVersion": VIRTUAL_MANUAL_GEOMETRY_VERSION,
                    "previousSourceGeometryRevisionId": str(
                        base_context.source_geometry_revision_id
                    ),
                    "sourceChecksumSha256": base_context.source_checksum_sha256,
                    "topologyRulesVersionId": str(base_context.topology_rules_version_id),
                }
            )
        ).hexdigest()
        entries: list[PreparedVirtualGridGeometry] = []
        for context, command, quad in prepared_inputs:
            cells = tuple(
                _cell_from_render(context.recognized_board_id, render)
                for render in rendered_by_item[context.target_id]
            )
            render_manifest: dict[str, object] = {
                "assetMode": "virtual_source",
                "cells": [
                    {
                        "cellIndex": cell.cell_index,
                        "cropSampleId": cell.crop_sample_id,
                        "logicalCellKeySha256": cell.logical_cell_key,
                        "logicalCellKeyV2Sha256": cell.logical_cell_key_v2,
                        "renderIdentityV2Sha256": cell.render_identity_v2_sha256,
                        "renderSpec": dict(cell.render_spec),
                        "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
                        "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                    }
                    for cell in cells
                ],
                "geometryChecksumSha256": source_geometry_checksum,
                "schemaVersion": VIRTUAL_MANUAL_RENDER_MANIFEST_VERSION,
            }
            if command.geometry_qualification is not None:
                render_manifest["configuration"] = context.render_configuration.to_dict()
                render_manifest["geometryQualification"] = command.geometry_qualification.to_dict()
            entries.append(
                PreparedVirtualGridGeometry(
                    command=command,
                    context=context,
                    source_geometry_checksum_sha256=source_geometry_checksum,
                    board_geometries=board_geometries,
                    board_geometry=_recognized_board_geometry(
                        context,
                        quad,
                        command.command_sha256,
                        qualification=command.geometry_qualification,
                    ),
                    virtual_render_spec=render_manifest,
                    virtual_render_spec_checksum_sha256=hashlib.sha256(
                        canonical_json_bytes(render_manifest)
                    ).hexdigest(),
                    cells=cells,
                    cropper_version=VirtualCellRenderer.version,
                    slot_prediction=(
                        self._predict_pending_slot(context, rendered_by_item[context.target_id])
                        if predict
                        else None
                    ),
                )
            )
        return (
            PreparedVirtualGridGeometrySource(
                entries=tuple(entries),
                source_geometry_checksum_sha256=source_geometry_checksum,
                board_geometries=board_geometries,
            ),
            rendered_by_item,
        )

    def _predict_pending_slot(
        self,
        context: VirtualGridGeometryContext,
        renders: Sequence[VirtualCellRender],
    ) -> VirtualSlotPrediction | None:
        """Classify a still-deferred slot with its import's pinned model."""

        if (
            self._symbol_predictor is None
            or context.review_item_id is not None
            or context.pending_symbol_model is None
        ):
            return None
        from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
            ManualBoardCellSymbolPredictionError,
            RenderedBoardCell,
        )

        from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

        try:
            snapshot = SymbolModelJobSnapshot.from_payload(context.pending_symbol_model)
        except (TypeError, ValueError) as error:
            raise ImageGridReviewError(
                "IMAGE_SYMBOL_MODEL_SNAPSHOT_INVALID",
                "The deferred slot's import has an invalid pinned symbol model.",
            ) from error
        try:
            prediction = self._symbol_predictor.predict_rendered_cells(
                tuple(
                    RenderedBoardCell(
                        row_index=render.row_index,
                        column_index=render.column_index,
                        rgb=render.rgb,
                    )
                    for render in sorted(renders, key=lambda value: value.cell_index)
                ),
                snapshot,
            )
        except ManualBoardCellSymbolPredictionError as error:
            raise ImageGridReviewError(error.code, str(error)) from error
        return VirtualSlotPrediction(
            model_iteration_id=prediction.model_iteration_id,
            model_manifest_checksum_sha256=prediction.model_manifest_checksum_sha256,
            model_version=prediction.model_version,
            temperature_applied=prediction.temperature_applied,
            cells=tuple(prediction.cells),
        )

    def _prepare(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
        geometry_qualification: GeometryQualification | None = None,
    ) -> tuple[PreparedVirtualGridGeometry, tuple[VirtualCellRender, ...]]:
        from game_predictor_worker.images.normalization import (
            CanonicalSourceLoader,
            CanonicalSourceLoadError,
        )
        from game_predictor_worker.images.virtual_cell_extraction import (
            VirtualCellExtractionError,
            VirtualCellRenderer,
        )

        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=actor,
            geometry_qualification=geometry_qualification,
        )
        context = _bind_current_renderer(
            self._repository.virtual_geometry_context(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                pending_geometry_id=None,
            )
        )
        _require_expected_context(
            context,
            command=command,
            source_checksum=expected_source_checksum_sha256,
            source_width=expected_source_width,
            source_height=expected_source_height,
            topology=BoardTopology(rows=expected_grid_rows, columns=expected_grid_columns),
        )
        source_path = resolve_grid_review_source_asset(
            context.source_asset,
            self._artifact_root,
        ).path
        loader = CanonicalSourceLoader()
        try:
            frame = loader.load(
                source_path,
                expected_source_checksum_sha256=context.source_checksum_sha256,
            )
            _require_frame(
                context,
                frame.source,
                raw_width=frame.raw_width,
                raw_height=frame.raw_height,
            )
            quad = SourceQuad(
                corners=cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(SourcePoint(x=point.x, y=point.y) for point in command.corners),
                )
            )
            if geometry_qualification is not None:
                geometry_qualification = resolve_manual_geometry_qualification(
                    quad,
                    source=frame.source,
                    topology=context.topology,
                    qualification=geometry_qualification,
                )
                command = validate_image_review_geometry_command(
                    corners=corners,
                    expected_geometry_revision=expected_geometry_revision,
                    expected_resolution_revision=expected_resolution_revision,
                    corrected_by=actor,
                    geometry_qualification=geometry_qualification,
                )
            geometry = VirtualBoardGeometry(
                source=frame.source,
                source_occurrence=SourceOccurrence(
                    import_job_id=context.import_job_id,
                    file_execution_key=context.file_execution_key,
                ),
                slot=ActiveBoardSlot(
                    range_start=context.sequence_range_start,
                    range_end=context.sequence_range_end,
                    position_index=context.position_index,
                    sequence_number=context.sequence_number,
                ),
                topology=context.topology,
                topology_rules_version_id=context.topology_rules_version_id,
                geometry_revision=context.geometry_revision + 1,
                geometry_version=VIRTUAL_MANUAL_GEOMETRY_VERSION,
                engine_kind=GeometryEngineKind.MANUAL_V1,
                symbol_grid_quad=quad,
                geometry_qualification=geometry_qualification,
            )
            renders = VirtualCellRenderer().render(
                frame,
                derive_virtual_cells(
                    geometry=geometry,
                    configuration=context.render_configuration,
                ),
            )
        except (
            CanonicalSourceLoadError,
            ImageGeometryContractError,
            VirtualCellExtractionError,
        ) as error:
            raise ImageGridReviewError(
                getattr(error, "code", "IMAGE_GRID_REVIEW_VIRTUAL_RENDER_FAILED"),
                str(error),
            ) from error
        finally:
            loader.clear()

        board_geometries = _replace_board_geometry(
            context, quad, qualification=geometry_qualification
        )
        source_geometry_checksum = hashlib.sha256(
            canonical_json_bytes(
                {
                    "activeBoardSlots": list(context.active_board_slots),
                    "boardGeometries": list(board_geometries),
                    "engineKind": GeometryEngineKind.MANUAL_V1.value,
                    "engineVersion": VIRTUAL_MANUAL_GEOMETRY_VERSION,
                    "previousSourceGeometryRevisionId": str(context.source_geometry_revision_id),
                    "sourceChecksumSha256": context.source_checksum_sha256,
                    "topologyRulesVersionId": str(context.topology_rules_version_id),
                }
            )
        ).hexdigest()
        cells = tuple(_cell_from_render(context.recognized_board_id, render) for render in renders)
        render_manifest: dict[str, object] = {
            "assetMode": "virtual_source",
            "cells": [
                {
                    "cellIndex": cell.cell_index,
                    "cropSampleId": cell.crop_sample_id,
                    "logicalCellKeySha256": cell.logical_cell_key,
                    "logicalCellKeyV2Sha256": cell.logical_cell_key_v2,
                    "renderIdentityV2Sha256": cell.render_identity_v2_sha256,
                    "renderSpec": dict(cell.render_spec),
                    "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
                    "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                }
                for cell in cells
            ],
            "geometryChecksumSha256": source_geometry_checksum,
            "schemaVersion": VIRTUAL_MANUAL_RENDER_MANIFEST_VERSION,
        }
        if geometry_qualification is not None:
            render_manifest["configuration"] = context.render_configuration.to_dict()
            render_manifest["geometryQualification"] = geometry_qualification.to_dict()
        board_geometry = _recognized_board_geometry(
            context, quad, command.command_sha256, qualification=geometry_qualification
        )
        return (
            PreparedVirtualGridGeometry(
                command=command,
                context=context,
                source_geometry_checksum_sha256=source_geometry_checksum,
                board_geometries=board_geometries,
                board_geometry=board_geometry,
                virtual_render_spec=render_manifest,
                virtual_render_spec_checksum_sha256=hashlib.sha256(
                    canonical_json_bytes(render_manifest)
                ).hexdigest(),
                cells=cells,
                cropper_version=VirtualCellRenderer.version,
            ),
            renders,
        )


def _bind_current_renderer(context: VirtualGridGeometryContext) -> VirtualGridGeometryContext:
    """Bind a context to the renderer that produces the new manual renders.

    Stored cells pin the renderer contract of the import that produced them.
    A manual correction always creates new renders, so it keeps the remaining
    pinned configuration and records the current renderer instead of rejecting
    every board imported before a renderer contract bump.
    """

    from game_predictor_worker.images.virtual_cell_extraction import VirtualCellRenderer

    return replace(
        context,
        render_configuration=replace(
            context.render_configuration,
            extractor_version=VirtualCellRenderer.version,
        ),
    )


def _require_expected_context(
    context: VirtualGridGeometryContext,
    *,
    command: ValidatedImageReviewGeometryCommand,
    source_checksum: str,
    source_width: int,
    source_height: int,
    topology: BoardTopology,
    check_revision: bool = True,
) -> None:
    if (
        check_revision
        and context.board_geometries[context.position_index].get("geometryQualification")
        is not None
        and command.geometry_qualification is None
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_QUALIFICATION_REQUIRED",
            "The current geometry qualification cannot be discarded by an older command.",
        )
    if check_revision and (
        context.geometry_revision != command.expected_geometry_revision
        or context.resolution_revision != command.expected_resolution_revision
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
            "The virtual grid review changed after it was loaded.",
        )
    if (
        context.source_checksum_sha256 != source_checksum
        or context.oriented_width != source_width
        or context.oriented_height != source_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The virtual source identity changed after the grid review was loaded.",
        )
    if context.topology != topology:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
            "The board topology changed after the grid review was loaded.",
        )


def _require_frame(
    context: VirtualGridGeometryContext,
    source: NormalizedSourceImage,
    *,
    raw_width: int,
    raw_height: int,
) -> None:
    if (
        source.source_checksum_sha256 != context.source_checksum_sha256
        or source.normalized_pixel_checksum_sha256 != context.normalized_pixel_checksum_sha256
        or source.width != context.oriented_width
        or source.height != context.oriented_height
        or source.exif_orientation != context.exif_orientation
        or source.normalization_adapter_version != context.normalization_adapter_version
        or raw_width != context.raw_width
        or raw_height != context.raw_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The decoded virtual source differs from its canonical coordinate metadata.",
        )


def _replace_board_geometry(
    context: VirtualGridGeometryContext,
    quad: SourceQuad,
    *,
    qualification: GeometryQualification | None = None,
) -> tuple[Mapping[str, object], ...]:
    if context.active_board_slots != tuple(range(len(context.board_geometries))):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
            "Virtual manual geometry requires a complete attested source prefix.",
        )
    values = [dict(value) for value in context.board_geometries]
    if not 0 <= context.position_index < len(values):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
            "The board slot is outside the attested source geometry.",
        )
    values[context.position_index].update(
        {
            "disposition": "automatic",
            "finalQuad": quad.to_dict(),
            "geometrySource": "manual",
            "positionIndex": context.position_index,
            "sequenceNumber": context.sequence_number,
        }
    )
    if qualification is not None:
        _apply_qualification(values[context.position_index], quad, qualification)
    return tuple(values)


def _require_source_batch_context(
    *,
    base_context: VirtualGridGeometryContext,
    values: Sequence[
        tuple[
            VirtualGridGeometryContext,
            ValidatedImageReviewGeometryCommand,
            SourceQuad,
        ]
    ],
) -> None:
    for context, _command, _quad in values:
        if (
            context.game_id != base_context.game_id
            or context.import_job_id != base_context.import_job_id
            or context.source_image_id != base_context.source_image_id
            or context.source_checksum_sha256 != base_context.source_checksum_sha256
            or context.oriented_width != base_context.oriented_width
            or context.oriented_height != base_context.oriented_height
            or context.normalized_pixel_checksum_sha256
            != base_context.normalized_pixel_checksum_sha256
            or context.normalization_adapter_version != base_context.normalization_adapter_version
            or context.topology != base_context.topology
            or context.topology_rules_version_id != base_context.topology_rules_version_id
            or context.source_geometry_revision_id != base_context.source_geometry_revision_id
            or context.active_board_slots != base_context.active_board_slots
            or context.board_geometries != base_context.board_geometries
            or context.render_configuration != base_context.render_configuration
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "The active source slots no longer share one current geometry snapshot.",
            )


def _replace_source_board_geometries(
    context: VirtualGridGeometryContext,
    values: Sequence[tuple[VirtualGridGeometryContext, SourceQuad]],
    *,
    qualifications: Mapping[int, GeometryQualification | None] | None = None,
) -> tuple[dict[str, object], ...]:
    if context.active_board_slots != tuple(range(len(context.board_geometries))):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
            "Virtual manual geometry requires a complete attested source prefix.",
        )
    result = [dict(value) for value in context.board_geometries]
    for entry_context, quad in values:
        if not 0 <= entry_context.position_index < len(result):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
                "A board slot is outside the attested source geometry.",
            )
        result[entry_context.position_index].update(
            {
                "disposition": "automatic",
                "finalQuad": quad.to_dict(),
                "geometrySource": "manual",
                "positionIndex": entry_context.position_index,
                "sequenceNumber": entry_context.sequence_number,
            }
        )
        qualification = (
            None if qualifications is None else qualifications.get(entry_context.position_index)
        )
        if qualification is not None:
            _apply_qualification(result[entry_context.position_index], quad, qualification)
    return tuple(result)


def _recognized_board_geometry(
    context: VirtualGridGeometryContext,
    quad: SourceQuad,
    command_checksum: str,
    *,
    qualification: GeometryQualification | None = None,
) -> Mapping[str, object]:
    value = dict(context.board_geometries[context.position_index])
    value.update(
        {
            "commandChecksumSha256": command_checksum,
            "coordinateSpace": "exif-normalized-rgb-pixels-v1",
            "geometryVersion": VIRTUAL_MANUAL_GEOMETRY_VERSION,
            "latticeBoundsQuad": quad.to_dict(),
            "source": "manual_override",
            "sourceQuad": quad.to_dict(),
        }
    )
    if qualification is not None:
        _apply_qualification(value, quad, qualification)
    return value


def _apply_qualification(
    value: dict[str, object], quad: SourceQuad, qualification: GeometryQualification
) -> None:
    value.update(
        {
            "geometryQualification": qualification.to_dict(),
            "completenessStatus": qualification.completeness_status,
            "unavailableCellIndices": list(qualification.unavailable_cell_indices),
            "disposition": "partial"
            if qualification.completeness_status == "pending_partial"
            else "automatic",
            "symbolGridQuad": quad.to_dict(),
            "finalQuad": quad.to_dict(),
        }
    )


def _cell_from_render(board_id: UUID, render: VirtualCellRender) -> VirtualGridGeometryCell:
    sample_id = hashlib.sha256(
        canonical_json_bytes(
            {
                "assetMode": "virtual_source",
                "recognizedBoardId": str(board_id),
                "renderSpecChecksumSha256": render.render_spec_checksum_sha256,
            }
        )
    ).hexdigest()
    return VirtualGridGeometryCell(
        cell_index=render.cell_index,
        row_index=render.row_index,
        column_index=render.column_index,
        crop_sample_id=sample_id,
        crop_checksum_sha256=render.rendered_pixel_checksum_sha256,
        logical_cell_key=render.logical_cell_key_sha256,
        logical_cell_key_v2=render.logical_cell_key_v2_sha256,
        render_identity_v2_sha256=render.render_identity_v2_sha256,
        render_spec=render.render_spec,
        render_spec_checksum_sha256=render.render_spec_checksum_sha256,
        rendered_pixel_checksum_sha256=render.rendered_pixel_checksum_sha256,
        extractor_version=render.extractor_version,
    )


def _contact_sheet_png(
    renders: Sequence[VirtualCellRender],
    topology: BoardTopology,
    *,
    qualification: GeometryQualification | None = None,
    configuration: DirectCellRenderConfiguration | None = None,
) -> bytes:
    missing = set(qualification.unavailable_cell_indices) if qualification else set()
    if {render.cell_index for render in renders} != set(range(topology.cell_count)) - missing:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE",
            "The virtual geometry preview is missing configured board cells.",
        )
    if not renders and configuration is None:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID",
            "Empty partial preview requires its pinned render configuration.",
        )
    tile_width = max(
        (render.rgb.shape[1] for render in renders),
        default=configuration.output_width if configuration else 0,
    )
    tile_height = max(
        (render.rgb.shape[0] for render in renders),
        default=configuration.output_height if configuration else 0,
    )
    sheet = Image.new(
        "RGB",
        (topology.columns * tile_width, topology.rows * tile_height),
        color=(0, 0, 0),
    )
    for render in renders:
        sheet.paste(
            Image.fromarray(render.rgb, mode="RGB"),
            (render.column_index * tile_width, render.row_index * tile_height),
        )
    output = BytesIO()
    sheet.save(output, format="PNG", optimize=False)
    return output.getvalue()


__all__ = [
    "LegacyConversionTarget",
    "PreparedVirtualGridGeometry",
    "PreparedVirtualGridGeometrySource",
    "VirtualGridGeometryCell",
    "VirtualGridGeometryContext",
    "VirtualGridGeometryPreview",
    "VirtualGridGeometryRepository",
    "VirtualGridGeometryRevision",
    "VirtualGridGeometrySaveResult",
    "VirtualGridGeometrySourceCommand",
    "VirtualGridGeometrySourceSaveResult",
    "VirtualGridGeometryService",
    "VirtualSlotPrediction",
]
