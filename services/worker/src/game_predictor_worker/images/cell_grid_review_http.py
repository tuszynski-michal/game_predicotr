"""Loopback-only HTTP adapter for independent cell-grid review."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable, Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, cast
from urllib.parse import parse_qs, urlsplit

from .cell_grid_golden import CellGridGoldenError, CellGridGoldenReview

_MAX_REQUEST_BYTES = 64 * 1024
_OBSERVATION_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class CellGridReviewHttpError(ValueError):
    """Stable client-facing error raised by the local HTTP adapter."""

    def __init__(self, status: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost"}


class CellGridReviewHttpApplication:
    """Own routing without accepting filesystem paths from the browser."""

    def __init__(
        self,
        review: CellGridGoldenReview,
        static_root: Path,
        *,
        token: str | None = None,
        calibration_profiles: Mapping[str, object] | None = None,
    ) -> None:
        self.review = review
        self.static_root = static_root.resolve(strict=True)
        self.token = token or secrets.token_urlsafe(32)
        self.allowed_origin = ""
        self.calibration_profiles = dict(calibration_profiles or {})

    def bind_origin(self, host: str, port: int) -> None:
        self.allowed_origin = f"http://{host}:{port}"

    def bootstrap(self) -> dict[str, object]:
        return {"token": self.token}

    def state(self, query: dict[str, list[str]]) -> dict[str, object]:
        status = _single_query_value(query, "status", "pending")
        offset = _integer_query_value(query, "offset", 0)
        limit = _integer_query_value(query, "limit", 1)
        return self.review.state(
            offset=offset,
            limit=limit,
            status=cast(Literal["all", "pending", "accepted"], status),
        )

    def profiles(self) -> dict[str, object]:
        if not self.calibration_profiles:
            return {"profiles": [], "status": "unavailable"}
        return self.calibration_profiles

    def static_file(self, path: str) -> tuple[bytes, str]:
        item = _STATIC_FILES.get(path)
        if item is None:
            raise CellGridReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "CELL_GRID_HTTP_NOT_FOUND",
                "Resource not found.",
            )
        filename, content_type = item
        try:
            candidate = (self.static_root / filename).resolve(strict=True)
        except OSError as error:
            raise CellGridReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "CELL_GRID_HTTP_NOT_FOUND",
                "Resource not found.",
            ) from error
        if not candidate.is_relative_to(self.static_root):
            raise CellGridReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "CELL_GRID_HTTP_NOT_FOUND",
                "Resource not found.",
            )
        return candidate.read_bytes(), content_type

    def board(self, observation_id: str) -> tuple[bytes, str]:
        if not _OBSERVATION_ID_PATTERN.fullmatch(observation_id):
            raise CellGridReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "CELL_GRID_HTTP_NOT_FOUND",
                "Board not found.",
            )
        path, checksum = self.review.resolve_board(observation_id)
        return path.read_bytes(), checksum

    def source(self, observation_id: str) -> tuple[bytes, str]:
        if not _OBSERVATION_ID_PATTERN.fullmatch(observation_id):
            raise CellGridReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "CELL_GRID_HTTP_NOT_FOUND",
                "Source image not found.",
            )
        path, checksum = self.review.resolve_source(observation_id)
        return path.read_bytes(), checksum

    def post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        if path == "/api/draft":
            changed = self.review.save_draft(
                observation_id=_required_string(body, "observationId"),
                source_quad=_required_quad(body, "sourceQuad"),
                v1_cut_cell_indexes=_integer_array(body, "v1CutCellIndexes"),
                v1_impact_reviewed=_required_boolean(body, "v1ImpactReviewed"),
            )
            return {"changed": changed}
        if path == "/api/accept":
            changed = self.review.accept(
                observation_id=_required_string(body, "observationId"),
                source_quad=_required_quad(body, "sourceQuad"),
                v1_cut_cell_indexes=_integer_array(body, "v1CutCellIndexes"),
                v1_impact_reviewed=_required_boolean(body, "v1ImpactReviewed"),
                reviewed_by=_required_string(body, "reviewedBy"),
            )
            return {"changed": changed}
        if path == "/api/reopen":
            changed = self.review.reopen(_required_string(body, "observationId"))
            return {"changed": changed}
        raise CellGridReviewHttpError(
            HTTPStatus.NOT_FOUND,
            "CELL_GRID_HTTP_NOT_FOUND",
            "Resource not found.",
        )


def create_cell_grid_review_server(
    review: CellGridGoldenReview,
    static_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    calibration_profiles: Mapping[str, object] | None = None,
) -> ThreadingHTTPServer:
    """Create a single-owner loopback server."""

    if not is_loopback_host(host):
        raise CellGridReviewHttpError(
            HTTPStatus.BAD_REQUEST,
            "CELL_GRID_HTTP_NON_LOOPBACK",
            "The review server may bind only to localhost.",
        )
    application = CellGridReviewHttpApplication(
        review,
        static_root,
        token=token,
        calibration_profiles=calibration_profiles,
    )
    handler = _handler_factory(application)
    server = ThreadingHTTPServer((host, port), handler)
    bound_host, bound_port = server.server_address[:2]
    application.bind_origin(str(bound_host), int(bound_port))
    return server


def _handler_factory(
    application: CellGridReviewHttpApplication,
) -> Callable[..., BaseHTTPRequestHandler]:
    class CellGridReviewRequestHandler(BaseHTTPRequestHandler):
        server_version = "M5CellGridReview/1"

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlsplit(self.path)
                if parsed.path == "/api/bootstrap":
                    self._send_json(HTTPStatus.OK, application.bootstrap())
                    return
                if parsed.path == "/api/state":
                    self._send_json(
                        HTTPStatus.OK,
                        application.state(parse_qs(parsed.query, keep_blank_values=True)),
                    )
                    return
                if parsed.path == "/api/profiles":
                    self._send_json(HTTPStatus.OK, application.profiles())
                    return
                board_prefix = "/api/boards/"
                if parsed.path.startswith(board_prefix):
                    content, checksum = application.board(parsed.path[len(board_prefix) :])
                    self._send_bytes(
                        HTTPStatus.OK,
                        content,
                        "image/png",
                        cache_control="private, max-age=31536000, immutable",
                        extra_headers={"ETag": f'"{checksum}"'},
                    )
                    return
                source_prefix = "/api/sources/"
                if parsed.path.startswith(source_prefix):
                    content, checksum = application.source(parsed.path[len(source_prefix) :])
                    self._send_bytes(
                        HTTPStatus.OK,
                        content,
                        "image/jpeg",
                        cache_control="private, max-age=31536000, immutable",
                        extra_headers={"ETag": f'"{checksum}"'},
                    )
                    return
                content, content_type = application.static_file(parsed.path)
                self._send_bytes(
                    HTTPStatus.OK,
                    content,
                    content_type,
                    cache_control="no-store",
                )
            except Exception as error:  # boundary maps stable public errors
                self._send_error(error)

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._authorize(application)
                parsed = urlsplit(self.path)
                result = application.post(parsed.path, self._json_body())
                self._send_json(HTTPStatus.OK, result)
            except Exception as error:  # boundary maps stable public errors
                self._send_error(error)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorize(self, app: CellGridReviewHttpApplication) -> None:
            if self.headers.get("X-Review-Token") != app.token:
                raise CellGridReviewHttpError(
                    HTTPStatus.FORBIDDEN,
                    "CELL_GRID_HTTP_FORBIDDEN",
                    "Missing or invalid review token.",
                )
            origin = self.headers.get("Origin")
            if origin is not None and origin != app.allowed_origin:
                raise CellGridReviewHttpError(
                    HTTPStatus.FORBIDDEN,
                    "CELL_GRID_HTTP_ORIGIN_REJECTED",
                    "Foreign browser origin is not allowed.",
                )
            if self.headers.get_content_type() != "application/json":
                raise CellGridReviewHttpError(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    "CELL_GRID_HTTP_CONTENT_TYPE",
                    "Content-Type must be application/json.",
                )

        def _json_body(self) -> dict[str, object]:
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError as error:
                raise _invalid_request("Content-Length must be an integer.") from error
            if content_length <= 0 or content_length > _MAX_REQUEST_BYTES:
                raise CellGridReviewHttpError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "CELL_GRID_HTTP_BODY_SIZE",
                    f"JSON body must contain 1-{_MAX_REQUEST_BYTES} bytes.",
                )
            try:
                value = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise _invalid_request("Body must contain valid UTF-8 JSON.") from error
            if not isinstance(value, dict):
                raise _invalid_request("JSON body must be an object.")
            return value

        def _send_error(self, error: Exception) -> None:
            if isinstance(error, CellGridReviewHttpError):
                status = error.status
                code = error.code
                message = str(error)
            elif isinstance(error, CellGridGoldenError):
                status = HTTPStatus.BAD_REQUEST
                code = error.code
                message = str(error)
            elif isinstance(error, FileNotFoundError | OSError):
                status = HTTPStatus.NOT_FOUND
                code = "CELL_GRID_HTTP_NOT_FOUND"
                message = "Resource not found."
            else:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
                code = "CELL_GRID_HTTP_INTERNAL"
                message = "The local review server failed."
            self._send_json(status, {"code": code, "message": message})

        def _send_json(self, status: HTTPStatus, value: object) -> None:
            content = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self._send_bytes(
                status,
                content,
                "application/json; charset=utf-8",
                cache_control="no-store",
            )

        def _send_bytes(
            self,
            status: HTTPStatus,
            content: bytes,
            content_type: str,
            *,
            cache_control: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", cache_control)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' blob:; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            if extra_headers:
                for name, value in extra_headers.items():
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

    return CellGridReviewRequestHandler


def _single_query_value(
    query: dict[str, list[str]],
    name: str,
    default: str,
) -> str:
    values = query.get(name)
    if values is None:
        return default
    if len(values) != 1:
        raise _invalid_request(f"{name} must occur once.")
    return values[0]


def _integer_query_value(
    query: dict[str, list[str]],
    name: str,
    default: int,
) -> int:
    value = _single_query_value(query, name, str(default))
    try:
        return int(value)
    except ValueError as error:
        raise _invalid_request(f"{name} must be an integer.") from error


def _required_string(body: dict[str, object], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise _invalid_request(f"{name} must be a string.")
    return value


def _required_boolean(body: dict[str, object], name: str) -> bool:
    value = body.get(name)
    if not isinstance(value, bool):
        raise _invalid_request(f"{name} must be a boolean.")
    return value


def _integer_array(body: dict[str, object], name: str) -> list[int]:
    value = body.get(name)
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise _invalid_request(f"{name} must be an array of integers.")
    return cast(list[int], value)


def _required_quad(
    body: dict[str, object],
    name: str,
) -> list[dict[str, object]]:
    value = body.get(name)
    if not isinstance(value, list) or len(value) != 4:
        raise _invalid_request(f"{name} must contain four points.")
    points: list[dict[str, object]] = []
    for point in value:
        if not isinstance(point, dict) or set(point) != {"x", "y"}:
            raise _invalid_request(f"{name} points must contain x and y.")
        if not all(
            isinstance(point[axis], int | float) and not isinstance(point[axis], bool)
            for axis in ("x", "y")
        ):
            raise _invalid_request(f"{name} coordinates must be numbers.")
        points.append(cast(dict[str, object], point))
    return points


def _invalid_request(message: str) -> CellGridReviewHttpError:
    return CellGridReviewHttpError(
        HTTPStatus.BAD_REQUEST,
        "CELL_GRID_HTTP_REQUEST_INVALID",
        message,
    )


__all__ = [
    "CellGridReviewHttpApplication",
    "CellGridReviewHttpError",
    "create_cell_grid_review_server",
    "is_loopback_host",
]
