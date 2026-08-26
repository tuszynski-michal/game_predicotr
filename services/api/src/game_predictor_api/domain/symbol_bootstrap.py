"""Deterministic symbol-catalog proposals from imported cell crops."""

from __future__ import annotations

import hashlib
import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from game_predictor_api.domain.catalog import CatalogConflictError, CatalogError

MAX_EXPECTED_SYMBOL_COUNT: Final = 32_767
_CODE_CHARS: Final = re.compile(r"[^A-Za-z0-9_-]+")


class SymbolBootstrapStatus(StrEnum):
    READY = "ready"
    CONFLICT = "conflict"
    APPLIED = "applied"


@dataclass(frozen=True, slots=True)
class SymbolBootstrapObservation:
    crop_checksum_sha256: str
    crop_relative_path: str
    predicted_symbol_code: str
    confidence: float


@dataclass(frozen=True, slots=True)
class SymbolBootstrapCandidate:
    candidate_id: str
    predicted_symbol_code: str
    proposed_code: str
    proposed_name: str
    sample_count: int
    mean_confidence: float
    representative_crop_relative_path: str
    representative_crop_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class SymbolBootstrapDefinition:
    mobile_code: int
    code: str
    name: str
    candidate_ids: tuple[str, ...]
    image_path: str


@dataclass(frozen=True, slots=True)
class SymbolBootstrapRun:
    id: UUID
    game_id: UUID
    expected_symbol_count: int
    detected_cluster_count: int
    source_state_sha256: str
    status: SymbolBootstrapStatus
    candidates: tuple[SymbolBootstrapCandidate, ...]
    resolution: tuple[SymbolBootstrapDefinition, ...]
    created_by: str
    created_at: datetime
    applied_at: datetime | None


@dataclass(frozen=True, slots=True)
class SymbolImageCandidate:
    observation_id: UUID
    crop_relative_path: str
    crop_checksum_sha256: str
    confidence: float

    @property
    def cursor_key(self) -> tuple[float, str, str]:
        return (-self.confidence, self.crop_checksum_sha256, str(self.observation_id))


@dataclass(frozen=True, slots=True)
class SymbolReferenceImage:
    """Checksum-bound image currently assigned to a catalog symbol.

    It may originate from a current cell observation or from the immutable
    bootstrap manifest that initially created the symbol catalog.
    """

    crop_relative_path: str
    crop_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class SymbolImageCandidatePage:
    items: tuple[SymbolImageCandidate, ...]
    next_cursor: str | None


