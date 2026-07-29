"""Deterministic review queue for missing local anchors and held-out boards."""

from __future__ import annotations

import hashlib
import json
import statistics
import threading
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from .cell_grid_golden import (
    BoardCandidate,
    CellGridGolden,
    CellGridGoldenError,
    CellGridGoldenReview,
    GridReviewEntry,
    _cut_cells,
    _load_json,
    _load_source_bundle,
    _mapping,
    _optional_text,
    _safe_relative_path,
    _source_quad,
    _write_atomic,
)
from .grid_calibration import FloatQuad, LocalOffsets, apply_local_corner_offsets
from .local_grid_calibration import (
    BASIS_VERSION,
    PROFILE_SET_VERSION,
    local_bounding_frame,
)

REVIEW_VERSION = "local-grid-calibration-review-v2"
SELECTION_VERSION = "missing-source-plus-heldout-v1"
SUGGESTION_VERSION = "local-image-frame-suggestion-v1"
MISSING_ANCHOR_PURPOSE: Literal["missing_anchor"] = "missing_anchor"
HELDOUT_PURPOSE: Literal["heldout"] = "heldout"
ReviewPurpose = Literal["missing_anchor", "heldout"]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CellGridGoldenError(
            "LOCAL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise CellGridGoldenError(
            "LOCAL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CellGridGoldenError(
            "LOCAL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be a non-negative integer.",
        )
    return value


def _profile_offsets(
    profiles: Mapping[str, object],
) -> tuple[dict[str, tuple[int, LocalOffsets]], LocalOffsets]:
    if (
        profiles.get("profileSetVersion") != PROFILE_SET_VERSION
        or profiles.get("basisVersion") != BASIS_VERSION
        or profiles.get("trainingAllowed") is not False
    ):
        raise CellGridGoldenError(
            "LOCAL_GRID_REVIEW_PROFILE_SET_INVALID",
            "The local profile set is unsupported.",
        )
    by_source: dict[str, tuple[int, LocalOffsets]] = {}
    all_offsets: list[LocalOffsets] = []
    for index, raw in enumerate(_sequence(profiles.get("profiles"), "profiles")):
        item = _mapping(raw, f"profiles[{index}]")
        source = _sha256(
            item.get("sourceImageChecksumSha256"),
            f"profiles[{index}].sourceImageChecksumSha256",
        )
        anchor = _mapping(item.get("anchor"), f"profiles[{index}].anchor")
        offsets_raw = _sequence(
            anchor.get("localCornerOffsets"),
            f"profiles[{index}].anchor.localCornerOffsets",
        )
        if len(offsets_raw) != 4:
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_PROFILE_SET_INVALID",
                "Every local profile must contain four offsets.",
            )
        offsets: list[tuple[float, float]] = []
        for offset_index, raw_offset in enumerate(offsets_raw):
            offset = _mapping(
                raw_offset,
                f"profiles[{index}].anchor.localCornerOffsets[{offset_index}]",
            )
            u = offset.get("u")
            v = offset.get("v")
            if (
                not isinstance(u, int | float)
                or isinstance(u, bool)
                or not isinstance(v, int | float)
                or isinstance(v, bool)
            ):
                raise CellGridGoldenError(
                    "LOCAL_GRID_REVIEW_PROFILE_SET_INVALID",
                    "Local profile offsets must be numeric.",
                )
            offsets.append((float(u), float(v)))
        typed_offsets = cast(LocalOffsets, tuple(offsets))
        by_source[source] = (
            _integer(anchor.get("boardPosition"), "anchor.boardPosition"),
            typed_offsets,
        )
        all_offsets.append(typed_offsets)
    if not all_offsets:
        raise CellGridGoldenError(
            "LOCAL_GRID_REVIEW_PROFILE_SET_INVALID",
            "At least one accepted source profile is required.",
        )
    median_offsets = cast(
        LocalOffsets,
        tuple(
            (
                statistics.median(offsets[corner][0] for offsets in all_offsets),
                statistics.median(offsets[corner][1] for offsets in all_offsets),
            )
            for corner in range(4)
        ),
    )
    return by_source, median_offsets


