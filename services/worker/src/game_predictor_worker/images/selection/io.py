"""Bounded manifest input and deterministic JSON audit output for the selector."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .contracts import (
    CheapImageObservation,
    ImageSelectionResult,
    ImageSelectionSource,
    SelectionContractError,
    SelectionGroupResult,
    SelectorCheckpoint,
)

_NATURAL_PART = re.compile(r"(\d+)")


def _natural_path_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in _NATURAL_PART.split(value)
    )


def load_browser_selection_manifest(
    manifest_path: Path,
) -> tuple[tuple[ImageSelectionSource, ...], str]:
    try:
        content = manifest_path.read_bytes()
        value = cast(dict[str, Any], json.loads(content))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_INPUT_MANIFEST_INVALID",
            "The staged browser manifest cannot be read.",
        ) from error
    if (
        value.get("schemaVersion") != 1
        or value.get("purpose") != "photo_selection"
        or value.get("orderingPolicy") != "natural_relative_path_v1"
        or not isinstance(value.get("files"), list)
    ):
        raise SelectionContractError(
            "IMAGE_SELECTION_INPUT_MANIFEST_INVALID",
            "The staged browser manifest has an unsupported contract.",
        )
    sources: list[ImageSelectionSource] = []
    try:
        for file_value in value["files"]:
            item = cast(dict[str, Any], file_value)
            sources.append(
                ImageSelectionSource(
                    order_index=int(item["orderIndex"]),
                    relative_path=str(item["relativePath"]),
                    stored_relative_path=str(item["storedFileName"]),
                    checksum_sha256=str(item["checksumSha256"]),
                    size_bytes=int(item["sizeBytes"]),
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_INPUT_MANIFEST_INVALID",
            "The staged browser manifest contains an invalid file entry.",
        ) from error
    ordered = tuple(sorted(sources, key=lambda source: source.order_index))
    if not ordered:
        raise SelectionContractError(
            "IMAGE_SELECTION_INPUT_MANIFEST_EMPTY",
            "The staged browser manifest contains no JPEG files.",
        )
    naturally_ordered = tuple(
        sorted(
            ordered,
            key=lambda source: (
                _natural_path_key(source.relative_path),
                source.relative_path,
            ),
        )
    )
    if naturally_ordered != ordered:
        raise SelectionContractError(
            "IMAGE_SELECTION_INPUT_ORDER_INVALID",
            "The staged browser manifest does not follow natural relative-path order.",
        )
    return ordered, hashlib.sha256(content).hexdigest()


class JsonSelectionAuditSink:
    """Write bounded JSONL observations and atomically replaced checkpoints."""

    def __init__(self, output_root: Path) -> None:
        self._root = output_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._candidates_path = self._root / "candidates.jsonl"
        self._groups_path = self._root / "groups.jsonl"
        self._checkpoint_path = self._root / "checkpoint.json"
        self._candidates_path.write_bytes(b"")
        self._groups_path.write_bytes(b"")

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        payload = {
            "boardCount": observation.board_count,
            "checksumSha256": observation.source.checksum_sha256,
            "geometryConfidence": observation.geometry_confidence,
            "groupOrder": group_order,
            "height": observation.height,
            "orderIndex": observation.source.order_index,
            "qualityMetrics": observation.quality.to_dict(),
            "reasonCodes": list(observation.reason_codes),
            "sourceRelativePath": observation.source.relative_path,
            "width": observation.width,
        }
        self._append_json(self._candidates_path, payload)

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        self._write_atomic_json(self._checkpoint_path, checkpoint.to_dict())

    def group_finalized(self, group: SelectionGroupResult) -> None:
        self._append_json(self._groups_path, group.to_dict())

    def write_result(
        self,
        result: ImageSelectionResult,
        *,
        input_manifest_sha256: str,
    ) -> Path:
        payload = result.to_dict()
        payload["inputManifestSha256"] = input_manifest_sha256
        destination = self._root / "selection-report.json"
        self._write_atomic_json(destination, payload)
        return destination

    @staticmethod
    def _append_json(path: Path, payload: Mapping[str, object]) -> None:
        line = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        with path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(f"{line}\n")

    @staticmethod
    def _write_atomic_json(path: Path, payload: Mapping[str, object]) -> None:
        content = json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        temporary = path.with_name(f".{path.name}.part")
        temporary.write_text(f"{content}\n", encoding="utf-8", newline="\n")
        temporary.replace(path)


__all__ = ["JsonSelectionAuditSink", "load_browser_selection_manifest"]
