"""Framework-independent game and symbol catalog domain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

_CODE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_NAME_LENGTH: Final = 200
_MAX_IMAGE_PATH_LENGTH: Final = 500
DEFAULT_EXPECTED_LAYOUT_COUNT: Final = 500_000
MAX_EXPECTED_LAYOUT_COUNT: Final = 10_000_000


class GameStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SymbolStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CatalogError(ValueError):
    """Stable domain failure translated by the HTTP boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class CatalogNotFoundError(CatalogError):
    """Requested catalog resource does not exist."""


class CatalogConflictError(CatalogError):
    """Catalog uniqueness rule was violated."""


@dataclass(frozen=True, slots=True)
class Game:
    id: UUID
    code: str
    name: str
    status: GameStatus
    expected_layout_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Symbol:
    id: UUID
    game_id: UUID
    mobile_code: int
    code: str
    name: str
    image_path: str | None
    is_wildcard: bool
    display_order: int
    status: SymbolStatus
    name_pl: str | None = None
    name_en: str | None = None


def validate_stable_code(value: str, *, field_name: str) -> str:
    if not _CODE_PATTERN.fullmatch(value):
        raise CatalogError(
            "INVALID_STABLE_CODE",
            "Stable code must contain 1-64 letters, digits, underscores, or hyphens.",
            details={"field": field_name},
        )
    return value


def validate_name(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_NAME_LENGTH:
        raise CatalogError(
            "INVALID_NAME",
            "Name must contain 1-200 non-whitespace characters.",
            details={"field": "name"},
        )
    return normalized


def validate_optional_name(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_NAME_LENGTH:
        raise CatalogError(
            "INVALID_NAME",
            "Localized name must contain 1-200 non-whitespace characters.",
            details={"field": field_name},
        )
    return normalized


def validate_mobile_code(value: int) -> int:
    if not 1 <= value <= 32767:
        raise CatalogError(
            "INVALID_MOBILE_CODE",
            "mobileCode must be between 1 and 32767.",
            details={"field": "mobileCode"},
        )
    return value


def validate_expected_layout_count(value: int) -> int:
    if isinstance(value, bool) or not 1 <= value <= MAX_EXPECTED_LAYOUT_COUNT:
        raise CatalogError(
            "INVALID_EXPECTED_LAYOUT_COUNT",
            "expectedLayoutCount must be between 1 and 10000000.",
            details={"field": "expectedLayoutCount"},
        )
    return value


def validate_display_order(value: int) -> int:
    if value < 0:
        raise CatalogError(
            "INVALID_DISPLAY_ORDER",
            "displayOrder cannot be negative.",
            details={"field": "displayOrder"},
        )
    return value


def validate_image_path(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or len(value) > _MAX_IMAGE_PATH_LENGTH or "\\" in value or ":" in value:
        raise CatalogError(
            "INVALID_IMAGE_PATH",
            "imagePath must be a relative POSIX path no longer than 500 characters.",
            details={"field": "imagePath"},
        )

    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CatalogError(
            "INVALID_IMAGE_PATH",
            "imagePath must be a relative path without parent traversal.",
            details={"field": "imagePath"},
        )
    return value
