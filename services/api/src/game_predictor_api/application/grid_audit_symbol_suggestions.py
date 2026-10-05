"""Checksum-bound, advisory symbols for the proposed cut of an audited board."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_audit_proposals import GridAuditProposalError
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewListItem

SYMBOL_SUGGESTIONS_SCHEMA = "grid-audit-symbol-suggestions-v1"
SYMBOL_SUGGESTIONS_DIRECTORY = "symbol-suggestions"
SYMBOL_ALGORITHM_VERSION = "symbol-reference-library-v1"
MAX_SYMBOL_SUGGESTIONS_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class GridAuditCellSymbolSuggestion:
    cell_index: int
    symbol_id: UUID | None
    is_tentative: bool = False


@dataclass(frozen=True, slots=True)
class GridAuditSymbolSuggestions:
    generated_at: str
    sha256: str
    preview_command: Mapping[str, Any]
    cells: tuple[GridAuditCellSymbolSuggestion, ...]


class FileGridAuditSymbolSuggestionStore:
    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve() / "grid-audit-proposals"

    def load(
        self,
        *,
        game_id: UUID,
        audit_id: str,
        audit_sha256: str,
        item_id: str,
        review_item: ImageGridReviewListItem,
    ) -> GridAuditSymbolSuggestions | None:
        directory = (self._root / str(game_id) / audit_id / SYMBOL_SUGGESTIONS_DIRECTORY).resolve()
        if not directory.is_relative_to(self._root) or not re.fullmatch(r"[a-z][0-9]{5}", item_id):
            raise _invalid("The symbol suggestion path is invalid.")
        manifest_path = directory / f"{item_id}.manifest.json"
        if not manifest_path.is_file():
            return None
        path = directory / f"{item_id}.json"
        try:
            if manifest_path.stat().st_size > MAX_SYMBOL_SUGGESTIONS_BYTES:
                raise ValueError("manifest size")
            manifest = json.loads(manifest_path.read_bytes())
            if not path.is_file() or path.stat().st_size > MAX_SYMBOL_SUGGESTIONS_BYTES:
                raise ValueError("payload size")
            content = path.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            if sha256 != manifest["sha256"]:
                raise GridAuditProposalError(
                    "GRID_AUDIT_SYMBOL_SUGGESTIONS_CHECKSUM_MISMATCH",
                    "The new symbol suggestions differ from their manifest.",
                )
            document = json.loads(content)
            if document["schema"] != SYMBOL_SUGGESTIONS_SCHEMA:
                raise ValueError("schema")
            if document["algorithmVersion"] != SYMBOL_ALGORITHM_VERSION:
                raise ValueError("algorithm")
            if (
                document["gameId"] != str(game_id)
                or document["auditId"] != audit_id
                or document["auditSha256"] != audit_sha256
                or document["itemId"] != item_id
                or document["reviewItemId"] != str(review_item.review_item_id)
            ):
                return None
            command = document["previewCommand"]
            expected = {
                "expectedGeometryRevision": review_item.geometry_revision,
                "expectedResolutionRevision": review_item.resolution_revision,
                "expectedSourceChecksumSha256": review_item.source_checksum_sha256,
                "expectedSourceWidth": review_item.source_width,
                "expectedSourceHeight": review_item.source_height,
                "expectedGridRows": review_item.topology.rows,
                "expectedGridColumns": review_item.topology.columns,
            }
            if any(command.get(key) != value for key, value in expected.items()):
                return None
            corners = command["corners"]
            if len(corners) != 4 or any(
                type(point[key]) is not int for point in corners for key in ("x", "y")
            ):
                raise ValueError("corners")
            cells = tuple(
                GridAuditCellSymbolSuggestion(
                    cell_index=cell["cellIndex"],
                    symbol_id=UUID(cell["symbolId"]) if cell["symbolId"] is not None else None,
                    is_tentative=cell.get("isTentative", False),
                )
                for cell in document["cells"]
            )
            if sorted(cell.cell_index for cell in cells) != list(
                range(review_item.topology.cell_count)
            ):
                raise ValueError("cells")
            if any(
                type(cell.is_tentative) is not bool
                or (cell.is_tentative and cell.symbol_id is None)
                for cell in cells
            ):
                raise ValueError("tentative cells")
            generated_at = document["generatedAt"]
            if not isinstance(generated_at, str):
                raise ValueError("generatedAt")
            return GridAuditSymbolSuggestions(generated_at, sha256, command, cells)
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
            if isinstance(error, GridAuditProposalError):
                raise
            raise _invalid("The new symbol suggestion artifact is malformed.") from error


def _invalid(message: str) -> GridAuditProposalError:
    return GridAuditProposalError("GRID_AUDIT_SYMBOL_SUGGESTIONS_INVALID", message)