def _detection_boxes(
    detection_report: Mapping[str, object],
) -> dict[tuple[str, int], tuple[int, int, int, int]]:
    boxes: dict[tuple[str, int], tuple[int, int, int, int]] = {}
    for image_index, raw in enumerate(_sequence(detection_report.get("detections"), "detections")):
        item = _mapping(raw, f"detections[{image_index}]")
        source = _sha256(
            item.get("sourceChecksumSha256"),
            f"detections[{image_index}].sourceChecksumSha256",
        )
        result = _mapping(item.get("result"), f"detections[{image_index}].result")
        for board_index, raw_board in enumerate(
            _sequence(result.get("boards"), f"detections[{image_index}].result.boards")
        ):
            board = _mapping(
                raw_board,
                f"detections[{image_index}].result.boards[{board_index}]",
            )
            position = _integer(board.get("positionIndex"), "board.positionIndex")
            value = _mapping(board.get("boundingBox"), "board.boundingBox")
            box = (
                _integer(value.get("x"), "board.boundingBox.x"),
                _integer(value.get("y"), "board.boundingBox.y"),
                _integer(value.get("width"), "board.boundingBox.width"),
                _integer(value.get("height"), "board.boundingBox.height"),
            )
            boxes[(source, position)] = box
    return boxes


def _selection(
    candidates: tuple[BoardCandidate, ...],
    *,
    profiles: Mapping[str, tuple[int, LocalOffsets]],
    median_offsets: LocalOffsets,
    boxes: Mapping[tuple[str, int], tuple[int, int, int, int]],
) -> tuple[
    tuple[GridReviewEntry, ...],
    dict[str, ReviewPurpose],
]:
    candidates_by_source: dict[str, list[BoardCandidate]] = {}
    for candidate in candidates:
        candidates_by_source.setdefault(
            candidate.source_image_checksum_sha256,
            [],
        ).append(candidate)
    selected: list[tuple[BoardCandidate, ReviewPurpose, LocalOffsets]] = []
    for source in sorted(set(candidates_by_source) - set(profiles)):
        source_candidates = sorted(
            candidates_by_source[source],
            key=lambda candidate: (
                abs(candidate.board_position - 4),
                candidate.board_position,
                candidate.observation_id,
            ),
        )
        selected.append((source_candidates[0], MISSING_ANCHOR_PURPOSE, median_offsets))

    heldout_sources: set[str] = set()
    for position in range(9):
        pool = [
            candidate
            for candidate in candidates
            if candidate.source_image_checksum_sha256 in profiles
            and candidate.source_image_checksum_sha256 not in heldout_sources
            and candidate.board_position == position
            and profiles[candidate.source_image_checksum_sha256][0] != position
        ]
        if not pool:
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_HELDOUT_INSUFFICIENT",
                f"No disjoint held-out source is available for position {position}.",
            )
        choice = min(
            pool,
            key=lambda candidate: hashlib.sha256(
                f"{SELECTION_VERSION}\0{position}\0{candidate.observation_id}".encode()
            ).hexdigest(),
        )
        heldout_sources.add(choice.source_image_checksum_sha256)
        selected.append(
            (
                choice,
                HELDOUT_PURPOSE,
                profiles[choice.source_image_checksum_sha256][1],
            )
        )

    entries: list[GridReviewEntry] = []
    purposes: dict[str, ReviewPurpose] = {}
    for index, (candidate, purpose, offsets) in enumerate(selected):
        box = boxes.get((candidate.source_image_checksum_sha256, candidate.board_position))
        if box is None:
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_DETECTION_MISSING",
                "A selected review board has no detector bounding frame.",
            )
        entries.append(
            GridReviewEntry(
                selection_index=index,
                candidate=candidate,
                source_quad=cast(
                    FloatQuad,
                    tuple(
                        (float(point.x), float(point.y))
                        for point in apply_local_corner_offsets(
                            local_bounding_frame(box),
                            offsets,
                        )
                    ),
                ),
                v1_cut_cell_indexes=(),
                v1_impact_reviewed=False,
                review_status="pending",
                reviewed_by=None,
                decision_revision=0,
                line_source="human-draft",
            )
        )
        purposes[candidate.observation_id] = purpose
    return tuple(entries), purposes


