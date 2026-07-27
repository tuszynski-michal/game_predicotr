"""FastAPI application factory for the local Admin API."""

from collections.abc import Callable, Iterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from game_predictor_api.api.router import create_api_router
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.rules import RulesService
from game_predictor_api.config import ApiSettings, get_settings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
)
from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetError,
    DatasetNotFoundError,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobError,
    JobNotFoundError,
)
from game_predictor_api.domain.rules import (
    RulesConflictError,
    RulesError,
    RulesNotFoundError,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.dataset_repository import (
    SqlAlchemyDatasetRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.rules_repository import SqlAlchemyRulesRepository


def create_app(
    settings: ApiSettings | None = None,
    *,
    catalog_service_dependency: Callable[..., object] | None = None,
    rules_service_dependency: Callable[..., object] | None = None,
    dataset_service_dependency: Callable[..., object] | None = None,
    job_service_dependency: Callable[..., object] | None = None,
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

    resolved_dataset_dependency = (
        dataset_service_dependency or default_dataset_service_dependency
    )

    def default_job_service_dependency() -> Iterator[JobService]:
        with session_factory() as session:
            try:
                yield JobService(SqlAlchemyJobRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_job_dependency = (
        job_service_dependency or default_job_service_dependency
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
        allow_origins=[resolved_settings.admin_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.state.database_engine = database_engine
    application.include_router(
        create_api_router(
            resolved_settings,
            resolved_catalog_dependency,
            resolved_rules_dependency,
            resolved_dataset_dependency,
            resolved_job_dependency,
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

    return application


app = create_app()
