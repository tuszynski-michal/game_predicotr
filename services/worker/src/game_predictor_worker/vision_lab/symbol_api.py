"""Symbol routes on the existing loopback application."""

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

from .annotation_contracts import BackupRequest, BackupResult
from .symbol_contracts import (
    CropRequest,
    DbCropPreview,
    DictionaryPage,
    DictionaryView,
    LabBoardPreview,
    LabCropPreview,
    LabQueuePreview,
    SymbolPage,
    SymbolRequest,
    SymbolResult,
)
from .symbol_store import SymbolLabelStore


def symbol_error(error: Exception) -> HTTPException:
    message = str(error.args[0]) if error.args else type(error).__name__
    if isinstance(error, KeyError):
        return HTTPException(404, message)
    if isinstance(error, OSError) or "INTEGRITY" in message or "CHECKSUM" in message:
        return HTTPException(500, "SYMBOL_INTEGRITY_OR_IO_ERROR")
    return HTTPException(409, message)


def install_symbol_routes(app: FastAPI, store: Callable[[], SymbolLabelStore]) -> None:
    @app.get("/symbols", response_model=SymbolPage, operation_id="list_symbol_labels")
    def list_labels(
        game_id: str | None = None,
        source_id: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        read_token: str | None = None,
    ) -> SymbolPage:
        try:
            return store().list_labels(game_id, source_id, offset, limit, read_token)
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error

    @app.get(
        "/symbol-dictionaries",
        response_model=DictionaryPage,
        operation_id="list_symbol_dictionaries",
    )
    def list_dictionaries(
        game_id: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        read_token: str | None = None,
    ) -> DictionaryPage:
        try:
            return store().list_dictionaries(game_id, offset, limit, read_token)
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error

    @app.get(
        "/symbol-dictionaries/{game_id}/{version}",
        response_model=DictionaryView,
        operation_id="get_symbol_dictionary",
    )
    def dictionary(game_id: str, version: int) -> DictionaryView:
        try:
            return store().dictionary(game_id, version)
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error

    @app.post(
        "/symbol-crops",
        response_model=LabCropPreview | DbCropPreview | LabBoardPreview | LabQueuePreview,
        operation_id="preview_symbol_crop",
    )
    def preview(
        body: CropRequest,
    ) -> LabCropPreview | DbCropPreview | LabBoardPreview | LabQueuePreview:
        try:
            return store().preview(body)
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error

    @app.post("/symbols", response_model=SymbolResult, operation_id="save_symbol_decision")
    def mutate(body: SymbolRequest) -> SymbolResult:
        try:
            return store().mutate(body)
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error

    @app.post("/symbol-backups", response_model=BackupResult, operation_id="create_symbol_backup")
    def backup(body: BackupRequest) -> BackupResult:
        try:
            return store().backup()
        except (ValueError, KeyError, OSError) as error:
            raise symbol_error(error) from error
