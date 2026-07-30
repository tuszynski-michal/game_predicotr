"""Load the checksum-bound real M5/M6 corpus into the M6.5 review workbench."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import torch
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewResolutionCell,
)
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import Engine, func, insert, select
from sqlalchemy.orm import Session

from .pipeline_contract import canonical_json_bytes, file_execution_key
from .symbol_classifier import load_image_tensor
from .symbol_model_release import (
    build_symbol_predictions,
    load_release_manifest,
)
from .symbol_onnx import LocalSymbolOnnxAdapter, tensor_batch_to_numpy

REAL_WORKBENCH_VERSION = "m65-real-workbench-v1"
REAL_WORKBENCH_GAME_CODE = "blazing-hot-7-deluxe"
REAL_WORKBENCH_GAME_NAME = "Blazing Hot 7 Deluxe"
REAL_WORKBENCH_ASSET_PREFIX = f"{REAL_WORKBENCH_VERSION}"
REAL_WORKBENCH_NAMESPACE = uuid5(NAMESPACE_URL, REAL_WORKBENCH_VERSION)
CORPUS_MANIFEST_PATH = Path("ai_docs/quality/m5-corpus-manifest.json")
GEOMETRY_REPORT_PATH = Path(
    "ai_docs/quality/m5-reviewed-manual-merge-v16-full-preflight-report.json"
)
INVENTORY_PATH = Path("ai_docs/quality/m6-symbol-crop-inventory-v3.json")
REVIEWED_LABELS_PATH = Path("artifacts/m6-symbol-review-v16/reviewed-labels.json")
RELEASE_MANIFEST_PATH = Path(
    "ai_docs/quality/m6-spatial-symbol-model-release-manifest.json"
)
SOURCE_ROOT_PATH = Path("examples/imgs")
GEOMETRY_ASSET_ROOT_PATH = Path(
    "artifacts/m5-reviewed-manual-merge-v16-full-preflight"
)


class RealWorkbenchFixtureError(RuntimeError):
    """Stable validation or persistence failure for the acceptance fixture."""


@dataclass(frozen=True, slots=True)
class RealWorkbenchSource:
    images: tuple[Mapping[str, object], ...]
    boards: tuple[Mapping[str, object], ...]
    samples_by_sequence: Mapping[int, tuple[Mapping[str, object], ...]]
    labels_by_sequence: Mapping[int, Mapping[int, str]]
    class_codes: tuple[str, ...]
    pipeline_fingerprint: str
    cropper_version: str
    release_manifest: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class RealWorkbenchFixtureResult:
    game_id: UUID
    import_job_id: UUID
    board_count: int
    pending_count: int
    completed_count: int
    reused: bool
    pipeline_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "boardCount": self.board_count,
            "completedCount": self.completed_count,
            "gameId": str(self.game_id),
            "importJobId": str(self.import_job_id),
            "pendingCount": self.pending_count,
            "pipelineFingerprint": self.pipeline_fingerprint,
            "reused": self.reused,
            "schemaVersion": 1,
            "version": REAL_WORKBENCH_VERSION,
        }


def load_real_workbench_source(repository_root: Path) -> RealWorkbenchSource:
    """Validate and join the accepted corpus, geometry, inventory and labels."""

    root = repository_root.resolve()
    corpus = _read_mapping(root / CORPUS_MANIFEST_PATH, "corpus manifest")
    geometry = _read_mapping(root / GEOMETRY_REPORT_PATH, "geometry report")
    inventory = _read_mapping(root / INVENTORY_PATH, "symbol inventory")
    reviewed = _read_mapping(root / REVIEWED_LABELS_PATH, "reviewed labels")
    release = load_release_manifest(
        root / RELEASE_MANIFEST_PATH,
        repository_root=root,
    )

    images = _mapping_rows(corpus.get("images"), "corpus images")
    boards = _mapping_rows(geometry.get("entries"), "geometry entries")
    samples = _mapping_rows(inventory.get("samples"), "inventory samples")
    class_codes = tuple(
        _text(value, "release class")
        for value in _sequence(release.get("classes"))
    )
    if (
        corpus.get("status") != "accepted"
        or corpus.get("imageCount") != 43
        or len(images) != 43
        or geometry.get("technicalPassed") is not True
        or geometry.get("boardCount") != 387
        or geometry.get("cellCount") != 5805
        or len(boards) != 387
        or inventory.get("status") != "ready"
        or inventory.get("boardCount") != 387
        or inventory.get("sampleCount") != 5805
        or len(samples) != 5805
        or len(class_codes) != 8
    ):
        raise RealWorkbenchFixtureError(
            "The accepted real-corpus cardinality or status contract has drifted."
        )

    boards_by_sequence: dict[int, Mapping[str, object]] = {}
    for board in boards:
        sequence_number = _positive_int(board.get("sequenceNumber"), "sequence number")
        if sequence_number in boards_by_sequence:
            raise RealWorkbenchFixtureError("The geometry report contains a duplicate sequence.")
        boards_by_sequence[sequence_number] = board
    if sorted(boards_by_sequence) != list(range(1, 388)):
        raise RealWorkbenchFixtureError("The geometry report is not the complete 1..387 range.")

    grouped_samples: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    sample_location: dict[str, tuple[int, int]] = {}
    for sample in samples:
        sequence_number = _positive_int(sample.get("sequenceNumber"), "sample sequence")
        row_index = _index(sample.get("rowIndex"), 3, "row index")
        column_index = _index(sample.get("columnIndex"), 5, "column index")
        sample_id = _sha256(sample.get("sampleId"), "sample id")
        grouped_samples[sequence_number].append(sample)
        sample_location[sample_id] = (sequence_number, row_index * 5 + column_index)
    normalized_samples: dict[int, tuple[Mapping[str, object], ...]] = {}
    for sequence_number in range(1, 388):
        rows = sorted(
            grouped_samples[sequence_number],
            key=lambda item: (
                _index(item.get("rowIndex"), 3, "row index"),
                _index(item.get("columnIndex"), 5, "column index"),
            ),
        )
        if len(rows) != 15:
            raise RealWorkbenchFixtureError(
                f"Sequence {sequence_number} does not contain exactly 15 cells."
            )
        normalized_samples[sequence_number] = tuple(rows)

    labels_by_sequence: dict[int, dict[int, str]] = defaultdict(dict)
    for label in _mapping_rows(reviewed.get("labels"), "reviewed labels"):
        sample_id = _sha256(label.get("sampleId"), "reviewed sample id")
        location = sample_location.get(sample_id)
        if location is None:
            raise RealWorkbenchFixtureError(
                "A reviewed label does not belong to the selected inventory."
            )
        symbol_code = _text(label.get("symbolCode"), "reviewed symbol code")
        if symbol_code not in class_codes:
            raise RealWorkbenchFixtureError(
                "A reviewed label is outside the released class catalog."
            )
        labels_by_sequence[location[0]][location[1]] = symbol_code

    inputs = {
        "corpusManifestSha256": _file_sha256(root / CORPUS_MANIFEST_PATH),
        "geometryReportSha256": _file_sha256(root / GEOMETRY_REPORT_PATH),
        "inventorySha256": _file_sha256(root / INVENTORY_PATH),
        "releaseManifestSha256": _file_sha256(root / RELEASE_MANIFEST_PATH),
        "version": REAL_WORKBENCH_VERSION,
    }
    pipeline_fingerprint = hashlib.sha256(canonical_json_bytes(inputs)).hexdigest()
    return RealWorkbenchSource(
        images=images,
        boards=tuple(boards_by_sequence[number] for number in range(1, 388)),
        samples_by_sequence=normalized_samples,
        labels_by_sequence={
            number: dict(values) for number, values in labels_by_sequence.items()
        },
        class_codes=class_codes,
        pipeline_fingerprint=pipeline_fingerprint,
        cropper_version=_text(geometry.get("cropperVersion"), "cropper version"),
        release_manifest=release,
    )


def prepare_real_workbench_fixture(
    engine: Engine,
    repository_root: Path,
    *,
    created_at: datetime | None = None,
) -> RealWorkbenchFixtureResult:
    """Create or verify one immutable real-corpus workbench import."""

    root = repository_root.resolve()
    source = load_real_workbench_source(root)
    now = created_at or datetime.now(UTC)
    _publish_assets(root, source)

    with Session(engine, expire_on_commit=False) as session:
        game_id = _ensure_catalog(session, source.class_codes)
        candidate = create_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "import_kind": "image_directory",
                "pipeline_fingerprint": source.pipeline_fingerprint,
            },
            created_at=now,
        )
        existing = SqlAlchemyJobRepository(session).get_job_by_input_key(
            candidate.input_key
        )
        if existing is not None:
            result = _fixture_result(
                session,
                game_id=game_id,
                job_id=existing.id,
                pipeline_fingerprint=source.pipeline_fingerprint,
                reused=True,
            )
            session.commit()
            return result
        job = SqlAlchemyJobRepository(session).add_job(candidate)
        session.commit()

    predictions = _infer_predictions(root, source)
    source_ids = _insert_sources(
        engine,
        source,
        job_id=job.id,
        created_at=now,
    )
    review_ids = _insert_boards(
        engine,
        source,
        source_ids=source_ids,
        predictions=predictions,
        created_at=now,
    )
    _resolve_complete_human_boards(
        engine,
        source,
        game_id=game_id,
        job_id=job.id,
        review_ids=review_ids,
    )
    with Session(engine) as session:
        record = session.get(JobModel, job.id)
        if record is None:
            raise RealWorkbenchFixtureError("The real-corpus import job disappeared.")
        record.status = JobStatus.WAITING_FOR_REVIEW
        record.stage = "manual_review"
        record.progress_current = 0
        record.progress_total = len(source.images)
        record.review_count = len(source.images)
        record.worker_version = REAL_WORKBENCH_VERSION
        record.updated_at = now
        result = _fixture_result(
            session,
            game_id=game_id,
            job_id=job.id,
            pipeline_fingerprint=source.pipeline_fingerprint,
            reused=False,
        )
        session.commit()
        return result


def _ensure_catalog(session: Session, class_codes: Sequence[str]) -> UUID:
    catalog = CatalogService(SqlAlchemyCatalogRepository(session))
    record = session.scalar(
        select(GameModel).where(GameModel.code == REAL_WORKBENCH_GAME_CODE)
    )
    if record is None:
        game = catalog.create_game(
            code=REAL_WORKBENCH_GAME_CODE,
            name=REAL_WORKBENCH_GAME_NAME,
            status=GameStatus.ACTIVE,
        )
    else:
        game = catalog.get_game(record.id)
        if game.status is not GameStatus.ACTIVE:
            game = catalog.update_game(game.id, status=GameStatus.ACTIVE)
    existing = tuple(catalog.list_symbols(game.id))
    if existing:
        existing_codes = tuple(item.code for item in existing)
        if existing_codes != tuple(class_codes) or any(
            item.status is not SymbolStatus.ACTIVE for item in existing
        ):
            raise RealWorkbenchFixtureError(
                "The existing game symbol catalog differs from the released model."
            )
    else:
        for index, code in enumerate(class_codes):
            catalog.create_symbol(
                game.id,
                mobile_code=index + 1,
                code=code,
                name=code.replace("-", " ").title(),
                image_path=None,
                is_wildcard=False,
                display_order=index,
                status=SymbolStatus.ACTIVE,
            )
    session.commit()
    return game.id


def _publish_assets(repository_root: Path, source: RealWorkbenchSource) -> None:
    data_root = repository_root / "artifacts" / "data"
    copies: list[tuple[Path, Path, str]] = []
    corpus_by_id = {
        _text(image.get("id"), "source image id"): image for image in source.images
    }
    for image in source.images:
        relative = _safe_relative(image.get("relativePath"), "source path")
        copies.append(
            (
                repository_root / SOURCE_ROOT_PATH / relative,
                data_root / REAL_WORKBENCH_ASSET_PREFIX / "sources" / relative,
                _sha256(image.get("sha256"), "source checksum"),
            )
        )
    for board in source.boards:
        sequence_number = _positive_int(board.get("sequenceNumber"), "sequence number")
        source_image_id = _text(board.get("sourceImageId"), "source image id")
        if source_image_id not in corpus_by_id:
            raise RealWorkbenchFixtureError("A board references an unknown source image.")
        board_relative = _safe_relative(
            board.get("boardRelativePath"), "board relative path"
        )
        copies.append(
            (
                repository_root / GEOMETRY_ASSET_ROOT_PATH / board_relative,
                data_root / REAL_WORKBENCH_ASSET_PREFIX / board_relative,
                _sha256(board.get("boardChecksumSha256"), "board checksum"),
            )
        )
        for sample in source.samples_by_sequence[sequence_number]:
            crop_relative = _safe_relative(
                sample.get("cropRelativePath"), "crop relative path"
            )
            copies.append(
                (
                    repository_root / GEOMETRY_ASSET_ROOT_PATH / crop_relative,
                    data_root / REAL_WORKBENCH_ASSET_PREFIX / crop_relative,
                    _sha256(sample.get("cropChecksumSha256"), "crop checksum"),
                )
            )
    with ThreadPoolExecutor(max_workers=16) as executor:
        tuple(executor.map(_copy_task, copies))


def _copy_task(values: tuple[Path, Path, str]) -> None:
    _copy_verified(*values)


def _infer_predictions(
    repository_root: Path,
    source: RealWorkbenchSource,
) -> Mapping[str, dict[str, object]]:
    manifest = source.release_manifest
    artifacts = cast(Mapping[str, object], manifest["artifacts"])
    onnx = cast(Mapping[str, object], artifacts["onnx"])
    adapter = LocalSymbolOnnxAdapter(
        repository_root / _safe_relative(onnx.get("relativePath"), "ONNX path"),
        expected_sha256=_sha256(onnx.get("sha256"), "ONNX checksum"),
        class_codes=source.class_codes,
        input_size=_positive_int(manifest.get("inputSize"), "model input size"),
    )
    rows = [
        sample
        for sequence_number in range(1, 388)
        for sample in source.samples_by_sequence[sequence_number]
    ]
    result: dict[str, dict[str, object]] = {}
    batch_size = 256
    for start in range(0, len(rows), batch_size):
        batch_rows = rows[start : start + batch_size]
        tensors = torch.stack(
            [
                load_image_tensor(
                    repository_root
                    / GEOMETRY_ASSET_ROOT_PATH
                    / _safe_relative(item.get("cropRelativePath"), "crop path"),
                    adapter.input_size,
                )
                for item in batch_rows
            ]
        )
        inference = adapter.infer(tensor_batch_to_numpy(tensors))
        predictions = build_symbol_predictions(
            inference.logits,
            temperature=_number(manifest.get("temperature"), "model temperature"),
            class_codes=source.class_codes,
        )
        for row, prediction in zip(batch_rows, predictions, strict=True):
            result[_sha256(row.get("sampleId"), "sample id")] = prediction.to_dict()
    return result


def _insert_sources(
    engine: Engine,
    source: RealWorkbenchSource,
    *,
    job_id: UUID,
    created_at: datetime,
) -> Mapping[str, UUID]:
    source_ids: dict[str, UUID] = {}
    executions: list[dict[str, object]] = []
    associations: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    for order_index, image in enumerate(source.images):
        source_image_id = _text(image.get("id"), "source image id")
        source_checksum = _sha256(image.get("sha256"), "source checksum")
        execution_key = file_execution_key(
            source_checksum,
            source.pipeline_fingerprint,
        )
        database_source_id = uuid5(
            REAL_WORKBENCH_NAMESPACE,
            f"{job_id}:source:{source_image_id}",
        )
        source_ids[source_image_id] = database_source_id
        relative = _safe_relative(image.get("relativePath"), "source path")
        asset_path = _asset_path("sources", relative)
        executions.append(
            {
                "file_execution_key": execution_key,
                "source_checksum_sha256": source_checksum,
                "pipeline_fingerprint": source.pipeline_fingerprint,
                "checkpoint_payload": {},
                "status": "waiting_for_review",
                "review_required": True,
                "retry_count": 0,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        associations.append(
            {
                "job_id": job_id,
                "file_execution_key": execution_key,
                "order_index": order_index,
                "source_relative_path": asset_path,
                "workflow_checkpoint_payload": {},
                "workflow_status": "waiting_for_review",
                "review_required": True,
                "retry_count": 0,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        sources.append(
            {
                "id": database_source_id,
                "import_job_id": job_id,
                "file_execution_key": execution_key,
                "relative_path": asset_path,
                "checksum_sha256": source_checksum,
                "width": _positive_int(image.get("width"), "source width"),
                "height": _positive_int(image.get("height"), "source height"),
                "status": "waiting_for_review",
                "created_at": created_at,
            }
        )
    with Session(engine) as session:
        session.execute(insert(ImageFileExecutionModel), executions)
        session.execute(insert(ImageImportJobFileModel), associations)
        session.execute(insert(SourceImageModel), sources)
        session.commit()
    return source_ids


def _insert_boards(
    engine: Engine,
    source: RealWorkbenchSource,
    *,
    source_ids: Mapping[str, UUID],
    predictions: Mapping[str, dict[str, object]],
    created_at: datetime,
) -> Mapping[int, UUID]:
    review_ids: dict[int, UUID] = {}
    batch_size = 50
    for start in range(0, len(source.boards), batch_size):
        board_rows: list[dict[str, object]] = []
        observation_rows: list[dict[str, object]] = []
        review_rows: list[dict[str, object]] = []
        for board in source.boards[start : start + batch_size]:
            sequence_number = _positive_int(
                board.get("sequenceNumber"), "sequence number"
            )
            source_image_id = _text(board.get("sourceImageId"), "source image id")
            board_id = uuid5(
                REAL_WORKBENCH_NAMESPACE,
                f"board:{source.pipeline_fingerprint}:{sequence_number}",
            )
            review_id = uuid5(
                REAL_WORKBENCH_NAMESPACE,
                f"review:{source.pipeline_fingerprint}:{sequence_number}",
            )
            review_ids[sequence_number] = review_id
            samples = source.samples_by_sequence[sequence_number]
            board_predictions = [
                predictions[_sha256(item.get("sampleId"), "sample id")]
                for item in samples
            ]
            board_relative = _safe_relative(
                board.get("boardRelativePath"), "board path"
            )
            board_rows.append(
                {
                    "id": board_id,
                    "source_image_id": source_ids[source_image_id],
                    "position_index": _index(
                        board.get("positionIndex"), 9, "board position"
                    ),
                    "sequence_number_raw": str(sequence_number),
                    "sequence_number": sequence_number,
                    "sequence_confidence": 1.0,
                    "board_geometry": {
                        "sourceQuad": _quad(
                            board.get("projectiveExpandedQuad"),
                            "projective expanded quad",
                        )
                    },
                    "board_relative_path": _asset_path("", board_relative),
                    "board_checksum_sha256": _sha256(
                        board.get("boardChecksumSha256"), "board checksum"
                    ),
                    "cells_prediction": {
                        "symbolCodes": [
                            cast(str, prediction["symbolCode"])
                            for prediction in board_predictions
                        ]
                    },
                    "board_confidence": sum(
                        _number(
                            prediction.get("confidence"),
                            "prediction confidence",
                        )
                        for prediction in board_predictions
                    )
                    / 15,
                    "pipeline_fingerprint": source.pipeline_fingerprint,
                    "geometry_revision": 0,
                    "status": "pending_review",
                    "created_at": created_at,
                }
            )
            for cell_index, (sample, prediction) in enumerate(
                zip(samples, board_predictions, strict=True)
            ):
                observation_rows.append(
                    {
                        "id": uuid5(
                            REAL_WORKBENCH_NAMESPACE,
                            (
                                f"cell:{source.pipeline_fingerprint}:"
                                f"{sequence_number}:{cell_index}"
                            ),
                        ),
                        "recognized_board_id": board_id,
                        "row_index": cell_index // 5,
                        "column_index": cell_index % 5,
                        "crop_relative_path": _asset_path(
                            "",
                            _safe_relative(
                                sample.get("cropRelativePath"), "crop path"
                            ),
                        ),
                        "crop_checksum_sha256": _sha256(
                            sample.get("cropChecksumSha256"), "crop checksum"
                        ),
                        "cropper_version": source.cropper_version,
                        "prediction": prediction,
                        "created_at": created_at,
                    }
                )
            review_rows.append(
                {
                    "id": review_id,
                    "recognized_board_id": board_id,
                    "status": "pending",
                    "snapshot": {
                        "source": "m6-symbol-review-v16",
                        "schemaVersion": 1,
                    },
                    "resolution_revision": 0,
                    "created_at": created_at,
                }
            )
        with Session(engine) as session:
            session.execute(insert(RecognizedBoardModel), board_rows)
            session.execute(insert(CellObservationModel), observation_rows)
            session.execute(insert(ImageReviewItemModel), review_rows)
            session.commit()
    return review_ids


def _resolve_complete_human_boards(
    engine: Engine,
    source: RealWorkbenchSource,
    *,
    game_id: UUID,
    job_id: UUID,
    review_ids: Mapping[int, UUID],
) -> None:
    complete = {
        sequence_number: values
        for sequence_number, values in source.labels_by_sequence.items()
        if len(values) == 15
    }
    with Session(engine) as session:
        service = OperationalImageReviewService(
            SqlAlchemyOperationalImageReviewRepository(session)
        )
        for sequence_number in sorted(complete):
            item = service.get_item(
                review_ids[sequence_number],
                game_id=game_id,
                import_job_id=job_id,
            )
            labels = complete[sequence_number]
            cells = tuple(
                ImageReviewResolutionCell(
                    cell_index=cell.cell_index,
                    crop_sample_id=cell.crop_sample_id,
                    symbol_code=labels[cell.cell_index],
                )
                for cell in item.cells
            )
            action = (
                ImageReviewAction.ACCEPTED
                if all(
                    labels[cell.cell_index] == cell.predicted_symbol_code
                    for cell in item.cells
                )
                else ImageReviewAction.CORRECTED
            )
            service.resolve_item(
                item.id,
                game_id=game_id,
                import_job_id=job_id,
                idempotency_key=uuid5(
                    REAL_WORKBENCH_NAMESPACE,
                    f"reviewed-labels:{source.pipeline_fingerprint}:{sequence_number}",
                ),
                expected_revision=0,
                action=action,
                sequence_number=sequence_number,
                geometry_revision=0,
                cells=cells,
                rejection_reason=None,
                resolved_by="import:m6-symbol-review-v16",
            )
        session.commit()


def _fixture_result(
    session: Session,
    *,
    game_id: UUID,
    job_id: UUID,
    pipeline_fingerprint: str,
    reused: bool,
) -> RealWorkbenchFixtureResult:
    rows = session.execute(
        select(ImageReviewItemModel.status, func.count())
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(
            SourceImageModel,
            SourceImageModel.id == RecognizedBoardModel.source_image_id,
        )
        .where(SourceImageModel.import_job_id == job_id)
        .group_by(ImageReviewItemModel.status)
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    total = sum(counts.values())
    if total != 387:
        raise RealWorkbenchFixtureError(
            "The existing real-corpus workbench import is incomplete."
        )
    completed = counts.get("accepted", 0) + counts.get("corrected", 0)
    return RealWorkbenchFixtureResult(
        game_id=game_id,
        import_job_id=job_id,
        board_count=total,
        pending_count=counts.get("pending", 0),
        completed_count=completed,
        reused=reused,
        pipeline_fingerprint=pipeline_fingerprint,
    )


def _copy_verified(source: Path, target: Path, expected_sha256: str) -> None:
    if _file_sha256(source) != expected_sha256:
        raise RealWorkbenchFixtureError(f"Source artifact checksum drift: {source}.")
    if target.exists():
        if _file_sha256(target) != expected_sha256:
            raise RealWorkbenchFixtureError(
                f"Managed workbench asset checksum drift: {target}."
            )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        if _file_sha256(temporary) != expected_sha256:
            raise RealWorkbenchFixtureError(
                f"Copied workbench asset checksum mismatch: {target}."
            )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _asset_path(prefix: str, relative: PurePosixPath) -> str:
    parts = [REAL_WORKBENCH_ASSET_PREFIX]
    if prefix:
        parts.append(prefix)
    parts.extend(relative.parts)
    return PurePosixPath(*parts).as_posix()


def _read_mapping(path: Path, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise RealWorkbenchFixtureError(f"Cannot read {label}.") from error
    if not isinstance(value, Mapping):
        raise RealWorkbenchFixtureError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _mapping_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    rows = _sequence(value)
    if not all(isinstance(row, Mapping) for row in rows):
        raise RealWorkbenchFixtureError(f"{label} must contain only objects.")
    return tuple(cast(Mapping[str, object], row) for row in rows)


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise RealWorkbenchFixtureError("Expected an array in a fixture contract.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RealWorkbenchFixtureError(f"{label} must be non-empty text.")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64:
        raise RealWorkbenchFixtureError(f"{label} must be a SHA-256 value.")
    try:
        int(text, 16)
    except ValueError as error:
        raise RealWorkbenchFixtureError(f"{label} must be a SHA-256 value.") from error
    return text


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RealWorkbenchFixtureError(f"{label} must be a positive integer.")
    return value


def _number(value: object, label: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or float(value) < 0
    ):
        raise RealWorkbenchFixtureError(f"{label} must be a non-negative number.")
    return float(value)


def _index(value: object, upper_bound: int, label: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value >= upper_bound
    ):
        raise RealWorkbenchFixtureError(f"{label} is outside its allowed range.")
    return value


def _safe_relative(value: object, label: str) -> PurePosixPath:
    path = PurePosixPath(_text(value, label))
    if path.is_absolute() or ".." in path.parts or "\\" in path.as_posix():
        raise RealWorkbenchFixtureError(f"{label} must be a safe relative POSIX path.")
    return path


def _quad(value: object, label: str) -> list[dict[str, float]]:
    rows = _mapping_rows(value, label)
    if len(rows) != 4:
        raise RealWorkbenchFixtureError(f"{label} must contain exactly four points.")
    result: list[dict[str, float]] = []
    for row in rows:
        x = row.get("x")
        y = row.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise RealWorkbenchFixtureError(f"{label} contains an invalid point.")
        result.append({"x": float(x), "y": float(y)})
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RealWorkbenchFixtureError(f"Cannot read required artifact {path}.") from error
    return digest.hexdigest()


__all__ = [
    "REAL_WORKBENCH_GAME_CODE",
    "REAL_WORKBENCH_VERSION",
    "RealWorkbenchFixtureError",
    "RealWorkbenchFixtureResult",
    "RealWorkbenchSource",
    "load_real_workbench_source",
    "prepare_real_workbench_fixture",
]
