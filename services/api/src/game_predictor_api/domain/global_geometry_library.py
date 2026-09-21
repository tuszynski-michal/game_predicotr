"""Immutable, game-neutral contracts for the shared shape-geometry library."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]

GLOBAL_GEOMETRY_PROFILE_SCHEMA_VERSION = "shape-geometry-global-profile-v1"
GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION = "shape-geometry-global-evidence-v1"
NORMALIZED_TEMPLATE_SCHEMA_VERSION = "shape-geometry-normalized-template-v1"
FRAME_APPEARANCE_SCHEMA_VERSION = "shape-geometry-frame-appearance-v1"
EVIDENCE_SUMMARY_SCHEMA_VERSION = "shape-geometry-evidence-summary-v1"
SUPPORTED_GEOMETRY_FAMILY = "framed_full_page_v2"

_GAME_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_TOKEN = re.compile(
    r"(?:anchor|boardid|crop|file|gameid|image|jpeg|layout|ocr|path|payout|pixel|sequence|symbol)"
)
_FRAME_SIDES = frozenset(("top", "right", "bottom", "left"))


class _FrozenDict(dict[str, JSONValue]):
    """A JSON-compatible dict that cannot be changed after canonicalization."""

    def __init__(self, values: Mapping[str, JSONValue]) -> None:
        dict.__init__(self, values)

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("global geometry snapshots are immutable")

    __delitem__ = _immutable
    __ior__ = _immutable  # type: ignore[assignment]
    __setitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable


class _FrozenList(list[JSONValue]):
    """A JSON-compatible list that cannot be changed after canonicalization."""

    def __init__(self, values: Sequence[JSONValue]) -> None:
        list.__init__(self, values)

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("global geometry snapshots are immutable")

    __delitem__ = _immutable
    __iadd__ = _immutable  # type: ignore[assignment]
    __imul__ = _immutable  # type: ignore[assignment]
    __setitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


class GlobalGeometryLibraryError(ValueError):
    """Stable domain error returned before a library write is attempted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GlobalGeometryLibraryConflictError(RuntimeError):
    """Stable conflict raised for an idempotency or concurrent-write conflict."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GlobalGeometryProfileStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class GlobalGeometryTopology:
    """Shared page and board topology; never a sequence position."""

    page_board_rows: int
    page_board_columns: int
    board_cell_rows: int
    board_cell_columns: int

    def __post_init__(self) -> None:
        if (
            self.page_board_rows,
            self.page_board_columns,
            self.board_cell_rows,
            self.board_cell_columns,
        ) != (3, 3, 3, 5):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_TOPOLOGY_UNSUPPORTED",
                "Shape geometry v2 accepts only the 3x3 page and 3x5 board topology.",
            )

    def to_dict(self) -> dict[str, int]:
        return {
            "pageBoardRows": self.page_board_rows,
            "pageBoardColumns": self.page_board_columns,
            "boardCellRows": self.board_cell_rows,
            "boardCellColumns": self.board_cell_columns,
        }


@dataclass(frozen=True, slots=True)
class GlobalGeometryEvidence:
    """A descriptor-only contribution to one immutable profile version."""

    source_game_ref: str
    evidence_checksum_sha256: str
    evidence_payload: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class GlobalGeometryCandidate:
    """A fully canonicalized candidate suitable for idempotent persistence."""

    geometry_family: str
    topology: GlobalGeometryTopology
    normalized_template: dict[str, JSONValue]
    frame_appearance: dict[str, JSONValue]
    evidence_summary: dict[str, JSONValue]
    evidence: tuple[GlobalGeometryEvidence, ...]
    profile_checksum_sha256: str

    def command_sha256(self) -> str:
        return _sha256(
            {
                "operation": "create_global_geometry_candidate",
                "profileChecksumSha256": self.profile_checksum_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class GlobalGeometryProfileVersion:
    id: UUID
    profile_number: int
    status: GlobalGeometryProfileStatus
    geometry_family: str
    topology: GlobalGeometryTopology
    normalized_template: dict[str, JSONValue]
    frame_appearance: dict[str, JSONValue]
    evidence_summary: dict[str, JSONValue]
    profile_checksum_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GlobalGeometryProfileWithEvidence:
    """One persisted profile paired with every descriptor-only evidence row."""

    profile: GlobalGeometryProfileVersion
    evidence: tuple[GlobalGeometryEvidence, ...]


def global_geometry_profile_preflight_reference(
    profile: GlobalGeometryProfileVersion,
) -> dict[str, JSONValue]:
    """Return the descriptor-only, active profile reference safe to pin to a job."""

    topology, template, appearance = validate_global_geometry_profile_for_preflight(profile)
    return {
        "profileId": str(profile.id),
        "profileNumber": profile.profile_number,
        "profileChecksumSha256": profile.profile_checksum_sha256,
        "profileDescriptorChecksumSha256": global_geometry_profile_descriptor_checksum(
            geometry_family=profile.geometry_family,
            topology=topology,
            normalized_template=template,
            frame_appearance=appearance,
        ),
        "geometryFamily": profile.geometry_family,
        "topology": cast(JSONValue, topology.to_dict()),
        "normalizedTemplate": _freeze_object(template),
        "frameAppearance": _freeze_object(appearance),
    }


def validate_global_geometry_profile_for_preflight(
    profile: GlobalGeometryProfileVersion,
) -> tuple[GlobalGeometryTopology, dict[str, JSONValue], dict[str, JSONValue]]:
    """Validate the immutable descriptor subset available on a stored profile."""

    if not isinstance(profile.id, UUID) or not isinstance(profile.profile_number, int) or (
        isinstance(profile.profile_number, bool) or profile.profile_number < 1
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PROFILE_REFERENCE_INVALID",
            "The global geometry profile has an invalid immutable identity.",
        )
    if profile.status is not GlobalGeometryProfileStatus.ACTIVE:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PROFILE_NOT_ACTIVE",
            "Only an active global geometry profile can be pinned to a preflight.",
        )
    if not isinstance(profile.topology, GlobalGeometryTopology):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TOPOLOGY_UNSUPPORTED",
            "The global geometry profile has an unsupported topology.",
        )
    if not isinstance(profile.profile_checksum_sha256, str) or not _CHECKSUM.fullmatch(
        profile.profile_checksum_sha256
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PROFILE_CHECKSUM_INVALID",
            "The global geometry profile checksum is invalid.",
        )
    template, appearance = validate_global_geometry_profile_descriptor(
        geometry_family=profile.geometry_family,
        topology=profile.topology,
        normalized_template=profile.normalized_template,
        frame_appearance=profile.frame_appearance,
    )
    summary = _canonical_object(profile.evidence_summary, field="evidence_summary")
    _validate_evidence_summary(summary)
    return profile.topology, template, appearance


def validate_global_geometry_profile_integrity(
    stored: GlobalGeometryProfileWithEvidence,
) -> GlobalGeometryCandidate:
    """Rebuild a persisted profile before it may be selected for a new job."""

    profile = stored.profile
    validate_global_geometry_profile_for_preflight(profile)
    return canonicalize_global_geometry_candidate(
        GlobalGeometryCandidate(
            geometry_family=profile.geometry_family,
            topology=profile.topology,
            normalized_template=profile.normalized_template,
            frame_appearance=profile.frame_appearance,
            evidence_summary=profile.evidence_summary,
            evidence=stored.evidence,
            profile_checksum_sha256=profile.profile_checksum_sha256,
        )
    )


def global_geometry_profile_descriptor_checksum(
    *,
    geometry_family: object,
    topology: GlobalGeometryTopology,
    normalized_template: Mapping[str, object],
    frame_appearance: Mapping[str, object],
) -> str:
    """Bind the descriptor subset copied into the immutable job snapshot."""

    template, appearance = validate_global_geometry_profile_descriptor(
        geometry_family=geometry_family,
        topology=topology,
        normalized_template=normalized_template,
        frame_appearance=frame_appearance,
    )
    return _sha256(
        {
            "schemaVersion": "shape-geometry-preflight-descriptor-v1",
            "geometryFamily": geometry_family,
            "topology": topology.to_dict(),
            "normalizedTemplate": template,
            "frameAppearance": appearance,
        }
    )


def validate_global_geometry_profile_descriptor(
    *,
    geometry_family: object,
    topology: GlobalGeometryTopology,
    normalized_template: Mapping[str, object],
    frame_appearance: Mapping[str, object],
) -> tuple[dict[str, JSONValue], dict[str, JSONValue]]:
    """Validate the game-neutral descriptor subset needed by local preflight."""

    if geometry_family != SUPPORTED_GEOMETRY_FAMILY:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_FAMILY_UNSUPPORTED",
            "The global geometry profile uses an unsupported geometry family.",
        )
    template = _canonical_object(normalized_template, field="normalized_template")
    appearance = _canonical_object(frame_appearance, field="frame_appearance")
    _validate_template(template, topology)
    _validate_frame_appearance(appearance)
    return template, appearance


def build_global_geometry_candidate(
    *,
    geometry_family: str,
    topology: GlobalGeometryTopology,
    normalized_template: Mapping[str, object],
    frame_appearance: Mapping[str, object],
    evidence_summary: Mapping[str, object],
    evidence: Sequence[tuple[str, Mapping[str, object]]],
) -> GlobalGeometryCandidate:
    """Canonicalize descriptor-only evidence and bind the complete profile checksum."""

    if geometry_family != SUPPORTED_GEOMETRY_FAMILY:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_FAMILY_UNSUPPORTED",
            "The shared shape-geometry library accepts only framed_full_page_v2.",
        )
    template = _canonical_object(normalized_template, field="normalized_template")
    appearance = _canonical_object(frame_appearance, field="frame_appearance")
    summary = _canonical_object(evidence_summary, field="evidence_summary")
    _validate_template(template, topology)
    _validate_frame_appearance(appearance)
    _validate_evidence_summary(summary)
    canonical_evidence = tuple(
        sorted(
            (_build_evidence(source_game_ref, payload) for source_game_ref, payload in evidence),
            key=lambda item: (item.source_game_ref, item.evidence_checksum_sha256),
        )
    )
    if not canonical_evidence:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_EMPTY",
            "A global geometry candidate requires at least one descriptor-only evidence sample.",
        )
    if len({item.evidence_checksum_sha256 for item in canonical_evidence}) != len(
        canonical_evidence
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_DUPLICATE",
            "A candidate cannot contain duplicate evidence checksums.",
        )
    _validate_summary_against_evidence(summary, canonical_evidence)
    checksum = _sha256(
        {
            "schemaVersion": GLOBAL_GEOMETRY_PROFILE_SCHEMA_VERSION,
            "geometryFamily": geometry_family,
            "topology": topology.to_dict(),
            "normalizedTemplate": template,
            "frameAppearance": appearance,
            "evidenceSummary": summary,
            "evidence": [
                {
                    "sourceGameRef": item.source_game_ref,
                    "evidenceChecksumSha256": item.evidence_checksum_sha256,
                    "evidencePayload": item.evidence_payload,
                }
                for item in canonical_evidence
            ],
        }
    )
    return GlobalGeometryCandidate(
        geometry_family=geometry_family,
        topology=topology,
        normalized_template=_freeze_object(template),
        frame_appearance=_freeze_object(appearance),
        evidence_summary=_freeze_object(summary),
        evidence=canonical_evidence,
        profile_checksum_sha256=checksum,
    )


def _build_evidence(
    source_game_ref: str, payload: Mapping[str, object]
) -> GlobalGeometryEvidence:
    if not _GAME_REF.fullmatch(source_game_ref):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_SOURCE_GAME_REF_INVALID",
            "source_game_ref must be a short, lowercase provenance label.",
        )
    canonical_payload = _canonical_object(payload, field="evidence_payload")
    _validate_evidence_payload(canonical_payload)
    checksum = _sha256(
        {
            "schemaVersion": GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
            "sourceGameRef": source_game_ref,
            "evidencePayload": canonical_payload,
        }
    )
    return GlobalGeometryEvidence(
        source_game_ref=source_game_ref,
        evidence_checksum_sha256=checksum,
        evidence_payload=_freeze_object(canonical_payload),
    )


def canonicalize_global_geometry_candidate(
    candidate: GlobalGeometryCandidate,
) -> GlobalGeometryCandidate:
    """Rebuild a caller-supplied candidate before it crosses the persistence boundary."""

    if not isinstance(candidate.topology, GlobalGeometryTopology):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_CANDIDATE_INVALID",
            "A global geometry candidate has an invalid topology object.",
        )
    try:
        raw_evidence = tuple(
            (item.source_game_ref, item.evidence_payload) for item in candidate.evidence
        )
    except AttributeError as error:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_CANDIDATE_INVALID",
            "A global geometry candidate has invalid evidence entries.",
        ) from error
    rebuilt = build_global_geometry_candidate(
        geometry_family=candidate.geometry_family,
        topology=candidate.topology,
        normalized_template=candidate.normalized_template,
        frame_appearance=candidate.frame_appearance,
        evidence_summary=candidate.evidence_summary,
        evidence=raw_evidence,
    )
    if tuple(
        (item.source_game_ref, item.evidence_checksum_sha256) for item in candidate.evidence
    ) != tuple(
        (item.source_game_ref, item.evidence_checksum_sha256) for item in rebuilt.evidence
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_CHECKSUM_MISMATCH",
            "The global geometry evidence differs from its supplied checksum.",
        )
    if candidate.profile_checksum_sha256 != rebuilt.profile_checksum_sha256:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PROFILE_CHECKSUM_MISMATCH",
            "The global geometry candidate differs from its supplied profile checksum.",
        )
    return rebuilt


def _validate_template(
    payload: Mapping[str, JSONValue], topology: GlobalGeometryTopology
) -> None:
    _require_exact_fields(
        payload,
        {"schemaVersion", "topology", "frameQuad", "aspectRatioRange"},
        code="GLOBAL_GEOMETRY_TEMPLATE_FIELDS_INVALID",
        name="normalized template",
    )
    if payload.get("schemaVersion") != NORMALIZED_TEMPLATE_SCHEMA_VERSION:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_SCHEMA_INVALID",
            "The normalized template has an unsupported schema version.",
        )
    if payload.get("topology") != topology.to_dict():
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_TOPOLOGY_MISMATCH",
            "The normalized template topology differs from the profile topology.",
        )
    frame_quad = payload.get("frameQuad")
    if not isinstance(frame_quad, list) or len(frame_quad) != 4:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_QUAD_INVALID",
            "The normalized template must provide exactly four frame points.",
        )
    points: list[tuple[float, float]] = []
    for point in frame_quad:
        if (
            not isinstance(point, list)
            or len(point) != 2
        ):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_TEMPLATE_QUAD_INVALID",
                "Each normalized frame point must contain two finite numeric coordinates.",
            )
        coordinates = [
            float(value)
            for value in point
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        if len(coordinates) != 2 or any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in coordinates
        ):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_TEMPLATE_QUAD_INVALID",
                "Normalized frame coordinates must be finite values between zero and one.",
            )
        points.append((coordinates[0], coordinates[1]))
    _validate_canonical_frame_quad(points)
    aspect_ratio = payload.get("aspectRatioRange")
    if not isinstance(aspect_ratio, dict):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_ASPECT_RATIO_INVALID",
            "The normalized template must contain an aspect-ratio range.",
        )
    _require_exact_fields(
        aspect_ratio,
        {"minimum", "maximum"},
        code="GLOBAL_GEOMETRY_TEMPLATE_ASPECT_RATIO_INVALID",
        name="aspect-ratio range",
    )
    minimum = aspect_ratio.get("minimum")
    maximum = aspect_ratio.get("maximum")
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int | float)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int | float)
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_ASPECT_RATIO_INVALID",
            "The aspect-ratio range must be finite, positive and ordered.",
        )
    minimum_value = float(minimum)
    maximum_value = float(maximum)
    if (
        not math.isfinite(minimum_value)
        or not math.isfinite(maximum_value)
        or minimum_value <= 0.0
        or minimum_value > maximum_value
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_ASPECT_RATIO_INVALID",
            "The aspect-ratio range must be finite, positive and ordered.",
        )


def _validate_frame_appearance(payload: Mapping[str, JSONValue]) -> None:
    _require_exact_fields(
        payload,
        {"schemaVersion", "sides"},
        code="GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
        name="frame appearance",
    )
    if payload.get("schemaVersion") != FRAME_APPEARANCE_SCHEMA_VERSION:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_FRAME_APPEARANCE_SCHEMA_INVALID",
            "The frame appearance has an unsupported schema version.",
        )
    sides = payload.get("sides")
    if not isinstance(sides, dict) or not sides:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
            "The frame appearance must describe at least one visible frame side.",
        )
    if not set(sides).issubset(_FRAME_SIDES):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
            "Frame appearance sides must be top, right, bottom or left.",
        )
    for side_payload in sides.values():
        if not isinstance(side_payload, dict):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                "Each frame side must contain descriptor statistics.",
            )
        _require_exact_fields(
            side_payload,
            {"clusters", "contrast", "continuity"},
            code="GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
            name="frame-side descriptor",
        )
        clusters = side_payload.get("clusters")
        contrast = side_payload.get("contrast")
        continuity = side_payload.get("continuity")
        if not isinstance(clusters, list) or not clusters or not isinstance(contrast, dict):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                "Each visible frame side requires color clusters and contrast statistics.",
            )
        for cluster in clusters:
            if not isinstance(cluster, dict):
                raise GlobalGeometryLibraryError(
                    "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                    "Each frame color cluster must be an object.",
                )
            _require_exact_fields(
                cluster,
                {"lab", "hsv"},
                code="GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                name="frame color cluster",
            )
            _validate_numeric_vector(
                cluster["lab"],
                length=3,
                minimums=(0.0, -128.0, -128.0),
                maximums=(100.0, 127.0, 127.0),
                name="Lab color descriptor",
            )
            _validate_numeric_vector(
                cluster["hsv"],
                length=3,
                minimums=(0.0, 0.0, 0.0),
                maximums=(360.0, 1.0, 1.0),
                name="HSV color descriptor",
            )
        _require_exact_fields(
            contrast,
            {"minimum", "median", "maximum"},
            code="GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
            name="frame contrast descriptor",
        )
        contrast_values = _numeric_mapping_values(contrast, name="frame contrast descriptor")
        if (
            contrast_values["minimum"] < 0.0
            or contrast_values["minimum"] > contrast_values["median"]
            or contrast_values["median"] > contrast_values["maximum"]
        ):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                "Frame contrast must be non-negative and ordered minimum, median, maximum.",
            )
        if (
            not isinstance(continuity, int | float)
            or isinstance(continuity, bool)
            or not math.isfinite(float(continuity))
            or not 0.0 <= float(continuity) <= 1.0
        ):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_FRAME_APPEARANCE_INVALID",
                "Frame continuity must be a finite value between zero and one.",
            )


def _validate_evidence_summary(payload: Mapping[str, JSONValue]) -> None:
    _require_exact_fields(
        payload,
        {
            "schemaVersion",
            "fullSourceCount",
            "partialSourceCount",
            "sourceGameRefs",
            "extractorVersion",
            "qualityMetrics",
        },
        code="GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
        name="evidence summary",
    )
    if payload.get("schemaVersion") != EVIDENCE_SUMMARY_SCHEMA_VERSION:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_SCHEMA_INVALID",
            "The evidence summary has an unsupported schema version.",
        )
    for key in ("fullSourceCount", "partialSourceCount"):
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
                "Evidence counts must be non-negative integers.",
            )
    source_game_refs = payload.get("sourceGameRefs")
    if not isinstance(source_game_refs, list) or not source_game_refs:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
            "Evidence summary must name at least one source-game provenance label.",
        )
    if any(
        not isinstance(value, str) or not _GAME_REF.fullmatch(value)
        for value in source_game_refs
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
            "Evidence summary has an invalid source-game provenance label.",
        )
    if len(set(source_game_refs)) != len(source_game_refs):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
            "Evidence summary cannot repeat a source-game provenance label.",
        )
    if not isinstance(payload.get("extractorVersion"), str) or not payload["extractorVersion"]:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
            "Evidence summary must identify its geometry extractor version.",
        )
    quality_metrics = payload["qualityMetrics"]
    if not isinstance(quality_metrics, dict):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_INVALID",
            "Evidence summary quality metrics must be an object of finite numbers.",
        )
    _numeric_mapping_values(quality_metrics, name="evidence summary quality metrics")


def _validate_summary_against_evidence(
    summary: Mapping[str, JSONValue], evidence: Sequence[GlobalGeometryEvidence]
) -> None:
    full_count = sum(item.evidence_payload["coverageKind"] == "full" for item in evidence)
    partial_count = sum(item.evidence_payload["coverageKind"] == "partial" for item in evidence)
    if (
        summary["fullSourceCount"] != full_count
        or summary["partialSourceCount"] != partial_count
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_COUNT_MISMATCH",
            "Evidence summary counts must equal the descriptor-only evidence samples.",
        )
    source_game_refs = summary["sourceGameRefs"]
    if not isinstance(source_game_refs, list) or set(source_game_refs) != {
        item.source_game_ref for item in evidence
    }:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SUMMARY_SOURCE_MISMATCH",
            "Evidence summary provenance must equal the evidence provenance labels.",
        )


def _validate_evidence_payload(payload: Mapping[str, JSONValue]) -> None:
    _require_exact_fields(
        payload,
        {"schemaVersion", "coverageKind", "visibleFrameSides", "extractorVersion", "metrics"},
        code="GLOBAL_GEOMETRY_EVIDENCE_FIELDS_INVALID",
        name="evidence descriptor",
    )
    if payload.get("schemaVersion") != GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_INVALID",
            "Evidence has an unsupported schema version.",
        )
    if payload.get("coverageKind") not in ("full", "partial"):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_COVERAGE_INVALID",
            "Evidence coverage must be full or partial.",
        )
    sides = payload.get("visibleFrameSides")
    if not isinstance(sides, list) or not sides or not set(sides).issubset(_FRAME_SIDES):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_VISIBLE_SIDES_INVALID",
            "Evidence must name one or more visible frame sides.",
        )
    if len(set(sides)) != len(sides):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_VISIBLE_SIDES_INVALID",
            "Evidence cannot name a frame side more than once.",
        )
    if payload["coverageKind"] == "full" and set(sides) != _FRAME_SIDES:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_FULL_COVERAGE_INCOMPLETE",
            "Full evidence must confirm all four frame sides.",
        )
    if not isinstance(payload.get("extractorVersion"), str) or not payload["extractorVersion"]:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_EXTRACTOR_VERSION_MISSING",
            "Evidence must identify its geometry extractor version.",
        )
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_EVIDENCE_METRICS_INVALID",
            "Evidence must contain descriptor-only metrics.",
        )
    _numeric_mapping_values(metrics, name="evidence descriptor metrics")


def _require_exact_fields(
    payload: Mapping[str, JSONValue],
    expected: set[str],
    *,
    code: str,
    name: str,
) -> None:
    if set(payload) != expected:
        raise GlobalGeometryLibraryError(
            code,
            f"The {name} has fields outside its descriptor-only contract.",
        )


def _validate_canonical_frame_quad(points: Sequence[tuple[float, float]]) -> None:
    sums = tuple(point[0] + point[1] for point in points)
    differences = tuple(point[0] - point[1] for point in points)
    indexes = (
        min(range(4), key=sums.__getitem__),
        max(range(4), key=differences.__getitem__),
        max(range(4), key=sums.__getitem__),
        min(range(4), key=differences.__getitem__),
    )
    if len(set(indexes)) != 4:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_QUAD_ORDER_INVALID",
            "The normalized frame quad does not have four unambiguous corners.",
        )
    ordered = tuple(points[index] for index in indexes)
    if _cross_product(ordered[0], ordered[1], ordered[2]) < 0.0:
        ordered = (ordered[0], ordered[3], ordered[2], ordered[1])
    if tuple(points) != ordered:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_QUAD_ORDER_INVALID",
            "The normalized frame quad must be ordered "
            "top-left, top-right, bottom-right, bottom-left.",
        )
    cross_products = [
        _cross_product(points[index], points[(index + 1) % 4], points[(index + 2) % 4])
        for index in range(4)
    ]
    if any(value <= 1e-9 for value in cross_products):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_QUAD_ORDER_INVALID",
            "The normalized frame quad must be strictly convex and canonically ordered.",
        )
    area = abs(
        sum(
            points[index][0] * points[(index + 1) % 4][1]
            - points[(index + 1) % 4][0] * points[index][1]
            for index in range(4)
        )
        / 2.0
    )
    if area <= 1e-9:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_TEMPLATE_QUAD_DEGENERATE",
            "The normalized frame quad must have non-zero area.",
        )


def _cross_product(
    first: tuple[float, float], second: tuple[float, float], third: tuple[float, float]
) -> float:
    return (second[0] - first[0]) * (third[1] - second[1]) - (
        second[1] - first[1]
    ) * (third[0] - second[0])


def _validate_numeric_vector(
    value: JSONValue,
    *,
    length: int,
    minimums: tuple[float, ...],
    maximums: tuple[float, ...],
    name: str,
) -> None:
    if not isinstance(value, list) or len(value) != length:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_NUMERIC_DESCRIPTOR_INVALID",
            f"The {name} must contain exactly {length} numeric values.",
        )
    values = [
        float(item)
        for item in value
        if isinstance(item, int | float) and not isinstance(item, bool)
    ]
    if len(values) != length or any(
        not math.isfinite(item)
        or item < minimum
        or item > maximum
        for item, minimum, maximum in zip(values, minimums, maximums, strict=True)
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_NUMERIC_DESCRIPTOR_INVALID",
            f"The {name} contains an invalid numeric value.",
        )


def _numeric_mapping_values(
    payload: Mapping[str, JSONValue], *, name: str
) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in payload.items():
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_NUMERIC_DESCRIPTOR_INVALID",
                f"The {name} must contain only finite numeric values.",
            )
        values[key] = float(value)
    return values


def _canonical_object(payload: Mapping[str, object], *, field: str) -> dict[str, JSONValue]:
    value = _canonical_json(payload, field=field)
    if not isinstance(value, dict):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PAYLOAD_OBJECT_REQUIRED",
            f"{field} must be a JSON object.",
        )
    return value


def _freeze_object(payload: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    frozen = _freeze_json(dict(payload))
    assert isinstance(frozen, dict)
    return frozen


def freeze_global_geometry_snapshot(payload: Mapping[str, object]) -> dict[str, JSONValue]:
    """Return a deeply isolated, immutable JSON object read from persistence."""

    return _freeze_object(_canonical_object(payload, field="stored_global_geometry_snapshot"))


def _freeze_json(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList([_freeze_json(item) for item in value])
    return value


def _canonical_json(value: object, *, field: str, path: str = "$") -> JSONValue:
    if value is None or isinstance(value, bool | str):
        if isinstance(value, str) and len(value) > 512:
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_PAYLOAD_VALUE_TOO_LONG",
                f"{field} has a text value that is too long at {path}.",
            )
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_PAYLOAD_NUMBER_INVALID",
                f"{field} has a non-finite number at {path}.",
            )
        return value
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise GlobalGeometryLibraryError(
                    "GLOBAL_GEOMETRY_PAYLOAD_KEY_INVALID",
                    f"{field} has a non-text key at {path}.",
                )
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if _FORBIDDEN_TOKEN.search(normalized):
                raise GlobalGeometryLibraryError(
                    "GLOBAL_GEOMETRY_PAYLOAD_FORBIDDEN_FIELD",
                    f"{field} contains forbidden field {key!r} at {path}.",
                )
            result[key] = _canonical_json(value[key], field=field, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        if len(value) > 2_000:
            raise GlobalGeometryLibraryError(
                "GLOBAL_GEOMETRY_PAYLOAD_TOO_LARGE",
                f"{field} has too many values at {path}.",
            )
        return [
            _canonical_json(item, field=field, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise GlobalGeometryLibraryError(
        "GLOBAL_GEOMETRY_PAYLOAD_VALUE_INVALID",
        f"{field} has a value that is not JSON-compatible at {path}.",
    )


def _sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )
    if len(encoded) > 65_536:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PAYLOAD_TOO_LARGE",
            "A global geometry profile exceeds the 64 KiB descriptor-only limit.",
        )
    return hashlib.sha256(encoded).hexdigest()


def validate_checksum(checksum: str) -> None:
    if not _CHECKSUM.fullmatch(checksum):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_CHECKSUM_INVALID",
            "A global geometry checksum must be a lowercase SHA-256 digest.",
        )
