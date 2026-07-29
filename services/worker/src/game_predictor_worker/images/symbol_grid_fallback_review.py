"""Fail-closed review queue for boards rejected by symbol-grid refinement."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from .cell_grid_golden import (
    CellGridGolden,
    CellGridGoldenError,
    CellGridGoldenReview,
    GridReviewEntry,
    LineSource,
    _cut_cells,
    _load_json,
    _load_source_bundle,
    _mapping,
    _optional_text,
    _safe_relative_path,
    _source_quad,
    _write_atomic,
)

REVIEW_VERSION = "symbol-grid-fallback-review-v1"
SELECTION_VERSION = "all-strict-refinement-fallbacks-v1"
SUGGESTION_VERSION = "detector-quad-manual-correction-v1"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be a non-negative integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return value


def _fallbacks(
    report: Mapping[str, object],
) -> dict[tuple[str, int], Mapping[str, object]]:
    if (
        report.get("reportVersion") != "m5-full-symbol-grid-refinement-benchmark-v1"
        or report.get("geometrySource") != "detector"
        or report.get("trainingAllowed") is not False
    ):
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_REPORT_INVALID",
            "The strict detector-based refinement report is unsupported.",
        )
    selected: dict[tuple[str, int], Mapping[str, object]] = {}
    for index, raw in enumerate(_sequence(report.get("entries"), "refinementReport.entries")):
        entry = _mapping(raw, f"refinementReport.entries[{index}]")
        if entry.get("status") != "fallback":
            continue
        source = _sha256(
            entry.get("sourceImageChecksumSha256"),
            f"refinementReport.entries[{index}].sourceImageChecksumSha256",
        )
        position = _integer(
            entry.get("boardPosition"),
            f"refinementReport.entries[{index}].boardPosition",
        )
        key = (source, position)
        if key in selected:
            raise CellGridGoldenError(
                "SYMBOL_GRID_REVIEW_SELECTION_DUPLICATED",
                "The refinement report duplicates a fallback board.",
            )
        selected[key] = entry
    summary = _mapping(report.get("summary"), "refinementReport.summary")
    if len(selected) != _integer(summary.get("fallbackCount"), "summary.fallbackCount"):
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_SELECTION_DRIFT",
            "Fallback count differs from the refinement report summary.",
        )
    if not selected:
        raise CellGridGoldenError(
            "SYMBOL_GRID_REVIEW_NOT_REQUIRED",
            "The strict refinement report contains no fallback boards.",
        )
    return selected


class SymbolGridFallbackReview(CellGridGoldenReview):
    """Reuse the perspective editor for the small strict-fallback queue."""

    def __init__(
        self,
        *,
        repository_root: Path,
        manifest_path: Path,
        annotations_path: Path,
        crop_report_path: Path,
        crop_root: Path,
        refinement_report_path: Path,
        output_path: Path,
    ) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.manifest_path = manifest_path.resolve(strict=True)
        self.annotations_path = annotations_path.resolve(strict=True)
        self.crop_report_path = crop_report_path.resolve(strict=True)
        self.crop_root = crop_root.resolve(strict=True)
        self.refinement_report_path = refinement_report_path.resolve(strict=True)
        self.output_path = output_path.resolve()
        _, manifest = _load_json(self.manifest_path, "corpusManifest")
        _, self.source_root = _safe_relative_path(
            self.repository_root,
            manifest.get("rootPath"),
            "corpusManifest.rootPath",
        )
        if self.output_path == self.crop_root or self.output_path.is_relative_to(self.crop_root):
            raise CellGridGoldenError(
                "SYMBOL_GRID_REVIEW_OUTPUT_IN_CROP_ROOT",
                "Fallback review data must be outside immutable board artifacts.",
            )
        report_bytes, report = _load_json(
            self.refinement_report_path,
            "refinementReport",
        )
        self._refinement_report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        fallback_by_key = _fallbacks(report)
        bundle = _load_source_bundle(
            self.repository_root,
            self.manifest_path,
            self.annotations_path,
            self.crop_report_path,
            self.crop_root,
        )
        candidates = {
            (
                candidate.source_image_checksum_sha256,
                candidate.board_position,
            ): candidate
            for candidate in bundle.candidates
        }
        missing = sorted(set(fallback_by_key) - set(candidates))
        if missing:
            raise CellGridGoldenError(
                "SYMBOL_GRID_REVIEW_SOURCE_DRIFT",
                "A fallback board is absent from the immutable source bundle.",
            )
        selected = sorted(
            (candidates[key] for key in fallback_by_key),
            key=lambda candidate: (
                candidate.sequence_number,
                candidate.board_position,
                candidate.observation_id,
            ),
        )
        self._fallback_by_observation = {
            candidate.observation_id: fallback_by_key[
                (
                    candidate.source_image_checksum_sha256,
                    candidate.board_position,
                )
            ]
            for candidate in selected
        }
        entries = tuple(
            GridReviewEntry(
                selection_index=index,
                candidate=candidate,
                source_quad=candidate.detected_source_quad,
                v1_cut_cell_indexes=(),
                v1_impact_reviewed=False,
                review_status="pending",
                reviewed_by=None,
                decision_revision=0,
                line_source="detected-quad-suggestion",
            )
            for index, candidate in enumerate(selected)
        )
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
            _, existing = _load_json(self.output_path, "symbolGridFallbackReview")
            self._golden = self._parse_existing(existing, initial)
        else:
            self._golden = initial
            self._save()

    def _document(self) -> dict[str, object]:
        value = self._golden.to_dict()
        value["goldenVersion"] = REVIEW_VERSION
        value["refinementReportSha256"] = self._refinement_report_sha256
        selection = cast(dict[str, object], value["selection"])
        selection["selectionVersion"] = SELECTION_VERSION
        selection["fallbackCount"] = len(self._golden.entries)
        entries = cast(list[dict[str, object]], value["entries"])
        for entry in entries:
            observation_id = cast(str, entry["observationId"])
            fallback = self._fallback_by_observation[observation_id]
            entry["fallbackReason"] = fallback["fallbackReason"]
            entry["refinerVersion"] = fallback["refinerVersion"]
            entry["refinementInlierCount"] = fallback["inlierCount"]
            entry["suggestionVersion"] = SUGGESTION_VERSION
        return value

    def _parse_existing(
        self,
        value: Mapping[str, object],
        initial: CellGridGolden,
    ) -> CellGridGolden:
        if (
            value.get("goldenVersion") != REVIEW_VERSION
            or value.get("refinementReportSha256") != self._refinement_report_sha256
            or value.get("corpusManifestSha256") != initial.corpus_manifest_sha256
            or value.get("cropReportSha256") != initial.crop_report_sha256
            or value.get("goldenAnnotationsSha256") != initial.golden_annotations_sha256
        ):
            raise CellGridGoldenError(
                "SYMBOL_GRID_REVIEW_SOURCE_DRIFT",
                "Existing fallback review differs from its immutable sources.",
            )
        raw_entries = _sequence(value.get("entries"), "fallbackReview.entries")
        if len(raw_entries) != len(initial.entries):
            raise CellGridGoldenError(
                "SYMBOL_GRID_REVIEW_SELECTION_DRIFT",
                "Existing fallback review entry count differs.",
            )
        parsed: list[GridReviewEntry] = []
        for index, (raw, expected) in enumerate(zip(raw_entries, initial.entries, strict=True)):
            item = _mapping(raw, f"fallbackReview.entries[{index}]")
            fallback = self._fallback_by_observation[expected.candidate.observation_id]
            immutable = expected.candidate.immutable_dict(index)
            if (
                any(item.get(key) != expected_value for key, expected_value in immutable.items())
                or item.get("fallbackReason") != fallback["fallbackReason"]
                or item.get("refinerVersion") != fallback["refinerVersion"]
                or item.get("refinementInlierCount") != fallback["inlierCount"]
                or item.get("suggestionVersion") != SUGGESTION_VERSION
            ):
                raise CellGridGoldenError(
                    "SYMBOL_GRID_REVIEW_SELECTION_DRIFT",
                    f"Existing fallback review entry {index} differs.",
                )
            status = item.get("reviewStatus")
            if status not in {"pending", "accepted"}:
                raise CellGridGoldenError(
                    "SYMBOL_GRID_REVIEW_CONTRACT_INVALID",
                    "Review status is invalid.",
                )
            reviewed_by = _optional_text(item.get("reviewedBy"), "entry.reviewedBy")
            line_source = item.get("lineSource")
            if line_source not in {
                "detected-quad-suggestion",
                "human-draft",
                "human-confirmed-detected-quad",
                "human-adjusted",
            }:
                raise CellGridGoldenError(
                    "SYMBOL_GRID_REVIEW_CONTRACT_INVALID",
                    "Review line source is invalid.",
                )
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
                    line_source=cast(LineSource, line_source),
                )
            )
        return replace(
            initial,
            review_revision=_integer(value.get("reviewRevision"), "reviewRevision"),
            entries=tuple(parsed),
        )

    def _entry_payload(self, entry: GridReviewEntry) -> dict[str, object]:
        value = super()._entry_payload(entry)
        fallback = self._fallback_by_observation[entry.candidate.observation_id]
        value["fallbackReason"] = fallback["fallbackReason"]
        value["refinerVersion"] = fallback["refinerVersion"]
        value["refinementInlierCount"] = fallback["inlierCount"]
        value["suggestionVersion"] = SUGGESTION_VERSION
        return value

    def _save(self) -> None:
        _write_atomic(self.output_path, _json_bytes(self._document()))


__all__ = [
    "REVIEW_VERSION",
    "SELECTION_VERSION",
    "SUGGESTION_VERSION",
    "SymbolGridFallbackReview",
]