class LocalGridCalibrationReview(CellGridGoldenReview):
    """Reuse the perspective editor for a deterministic corrective queue."""

    def __init__(
        self,
        *,
        repository_root: Path,
        manifest_path: Path,
        annotations_path: Path,
        crop_report_path: Path,
        crop_root: Path,
        profiles_path: Path,
        detection_report_path: Path,
        output_path: Path,
    ) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.manifest_path = manifest_path.resolve(strict=True)
        self.annotations_path = annotations_path.resolve(strict=True)
        self.crop_report_path = crop_report_path.resolve(strict=True)
        self.crop_root = crop_root.resolve(strict=True)
        self.output_path = output_path.resolve()
        self.profiles_path = profiles_path.resolve(strict=True)
        self.detection_report_path = detection_report_path.resolve(strict=True)
        manifest_bytes, manifest = _load_json(self.manifest_path, "corpusManifest")
        _, self.source_root = _safe_relative_path(
            self.repository_root,
            manifest.get("rootPath"),
            "corpusManifest.rootPath",
        )
        profile_bytes, profile_document = _load_json(
            self.profiles_path,
            "localProfiles",
        )
        detection_bytes, detection_document = _load_json(
            self.detection_report_path,
            "detectionReport",
        )
        if (
            profile_document.get("corpusManifestSha256")
            != hashlib.sha256(manifest_bytes).hexdigest()
            or profile_document.get("detectorReportSha256")
            != hashlib.sha256(detection_bytes).hexdigest()
        ):
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_SOURCE_DRIFT",
                "Profiles differ from the manifest or detection report.",
            )
        self._profiles_sha256 = hashlib.sha256(profile_bytes).hexdigest()
        self._detection_sha256 = hashlib.sha256(detection_bytes).hexdigest()
        bundle = _load_source_bundle(
            self.repository_root,
            self.manifest_path,
            self.annotations_path,
            self.crop_report_path,
            self.crop_root,
        )
        profiles, median_offsets = _profile_offsets(profile_document)
        entries, purposes = _selection(
            bundle.candidates,
            profiles=profiles,
            median_offsets=median_offsets,
            boxes=_detection_boxes(detection_document),
        )
        self._purposes = purposes
        initial = CellGridGolden(
            corpus_id=bundle.corpus_id,
            corpus_manifest_sha256=bundle.corpus_manifest_sha256,
            golden_annotations_sha256=bundle.golden_annotations_sha256,
            crop_report_sha256=bundle.crop_report_sha256,
            source_groups=bundle.source_groups,
            review_revision=0,
            entries=entries,
        )
        self._lock = threading.RLock()
        if self.output_path.exists():
            _, existing = _load_json(self.output_path, "localGridReview")
            self._golden = self._parse_existing(existing, initial)
            if self._golden is initial:
                self._save()
        else:
            self._golden = initial
            self._save()

    def _document(self) -> dict[str, object]:
        value = self._golden.to_dict()
        entries = cast(list[dict[str, object]], value["entries"])
        for entry in entries:
            observation_id = cast(str, entry["observationId"])
            entry["purpose"] = self._purposes[observation_id]
            entry["suggestionVersion"] = SUGGESTION_VERSION
        selection = cast(dict[str, object], value["selection"])
        selection["selectionVersion"] = SELECTION_VERSION
        selection["missingAnchorCount"] = sum(
            purpose == MISSING_ANCHOR_PURPOSE for purpose in self._purposes.values()
        )
        selection["heldoutCount"] = sum(
            purpose == HELDOUT_PURPOSE for purpose in self._purposes.values()
        )
        value["detectionReportSha256"] = self._detection_sha256
        value["goldenVersion"] = REVIEW_VERSION
        value["localProfileSetSha256"] = self._profiles_sha256
        return value

    def _parse_existing(
        self,
        value: Mapping[str, object],
        initial: CellGridGolden,
    ) -> CellGridGolden:
        if (
            value.get("goldenVersion") != REVIEW_VERSION
            or value.get("localProfileSetSha256") != self._profiles_sha256
            or value.get("detectionReportSha256") != self._detection_sha256
            or value.get("corpusManifestSha256") != initial.corpus_manifest_sha256
        ):
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_SOURCE_DRIFT",
                "Existing local review differs from its immutable sources.",
            )
        raw_entries = _sequence(value.get("entries"), "localReview.entries")
        if len(raw_entries) != len(initial.entries):
            raise CellGridGoldenError(
                "LOCAL_GRID_REVIEW_SELECTION_DRIFT",
                "Existing local review entry count differs.",
            )
        review_revision = _integer(value.get("reviewRevision"), "reviewRevision")
        if review_revision == 0 and all(
            _mapping(raw, f"localReview.entries[{index}]").get("reviewStatus") == "pending"
            and _mapping(raw, f"localReview.entries[{index}]").get("decisionRevision") == 0
            and _mapping(raw, f"localReview.entries[{index}]").get("reviewedBy") is None
            for index, raw in enumerate(raw_entries)
        ):
            return initial
        parsed: list[GridReviewEntry] = []
        for index, (raw, expected) in enumerate(zip(raw_entries, initial.entries, strict=True)):
            item = _mapping(raw, f"localReview.entries[{index}]")
            immutable = expected.candidate.immutable_dict(index)
            if (
                any(item.get(key) != expected_value for key, expected_value in immutable.items())
                or item.get("purpose") != self._purposes[expected.candidate.observation_id]
                or item.get("suggestionVersion") != SUGGESTION_VERSION
            ):
                raise CellGridGoldenError(
                    "LOCAL_GRID_REVIEW_SELECTION_DRIFT",
                    f"Existing local review entry {index} differs.",
                )
            status = item.get("reviewStatus")
            if status not in {"pending", "accepted"}:
                raise CellGridGoldenError(
                    "LOCAL_GRID_REVIEW_CONTRACT_INVALID",
                    "Review status is invalid.",
                )
            reviewed_by = _optional_text(item.get("reviewedBy"), "entry.reviewedBy")
            parsed.append(
                replace(
                    expected,
                    source_quad=_source_quad(
                        item.get("sourceQuad"),
                        "entry.sourceQuad",
                        image_width=expected.candidate.source_image_width,
                        image_height=expected.candidate.source_image_height,
                    ),
                    v1_cut_cell_indexes=_cut_cells(
                        item.get("v1CutCellIndexes"),
                        "entry.v1CutCellIndexes",
                    ),
                    v1_impact_reviewed=item.get("v1ImpactReviewed") is True,
                    review_status=cast(Literal["pending", "accepted"], status),
                    reviewed_by=reviewed_by,
                    decision_revision=_integer(
                        item.get("decisionRevision"),
                        "entry.decisionRevision",
                    ),
                    line_source=cast(
                        Literal[
                            "detected-quad-suggestion",
                            "human-draft",
                            "human-confirmed-detected-quad",
                            "human-adjusted",
                        ],
                        item.get("lineSource"),
                    ),
                )
            )
        return replace(
            initial,
            review_revision=review_revision,
            entries=tuple(parsed),
        )

    def _entry_payload(self, entry: GridReviewEntry) -> dict[str, object]:
        value = super()._entry_payload(entry)
        value["purpose"] = self._purposes[entry.candidate.observation_id]
        value["suggestionVersion"] = SUGGESTION_VERSION
        return value

    def _save(self) -> None:
        _write_atomic(self.output_path, _json_bytes(self._document()))


__all__ = [
    "HELDOUT_PURPOSE",
    "MISSING_ANCHOR_PURPOSE",
    "REVIEW_VERSION",
    "SELECTION_VERSION",
    "SUGGESTION_VERSION",
    "LocalGridCalibrationReview",
]
