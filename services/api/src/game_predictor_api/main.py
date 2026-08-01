"""FastAPI application factory for the local Admin API."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from game_predictor_worker.images.manual_geometry_recrop import (
    ManualGeometryRecropper,
)

from game_predictor_api.api.router import create_api_router
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.cleanup import (
    CleanupService,
    ManagedCleanupArtifactStore,
)
from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.application.image_imports import (
    IMAGE_RELATIVE_PATH_HEADER,
    BrowserImageSelectionService,
    ImageFolderSelectionService,
    WindowsFolderPicker,
)
from game_predictor_api.application.image_jobs import ImageJobOperationsService
from game_predictor_api.application.image_review_cohorts import (
    VerifiedCohortArtifactStore,
    VerifiedCohortService,
)
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewService,
)
from game_predictor_api.application.image_storage import (
    ImageArtifactStore,
    ImageStorageService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportService,
)
from game_predictor_api.application.layout_imports import (
    LayoutImportSourceInspector,
)
from game_predictor_api.application.mobile_releases import (
    MobileReleaseService,
)
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessError,
    ReviewerAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
)
from game_predictor_api.application.reviews import ReviewService
from game_predictor_api.application.rules import RulesService
from game_predictor_api.application.symbol_bootstrap import SymbolBootstrapService
from game_predictor_api.config import ApiSettings, get_settings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
)
from game_predictor_api.domain.cleanup import (
    CleanupConflictError,
    CleanupError,
    CleanupNotFoundError,
)
from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetError,
    DatasetNotFoundError,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobError,
    JobNotFoundError,
)
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseConflictError,
    MobileReleaseError,
    MobileReleaseNotFoundError,
)
from game_predictor_api.domain.reviews import (
    ReviewConflictError,
    ReviewError,
    ReviewNotFoundError,
)
from game_predictor_api.domain.rules import (
    RulesConflictError,
    RulesError,
    RulesNotFoundError,
)
from game_predictor_api.security.local_admin import (
    ADMIN_CONFIRMATION_HEADER,
    ADMIN_INTENT_HEADER,
    ADMIN_TARGET_HEADER,
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
    augment_admin_security_openapi,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.dataset_repository import (
    SqlAlchemyDatasetRepository,
)
from game_predictor_api.storage.image_job_repository import (
    SqlAlchemyImageJobOperationsRepository,
)
from game_predictor_api.storage.image_review_cohort_repository import (
    SqlAlchemyVerifiedCohortExportRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.layout_import_report_repository import (
    SqlAlchemyLayoutImportReportRepository,
)
from game_predictor_api.storage.mobile_release_repository import (
    SqlAlchemyMobileReleaseRepository,
)
from game_predictor_api.storage.review_repository import (
    SqlAlchemyReviewRepository,
)
from game_predictor_api.storage.reviewer_access_repository import (
    SqlAlchemyReviewerAccessRepository,
)
from game_predictor_api.storage.rules_repository import SqlAlchemyRulesRepository
from game_predictor_api.storage.symbol_bootstrap_repository import (
    SqlAlchemySymbolBootstrapRepository,
)


def create_app(
    settings: ApiSettings | None = None,
    *,
    catalog_service_dependency: Callable[..., object] | None = None,
    cleanup_service_dependency: Callable[..., object] | None = None,
    rules_service_dependency: Callable[..., object] | None = None,
    dataset_service_dependency: Callable[..., object] | None = None,
    job_service_dependency: Callable[..., object] | None = None,
    image_job_service_dependency: Callable[..., object] | None = None,
    image_folder_selection_service_dependency: Callable[..., object] | None = None,
    browser_image_selection_service_dependency: Callable[..., object] | None = None,
    image_storage_service_dependency: Callable[..., object] | None = None,
    image_review_service_dependency: Callable[..., object] | None = None,
    image_review_cohort_service_dependency: Callable[..., object] | None = None,
    layout_import_report_service_dependency: Callable[..., object] | None = None,
    mobile_release_service_dependency: Callable[..., object] | None = None,
    review_service_dependency: Callable[..., object] | None = None,
    reviewer_access_service_dependency: Callable[..., object] | None = None,
    reviewer_ingress_service_dependency: Callable[..., object] | None = None,
    symbol_bootstrap_service_dependency: Callable[..., object] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    database_engine = create_database_engine(resolved_settings)
    session_factory = create_session_factory(database_engine)

    def default_catalog_service_dependency() -> Iterator[CatalogService]:
        with session_factory() as session:
            try:
                yield CatalogService(SqlAlchemyCatalogRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_catalog_dependency = catalog_service_dependency or default_catalog_service_dependency

    def default_cleanup_service_dependency() -> Iterator[CleanupService]:
        with session_factory() as session:
            try:
                yield CleanupService(
                    SqlAlchemyCleanupRepository(session),
                    ManagedCleanupArtifactStore(resolved_settings.artifact_root),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_cleanup_dependency = cleanup_service_dependency or default_cleanup_service_dependency

    def default_symbol_bootstrap_service_dependency() -> Iterator[SymbolBootstrapService]:
        with session_factory() as session:
            try:
                yield SymbolBootstrapService(SqlAlchemySymbolBootstrapRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_bootstrap_dependency = (
        symbol_bootstrap_service_dependency
        or default_symbol_bootstrap_service_dependency
    )

    def default_rules_service_dependency() -> Iterator[RulesService]:
        with session_factory() as session:
            try:
                yield RulesService(SqlAlchemyRulesRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_rules_dependency = rules_service_dependency or default_rules_service_dependency

    def default_dataset_service_dependency() -> Iterator[DatasetService]:
        with session_factory() as session:
            try:
                yield DatasetService(SqlAlchemyDatasetRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_dataset_dependency = dataset_service_dependency or default_dataset_service_dependency

    def default_job_service_dependency() -> Iterator[JobService]:
        with session_factory() as session:
            try:
                yield JobService(
                    SqlAlchemyJobRepository(session),
                    LayoutImportSourceInspector(
                        resolved_settings.import_root,
                        max_bytes=resolved_settings.import_max_bytes,
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_job_dependency = job_service_dependency or default_job_service_dependency

    default_image_folder_selection_service = ImageFolderSelectionService(
        WindowsFolderPicker(Path.cwd() / "scripts" / "select_local_image_folder.ps1")
    )
    resolved_image_folder_selection_dependency = image_folder_selection_service_dependency or (
        lambda: default_image_folder_selection_service
    )
    default_browser_image_selection_service = BrowserImageSelectionService(
        default_image_folder_selection_service,
        resolved_settings.import_root,
        max_bytes=resolved_settings.import_max_bytes,
    )
    resolved_browser_image_selection_dependency = (
        browser_image_selection_service_dependency
        or (lambda: default_browser_image_selection_service)
    )

    def default_image_job_service_dependency() -> Iterator[ImageJobOperationsService]:
        with session_factory() as session:
            try:
                yield ImageJobOperationsService(SqlAlchemyImageJobOperationsRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_job_dependency = (
        image_job_service_dependency or default_image_job_service_dependency
    )

    def default_image_storage_service_dependency() -> Iterator[ImageStorageService]:
        with session_factory() as session:
            try:
                yield ImageStorageService(
                    SqlAlchemyImageJobOperationsRepository(session),
                    ImageArtifactStore(resolved_settings.artifact_root),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_storage_dependency = (
        image_storage_service_dependency or default_image_storage_service_dependency
    )

    def default_image_review_service_dependency() -> Iterator[OperationalImageReviewService]:
        with session_factory() as session:
            try:
                yield OperationalImageReviewService(
                    SqlAlchemyOperationalImageReviewRepository(session),
                    artifact_root=resolved_settings.artifact_root,
                    geometry_recropper=ManualGeometryRecropper(),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_review_dependency = (
        image_review_service_dependency or default_image_review_service_dependency
    )

    def default_image_review_cohort_service_dependency() -> Iterator[VerifiedCohortService]:
        with session_factory() as session:
            try:
                yield VerifiedCohortService(
                    SqlAlchemyOperationalImageReviewRepository(session),
                    SqlAlchemyVerifiedCohortExportRepository(session),
                    VerifiedCohortArtifactStore(resolved_settings.artifact_root),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_review_cohort_dependency = (
        image_review_cohort_service_dependency or default_image_review_cohort_service_dependency
    )

    def default_layout_import_report_service_dependency() -> Iterator[LayoutImportReportService]:
        with session_factory() as session:
            try:
                yield LayoutImportReportService(SqlAlchemyLayoutImportReportRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_layout_import_report_dependency = (
        layout_import_report_service_dependency or default_layout_import_report_service_dependency
    )

    def default_mobile_release_service_dependency() -> Iterator[MobileReleaseService]:
        with session_factory() as session:
            try:
                yield MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_mobile_release_dependency = (
        mobile_release_service_dependency or default_mobile_release_service_dependency
    )

    def default_review_service_dependency() -> Iterator[ReviewService]:
        with session_factory() as session:
            try:
                yield ReviewService(SqlAlchemyReviewRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_review_dependency = review_service_dependency or default_review_service_dependency

    def default_reviewer_access_service_dependency() -> Iterator[ReviewerAccessService]:
        with session_factory() as session:
            try:
                yield ReviewerAccessService(
                    lambda: _active_reviewer_origin(
                        resolved_settings.reviewer_origin,
                    ),
                    SqlAlchemyReviewerAccessRepository(session),
                )
                session.commit()
            except ReviewerAccessError:
                # Failed unlock attempts and the fifth-attempt lock are
                # security events that must survive the HTTP error response.
                session.commit()
                raise
            except BaseException:
                session.rollback()
                raise

    resolved_reviewer_access_dependency = (
        reviewer_access_service_dependency or default_reviewer_access_service_dependency
    )
    project_root = Path(__file__).resolve().parents[4]
    reviewer_ingress_service = ReviewerIngressService(project_root)
    resolved_reviewer_ingress_dependency = reviewer_ingress_service_dependency or (
        lambda: reviewer_ingress_service
    )
    api_host = (
        f"[{resolved_settings.host}]" if resolved_settings.host == "::1" else resolved_settings.host
    )
    application = FastAPI(
        title=resolved_settings.application_name,
        version=resolved_settings.version,
        servers=[
            {
                "url": f"http://{api_host}:{resolved_settings.port}",
                "description": "Local Admin API",
            }
        ],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            resolved_settings.admin_origin,
            resolved_settings.reviewer_origin,
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            IMAGE_RELATIVE_PATH_HEADER,
            ADMIN_INTENT_HEADER,
            ADMIN_CONFIRMATION_HEADER,
            ADMIN_TARGET_HEADER,
        ],
    )
    application.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin=resolved_settings.admin_origin,
        audit_log=AppendOnlyAdminAuditLog(resolved_settings.artifact_root),
    )
    application.state.database_engine = database_engine
    application.include_router(
        create_api_router(
            resolved_settings,
            resolved_catalog_dependency,
            resolved_cleanup_dependency,
            resolved_rules_dependency,
            resolved_dataset_dependency,
            resolved_job_dependency,
            resolved_image_job_dependency,
            resolved_image_folder_selection_dependency,
            resolved_browser_image_selection_dependency,
            resolved_image_storage_dependency,
            resolved_image_review_dependency,
            resolved_image_review_cohort_dependency,
            resolved_layout_import_report_dependency,
            resolved_mobile_release_dependency,
            resolved_review_dependency,
            resolved_reviewer_access_dependency,
            resolved_reviewer_ingress_dependency,
            resolved_symbol_bootstrap_dependency,
        )
    )

    @application.exception_handler(CatalogError)
    async def handle_catalog_error(
        _request: Request,
        error: CatalogError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, CatalogNotFoundError):
            status_code = 404
        elif isinstance(error, CatalogConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(CleanupError)
    async def handle_cleanup_error(
        _request: Request,
        error: CleanupError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, CleanupNotFoundError):
            status_code = 404
        elif isinstance(error, CleanupConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ImageReviewError)
    async def handle_image_review_error(
        _request: Request,
        error: ImageReviewError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, ImageReviewNotFoundError):
            status_code = 404
        elif isinstance(error, ImageReviewConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(RulesError)
    async def handle_rules_error(
        _request: Request,
        error: RulesError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, RulesNotFoundError):
            status_code = 404
        elif isinstance(error, RulesConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(DatasetError)
    async def handle_dataset_error(
        _request: Request,
        error: DatasetError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, DatasetNotFoundError):
            status_code = 404
        elif isinstance(error, DatasetConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(JobError)
    async def handle_job_error(
        _request: Request,
        error: JobError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, JobNotFoundError):
            status_code = 404
        elif isinstance(error, JobConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(MobileReleaseError)
    async def handle_mobile_release_error(
        _request: Request,
        error: MobileReleaseError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, MobileReleaseNotFoundError):
            status_code = 404
        elif isinstance(error, MobileReleaseConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ReviewError)
    async def handle_review_error(
        _request: Request,
        error: ReviewError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, ReviewNotFoundError):
            status_code = 404
        elif isinstance(error, ReviewConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ReviewerAccessError)
    async def handle_reviewer_access_error(
        _request: Request,
        error: ReviewerAccessError,
    ) -> JSONResponse:
        status_code = {
            "REVIEWER_ACCESS_CODE_INVALID": 401,
            "REVIEWER_SESSION_LOCKED": 401,
            "REVIEWER_SESSION_REVOKED": 401,
            "REVIEWER_TOKEN_INVALID": 401,
            "REVIEWER_TOKEN_REQUIRED": 401,
            "REVIEWER_SCOPE_FORBIDDEN": 403,
            "REVIEWER_SESSION_NOT_FOUND": 404,
            "REVIEWER_SCOPE_INVALID": 422,
            "REVIEWER_SESSION_LIFETIME_INVALID": 422,
        }.get(error.code, 422)
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(ReviewerIngressError)
    async def handle_reviewer_ingress_error(
        _request: Request,
        error: ReviewerIngressError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request data is invalid.",
                "details": {
                    "errors": [
                        {
                            "location": [str(part) for part in item["loc"]],
                            "message": item["msg"],
                            "type": item["type"],
                        }
                        for item in error.errors()
                    ]
                },
            },
        )

    generated_openapi = application.openapi

    def local_admin_openapi() -> dict[str, Any]:
        schema = cast(dict[str, Any], generated_openapi())
        augment_admin_security_openapi(schema)
        return schema

    application.openapi = local_admin_openapi

    return application


def _active_reviewer_origin(local_origin: str) -> str:
    state_path = Path(__file__).resolve().parents[4] / ".runtime" / "remote-reviewer.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        public_origin = str(payload.get("publicOrigin", "")).rstrip("/")
        parsed = urlparse(public_origin)
        if (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.endswith(".trycloudflare.com")
            and parsed.path in {"", "/"}
        ):
            return public_origin
    except (OSError, ValueError, TypeError):
        pass
    return local_origin.rstrip("/")


app = create_app()
