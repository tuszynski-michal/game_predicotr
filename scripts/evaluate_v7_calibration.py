"""Validate V7 calibration annotations against a frozen, read-only corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7AcceptancePrediction,
    V7AcceptanceTruth,
    V7AutomaticOutcome,
    V7CalibrationError,
    V7CropAssessment,
    V7LabelGeometryAnnotation,
    V7SourceReference,
    calibrate_v7_label_geometry,
    evaluate_v7_acceptance,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import (
    V7CorpusManifest,
    V7CorpusSplit,
    load_v7_corpus_manifest,
)

_ANNOTATION_SCHEMA_VERSION = 2
_DEFAULT_SPLITS = (V7CorpusSplit.DEVELOPMENT, V7CorpusSplit.CALIBRATION)
_PERMITTED_SPLITS = {
    V7CorpusSplit.DEVELOPMENT,
    V7CorpusSplit.CALIBRATION,
    V7CorpusSplit.VALIDATION,
}


def _frozen_inventory(path: Path) -> tuple[str, tuple[dict[str, object], ...]]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Frozen V7 corpus inventory cannot be read.") from error
    cases = payload.get("cases") if isinstance(payload, dict) else None
    fingerprint = payload.get("manifestFingerprint") if isinstance(payload, dict) else None
    if (
        payload.get("schemaVersion") != 1
        or not isinstance(fingerprint, str)
        or not isinstance(cases, list)
        or not all(isinstance(item, dict) for item in cases)
    ):
        raise ValueError("Frozen V7 corpus inventory has an invalid contract.")
    return fingerprint, tuple(cases)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identities(
    manifest: V7CorpusManifest,
    selected_splits: set[V7CorpusSplit],
) -> dict[str, tuple[str, V7CorpusSplit, str, str | None]]:
    result: dict[str, tuple[str, V7CorpusSplit, str, str | None]] = {}
    for case in manifest.cases:
        if case.split not in selected_splits:
            continue
        for path in case_directory_jpegs(manifest.corpus_root / case.directory_name):
            source_id = f"{case.case_id}/{path.name}"
            result[source_id] = (
                case.case_id,
                case.split,
                _sha256_file(path),
                case.geometry_family_id,
            )
    return result


def case_directory_jpegs(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )


def _load_payload(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("V7 calibration annotation file cannot be read.") from error
    if not isinstance(value, dict) or value.get("schemaVersion") not in {
        1,
        _ANNOTATION_SCHEMA_VERSION,
    }:
        raise ValueError("V7 calibration annotation schema version is unsupported.")
    required = (
        "manifestFingerprint",
        "geometryAnnotations",
        "acceptanceTruth",
        "acceptancePredictions",
    )
    if any(name not in value for name in required):
        raise ValueError("V7 calibration annotation file lacks required fields.")
    if not isinstance(value["manifestFingerprint"], str) or any(
        not isinstance(value[name], list) for name in required[1:]
    ):
        raise ValueError("V7 calibration annotation fields are invalid.")
    return value


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V7 calibration {name} entry must be an object.")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"V7 calibration {field} must be a list.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"V7 calibration {field} must be a string.")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"V7 calibration {field} must be boolean.")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"V7 calibration {field} must be a number.")
    return float(value)


def _integer(value: object, field: str) -> int:
    number = _number(value, field)
    if not number.is_integer():
        raise ValueError(f"V7 calibration {field} must be an integer.")
    return int(number)


def _split(value: object, field: str) -> V7CorpusSplit:
    try:
        return V7CorpusSplit(_text(value, field))
    except ValueError as error:
        raise ValueError(f"V7 calibration {field} is invalid.") from error


def _source_reference(value: object, field: str) -> V7SourceReference:
    entry = _mapping(value, field)
    return V7SourceReference(
        source_id=_text(entry.get("sourceId"), "sourceId"),
        source_checksum_sha256=_text(entry.get("sourceChecksumSha256"), "sourceChecksumSha256"),
    )


def _geometry_annotations(entries: Sequence[object]) -> tuple[V7LabelGeometryAnnotation, ...]:
    annotations = []
    for raw in entries:
        value = _mapping(raw, "geometry annotation")
        annotations.append(
            V7LabelGeometryAnnotation(
                source_id=_text(value.get("sourceId"), "sourceId"),
                source_checksum_sha256=_text(
                    value.get("sourceChecksumSha256"), "sourceChecksumSha256"
                ),
                split=_split(value.get("split"), "split"),
                position_index=_integer(value.get("positionIndex"), "positionIndex"),
                center_x=_number(value.get("centerX"), "centerX"),
                center_y=_number(value.get("centerY"), "centerY"),
                geometry_family_id=_text(value.get("geometryFamilyId"), "geometryFamilyId"),
                capture_group_id=_text(value.get("captureGroupId"), "captureGroupId"),
                crop_assessment=V7CropAssessment(
                    _text(value.get("cropAssessment"), "cropAssessment")
                ),
            )
        )
    return tuple(annotations)


def _truths(entries: Sequence[object]) -> tuple[V7AcceptanceTruth, ...]:
    values = []
    for raw in entries:
        value = _mapping(raw, "acceptance truth")
        values.append(
            V7AcceptanceTruth(
                case_id=_text(value.get("caseId"), "caseId"),
                corpus_case_id=_text(value.get("corpusCaseId"), "corpusCaseId"),
                split=_split(value.get("split"), "split"),
                expected_range_start=_integer(
                    value.get("expectedRangeStart"), "expectedRangeStart"
                ),
                expected_range_end=_integer(value.get("expectedRangeEnd"), "expectedRangeEnd"),
                evidence_sources=tuple(
                    _source_reference(item, "evidenceSource")
                    for item in _list(value.get("evidenceSources"), "evidenceSources")
                ),
                automatically_recoverable=_boolean(
                    value.get("automaticallyRecoverable"), "automaticallyRecoverable"
                ),
                eligible_acceptable_representative=_boolean(
                    value.get("eligibleAcceptableRepresentative"),
                    "eligibleAcceptableRepresentative",
                ),
                top_cropped=_boolean(value.get("topCropped"), "topCropped"),
                bottom_cropped=_boolean(value.get("bottomCropped"), "bottomCropped"),
            )
        )
    return tuple(values)


def _predictions(entries: Sequence[object]) -> tuple[V7AcceptancePrediction, ...]:
    values = []
    for raw in entries:
        value = _mapping(raw, "acceptance prediction")
        try:
            values.append(
                V7AcceptancePrediction(
                    case_id=_text(value.get("caseId"), "caseId"),
                    range_outcome=V7AutomaticOutcome(
                        _text(value.get("rangeOutcome"), "rangeOutcome")
                    ),
                    representative_outcome=V7AutomaticOutcome(
                        _text(value.get("representativeOutcome"), "representativeOutcome")
                    ),
                    selected_source=(
                        None
                        if value.get("selectedSource") is None
                        else _source_reference(value["selectedSource"], "selectedSource")
                    ),
                    top_warning=_boolean(value.get("topWarning"), "topWarning"),
                    bottom_warning=_boolean(value.get("bottomWarning"), "bottomWarning"),
                    manual_review=_boolean(value.get("manualReview"), "manualReview"),
                )
            )
        except ValueError as error:
            raise ValueError("V7 calibration prediction outcome is invalid.") from error
    return tuple(values)


def _validate_annotation_sources(
    annotations: Sequence[V7LabelGeometryAnnotation],
    identities: Mapping[str, tuple[str, V7CorpusSplit, str, str | None]],
    selected_splits: set[V7CorpusSplit],
) -> None:
    for annotation in annotations:
        if annotation.split not in selected_splits:
            raise ValueError("V7 calibration annotation uses a split excluded from this run.")
        current = identities.get(annotation.source_id)
        if (
            current is None
            or current[1:3] != (annotation.split, annotation.source_checksum_sha256)
            or current[3] != annotation.geometry_family_id
        ):
            raise ValueError("V7 calibration annotation source identity or checksum drifted.")


def _validate_acceptance_sources(
    truths: Sequence[V7AcceptanceTruth],
    predictions: Sequence[V7AcceptancePrediction],
    identities: Mapping[str, tuple[str, V7CorpusSplit, str, str | None]],
    selected_splits: set[V7CorpusSplit],
) -> None:
    predictions_by_case = {item.case_id: item for item in predictions}
    for truth in truths:
        if truth.split not in _PERMITTED_SPLITS or truth.split not in selected_splits:
            raise ValueError("V7 acceptance truth uses a split excluded from this run.")
        for source in truth.evidence_sources:
            _validate_acceptance_source(
                source,
                truth=truth,
                identities=identities,
                selected_splits=selected_splits,
            )
        prediction = predictions_by_case.get(truth.case_id)
        if prediction is not None and prediction.selected_source is not None:
            _validate_acceptance_source(
                prediction.selected_source,
                truth=truth,
                identities=identities,
                selected_splits=selected_splits,
            )


def _validate_acceptance_source(
    source: V7SourceReference,
    *,
    truth: V7AcceptanceTruth,
    identities: Mapping[str, tuple[str, V7CorpusSplit, str, str | None]],
    selected_splits: set[V7CorpusSplit],
) -> None:
    actual = identities.get(source.source_id)
    if (
        actual is None
        or actual[:3]
        != (
            truth.corpus_case_id,
            truth.split,
            source.source_checksum_sha256,
        )
        or actual[1] not in selected_splits
    ):
        raise ValueError("V7 acceptance source, case, split, or checksum drifted.")


def evaluate_annotation_payload(
    *,
    manifest_path: Path,
    inventory_path: Path,
    annotations_path: Path,
    selected_splits: set[V7CorpusSplit],
) -> dict[str, object]:
    """Return a non-activating, reproducible report for one annotation snapshot."""

    if not selected_splits or not selected_splits.issubset(_PERMITTED_SPLITS):
        raise ValueError("V7 T05 allows only development, calibration, or validation splits.")
    manifest = load_v7_corpus_manifest(manifest_path)
    inventory = manifest.freeze_inventory()
    frozen_fingerprint, frozen_cases = _frozen_inventory(inventory_path)
    if (
        frozen_fingerprint != manifest.fingerprint()
        or tuple(item.as_dict() for item in inventory) != frozen_cases
    ):
        raise ValueError("V7 corpus manifest or source inventory drifted; evaluation is blocked.")
    payload = _load_payload(annotations_path)
    if payload["manifestFingerprint"] != manifest.fingerprint():
        raise ValueError("V7 annotation manifest fingerprint differs from the frozen corpus.")
    geometry = _geometry_annotations(_list(payload["geometryAnnotations"], "geometryAnnotations"))
    truths = _truths(_list(payload["acceptanceTruth"], "acceptanceTruth"))
    predictions = _predictions(_list(payload["acceptancePredictions"], "acceptancePredictions"))
    identities = _source_identities(manifest, selected_splits) if geometry or truths else {}
    if geometry:
        _validate_annotation_sources(
            geometry,
            identities,
            selected_splits,
        )
    _validate_acceptance_sources(truths, predictions, identities, selected_splits)
    geometry_report: dict[str, object]
    if geometry:
        geometry_report = calibrate_v7_label_geometry(
            geometry,
            manifest_fingerprint=manifest.fingerprint(),
            geometry_family_id=_text(payload.get("geometryFamilyId"), "geometryFamilyId"),
        ).as_dict()
    else:
        geometry_report = {
            "reason": "no_calibration_annotations",
            "status": "not_evaluable",
        }
    acceptance_report = evaluate_v7_acceptance(truths, predictions).as_dict()
    return {
        "acceptance": acceptance_report,
        "corpusInventory": [item.as_dict() for item in inventory],
        "corpusManifestFingerprint": manifest.fingerprint(),
        "geometry": geometry_report,
        "includedSplits": sorted(item.value for item in selected_splits),
        "productionActivation": {
            "reason": "T12 acceptance plus an explicit activation decision are still required.",
            "status": "blocked",
        },
        "schemaVersion": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--include-split",
        action="append",
        choices=tuple(
            item.value for item in sorted(_PERMITTED_SPLITS, key=lambda item: item.value)
        ),
        default=None,
        help="Defaults to development and calibration. Validation requires explicit selection.",
    )
    arguments = parser.parse_args()
    selected_splits = {
        V7CorpusSplit(value)
        for value in (arguments.include_split or [item.value for item in _DEFAULT_SPLITS])
    }
    try:
        report = evaluate_annotation_payload(
            manifest_path=arguments.manifest,
            inventory_path=arguments.inventory,
            annotations_path=arguments.annotations,
            selected_splits=selected_splits,
        )
    except (OSError, V7CalibrationError, ValueError) as error:
        parser.error(str(error))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