def encode_symbol_candidate_cursor(
    *, game_id: UUID, symbol_id: UUID, key: tuple[float, str, str]
) -> str:
    raw = json.dumps(
        {"gameId": str(game_id), "key": list(key), "symbolId": str(symbol_id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_symbol_candidate_cursor(
    value: str, *, game_id: UUID, symbol_id: UUID
) -> tuple[float, str, str]:
    try:
        payload = json.loads(urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8"))
        key = payload["key"]
        if (
            payload["gameId"] != str(game_id)
            or payload["symbolId"] != str(symbol_id)
            or not isinstance(key, list)
            or len(key) != 3
            or not isinstance(key[0], int | float)
            or not isinstance(key[1], str)
            or not isinstance(key[2], str)
        ):
            raise ValueError
        return float(key[0]), key[1], key[2]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogConflictError(
            "SYMBOL_IMAGE_CURSOR_INVALID",
            "The symbol image candidate cursor is invalid for this scope.",
        ) from error


def validate_expected_symbol_count(value: int) -> int:
    if isinstance(value, bool) or not 1 <= value <= MAX_EXPECTED_SYMBOL_COUNT:
        raise CatalogError(
            "INVALID_EXPECTED_SYMBOL_COUNT",
            "expectedSymbolCount must be between 1 and 32767.",
            details={"field": "expectedSymbolCount"},
        )
    return value


def build_symbol_candidates(
    observations: tuple[SymbolBootstrapObservation, ...],
) -> tuple[str, tuple[SymbolBootstrapCandidate, ...]]:
    if not observations:
        raise CatalogConflictError(
            "SYMBOL_BOOTSTRAP_NO_CROPS",
            "No imported cell crops are available for symbol bootstrap.",
        )
    normalized = tuple(sorted(observations, key=_observation_key))
    source_state = _sha256(
        [
            {
                "checksum": item.crop_checksum_sha256,
                "confidence": round(item.confidence, 8),
                "path": item.crop_relative_path,
                "prediction": item.predicted_symbol_code,
            }
            for item in normalized
        ]
    )
    groups: dict[str, list[SymbolBootstrapObservation]] = defaultdict(list)
    for observation in normalized:
        _validate_observation(observation)
        groups[observation.predicted_symbol_code].append(observation)

    used_codes: set[str] = set()
    candidates: list[SymbolBootstrapCandidate] = []
    for index, predicted_code in enumerate(sorted(groups), start=1):
        samples = groups[predicted_code]
        representative = min(
            samples,
            key=lambda item: (
                -item.confidence,
                item.crop_checksum_sha256,
                item.crop_relative_path,
            ),
        )
        proposed_code = _unique_code(predicted_code, index, used_codes)
        candidate_id = _sha256(
            {
                "prediction": predicted_code,
                "samples": [
                    [item.crop_checksum_sha256, item.crop_relative_path] for item in samples
                ],
            }
        )
        candidates.append(
            SymbolBootstrapCandidate(
                candidate_id=candidate_id,
                predicted_symbol_code=predicted_code,
                proposed_code=proposed_code,
                proposed_name=_proposed_name(predicted_code, index),
                sample_count=len(samples),
                mean_confidence=round(
                    sum(item.confidence for item in samples) / len(samples),
                    6,
                ),
                representative_crop_relative_path=representative.crop_relative_path,
                representative_crop_checksum_sha256=(representative.crop_checksum_sha256),
            )
        )
    return source_state, tuple(candidates)


def automatic_definitions(
    candidates: tuple[SymbolBootstrapCandidate, ...],
    expected_symbol_count: int,
) -> tuple[SymbolBootstrapDefinition, ...]:
    validate_expected_symbol_count(expected_symbol_count)
    if len(candidates) != expected_symbol_count:
        return ()
    return tuple(
        SymbolBootstrapDefinition(
            mobile_code=index,
            code=candidate.proposed_code,
            name=candidate.proposed_name,
            candidate_ids=(candidate.candidate_id,),
            image_path=candidate.representative_crop_relative_path,
        )
        for index, candidate in enumerate(candidates, start=1)
    )


def validate_manual_definitions(
    candidates: tuple[SymbolBootstrapCandidate, ...],
    expected_symbol_count: int,
    definitions: tuple[SymbolBootstrapDefinition, ...],
) -> tuple[SymbolBootstrapDefinition, ...]:
    validate_expected_symbol_count(expected_symbol_count)
    if len(definitions) != expected_symbol_count:
        _resolution_error("Resolution must define exactly expectedSymbolCount symbols.")
    candidate_by_id = {item.candidate_id: item for item in candidates}
    known = set(candidate_by_id)
    used_codes: set[str] = set()
    used_mobile_codes: set[int] = set()
    referenced: set[str] = set()
    occurrences: defaultdict[str, int] = defaultdict(int)
    for definition in definitions:
        if (
            not 1 <= definition.mobile_code <= MAX_EXPECTED_SYMBOL_COUNT
            or definition.mobile_code in used_mobile_codes
            or not definition.candidate_ids
            or not definition.code
            or len(definition.code) > 64
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", definition.code)
            or definition.code in used_codes
            or not definition.name.strip()
            or len(definition.name.strip()) > 200
        ):
            _resolution_error("Resolution contains an invalid or duplicate symbol definition.")
        unknown = set(definition.candidate_ids) - known
        if unknown:
            _resolution_error("Resolution references an unknown candidate.")
        for candidate_id in definition.candidate_ids:
            occurrences[candidate_id] += 1
        referenced.update(definition.candidate_ids)
        used_codes.add(definition.code)
        used_mobile_codes.add(definition.mobile_code)
    if referenced != known:
        _resolution_error("Resolution must preserve every detected candidate.")
    if len(candidates) >= expected_symbol_count and any(
        value > 1 for value in occurrences.values()
    ):
        _resolution_error(
            "A candidate may be split only when fewer clusters than expected were detected."
        )
    return tuple(sorted(definitions, key=lambda item: item.mobile_code))


def _validate_observation(value: SymbolBootstrapObservation) -> None:
    if (
        not re.fullmatch(r"[0-9a-f]{64}", value.crop_checksum_sha256)
        or not value.crop_relative_path
        or not value.predicted_symbol_code.strip()
        or not 0 <= value.confidence <= 1
    ):
        raise CatalogConflictError(
            "SYMBOL_BOOTSTRAP_CROP_INVALID",
            "An imported crop does not match the symbol bootstrap contract.",
        )


def _observation_key(value: SymbolBootstrapObservation) -> tuple[str, str, str, float]:
    return (
        value.predicted_symbol_code,
        value.crop_checksum_sha256,
        value.crop_relative_path,
        value.confidence,
    )


def _unique_code(value: str, index: int, used: set[str]) -> str:
    base = _CODE_CHARS.sub("_", value.strip()).strip("_-")[:56] or f"SYMBOL_{index:02d}"
    if not base[0].isalnum():
        base = f"S_{base}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:58]}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _proposed_name(value: str, index: int) -> str:
    normalized = re.sub(r"[_-]+", " ", value).strip()
    return normalized.title() if normalized else f"Symbol {index}"


def _sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolution_error(message: str) -> None:
    raise CatalogConflictError("SYMBOL_BOOTSTRAP_RESOLUTION_INVALID", message)


__all__ = [
    "MAX_EXPECTED_SYMBOL_COUNT",
    "SymbolBootstrapCandidate",
    "SymbolBootstrapDefinition",
    "SymbolBootstrapObservation",
    "SymbolBootstrapRun",
    "SymbolBootstrapStatus",
    "SymbolImageCandidate",
    "SymbolImageCandidatePage",
    "SymbolReferenceImage",
    "automatic_definitions",
    "build_symbol_candidates",
    "decode_symbol_candidate_cursor",
    "encode_symbol_candidate_cursor",
    "validate_expected_symbol_count",
    "validate_manual_definitions",
]
