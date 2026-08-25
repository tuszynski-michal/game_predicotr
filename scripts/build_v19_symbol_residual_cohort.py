"""Freeze an immutable cohort of human-resolved, fail-closed v19 symbol crops."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModelIterationModel,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryEntry,
    canonical_json_bytes,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceDirectCropper,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    estimate_board_cell_geometry,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.v19_symbol_residuals import (
    ResidualBoard,
    ResidualCell,
    V19SymbolResidualError,
    build_cohort_document,
    document_checksum_sha256,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, select

DESCRIPTOR_VERSION = "v19-symbol-residual-cohort-descriptor-v1"
SCRIPT_VERSION = "build-v19-symbol-residual-cohort-v1"
DEFAULT_DESCRIPTOR = Path("ai_docs/quality/v19-symbol-residual-cohort.json")
DEFAULT_OUTPUT_ROOT = Path("artifacts/quality/v19-symbol-residuals")


@dataclass(frozen=True, slots=True)
class _Descriptor:
    game_id: UUID
    minimum_board_count: int
    staging_labels: tuple[str, ...]
    split_seed: str
    expected_model_fingerprint: str
    expected_training_dataset_checksum: str
    expected_cohort_checksum: str | None
    audited_label_conflicts: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _CropAsset:
    cell_index: int
    symbol_code: str
    content: bytes
    checksum_sha256: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    session = None
    try:
        descriptor = _load_descriptor(arguments.descriptor)
        settings = get_settings()
        session = create_session_factory(create_database_engine(settings))()
        snapshot = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=descriptor.game_id)
        if snapshot.inference_fingerprint != descriptor.expected_model_fingerprint:
            raise _error(
                "V19_SYMBOL_COHORT_MODEL_DRIFT",
                "The active symbol model differs from the pinned descriptor.",
            )
        training_dataset = _training_dataset_summary(
            session,
            iteration_id=snapshot.iteration_id,
            artifact_root=settings.artifact_root,
            expected_checksum=descriptor.expected_training_dataset_checksum,
        )
        boards, excluded = _collect_boards(
            session,
            descriptor=descriptor,
            artifact_root=settings.artifact_root,
            output_root=arguments.output_root,
            input_size=snapshot.input_size,
            check=arguments.check,
        )
        model = {
            "classCodes": list(snapshot.class_codes),
            "inferenceFingerprintSha256": snapshot.inference_fingerprint,
            "inputSize": snapshot.input_size,
            "iterationId": None if snapshot.iteration_id is None else str(snapshot.iteration_id),
            "manifestChecksumSha256": snapshot.manifest_checksum_sha256,
            "modelVersion": snapshot.model_version,
            "onnxChecksumSha256": snapshot.onnx_checksum_sha256,
            "temperatureApplied": max(0.50, snapshot.temperature),
        }
        document = build_cohort_document(
            boards,
            game_id=str(descriptor.game_id),
            required_stagings=descriptor.staging_labels,
            model=model,
            training_dataset=training_dataset,
            excluded_counts=excluded,
            audited_label_conflicts=descriptor.audited_label_conflicts,
            split_seed=descriptor.split_seed,
            minimum_board_count=descriptor.minimum_board_count,
        )
        document["scriptVersion"] = SCRIPT_VERSION
        checksum = document_checksum_sha256(document)
        content = canonical_json_bytes(document)
        destination = arguments.output_root / "cohorts" / f"{checksum}.json"
        if arguments.check:
            if descriptor.expected_cohort_checksum != checksum:
                raise _error(
                    "V19_SYMBOL_COHORT_CHECKSUM_DRIFT",
                    "The rebuilt cohort differs from the pinned descriptor.",
                )
            _verify_immutable(destination, content)
        else:
            _write_immutable(destination, content)
        print(
            json.dumps(
                {
                    "boardCount": cast(Mapping[str, object], document["scope"])[
                        "boardCount"
                    ],
                    "check": arguments.check,
                    "checksumSha256": checksum,
                    "excludedCounts": dict(sorted(excluded.items())),
                    "path": destination.as_posix(),
                    "stagingLabels": list(descriptor.staging_labels),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (V19SymbolResidualError, OSError, UnidentifiedImageError, ValueError) as error:
        code = getattr(error, "code", "V19_SYMBOL_COHORT_BUILD_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _collect_boards(
    session: Any,
    *,
    descriptor: _Descriptor,
    artifact_root: Path,
    output_root: Path,
    input_size: int,
    check: bool,
) -> tuple[tuple[ResidualBoard, ...], Counter[str]]:
    rows = session.execute(
        select(
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            JobModel,
            ImageBoardGeometryRevisionModel,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .outerjoin(
            ImageBoardGeometryRevisionModel,
            and_(
                ImageBoardGeometryRevisionModel.recognized_board_id == RecognizedBoardModel.id,
                ImageBoardGeometryRevisionModel.revision
                == RecognizedBoardModel.geometry_revision,
            ),
        )
        .where(
            ImageReviewItemModel.status.in_(("accepted", "corrected")),
            JobModel.game_id == descriptor.game_id,
        )
        .order_by(RecognizedBoardModel.sequence_number, RecognizedBoardModel.id)
    ).all()
    excluded: Counter[str] = Counter()
    source_cache: dict[str, np.ndarray] = {}
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=input_size)
    included: list[ResidualBoard] = []
    seen_sequences: set[int] = set()
    audited_by_sequence = {
        cast(int, row["sequenceNumber"]): row for row in descriptor.audited_label_conflicts
    }
    observed_audited_sequences: set[int] = set()
    for item, board, source, job, revision in rows:
        staging = _staging_label(job)
        if staging not in descriptor.staging_labels:
            excluded["outside_pinned_staging_scope"] += 1
            continue
        if board.sequence_number is None or board.sequence_number in seen_sequences:
            excluded["sequence_unresolved_or_duplicate"] += 1
            continue
        seen_sequences.add(board.sequence_number)
        expected = _expected_symbols(item.resolved_value)
        if expected is None:
            excluded["resolved_labels_invalid"] += 1
            continue
        try:
            rgb = source_cache.get(source.checksum_sha256)
            if rgb is None:
                rgb = _load_source(artifact_root, source)
                source_cache[source.checksum_sha256] = rgb
            assets, provenance = _v19_assets(
                revision,
                board=board,
                source=source,
                job=job,
                expected=expected,
                rgb=rgb,
                artifact_root=artifact_root,
                cropper=cropper,
            )
            audited = audited_by_sequence.get(board.sequence_number)
            if audited is not None:
                evidence = set(
                    cast(Sequence[str], audited["evidenceCropChecksumsSha256"])
                )
                if not evidence.issubset({asset.checksum_sha256 for asset in assets}):
                    raise _error(
                        "V19_SYMBOL_COHORT_AUDIT_EVIDENCE_DRIFT",
                        "Audited label-conflict evidence no longer matches the v19 board crops.",
                    )
                excluded["audited_label_conflict"] += 1
                observed_audited_sequences.add(board.sequence_number)
                continue
            cells = tuple(
                _materialize_cell(
                    asset,
                    output_root=output_root,
                    check=check,
                )
                for asset in assets
            )
        except V19SymbolResidualError as error:
            excluded[error.code.lower()] += 1
            continue
        included.append(
            ResidualBoard(
                board_id=str(board.id),
                review_item_id=str(item.id),
                import_job_id=str(job.id),
                decision_status=cast(Literal["accepted", "corrected"], item.status),
                resolution_revision=item.resolution_revision,
                sequence_number=board.sequence_number,
                position_index=board.position_index,
                staging_label=staging,
                source_image_id=str(source.id),
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                geometry_provenance=provenance,
                cells=cells,
            )
        )
    missing_audits = set(audited_by_sequence) - observed_audited_sequences
    if missing_audits:
        raise _error(
            "V19_SYMBOL_COHORT_AUDIT_SOURCE_MISSING",
            "An audited label-conflict board is no longer available in the pinned scope.",
        )
    return tuple(included), excluded


def _v19_assets(
    revision: ImageBoardGeometryRevisionModel | None,
    *,
    board: RecognizedBoardModel,
    source: SourceImageModel,
    job: JobModel,
    expected: tuple[str, ...],
    rgb: np.ndarray,
    artifact_root: Path,
    cropper: BoardCellGeometrySourceDirectCropper,
) -> tuple[tuple[_CropAsset, ...], Literal["persisted_v19", "read_only_estimated_v19"]]:
    sequence_number = board.sequence_number
    if sequence_number is None:
        raise _error(
            "V19_SYMBOL_COHORT_SEQUENCE_UNRESOLVED",
            "A verified board does not have a sequence number.",
        )
    if (
        revision is not None
        and revision.cropper_version == CROPPER_VERSION
        and revision.geometry.get("geometryVersion") == BOARD_CELL_GEOMETRY_VERSION
        and _trusted_persisted_geometry(revision)
    ):
        return (
            _persisted_assets(
                revision.crop_artifacts,
                expected=expected,
                artifact_root=artifact_root,
            ),
            "persisted_v19",
        )
    quad = _board_quad(board.board_geometry)
    estimate = estimate_board_cell_geometry(rgb, quad)
    if (
        estimate.status != "estimated"
        or estimate.lattice_bounds_quad is None
        or estimate.evidence is None
        or len(estimate.cells) != 15
    ):
        raise _error(
            "V19_SYMBOL_COHORT_GEOMETRY_UNCERTAIN",
            estimate.fallback_reason or "Automatic v19 geometry is incomplete.",
        )
    entry = BoardCellGeometryEntry(
        source_order_index=sequence_number - board.position_index,
        image_id=str(source.id),
        source_image_checksum_sha256=source.checksum_sha256,
        source_image_relative_path=source.relative_path,
        source_image_width=source.width,
        source_image_height=source.height,
        source_group=str(job.id),
        condition_tags=("residual-cohort-read-only",),
        sequence_number=sequence_number,
        position_index=board.position_index,
        lattice_bounds_quad=estimate.lattice_bounds_quad,
        cells=estimate.cells,
        evidence=estimate.evidence,
    )
    result = cropper.crop(rgb, entry)
    if result.status != "cropped" or len(result.cells) != 15:
        raise _error(
            "V19_SYMBOL_COHORT_CROP_UNCERTAIN",
            result.review_reasons[0] if result.review_reasons else "v19 crop is incomplete.",
        )
    assets = []
    for index, cell in enumerate(result.cells):
        content = _png_bytes(cell.rgb)
        assets.append(
            _CropAsset(
                cell_index=index,
                symbol_code=expected[index],
                content=content,
                checksum_sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return tuple(assets), "read_only_estimated_v19"


def _trusted_persisted_geometry(revision: ImageBoardGeometryRevisionModel) -> bool:
    raw_cells = revision.geometry.get("cells")
    if not isinstance(raw_cells, Sequence) or isinstance(raw_cells, str | bytes):
        return False
    positions = [
        (cell.get("rowIndex"), cell.get("columnIndex"))
        for cell in raw_cells
        if isinstance(cell, Mapping)
    ]
    if positions != [(row, column) for row in range(3) for column in range(5)]:
        return False
    if revision.corrected_by == "local-admin":
        return True
    evidence = revision.geometry.get("evidence")
    return isinstance(evidence, Mapping) and evidence.get("kind") == "automatic"


def _persisted_assets(
    artifacts: Sequence[Mapping[str, object]],
    *,
    expected: tuple[str, ...],
    artifact_root: Path,
) -> tuple[_CropAsset, ...]:
    ordered = sorted(artifacts, key=lambda row: (row.get("rowIndex"), row.get("columnIndex")))
    if len(ordered) != 15 or [
        (row.get("rowIndex"), row.get("columnIndex")) for row in ordered
    ] != [(row, column) for row in range(3) for column in range(5)]:
        raise _error(
            "V19_SYMBOL_COHORT_PERSISTED_CROPS_INVALID",
            "Persisted v19 crops are not a complete row-major board.",
        )
    assets: list[_CropAsset] = []
    for index, artifact in enumerate(ordered):
        relative = artifact.get("cropRelativePath")
        checksum = artifact.get("cropChecksumSha256")
        if not isinstance(relative, str) or not isinstance(checksum, str):
            raise _error(
                "V19_SYMBOL_COHORT_PERSISTED_CROPS_INVALID", "A persisted crop is incomplete."
            )
        path = _managed_path(artifact_root / "data", relative)
        try:
            content = path.read_bytes()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                image.convert("RGB")
        except (OSError, UnidentifiedImageError) as error:
            raise _error(
                "V19_SYMBOL_COHORT_CROP_UNAVAILABLE", "A persisted v19 crop is unavailable."
            ) from error
        if hashlib.sha256(content).hexdigest() != checksum:
            raise _error("V19_SYMBOL_COHORT_CROP_DRIFT", "A persisted crop checksum differs.")
        assets.append(_CropAsset(index, expected[index], content, checksum))
    return tuple(assets)


def _materialize_cell(
    asset: _CropAsset,
    *,
    output_root: Path,
    check: bool,
) -> ResidualCell:
    relative = PurePosixPath(
        "crops", asset.checksum_sha256[:2], f"{asset.checksum_sha256}.png"
    )
    destination = output_root.joinpath(*relative.parts)
    if check:
        _verify_immutable(destination, asset.content)
    else:
        _write_immutable(destination, asset.content)
    return ResidualCell(
        cell_index=asset.cell_index,
        symbol_code=asset.symbol_code,
        crop_checksum_sha256=asset.checksum_sha256,
        crop_relative_path=relative.as_posix(),
    )


def _training_dataset_summary(
    session: Any,
    *,
    iteration_id: UUID | None,
    artifact_root: Path,
    expected_checksum: str,
) -> dict[str, object]:
    if iteration_id is None:
        raise _error("V19_SYMBOL_COHORT_TRAINING_DATASET_MISSING", "Active iteration is missing.")
    iteration = session.get(SymbolModelIterationModel, iteration_id)
    if (
        iteration is None
        or iteration.dataset_manifest_checksum_sha256 != expected_checksum
        or iteration.dataset_manifest_relative_path is None
    ):
        raise _error(
            "V19_SYMBOL_COHORT_TRAINING_DATASET_DRIFT",
            "The active model training dataset differs from the descriptor.",
        )
    path = _managed_path(artifact_root / "data", iteration.dataset_manifest_relative_path)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise _error(
            "V19_SYMBOL_COHORT_TRAINING_DATASET_DRIFT", "Training dataset checksum differs."
        )
    payload = json.loads(content)
    if not isinstance(payload, Mapping):
        raise _error(
            "V19_SYMBOL_COHORT_TRAINING_DATASET_INVALID", "Training dataset is invalid."
        )
    raw_samples = payload.get("samples")
    raw_symbols = payload.get("symbols")
    if (
        not isinstance(raw_samples, Sequence)
        or isinstance(raw_samples, str | bytes)
        or not isinstance(raw_symbols, Sequence)
        or isinstance(raw_symbols, str | bytes)
    ):
        raise _error(
            "V19_SYMBOL_COHORT_TRAINING_DATASET_INVALID", "Training dataset is incomplete."
        )
    source_families = sorted(
        {
            str(sample["sourceFamily"])
            for sample in raw_samples
            if isinstance(sample, Mapping) and isinstance(sample.get("sourceFamily"), str)
        }
    )
    symbols = [
        {
            "sampleCount": row.get("sampleCount"),
            "sourceFamilyCount": row.get("sourceFamilyCount"),
            "symbolCode": row.get("symbolCode"),
        }
        for row in raw_symbols
        if isinstance(row, Mapping)
    ]
    return {
        "datasetVersion": payload.get("datasetVersion"),
        "manifestChecksumSha256": expected_checksum,
        "sourceFamilies": source_families,
        "sourceFamilyCount": len(source_families),
        "symbols": symbols,
    }


def _load_source(artifact_root: Path, source: SourceImageModel) -> np.ndarray:
    path = _managed_path(artifact_root / "data", source.relative_path)
    try:
        content = path.read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise _error(
            "V19_SYMBOL_COHORT_SOURCE_UNAVAILABLE", "A source image is unavailable."
        ) from error
    if hashlib.sha256(content).hexdigest() != source.checksum_sha256:
        raise _error("V19_SYMBOL_COHORT_SOURCE_DRIFT", "A source image checksum differs.")
    if rgb.shape[:2] != (source.height, source.width):
        raise _error("V19_SYMBOL_COHORT_SOURCE_DIMENSIONS", "Source dimensions differ.")
    return cast(np.ndarray[Any, np.dtype[np.uint8]], rgb)


def _board_quad(value: object) -> tuple[Point, Point, Point, Point]:
    if not isinstance(value, Mapping):
        raise _error("V19_SYMBOL_COHORT_PAGE_QUAD_INVALID", "Board geometry is invalid.")
    raw = value.get("pageBoardQuad") or value.get("quad") or value.get("sourceQuad")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or len(raw) != 4:
        raise _error("V19_SYMBOL_COHORT_PAGE_QUAD_INVALID", "Board quad is missing.")
    points: list[Point] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise _error("V19_SYMBOL_COHORT_PAGE_QUAD_INVALID", "Board quad is invalid.")
        x = item.get("x")
        y = item.get("y")
        if (
            isinstance(x, bool)
            or not isinstance(x, int | float)
            or isinstance(y, bool)
            or not isinstance(y, int | float)
        ):
            raise _error("V19_SYMBOL_COHORT_PAGE_QUAD_INVALID", "Board point is invalid.")
        points.append(Point(round(float(x)), round(float(y))))
    return cast(tuple[Point, Point, Point, Point], tuple(points))


def _expected_symbols(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("cells")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or len(raw) != 15:
        return None
    indexed: dict[int, str] = {}
    for cell in raw:
        if not isinstance(cell, Mapping):
            return None
        index = cell.get("cellIndex")
        symbol = cell.get("symbolCode")
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(symbol, str):
            return None
        indexed[index] = symbol
    return tuple(indexed[index] for index in range(15)) if set(indexed) == set(range(15)) else None


def _load_descriptor(path: Path) -> _Descriptor:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping) or payload.get("version") != DESCRIPTOR_VERSION:
        raise _error("V19_SYMBOL_COHORT_DESCRIPTOR_INVALID", "Descriptor version is invalid.")
    labels = payload.get("stagingLabels")
    if (
        not isinstance(labels, Sequence)
        or isinstance(labels, str | bytes)
        or len(labels) != 6
        or any(not isinstance(label, str) or not label for label in labels)
    ):
        raise _error("V19_SYMBOL_COHORT_DESCRIPTOR_INVALID", "Staging scope is invalid.")
    minimum = payload.get("minimumBoardCount")
    split_seed = payload.get("splitSeed")
    if not isinstance(minimum, int) or minimum < 300 or not isinstance(split_seed, str):
        raise _error("V19_SYMBOL_COHORT_DESCRIPTOR_INVALID", "Descriptor scope is invalid.")
    expected = payload.get("expectedCohortChecksumSha256")
    audited = _audited_label_conflicts(payload.get("auditedLabelConflicts"))
    return _Descriptor(
        game_id=UUID(str(payload.get("gameId"))),
        minimum_board_count=minimum,
        staging_labels=cast(tuple[str, ...], tuple(labels)),
        split_seed=split_seed,
        expected_model_fingerprint=_sha256(payload.get("expectedActiveModelFingerprintSha256")),
        expected_training_dataset_checksum=_sha256(
            payload.get("expectedTrainingDatasetChecksumSha256")
        ),
        expected_cohort_checksum=None if expected is None else _sha256(expected),
        audited_label_conflicts=audited,
    )


def _audited_label_conflicts(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise _error(
            "V19_SYMBOL_COHORT_DESCRIPTOR_INVALID",
            "Audited label conflicts must be a list.",
        )
    rows: list[dict[str, object]] = []
    seen_sequences: set[int] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise _error(
                "V19_SYMBOL_COHORT_DESCRIPTOR_INVALID",
                "An audited label conflict is invalid.",
            )
        sequence_number = raw.get("sequenceNumber")
        reason = raw.get("reason")
        evidence = raw.get("evidenceCropChecksumsSha256")
        if (
            isinstance(sequence_number, bool)
            or not isinstance(sequence_number, int)
            or sequence_number < 1
            or sequence_number in seen_sequences
            or reason != "visual_label_or_slot_conflict"
            or not isinstance(evidence, Sequence)
            or isinstance(evidence, str | bytes)
            or not evidence
        ):
            raise _error(
                "V19_SYMBOL_COHORT_DESCRIPTOR_INVALID",
                "An audited label conflict is incomplete or duplicated.",
            )
        checksums = tuple(sorted({_sha256(checksum) for checksum in evidence}))
        rows.append(
            {
                "evidenceCropChecksumsSha256": list(checksums),
                "reason": reason,
                "sequenceNumber": sequence_number,
            }
        )
        seen_sequences.add(sequence_number)
    return tuple(sorted(rows, key=lambda row: cast(int, row["sequenceNumber"])))


def _managed_path(root: Path, relative_value: str) -> Path:
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise _error("V19_SYMBOL_COHORT_PATH_UNSAFE", "A managed path is unsafe.")
    resolved_root = root.resolve()
    path = resolved_root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(resolved_root):
        raise _error("V19_SYMBOL_COHORT_PATH_UNSAFE", "A managed path escapes storage.")
    return path


def _staging_label(job: JobModel) -> str:
    value = job.input_payload.get("source_display_name")
    return value if isinstance(value, str) and value else str(job.id)


def _png_bytes(rgb: np.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(output, format="PNG", optimize=False, compress_level=6)
    return output.getvalue()


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _verify_immutable(path, content)
        return
    descriptor, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _verify_immutable(path, content)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_immutable(path: Path, content: bytes) -> None:
    try:
        actual = path.read_bytes()
    except OSError as error:
        raise _error("V19_SYMBOL_COHORT_ARTIFACT_MISSING", f"Missing {path.as_posix()}.") from error
    if actual != content:
        raise _error("V19_SYMBOL_COHORT_ARTIFACT_DRIFT", f"Artifact differs: {path.as_posix()}.")


def _sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise _error("V19_SYMBOL_COHORT_DESCRIPTOR_INVALID", "A descriptor checksum is invalid.")
    return value


def _error(code: str, message: str) -> V19SymbolResidualError:
    return V19SymbolResidualError(code, message)


if __name__ == "__main__":
    raise SystemExit(main())
