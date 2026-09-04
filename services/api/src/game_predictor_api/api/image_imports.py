"""Loopback-only image folder selection and import creation."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status
from fastapi.responses import FileResponse
from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_api.application.image_imports import (
    IMAGE_RELATIVE_PATH_HEADER,
    BrowserImageSelectionService,
    BrowserImageUpload,
    ImageFolderSelectionService,
    ImageSelectionPurpose,
)
from game_predictor_api.application.iterative_image_imports import (
    IterativeImageImportService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.page_geometry_overrides import (
    PageGeometryOverrideService,
)
from game_predictor_api.domain.image_import_engine_policy import ImageImportEnginePolicy
from game_predictor_api.domain.image_sequence_canonical import (
    BrowserUploadPlanSource,
    ImageSequenceCanonicalService,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError, JobStatus, JobType
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_imports import (
    BrowserImageImportPreflightCreate,
    BrowserImageImportPreflightResponse,
    BrowserImageImportStart,
    BrowserImageImportStartResponse,
    BrowserImageSelectionCreate,
    BrowserImageSelectionFileUploadResponse,
    BrowserImageSelectionUploadResponse,
    BrowserImageUploadPlanCreate,
    BrowserImageUploadPlanResponse,
    BrowserPageGeometryOverrideCreate,
    BrowserPageGeometryOverrideResponse,
    BrowserPageGeometryPreflightResponse,
    BrowserPageGeometryReviewSourceResponse,
    BrowserPageGeometryReviewSourcesResponse,
    BrowserReadySelectionResponse,
    CuratedImageImportBatchCreate,
    CuratedImageImportSourceCreate,
    CuratedImageImportSourceResponse,
    ImageFolderImportCreate,
    ImageFolderImportResponse,
    ImageFolderSelectionResponse,
    ImageSequenceImportPreflightResponse,
)
from game_predictor_api.schemas.jobs import JobResponse


def _validate_skipped_canonical_ranges(
    *,
    canonical_service: ImageSequenceCanonicalService,
    game_id: UUID,
    skipped_ranges: tuple[tuple[int, int], ...],
) -> None:
    if not skipped_ranges:
        return
    canonical_numbers = canonical_service.canonical_numbers(game_id)
    missing_numbers = [
        number
        for start, end in skipped_ranges
        for number in range(start, end + 1)
        if number not in canonical_numbers
    ]
    if missing_numbers:
        raise JobConflictError(
            "IMAGE_SEQUENCE_UPLOAD_PLAN_STALE",
            "A range skipped before upload is no longer fully canonical. Create a new upload plan.",
            details={"missingSequenceNumbers": missing_numbers[:100]},
        )


def _geometry_manifest_descriptor(
    *,
    job_service: JobService,
    game_id: UUID,
    upload_id: UUID,
    preflight_job_id: UUID | None,
    expected_checksum: str | None,
) -> dict[str, object] | None:
    """Validate an immutable completed geometry preflight before import."""

    # Listing the correction queue needs only an immutable, completed
    # preflight. The checksum is mandatory only when starting an import,
    # where it protects against the manifest changing between preview and
    # mutation.
    if preflight_job_id is None:
        raise JobConflictError(
            "IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED",
            "A completed geometry preflight and its immutable checksum are required.",
        )
    job = job_service.get_job(preflight_job_id)
    if (
        job.job_type is not JobType.VALIDATE
        or job.game_id != game_id
        or job.status is not JobStatus.COMPLETED
        or job.input_payload.get("validation_kind") != "page_geometry_preflight"
        or job.input_payload.get("source_selection_id") != str(upload_id)
    ):
        raise JobConflictError(
            "IMAGE_PAGE_GEOMETRY_PREFLIGHT_INVALID",
            "The selected page geometry preflight is not completed for this staging.",
        )
    checkpoint = job.checkpoint_payload
    if not isinstance(checkpoint, dict) or checkpoint.get("complete") is not True:
        raise JobConflictError(
            "IMAGE_PAGE_GEOMETRY_PREFLIGHT_INCOMPLETE",
            "The page geometry preflight did not produce an immutable manifest.",
        )
    checksum = checkpoint.get("geometry_manifest_checksum_sha256")
    relative_path = checkpoint.get("geometry_manifest_relative_path")
    if (
        not isinstance(checksum, str)
        or (expected_checksum is not None and checksum != expected_checksum)
        or not isinstance(relative_path, str)
    ):
        raise JobConflictError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_STALE",
            "The page geometry manifest changed after preflight.",
        )
    return {
        "checksumSha256": checksum,
        "preflightJobId": str(job.id),
        "relativePath": relative_path,
    }


def _load_page_geometry_manifest(
    artifact_root: Path,
    descriptor: dict[str, object],
) -> dict[str, object]:
    checksum = descriptor.get("checksumSha256")
    relative_path = descriptor.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(relative_path, str)
        or not relative_path.startswith("data/")
    ):
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The page geometry manifest descriptor is invalid.",
        )
    path = (artifact_root / Path(*PurePosixPath(relative_path).parts)).resolve()
    data_root = (artifact_root / "data").resolve()
    if not path.is_relative_to(data_root) or not path.is_file():
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_UNAVAILABLE",
            "The verified page geometry manifest is unavailable.",
        )
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The verified page geometry manifest cannot be read.",
        ) from error
    if (
        hashlib.sha256(content).hexdigest() != checksum
        or not isinstance(value, dict)
        or not isinstance(value.get("entries"), dict)
        or not all(
            isinstance(value.get(key), int)
            for key in (
                "registeredSourceCount",
                "reviewRequiredSourceCount",
                "skippedHumanResolvedSourceCount",
            )
        )
    ):
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The verified page geometry manifest has an unsupported structure.",
        )
    return cast(dict[str, object], value)


def _uses_touching_page_grid(raw_override: object) -> bool:
    """Identify legacy 3x3 overrides whose neighbouring boards share edges."""

    if not isinstance(raw_override, dict):
        return False
    raw_quads = raw_override.get("quads")
    if not isinstance(raw_quads, list | tuple) or len(raw_quads) != 9:
        return False
    quads = list(raw_quads)

    def point(quad_index: int, point_index: int) -> tuple[int, int] | None:
        quad = quads[quad_index]
        if not isinstance(quad, list | tuple) or len(quad) != 4:
            return None
        value = quad[point_index]
        if not isinstance(value, dict):
            return None
        x, y = value.get("x"), value.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        return x, y

    comparisons: list[tuple[tuple[int, int] | None, tuple[int, int] | None]] = []
    for row in range(3):
        for column in range(2):
            left = row * 3 + column
            right = left + 1
            comparisons.extend(
                ((point(left, 1), point(right, 0)), (point(left, 2), point(right, 3)))
            )
    for row in range(2):
        for column in range(3):
            upper = row * 3 + column
            lower = upper + 3
            comparisons.extend(
                ((point(upper, 3), point(lower, 0)), (point(upper, 2), point(lower, 1)))
            )
    return bool(comparisons) and all(
        left is not None and left == right for left, right in comparisons
    )


def _attested_range_from_relative_path(value: str) -> tuple[int | None, int | None]:
    stem = Path(value).stem
    if not stem.startswith("seq_") or "-" not in stem:
        return None, None
    start_text, end_text = stem[4:].split("-", maxsplit=1)
    try:
        start, end = int(start_text), int(end_text)
    except ValueError:
        return None, None
    if start < 1 or end < start or end - start > 8:
        return None, None
    return start, end


def _expected_board_count_from_relative_path(value: str) -> int:
    start, end = _attested_range_from_relative_path(value)
    return 9 if start is None or end is None else end - start + 1


def create_image_imports_router(
    selection_service_dependency: Callable[..., object],
    browser_selection_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
    iterative_import_service_dependency: Callable[..., object],
    image_sequence_canonical_service_dependency: Callable[..., object] | None = None,
    page_geometry_override_service_dependency: Callable[..., object] | None = None,
    artifact_root: Path | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-imports", tags=["image-imports"])
    selection_parameter = Depends(selection_service_dependency)
    browser_selection_parameter = Depends(browser_selection_service_dependency)
    job_parameter = Depends(job_service_dependency)
    iterative_import_parameter = Depends(iterative_import_service_dependency)
    canonical_parameter = (
        None
        if image_sequence_canonical_service_dependency is None
        else Depends(image_sequence_canonical_service_dependency)
    )
    page_geometry_override_parameter = (
        None
        if page_geometry_override_service_dependency is None
        else Depends(page_geometry_override_service_dependency)
    )
    responses: dict[int | str, dict[str, object]] = {
        404: {"model": ErrorResponse, "description": "Game or folder not found"},
        409: {"model": ErrorResponse, "description": "Import conflict"},
        422: {"model": ErrorResponse, "description": "Folder validation error"},
    }
    resolved_artifact_root = None if artifact_root is None else artifact_root.resolve()

    def upload_response(upload: BrowserImageUpload) -> BrowserImageSelectionUploadResponse:
        return BrowserImageSelectionUploadResponse(
            upload_id=upload.upload_id,
            expected_file_count=upload.expected_file_count,
            uploaded_file_count=len(upload.uploaded_indexes),
            uploaded_file_indexes=sorted(upload.uploaded_indexes),
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_bytes=upload.uploaded_bytes,
            purpose=upload.purpose,
            game_id=upload.game_id,
        )

    def file_upload_response(
        upload: BrowserImageUpload,
    ) -> BrowserImageSelectionFileUploadResponse:
        return BrowserImageSelectionFileUploadResponse(
            upload_id=upload.upload_id,
            expected_file_count=upload.expected_file_count,
            uploaded_file_count=len(upload.uploaded_indexes),
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_bytes=upload.uploaded_bytes,
        )

    def browser_preflight(
        *,
        upload_id: UUID,
        game_id: UUID,
        service: BrowserImageSelectionService,
        canonical_service: object | None,
        job_service: JobService,
    ) -> BrowserImageImportPreflightResponse:
        if canonical_service is None:
            raise JobError(
                "IMAGE_SEQUENCE_PREFLIGHT_UNAVAILABLE",
                "Canonical sequence preflight is not configured.",
            )
        ready = service.get_ready(upload_id)
        if ready.upload.game_id is not None and ready.upload.game_id != game_id:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                "The staged folder belongs to a different game.",
            )
        result = cast(ImageSequenceCanonicalService, canonical_service).preflight(
            game_id=game_id,
            manifest=ready.manifest,
        )
        _validate_skipped_canonical_ranges(
            canonical_service=cast(ImageSequenceCanonicalService, canonical_service),
            game_id=game_id,
            skipped_ranges=ready.upload.skipped_canonical_ranges,
        )
        base = ImageSequenceImportPreflightResponse.from_domain(result)
        payload = base.model_dump(mode="json", by_alias=True)
        payload["uploadPlanChecksumSha256"] = ready.upload.upload_plan_checksum_sha256
        payload["skippedCanonicalRanges"] = [
            {"sequenceRangeStart": start, "sequenceRangeEnd": end}
            for start, end in ready.upload.skipped_canonical_ranges
        ]
        (
            symbol_fingerprint,
            grid_fingerprint,
            symbol_blocker_code,
        ) = job_service.preview_image_import_model_fingerprints(game_id=game_id)
        engine_policy = job_service.current_image_import_engine_policy(game_id=game_id)
        payload["imageEnginePolicy"] = engine_policy.policy.value
        payload["imageEnginePolicyRevision"] = engine_policy.revision
        # Every selectable engine requires checksum-bound page geometry.  The
        # structured production path uses it as immutable source provenance;
        # switching the game policy must never bypass the reviewed page gate.
        payload["geometryPreflightRequired"] = True
        payload["symbolModelReady"] = symbol_fingerprint is not None
        payload["symbolModelBlockerCode"] = symbol_blocker_code
        checksum = hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
        ).hexdigest()
        return BrowserImageImportPreflightResponse(
            **payload,
            upload_id=upload_id,
            display_name=ready.upload.display_name,
            manifest_checksum_sha256=ready.manifest.checksum_sha256,
            preflight_checksum_sha256=checksum,
            symbol_model_inference_fingerprint=symbol_fingerprint,
            grid_profile_inference_fingerprint=grid_fingerprint,
        )

    @router.post(
        "/browser-selections",
        response_model=BrowserImageSelectionUploadResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createBrowserImageSelection",
        summary="Start a browser-native image folder upload",
        responses=responses,
    )
    def create_browser_selection(
        payload: BrowserImageSelectionCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageSelectionUploadResponse:
        skipped_ranges = tuple(
            (item.sequence_range_start, item.sequence_range_end)
            for item in payload.skipped_canonical_ranges
        )
        if skipped_ranges:
            if canonical_service is None or payload.game_id is None:
                raise JobError(
                    "IMAGE_SEQUENCE_UPLOAD_PLAN_UNAVAILABLE",
                    "A game-scoped canonical plan is required for skipped source ranges.",
                )
            _validate_skipped_canonical_ranges(
                canonical_service=cast(ImageSequenceCanonicalService, canonical_service),
                game_id=payload.game_id,
                skipped_ranges=skipped_ranges,
            )
        return upload_response(
            service.begin(
                display_name=payload.display_name,
                expected_file_count=payload.expected_file_count,
                expected_total_bytes=payload.expected_total_bytes,
                purpose=payload.purpose,
                game_id=payload.game_id,
                upload_plan_checksum_sha256=payload.upload_plan_checksum_sha256,
                skipped_canonical_ranges=skipped_ranges,
            )
        )

    @router.post(
        "/browser-selections/upload-plan",
        response_model=BrowserImageUploadPlanResponse,
        operation_id="planBrowserImageSelectionUpload",
        summary="Filter fully imported seq_* sources before browser upload",
        responses=responses,
    )
    def plan_browser_selection_upload(
        payload: BrowserImageUploadPlanCreate,
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageUploadPlanResponse:
        if canonical_service is None:
            raise JobError(
                "IMAGE_SEQUENCE_PREFLIGHT_UNAVAILABLE",
                "Canonical sequence preflight is not configured.",
            )
        plan = cast(ImageSequenceCanonicalService, canonical_service).plan_browser_upload(
            game_id=payload.game_id,
            files=tuple(
                BrowserUploadPlanSource(
                    source_index=item.source_index,
                    relative_path=item.relative_path,
                    size_bytes=item.size_bytes,
                )
                for item in payload.files
            ),
        )
        return BrowserImageUploadPlanResponse.from_domain(plan)

    @router.get(
        "/browser-selections/{upload_id}",
        response_model=BrowserImageSelectionUploadResponse,
        operation_id="getBrowserImageSelection",
        summary="Restore progress for an unfinished browser folder upload",
        responses=responses,
    )
    def get_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> BrowserImageSelectionUploadResponse:
        return upload_response(service.get(upload_id))

    @router.put(
        "/browser-selections/{upload_id}/files/{file_index}",
        response_model=BrowserImageSelectionFileUploadResponse,
        operation_id="uploadBrowserImageSelectionFile",
        summary="Upload one JPEG from a browser-native folder selection",
        responses=responses,
    )
    def upload_browser_selection_file(
        upload_id: UUID,
        file_index: int,
        relative_path: Annotated[
            str,
            Header(alias=IMAGE_RELATIVE_PATH_HEADER, min_length=1, max_length=1000),
        ],
        payload: Annotated[bytes, Body(media_type="application/octet-stream")],
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> BrowserImageSelectionFileUploadResponse:
        return file_upload_response(
            service.upload_file(
                upload_id,
                file_index,
                relative_path=relative_path,
                content=payload,
            )
        )

    @router.post(
        "/browser-selections/{upload_id}/finalize",
        response_model=ImageFolderSelectionResponse,
        operation_id="finalizeBrowserImageSelection",
        summary="Finalize a browser-native image folder selection",
        responses=responses,
    )
    def finalize_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> ImageFolderSelectionResponse:
        return ImageFolderSelectionResponse.selected(service.finalize(upload_id))

    @router.delete(
        "/browser-selections/{upload_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="cancelBrowserImageSelection",
        summary="Cancel and remove a browser-native image folder selection",
        responses=responses,
    )
    def cancel_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> Response:
        service.cancel(upload_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/browser-selections",
        response_model=list[BrowserReadySelectionResponse],
        operation_id="listReadyBrowserImageSelections",
        summary="List finalized browser staging folders ready for layout import",
        responses=responses,
    )
    def list_ready_browser_selections(
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        purpose: Annotated[ImageSelectionPurpose | None, Query()] = None,
    ) -> list[BrowserReadySelectionResponse]:
        if purpose not in {None, ImageSelectionPurpose.LAYOUT_IMPORT}:
            return []
        return [BrowserReadySelectionResponse.from_domain(item) for item in service.list_ready()]

    @router.post(
        "/browser-selections/{upload_id}/preflight",
        response_model=BrowserImageImportPreflightResponse,
        operation_id="previewReadyBrowserImageImport",
        summary="Preview a finalized browser staging folder before creating a job",
        responses=responses,
    )
    def preview_ready_browser_import(
        upload_id: UUID,
        payload: BrowserImageImportPreflightCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        job_service: Annotated[JobService, job_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageImportPreflightResponse:
        return browser_preflight(
            upload_id=upload_id,
            game_id=payload.game_id,
            service=service,
            canonical_service=canonical_service,
            job_service=job_service,
        )

    @router.post(
        "/browser-selections/{upload_id}/start",
        response_model=BrowserImageImportStartResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="startReadyBrowserImageImport",
        summary="Create an idempotent image import from finalized browser staging",
        responses=responses,
    )
    def start_ready_browser_import(
        upload_id: UUID,
        payload: BrowserImageImportStart,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        job_service: Annotated[JobService, job_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageImportStartResponse:
        ready = service.bind_ready_game(upload_id, payload.game_id)
        if ready.manifest.checksum_sha256 != payload.manifest_checksum_sha256:
            raise JobConflictError(
                "IMAGE_SEQUENCE_MANIFEST_CHANGED",
                "The staged manifest changed after preflight.",
            )
        preflight = browser_preflight(
            upload_id=upload_id,
            game_id=payload.game_id,
            service=service,
            canonical_service=canonical_service,
            job_service=job_service,
        )
        current_symbol, current_grid = job_service.current_image_import_model_fingerprints(
            game_id=payload.game_id
        )
        if (
            payload.symbol_model_inference_fingerprint is not None
            and payload.symbol_model_inference_fingerprint != current_symbol
        ) or (
            payload.grid_profile_inference_fingerprint is not None
            and payload.grid_profile_inference_fingerprint != current_grid
        ):
            raise JobConflictError(
                "IMAGE_SEQUENCE_MODEL_SNAPSHOT_STALE",
                "The active model snapshot changed after preflight.",
            )
        if preflight.preflight_checksum_sha256 != payload.preflight_checksum_sha256:
            raise JobConflictError(
                "IMAGE_SEQUENCE_PREFLIGHT_STALE",
                "The canonical sequence projection changed after preflight.",
            )
        if (
            payload.image_engine_policy is not None
            and payload.image_engine_policy is not preflight.image_engine_policy
        ) or (
            payload.image_engine_policy_revision is not None
            and payload.image_engine_policy_revision != preflight.image_engine_policy_revision
        ):
            raise JobConflictError(
                "IMAGE_ENGINE_POLICY_STALE",
                "The game image engine policy changed after preflight.",
            )
        if (
            payload.board_cell_processing_mode is not None
            and payload.board_cell_processing_mode != preflight.image_engine_policy.value
        ):
            raise JobConflictError(
                "IMAGE_ENGINE_POLICY_STALE",
                "The requested engine does not match the game policy.",
            )
        existing = job_service.get_image_import_by_source_selection(
            game_id=payload.game_id,
            source_selection_id=upload_id,
        )
        # A browser staging is immutable, but its old job may be terminal and
        # pinned to bootstrap models. In that case create one fresh, model-pinned
        # job while preserving the old job for auditability.
        requested_mode = payload.start_mode
        rerun = requested_mode == "rerun_current_models" or existing is None
        if existing is not None and existing.input_payload.get("schema_version") != 5:
            rerun = True
        requested_v19 = preflight.image_engine_policy is ImageImportEnginePolicy.VERIFIED_V19
        if existing is not None and (
            (existing.input_payload.get("board_cell_processing") is not None) != requested_v19
        ):
            rerun = True
        geometry_manifest = _geometry_manifest_descriptor(
            job_service=job_service,
            game_id=payload.game_id,
            upload_id=upload_id,
            preflight_job_id=payload.geometry_preflight_job_id,
            expected_checksum=payload.geometry_manifest_checksum_sha256,
        )
        if rerun:
            canonical_numbers = (
                sorted(
                    cast(ImageSequenceCanonicalService, canonical_service).canonical_numbers(
                        payload.game_id
                    )
                )
                if canonical_service is not None
                else None
            )
            try:
                job = job_service.create_image_import_job(
                    game_id=payload.game_id,
                    selection_id=upload_id,
                    source_directory=ready.upload.path,
                    source_display_name=ready.upload.display_name,
                    pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
                    canonical_sequence_numbers=canonical_numbers,
                    source_manifest_sha256=ready.manifest.checksum_sha256,
                    start_mode="rerun_current_models",
                    previous_job_id=None if existing is None else existing.id,
                    page_geometry_manifest=geometry_manifest,
                    use_verified_board_cell_geometry=requested_v19,
                )
                created = True
            except JobConflictError as error:
                if error.code != "JOB_INPUT_ALREADY_EXISTS":
                    raise
                details = getattr(error, "details", {})
                existing_id = details.get("existingJobId") if isinstance(details, dict) else None
                existing = (
                    job_service.get_job(UUID(str(existing_id))) if existing_id is not None else None
                )
                if existing is None:
                    raise
                job = existing
                created = False
        else:
            if existing is None:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_IMPORT_MISSING",
                    "The existing browser import is unavailable.",
                )
            expected_manifest = existing.input_payload.get("source_manifest_sha256")
            if expected_manifest not in {None, ready.manifest.checksum_sha256}:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_MANIFEST_CHANGED",
                    "This staging folder was already used with another manifest.",
                )
            job = existing
            created = False
        if not created:
            service.mark_in_use(upload_id, game_id=payload.game_id, job_id=job.id)
        return BrowserImageImportStartResponse(
            created=created,
            job=JobResponse.from_domain(job),
            preflight=preflight,
        )

    @router.post(
        "/browser-selections/{upload_id}/geometry-preflight",
        response_model=BrowserPageGeometryPreflightResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="startBrowserPageGeometryPreflight",
        summary="Build a verified complete-page geometry manifest before layout import",
        responses=responses,
    )
    def start_browser_page_geometry_preflight(
        upload_id: UUID,
        payload: BrowserImageImportPreflightCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        job_service: Annotated[JobService, job_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserPageGeometryPreflightResponse:
        ready = service.bind_ready_game(upload_id, payload.game_id)
        try:
            job = job_service.create_page_geometry_preflight_job(
                game_id=payload.game_id,
                selection_id=upload_id,
                source_directory=ready.upload.path,
                source_display_name=ready.upload.display_name,
                source_manifest_sha256=ready.manifest.checksum_sha256,
                canonical_sequence_numbers=(
                    ()
                    if canonical_service is None
                    else sorted(
                        cast(ImageSequenceCanonicalService, canonical_service).canonical_numbers(
                            payload.game_id
                        )
                    )
                ),
            )
            created = True
        except JobConflictError as error:
            if error.code != "JOB_INPUT_ALREADY_EXISTS":
                raise
            details = error.details
            existing_id = details.get("existingJobId")
            if not isinstance(existing_id, str):
                raise
            job = job_service.get_job(UUID(existing_id))
            created = False
        if not created:
            service.mark_in_use(upload_id, game_id=payload.game_id, job_id=job.id)
        return BrowserPageGeometryPreflightResponse(
            created=created,
            job=JobResponse.from_domain(job),
        )

    @router.get(
        "/browser-selections/{upload_id}/geometry-preflights/{preflight_job_id}/review-sources",
        response_model=BrowserPageGeometryReviewSourcesResponse,
        operation_id="listBrowserPageGeometryReviewSources",
        summary="List pages requiring full-page geometry correction",
        responses=responses,
    )
    def list_browser_page_geometry_review_sources(
        upload_id: UUID,
        preflight_job_id: UUID,
        game_id: Annotated[UUID, Query()],
        job_service: Annotated[JobService, job_parameter],
        override_service: PageGeometryOverrideService | None = page_geometry_override_parameter,
    ) -> BrowserPageGeometryReviewSourcesResponse:
        descriptor = _geometry_manifest_descriptor(
            job_service=job_service,
            game_id=game_id,
            upload_id=upload_id,
            preflight_job_id=preflight_job_id,
            expected_checksum=None,
        )
        if descriptor is None or resolved_artifact_root is None:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_MANIFEST_UNAVAILABLE",
                "The page geometry manifest store is not configured.",
            )
        manifest = _load_page_geometry_manifest(resolved_artifact_root, descriptor)
        entries = cast(dict[str, object], manifest["entries"])
        job = job_service.get_job(preflight_job_id)
        pinned_overrides = job.input_payload.get("page_geometry_overrides")
        pinned_overrides = pinned_overrides if isinstance(pinned_overrides, dict) else {}
        current_overrides = (
            {} if override_service is None else override_service.snapshot(game_id=game_id)
        )
        sources: list[BrowserPageGeometryReviewSourceResponse] = []
        for checksum, raw in sorted(entries.items()):
            if not isinstance(raw, dict):
                continue
            current_override = current_overrides.get(checksum)
            has_manual_override = raw.get(
                "registrationVersion"
            ) == "manual-page-geometry-override-v1" or isinstance(current_override, dict)
            pinned_override = pinned_overrides.get(checksum)
            current_checksum = (
                current_override.get("decisionChecksumSha256")
                if isinstance(current_override, dict)
                else None
            )
            pinned_checksum = (
                pinned_override.get("decisionChecksumSha256")
                if isinstance(pinned_override, dict)
                else None
            )
            legacy_touching_grid = _uses_touching_page_grid(current_override)
            saved_since_preflight = (
                isinstance(current_checksum, str)
                and current_checksum != pinned_checksum
                and not legacy_touching_grid
            )
            manual_review_required = has_manual_override and (
                saved_since_preflight or legacy_touching_grid
            )
            if raw.get("status") != "review_required" and not manual_review_required:
                continue
            source_relative_path = raw.get("sourceRelativePath")
            if not isinstance(source_relative_path, str) or not source_relative_path:
                continue
            start, end = _attested_range_from_relative_path(source_relative_path)
            sources.append(
                BrowserPageGeometryReviewSourceResponse(
                    source_checksum_sha256=checksum,
                    source_relative_path=source_relative_path,
                    sequence_range_start=start,
                    sequence_range_end=end,
                    expected_board_count=_expected_board_count_from_relative_path(
                        source_relative_path
                    ),
                    review_reason=(
                        "manual_override" if manual_review_required else "review_required"
                    ),
                    existing_final_quads=(
                        current_override.get("quads")
                        if isinstance(current_override, dict)
                        else None
                    ),
                    existing_override_revision=(
                        current_override.get("revision")
                        if isinstance(current_override, dict)
                        and isinstance(current_override.get("revision"), int)
                        else None
                    ),
                    saved_since_preflight=saved_since_preflight,
                )
            )
        sources.sort(
            key=lambda source: (
                source.sequence_range_start is None,
                source.sequence_range_start or 0,
                source.sequence_range_end or 0,
                source.source_relative_path,
                source.source_checksum_sha256,
            )
        )
        return BrowserPageGeometryReviewSourcesResponse(
            job=JobResponse.from_domain(job),
            geometry_manifest_checksum_sha256=cast(str, descriptor["checksumSha256"]),
            registered_source_count=cast(int, manifest["registeredSourceCount"]),
            review_required_source_count=sum(
                source.review_reason == "review_required" for source in sources
            ),
            skipped_human_resolved_source_count=cast(
                int, manifest["skippedHumanResolvedSourceCount"]
            ),
            sources=sources,
        )

    @router.get(
        "/browser-selections/{upload_id}/page-geometry-sources/{source_checksum_sha256}/asset",
        operation_id="getBrowserPageGeometrySourceAsset",
        summary="Read one staged source image for local page-geometry correction",
        responses=responses,
    )
    def get_browser_page_geometry_source_asset(
        upload_id: UUID,
        source_checksum_sha256: str,
        game_id: Annotated[UUID, Query()],
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> FileResponse:
        ready = service.bind_ready_game(upload_id, game_id)
        source = next(
            (
                item
                for item in ready.manifest.files
                if item.checksum_sha256 == source_checksum_sha256
            ),
            None,
        )
        if source is None:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_NOT_IN_STAGING",
                "The page geometry source is not part of this staging.",
            )
        path = (ready.upload.path / source.stored_file_name).resolve()
        root = ready.upload.path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
                "The staged page geometry source is unavailable.",
            )
        return FileResponse(path, media_type="image/jpeg", filename=source.relative_path)

    @router.post(
        "/browser-selections/{upload_id}/page-geometry-overrides",
        response_model=BrowserPageGeometryOverrideResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createBrowserPageGeometryOverride",
        summary="Persist one complete-page geometry correction for a staged source",
        responses=responses,
    )
    def create_browser_page_geometry_override(
        upload_id: UUID,
        payload: BrowserPageGeometryOverrideCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        override_service: PageGeometryOverrideService | None = page_geometry_override_parameter,
    ) -> BrowserPageGeometryOverrideResponse:
        if override_service is None:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_OVERRIDE_UNAVAILABLE",
                "Page geometry corrections are not configured.",
            )
        ready = service.bind_ready_game(upload_id, payload.game_id)
        source = next(
            (
                item
                for item in ready.manifest.files
                if item.checksum_sha256 == payload.source_checksum_sha256
            ),
            None,
        )
        if source is None:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_NOT_IN_STAGING",
                "The geometry correction source is not part of this staging.",
            )
        try:
            with Image.open(ready.upload.path / source.stored_file_name) as image:
                image.load()
                width, height = ImageOps.exif_transpose(image).size
        except (OSError, UnidentifiedImageError) as error:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
                "The staged source image cannot be decoded for geometry correction.",
            ) from error
        if (payload.image_width, payload.image_height) != (width, height):
            raise JobConflictError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_DIMENSIONS_CHANGED",
                "The source dimensions differ from the geometry correction.",
            )
        expected_board_count = _expected_board_count_from_relative_path(source.relative_path)
        if len(payload.final_quads) != expected_board_count:
            raise JobConflictError(
                "IMAGE_PAGE_GEOMETRY_BOARD_COUNT_CHANGED",
                "The correction does not match the attested board count for this source.",
            )
        value, created = override_service.save(
            game_id=payload.game_id,
            source_checksum_sha256=payload.source_checksum_sha256,
            image_width=width,
            image_height=height,
            expected_board_count=expected_board_count,
            final_quads=tuple(
                tuple(point.model_dump(by_alias=True) for point in quad)
                for quad in payload.final_quads
            ),
            actor=payload.actor,
        )
        return BrowserPageGeometryOverrideResponse(
            created=created,
            id=value.id,
            revision=value.revision,
            decision_checksum_sha256=value.decision_checksum_sha256,
        )

    @router.post(
        "/folder-selection",
        response_model=ImageFolderSelectionResponse,
        operation_id="selectLocalImageFolder",
        summary="Open the controlled native Windows folder picker",
        responses=responses,
    )
    def select_folder(
        service: Annotated[ImageFolderSelectionService, selection_parameter],
    ) -> ImageFolderSelectionResponse:
        selected = service.select()
        return (
            ImageFolderSelectionResponse.cancelled()
            if selected is None
            else ImageFolderSelectionResponse.selected(selected)
        )

    @router.post(
        "",
        response_model=ImageFolderImportResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createImageFolderImport",
        summary="Create an image import from an approved local folder selection",
        responses=responses,
    )
    def create_import(
        payload: ImageFolderImportCreate,
        selection_service: Annotated[
            ImageFolderSelectionService,
            selection_parameter,
        ],
        job_service: Annotated[JobService, job_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> ImageFolderImportResponse:
        canonical_numbers: list[int] | None = None
        if canonical_service is not None:
            get_numbers = getattr(canonical_service, "canonical_numbers", None)
            if callable(get_numbers):
                canonical_numbers = sorted(set(get_numbers(payload.game_id)))
        job = selection_service.create_import_job(
            job_service,
            game_id=payload.game_id,
            selection_token=payload.selection_token,
            canonical_sequence_numbers=canonical_numbers,
        )
        return ImageFolderImportResponse(job=JobResponse.from_domain(job))

    @router.post(
        "/preflight",
        response_model=ImageSequenceImportPreflightResponse,
        operation_id="previewImageSequenceImport",
        summary="Preview reuse of already resolved seq_* ranges",
        responses=responses,
    )
    def preflight_import(
        payload: ImageFolderImportCreate,
        selection_service: Annotated[
            ImageFolderSelectionService,
            selection_parameter,
        ],
        canonical_service: object | None = canonical_parameter,
    ) -> ImageSequenceImportPreflightResponse:
        if canonical_service is None:
            raise JobError(
                "IMAGE_SEQUENCE_PREFLIGHT_UNAVAILABLE",
                "Canonical sequence preflight is not configured.",
            )
        selected = selection_service.get_for_import(
            game_id=payload.game_id,
            selection_token=payload.selection_token,
        )
        # Keep this annotation-free at the transport boundary so custom test
        # dependencies can provide the same small service contract.
        result = cast(ImageSequenceCanonicalService, canonical_service).preflight(
            game_id=payload.game_id,
            source_directory=selected.path,
        )
        return ImageSequenceImportPreflightResponse.from_domain(result)

    @router.post(
        "/{source_job_id}/reprocess",
        response_model=ImageFolderImportResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="reprocessManagedImageImport",
        summary="Reprocess an image import from its preserved managed originals",
        responses=responses,
    )
    def reprocess_import(
        source_job_id: UUID,
        job_service: Annotated[JobService, job_parameter],
    ) -> ImageFolderImportResponse:
        job = job_service.create_managed_image_reprocess_job(
            source_job_id,
            pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
        )
        return ImageFolderImportResponse(job=JobResponse.from_domain(job))

    @router.post(
        "/curated-sources",
        response_model=CuratedImageImportSourceResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="registerCuratedImageImportSource",
        summary="Register verified image-selection output for incremental import",
        responses=responses,
    )
    def register_curated_source(
        payload: CuratedImageImportSourceCreate,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(
            service.register_source(
                game_id=payload.game_id,
                image_selection_run_id=payload.image_selection_run_id,
            )
        )

    @router.get(
        "/curated-sources",
        response_model=list[CuratedImageImportSourceResponse],
        operation_id="listCuratedImageImportSources",
        summary="List incremental curated sources for one game",
        responses=responses,
    )
    def list_curated_sources(
        game_id: Annotated[UUID, Query(alias="gameId")],
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> list[CuratedImageImportSourceResponse]:
        return [
            CuratedImageImportSourceResponse.from_domain(item)
            for item in service.list_sources(game_id=game_id)
        ]

    @router.get(
        "/curated-sources/{source_id}",
        response_model=CuratedImageImportSourceResponse,
        operation_id="getCuratedImageImportSource",
        summary="Get durable progress for one incremental curated source",
        responses=responses,
    )
    def get_curated_source(
        source_id: UUID,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(service.get_source(source_id))

    @router.post(
        "/curated-sources/{source_id}/batches",
        response_model=CuratedImageImportSourceResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createNextCuratedImageImportBatch",
        summary="Atomically reserve and import the next N curated images",
        responses=responses,
    )
    def create_next_curated_batch(
        source_id: UUID,
        payload: CuratedImageImportBatchCreate,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(
            service.create_next_batch(source_id, requested_count=payload.image_count)
        )

    return router


__all__ = ["create_image_imports_router"]
