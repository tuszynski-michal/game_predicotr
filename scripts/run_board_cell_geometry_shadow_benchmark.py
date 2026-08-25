"""Run the immutable 300-page, six-staging automatic v19 shadow benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.images.board_cell_geometry_audit import (
    BoardCellGeometryAuditError,
    RegisteredPage,
    load_page_geometry_manifest,
    registered_pages,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BoardCellGeometryEntry,
    BoardCellQuad,
    canonical_json_bytes,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    BoardCellGeometrySourceDirectCropper,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    estimate_board_cell_geometry,
)
from game_predictor_worker.images.board_cell_geometry_shadow_benchmark import (
    DEFAULT_SAMPLE_SEED,
    EXPECTED_PAGES_PER_STAGING,
    EXPECTED_STAGING_COUNT,
    SHADOW_MANIFEST_VERSION,
    BoardCellGeometryShadowError,
    ShadowChallengeBoard,
    ShadowStagingSpec,
    cell_geometry_error,
    render_content_addressed_shadow_gallery,
    run_board_cell_geometry_shadow_benchmark,
    write_content_addressed_run_report,
    write_content_addressed_shadow_manifest,
)
from game_predictor_worker.images.grid_symbol_diagnosis import (
    CellPrediction,
    GridSymbolDiagnosisError,
    production_preprocess_rgb,
)
from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

DESCRIPTOR_VERSION = "board-cell-geometry-v19-shadow-benchmark-descriptor-v1"
SCRIPT_VERSION = "run-board-cell-geometry-shadow-benchmark-v1"
MANUAL_V19_CROPPER = "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
DEFAULT_DESCRIPTOR = Path("ai_docs/quality/board-cell-geometry-v19-shadow-benchmark.json")
DEFAULT_OUTPUT_ROOT = Path("artifacts/quality/board-cell-geometry-v19-shadow-benchmark")
_SHA256 = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class _Descriptor:
    game_id: UUID
    corrected_by: str
    expected_model_fingerprint: str
    task_one_report_checksum: str
    pages_per_staging: int
    sample_seed: str
    stagings: tuple[tuple[str, str], ...]
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class _PreparedChallenge:
    board_id: str
    staging_label: str
    sequence_number: int
    position_index: int
    source_checksum_sha256: str
    source_relative_path: str
    page_quad: tuple[tuple[float, float], ...]
    manual_cells: tuple[BoardCellQuad, ...]
    expected_symbols: tuple[str, ...]
    automatic_cells: tuple[BoardCellQuad, ...]
    tensors: tuple[np.ndarray, ...]
    fallback_reason: str | None
    residual: float | None
    mean_error: float | None
    max_error: float | None
    catastrophic_shift: bool
    source_rgb: np.ndarray


@dataclass(frozen=True, slots=True)
class _AttestedChallengeBoard:
    board_id: UUID
    staging_label: str
    sequence_number: int
    position_index: int
    source_checksum_sha256: str
    source_relative_path: str
    expected_symbols: tuple[str, ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    session = None
    try:
        # OpenCV may otherwise select a different parallel reduction order in
        # separate Windows processes. The shadow manifest is content-addressed,
        # so the read-only benchmark deliberately uses one deterministic lane.
        cv2.setNumThreads(1)
        cv2.setRNGSeed(0)
        descriptor = _load_descriptor(arguments.descriptor)
        attested_challenge = _load_task_one_challenge(descriptor.task_one_report_checksum)
        settings = get_settings()
        session = create_session_factory(create_database_engine(settings))()
        snapshot = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=descriptor.game_id)
        if snapshot.inference_fingerprint != descriptor.expected_model_fingerprint:
            raise _error(
                "BOARD_CELL_SHADOW_MODEL_DRIFT",
                "The active symbol model differs from the pinned TASK 2 descriptor.",
            )
        adapter = _load_adapter(snapshot, settings.artifact_root)
        staging_specs, page_index = _staging_inputs(descriptor)
        challenge, challenge_images, excluded = _collect_challenge_boards(
            session,
            game_id=descriptor.game_id,
            corrected_by=descriptor.corrected_by,
            page_index=page_index,
            attested_challenge=attested_challenge,
            adapter=adapter,
            artifact_root=settings.artifact_root,
            temperature=max(0.50, snapshot.temperature),
        )
        benchmark = run_board_cell_geometry_shadow_benchmark(
            staging_specs=staging_specs,
            source_root=arguments.source_root,
            challenge_boards=challenge,
            challenge_source_images=challenge_images,
            pages_per_staging=descriptor.pages_per_staging,
            sample_seed=descriptor.sample_seed,
            expected_staging_count=EXPECTED_STAGING_COUNT,
            cell_output_size=snapshot.input_size,
        )
        benchmark.document["challengeExcludedCounts"] = dict(sorted(excluded.items()))
        benchmark.document["descriptorChecksumSha256"] = descriptor.checksum_sha256
        benchmark.document["model"] = {
            "classCodes": list(snapshot.class_codes),
            "inferenceFingerprintSha256": snapshot.inference_fingerprint,
            "inputSize": snapshot.input_size,
            "iterationId": None if snapshot.iteration_id is None else str(snapshot.iteration_id),
            "manifestChecksumSha256": snapshot.manifest_checksum_sha256,
            "modelVersion": snapshot.model_version,
            "onnxChecksumSha256": snapshot.onnx_checksum_sha256,
            "temperatureApplied": max(0.50, snapshot.temperature),
        }
        benchmark.document["scriptVersion"] = SCRIPT_VERSION
        benchmark.document["taskOneDiagnosticChecksumSha256"] = descriptor.task_one_report_checksum
        _validate_acceptance_shape(benchmark.document)
        expected_manifest = (
            arguments.output_root / "manifests" / (f"{benchmark.checksum_sha256}.json")
        )
        if arguments.check:
            if (
                not expected_manifest.is_file()
                or expected_manifest.read_bytes() != canonical_json_bytes(benchmark.document)
            ):
                raise _error(
                    "BOARD_CELL_SHADOW_REPORT_MISSING",
                    "The expected immutable TASK 2 shadow manifest is missing or differs.",
                )
            gallery_path = _find_gallery_index(
                arguments.output_root / "galleries" / "indexes",
                shadow_manifest_checksum=benchmark.checksum_sha256,
            )
            if gallery_path is None:
                raise _error(
                    "BOARD_CELL_SHADOW_GALLERY_MISSING",
                    "The complete content-addressed shadow gallery is missing.",
                )
            manifest_path = expected_manifest
            run_report_path = None
        else:
            manifest_path = write_content_addressed_shadow_manifest(
                benchmark, arguments.output_root
            )
            run_report_path = write_content_addressed_run_report(benchmark, arguments.output_root)
            gallery_path = render_content_addressed_shadow_gallery(benchmark, arguments.output_root)
        summary = cast(Mapping[str, object], benchmark.document["summary"])
        print(
            json.dumps(
                {
                    "challengeExcludedCounts": dict(sorted(excluded.items())),
                    "check": arguments.check,
                    "galleryPath": gallery_path.as_posix(),
                    "manifestChecksumSha256": benchmark.checksum_sha256,
                    "manifestPath": manifest_path.as_posix(),
                    "runReportPath": (
                        None if run_report_path is None else run_report_path.as_posix()
                    ),
                    "summary": summary,
                    "timing": benchmark.timing_report,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        BoardCellGeometryShadowError,
        BoardCellGeometryAuditError,
        GridSymbolDiagnosisError,
        SymbolOnnxError,
        ValueError,
    ) as error:
        code = getattr(error, "code", "BOARD_CELL_SHADOW_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _load_descriptor(path: Path) -> _Descriptor:
    try:
        content = path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error(
            "BOARD_CELL_SHADOW_DESCRIPTOR_UNREADABLE", "Descriptor is unreadable."
        ) from error
    if not isinstance(payload, Mapping) or payload.get("version") != DESCRIPTOR_VERSION:
        raise _error("BOARD_CELL_SHADOW_DESCRIPTOR_INVALID", "Descriptor version is invalid.")
    raw_stagings = payload.get("stagingManifests")
    if not isinstance(raw_stagings, Sequence) or isinstance(raw_stagings, str | bytes):
        raise _error("BOARD_CELL_SHADOW_DESCRIPTOR_INVALID", "Staging manifests are missing.")
    stagings: list[tuple[str, str]] = []
    for raw in raw_stagings:
        if not isinstance(raw, Mapping):
            raise _error("BOARD_CELL_SHADOW_DESCRIPTOR_INVALID", "A staging entry is invalid.")
        label = raw.get("label")
        checksum = raw.get("pageGeometryManifestChecksumSha256")
        if not isinstance(label, str) or not label or not isinstance(checksum, str):
            raise _error("BOARD_CELL_SHADOW_DESCRIPTOR_INVALID", "A staging entry is incomplete.")
        stagings.append((label, _require_sha256(checksum, "page manifest")))
    if len(stagings) != EXPECTED_STAGING_COUNT:
        raise _error(
            "BOARD_CELL_SHADOW_DESCRIPTOR_INVALID",
            f"Descriptor must pin exactly {EXPECTED_STAGING_COUNT} staging manifests.",
        )
    pages_per_staging = payload.get("pagesPerStaging")
    sample_seed = payload.get("sampleSeed")
    corrected_by = payload.get("challengeCorrectedBy")
    game_id = payload.get("gameId")
    model_fingerprint = payload.get("expectedActiveModelFingerprintSha256")
    task_one_checksum = payload.get("taskOneDiagnosticChecksumSha256")
    if (
        pages_per_staging != EXPECTED_PAGES_PER_STAGING
        or not isinstance(sample_seed, str)
        or sample_seed != DEFAULT_SAMPLE_SEED
        or not isinstance(corrected_by, str)
        or not corrected_by
        or not isinstance(game_id, str)
        or not isinstance(model_fingerprint, str)
        or not isinstance(task_one_checksum, str)
    ):
        raise _error("BOARD_CELL_SHADOW_DESCRIPTOR_INVALID", "Descriptor scope is invalid.")
    return _Descriptor(
        game_id=UUID(game_id),
        corrected_by=corrected_by,
        expected_model_fingerprint=_require_sha256(model_fingerprint, "model fingerprint"),
        task_one_report_checksum=_require_sha256(task_one_checksum, "TASK 1 report"),
        pages_per_staging=pages_per_staging,
        sample_seed=sample_seed,
        stagings=tuple(stagings),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


def _staging_inputs(
    descriptor: _Descriptor,
) -> tuple[tuple[ShadowStagingSpec, ...], dict[str, tuple[str, RegisteredPage]]]:
    specs: list[ShadowStagingSpec] = []
    index: dict[str, tuple[str, RegisteredPage]] = {}
    root = Path("artifacts/data/page-geometry-manifests")
    for label, checksum in descriptor.stagings:
        path = root / f"{checksum}.json"
        content, payload = load_page_geometry_manifest(path)
        if hashlib.sha256(content).hexdigest() != checksum:
            raise _error("BOARD_CELL_SHADOW_MANIFEST_DRIFT", f"Page manifest differs for {label}.")
        specs.append(
            ShadowStagingSpec(
                label=label,
                manifest_path=path,
                manifest_checksum_sha256=checksum,
            )
        )
        for page in registered_pages(payload):
            prior = index.get(page.source_checksum_sha256)
            if prior is not None and prior[0] != label:
                raise _error(
                    "BOARD_CELL_SHADOW_SOURCE_DUPLICATE",
                    "A registered source belongs to multiple pinned staging manifests.",
                )
            index[page.source_checksum_sha256] = (label, page)
    return tuple(specs), index


def _load_task_one_challenge(
    expected_checksum: str,
) -> tuple[_AttestedChallengeBoard, ...]:
    path = Path("artifacts/quality/grid-symbol-diagnosis") / f"{expected_checksum}.json"
    try:
        content = path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_UNAVAILABLE",
            "The pinned TASK 1 diagnostic report is unavailable.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_DRIFT",
            "The pinned TASK 1 diagnostic report checksum differs.",
        )
    raw_boards = payload.get("boards") if isinstance(payload, Mapping) else None
    if not isinstance(raw_boards, Sequence) or isinstance(raw_boards, str | bytes):
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
            "The TASK 1 diagnostic report does not contain a challenge cohort.",
        )
    boards: list[_AttestedChallengeBoard] = []
    for raw in raw_boards:
        if not isinstance(raw, Mapping):
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
                "A TASK 1 challenge record is invalid.",
            )
        expected_symbols = raw.get("expectedSymbols")
        if (
            not isinstance(expected_symbols, Sequence)
            or isinstance(expected_symbols, str | bytes)
            or len(expected_symbols) != 15
            or any(not isinstance(symbol, str) or not symbol for symbol in expected_symbols)
        ):
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
                "A TASK 1 challenge record has invalid symbol labels.",
            )
        try:
            board = _AttestedChallengeBoard(
                board_id=UUID(str(raw["boardId"])),
                staging_label=str(raw["stagingLabel"]),
                sequence_number=int(raw["sequenceNumber"]),
                position_index=int(raw["positionIndex"]),
                source_checksum_sha256=_require_sha256(
                    str(raw["sourceImageChecksumSha256"]), "challenge source"
                ),
                source_relative_path=str(raw["sourceImageRelativePath"]),
                expected_symbols=tuple(cast(Sequence[str], expected_symbols)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
                "A TASK 1 challenge record is incomplete.",
            ) from error
        if (
            not board.staging_label
            or board.sequence_number < 1
            or board.position_index not in range(9)
            or not board.source_relative_path
        ):
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
                "A TASK 1 challenge record is outside the supported domain.",
            )
        boards.append(board)
    ordered = tuple(sorted(boards, key=lambda item: (item.sequence_number, str(item.board_id))))
    if not ordered or len({item.board_id for item in ordered}) != len(ordered):
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INVALID",
            "The TASK 1 challenge cohort is empty or contains duplicate board IDs.",
        )
    return ordered


def _collect_challenge_boards(
    session: Any,
    *,
    game_id: UUID,
    corrected_by: str,
    page_index: Mapping[str, tuple[str, RegisteredPage]],
    attested_challenge: Sequence[_AttestedChallengeBoard],
    adapter: LocalSymbolOnnxAdapter,
    artifact_root: Path,
    temperature: float,
) -> tuple[tuple[ShadowChallengeBoard, ...], tuple[np.ndarray, ...], Counter[str]]:
    attested_by_id = {item.board_id: item for item in attested_challenge}
    rows = session.execute(
        select(
            ImageBoardGeometryRevisionModel,
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            JobModel,
        )
        .join(
            ImageReviewItemModel,
            ImageReviewItemModel.id == ImageBoardGeometryRevisionModel.review_item_id,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageBoardGeometryRevisionModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(
            ImageReviewItemModel.status.in_(("accepted", "corrected")),
            ImageBoardGeometryRevisionModel.corrected_by == corrected_by,
            ImageBoardGeometryRevisionModel.cropper_version == MANUAL_V19_CROPPER,
            JobModel.game_id == game_id,
            RecognizedBoardModel.id.in_(tuple(attested_by_id)),
        )
        .order_by(RecognizedBoardModel.sequence_number, RecognizedBoardModel.id)
    ).all()
    excluded: Counter[str] = Counter()
    source_cache: dict[str, np.ndarray] = {}
    prepared: list[_PreparedChallenge] = []
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=adapter.input_size)
    for geometry, item, board, source, job in rows:
        attested = attested_by_id.get(board.id)
        if attested is None:
            excluded["outside_attested_task_one_cohort"] += 1
            continue
        if geometry.revision != board.geometry_revision:
            excluded["stale_geometry_revision"] += 1
            continue
        if board.sequence_number is None:
            excluded["sequence_unresolved"] += 1
            continue
        expected = _expected_symbols(item.resolved_value)
        manual_cells = _manual_cells(geometry.geometry)
        page_match = page_index.get(source.checksum_sha256)
        if expected is None:
            excluded["resolved_labels_invalid"] += 1
            continue
        if (
            expected != attested.expected_symbols
            or board.sequence_number != attested.sequence_number
            or board.position_index != attested.position_index
            or source.checksum_sha256 != attested.source_checksum_sha256
            or source.relative_path != attested.source_relative_path
        ):
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_DRIFT",
                "A current challenge board differs from the immutable TASK 1 report.",
            )
        if manual_cells is None:
            excluded["manual_geometry_invalid"] += 1
            continue
        if page_match is None:
            excluded["page_geometry_unavailable"] += 1
            continue
        staging_label, page = page_match
        if staging_label != attested.staging_label:
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_DRIFT",
                "A challenge board moved to a different pinned staging.",
            )
        if page.sequence_start + board.position_index != board.sequence_number:
            excluded["attested_sequence_mismatch"] += 1
            continue
        rgb = source_cache.get(source.checksum_sha256)
        if rgb is None:
            rgb = _load_managed_source(
                artifact_root,
                relative_path=source.relative_path,
                expected_checksum=source.checksum_sha256,
                expected_width=source.width,
                expected_height=source.height,
            )
            source_cache[source.checksum_sha256] = rgb
        page_quad = page.quads[board.position_index]
        estimate = estimate_board_cell_geometry(rgb, page_quad)
        fallback_reason = estimate.fallback_reason
        automatic_cells: tuple[BoardCellQuad, ...] = ()
        tensors: tuple[np.ndarray, ...] = ()
        mean_error: float | None = None
        max_error: float | None = None
        catastrophic = False
        if (
            estimate.status == "estimated"
            and estimate.lattice_bounds_quad is not None
            and estimate.evidence is not None
            and len(estimate.cells) == 15
        ):
            entry = BoardCellGeometryEntry(
                source_order_index=page.sequence_start,
                image_id=str(source.id),
                source_image_checksum_sha256=source.checksum_sha256,
                source_image_relative_path=source.relative_path,
                source_image_width=source.width,
                source_image_height=source.height,
                source_group=str(job.id),
                condition_tags=("challenge-manual-override",),
                sequence_number=board.sequence_number,
                position_index=board.position_index,
                lattice_bounds_quad=estimate.lattice_bounds_quad,
                cells=estimate.cells,
                evidence=estimate.evidence,
            )
            cropped = cropper.crop(rgb, entry)
            if cropped.status == "cropped" and len(cropped.cells) == 15:
                automatic_cells = estimate.cells
                tensors = tuple(
                    production_preprocess_rgb(cell.rgb, input_size=adapter.input_size)
                    for cell in cropped.cells
                )
                mean_error, max_error, catastrophic = cell_geometry_error(
                    automatic_cells, manual_cells
                )
                fallback_reason = None
            else:
                fallback_reason = (
                    cropped.review_reasons[0]
                    if cropped.review_reasons
                    else "BOARD_CELL_CROP_RESULT_INCOMPLETE"
                )
        prepared.append(
            _PreparedChallenge(
                board_id=str(board.id),
                staging_label=staging_label,
                sequence_number=board.sequence_number,
                position_index=board.position_index,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                page_quad=tuple((float(point.x), float(point.y)) for point in page_quad),
                manual_cells=manual_cells,
                expected_symbols=expected,
                automatic_cells=automatic_cells,
                tensors=tensors,
                fallback_reason=(
                    fallback_reason or "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"
                    if not tensors
                    else None
                ),
                residual=estimate.inlier_p95_residual_px,
                mean_error=mean_error,
                max_error=max_error,
                catastrophic_shift=catastrophic,
                source_rgb=rgb,
            )
        )
    all_tensors = [tensor for item in prepared for tensor in item.tensors]
    predictions: list[CellPrediction] = []
    if all_tensors:
        result = adapter.infer(np.stack(all_tensors).astype(np.float32))
        predictions = [
            CellPrediction(prediction.symbol_code, prediction.confidence)
            for prediction in build_symbol_predictions(
                result.logits,
                temperature=temperature,
                class_codes=adapter.class_codes,
                alternative_limit=3,
            )
        ]
    prediction_offset = 0
    challenge: list[ShadowChallengeBoard] = []
    images: list[np.ndarray] = []
    for item in prepared:
        count = len(item.tensors)
        board_predictions = tuple(predictions[prediction_offset : prediction_offset + count])
        prediction_offset += count
        challenge.append(
            ShadowChallengeBoard(
                board_id=item.board_id,
                staging_label=item.staging_label,
                sequence_number=item.sequence_number,
                position_index=item.position_index,
                source_checksum_sha256=item.source_checksum_sha256,
                source_relative_path=item.source_relative_path,
                page_quad=item.page_quad,
                manual_cells=item.manual_cells,
                automatic_cells=item.automatic_cells,
                expected_symbols=item.expected_symbols,
                predictions=board_predictions,
                status="automatic_success" if count == 15 else "deferred",
                fallback_reason=item.fallback_reason,
                inlier_p95_residual_px=item.residual,
                mean_cell_corner_error_px=item.mean_error,
                max_cell_corner_error_px=item.max_error,
                catastrophic_slot_shift=item.catastrophic_shift,
            )
        )
        images.append(item.source_rgb)
    if prediction_offset != len(predictions):
        raise _error("BOARD_CELL_SHADOW_CHALLENGE_INVALID", "Challenge predictions do not align.")
    included_ids = {UUID(item.board_id) for item in challenge}
    missing = set(attested_by_id) - included_ids
    if missing:
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_ATTESTATION_INCOMPLETE",
            "The current database cannot reproduce every board in the immutable TASK 1 cohort.",
        )
    ordered = sorted(
        zip(challenge, images, strict=True),
        key=lambda pair: (
            pair[0].sequence_number,
            pair[0].board_id,
        ),
    )
    return (
        tuple(item for item, _image in ordered),
        tuple(image for _item, image in ordered),
        excluded,
    )


def _expected_symbols(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Mapping):
        return None
    raw_cells = value.get("cells")
    if (
        not isinstance(raw_cells, Sequence)
        or isinstance(raw_cells, str | bytes)
        or len(raw_cells) != 15
    ):
        return None
    indexed: dict[int, str] = {}
    for raw in raw_cells:
        if not isinstance(raw, Mapping):
            return None
        index = raw.get("cellIndex")
        symbol = raw.get("symbolCode")
        if not isinstance(index, int) or isinstance(index, bool) or not isinstance(symbol, str):
            return None
        indexed[index] = symbol
    if set(indexed) != set(range(15)):
        return None
    return tuple(indexed[index] for index in range(15))


def _manual_cells(value: object) -> tuple[BoardCellQuad, ...] | None:
    if not isinstance(value, Mapping):
        return None
    raw_cells = value.get("cells")
    if (
        not isinstance(raw_cells, Sequence)
        or isinstance(raw_cells, str | bytes)
        or len(raw_cells) != 15
    ):
        return None
    parsed: list[BoardCellQuad] = []
    for raw in raw_cells:
        if not isinstance(raw, Mapping):
            return None
        row = raw.get("rowIndex")
        column = raw.get("columnIndex")
        quad = _float_quad(raw.get("sourceQuad"))
        if (
            not isinstance(row, int)
            or isinstance(row, bool)
            or not isinstance(column, int)
            or isinstance(column, bool)
            or quad is None
        ):
            return None
        parsed.append(BoardCellQuad(row_index=row, column_index=column, quad=quad))
    ordered = tuple(sorted(parsed, key=lambda cell: (cell.row_index, cell.column_index)))
    if [(cell.row_index, cell.column_index) for cell in ordered] != [
        (row, column) for row in range(3) for column in range(5)
    ]:
        return None
    return ordered


def _float_quad(value: object) -> tuple[tuple[float, float], ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[tuple[float, float]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            return None
        x = raw.get("x")
        y = raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            return None
        points.append((float(x), float(y)))
    return tuple(points)


def _load_managed_source(
    artifact_root: Path,
    *,
    relative_path: str,
    expected_checksum: str,
    expected_width: int,
    expected_height: int,
) -> np.ndarray:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise _error("BOARD_CELL_SHADOW_PATH_UNSAFE", "Managed source path is unsafe.")
    root = (artifact_root / "data").resolve()
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root):
        raise _error("BOARD_CELL_SHADOW_PATH_UNSAFE", "Managed source path escapes storage.")
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise _error(
            "BOARD_CELL_SHADOW_SOURCE_UNAVAILABLE", "Managed source is unavailable."
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise _error("BOARD_CELL_SHADOW_SOURCE_DRIFT", "Managed source checksum differs.")
    if rgb.shape[:2] != (expected_height, expected_width):
        raise _error("BOARD_CELL_SHADOW_SOURCE_DRIFT", "Managed source dimensions differ.")
    return cast(np.ndarray[Any, np.dtype[np.uint8]], rgb)


def _load_adapter(snapshot: Any, artifact_root: Path) -> LocalSymbolOnnxAdapter:
    root = artifact_root if snapshot.storage_root.value == "artifact" else Path.cwd()
    relative = PurePosixPath(snapshot.onnx_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise _error("BOARD_CELL_SHADOW_MODEL_PATH_UNSAFE", "Model path is unsafe.")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise _error("BOARD_CELL_SHADOW_MODEL_PATH_UNSAFE", "Model path escapes storage.")
    return LocalSymbolOnnxAdapter(
        path,
        expected_sha256=snapshot.onnx_checksum_sha256,
        class_codes=snapshot.class_codes,
        input_size=snapshot.input_size,
    )


def _validate_acceptance_shape(document: Mapping[str, object]) -> None:
    if document.get("version") != SHADOW_MANIFEST_VERSION:
        raise _error("BOARD_CELL_SHADOW_REPORT_INVALID", "Shadow manifest version differs.")
    scope = document.get("scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("pageCount") != 300
        or scope.get("boardCount") != 2700
    ):
        raise _error(
            "BOARD_CELL_SHADOW_REPORT_INVALID", "TASK 2 must cover 300 pages and 2700 boards."
        )
    pages = document.get("pages")
    if not isinstance(pages, Sequence) or isinstance(pages, str | bytes) or len(pages) != 300:
        raise _error("BOARD_CELL_SHADOW_REPORT_INVALID", "Shadow pages are incomplete.")
    positions = Counter(
        cast(Mapping[str, object], board).get("positionIndex")
        for page in pages
        if isinstance(page, Mapping)
        for board in cast(Sequence[object], page.get("boards", ()))
    )
    if positions != Counter({position: 300 for position in range(9)}):
        raise _error(
            "BOARD_CELL_SHADOW_REPORT_INVALID", "Every page position must occur 300 times."
        )


def _find_gallery_index(
    root: Path,
    *,
    shadow_manifest_checksum: str,
) -> Path | None:
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if (
            isinstance(payload, Mapping)
            and payload.get("shadowManifestChecksumSha256") == shadow_manifest_checksum
        ):
            return path
    return None


def _require_sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in _SHA256 for character in value):
        raise _error("BOARD_CELL_SHADOW_CHECKSUM_INVALID", f"The {label} is not SHA-256.")
    return value


def _error(code: str, message: str) -> BoardCellGeometryShadowError:
    return BoardCellGeometryShadowError(code, message)


if __name__ == "__main__":
    raise SystemExit(main())
