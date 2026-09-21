"""Evaluate one frozen V7 holdout without calibrating or activating the workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7CalibrationError,
    V7EvaluationStatus,
    V7HoldoutAcceptanceTruth,
    V7HoldoutPredictionSnapshot,
    V7HoldoutSourceObservation,
    V7SourceReference,
    evaluate_v7_holdout_acceptance,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import (
    V7CorpusManifest,
    V7CorpusSplit,
    load_v7_corpus_manifest,
)

_SCHEMA_VERSION = 1
_CALIBRATION_VERSION = "v7-calibration-v1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_object(path: Path, name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"V7 {name} cannot be read.") from error
    if not isinstance(value, dict):
        raise ValueError(f"V7 {name} must be an object.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"V7 holdout {field} must be a string.")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"V7 holdout {field} must be an integer.")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"V7 holdout {field} must be boolean.")
    return value


def _items(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"V7 holdout {field} must be a list.")
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V7 holdout {field} must be an object.")
    return value


def _validate_sha256(value: object, field: str) -> str:
    result = _text(value, field)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError(f"V7 holdout {field} must be a lowercase SHA-256.")
    return result


def _source_reference(value: object, field: str) -> V7SourceReference:
    item = _mapping(value, field)
    return V7SourceReference(
        source_id=_text(item.get("sourceId"), "sourceId"),
        source_checksum_sha256=_validate_sha256(
            item.get("sourceChecksumSha256"), "sourceChecksumSha256"
        ),
    )


def _truths(payload: Mapping[str, object]) -> tuple[V7HoldoutAcceptanceTruth, ...]:
    values = []
    for raw in _items(payload.get("cases"), "truth cases"):
        item = _mapping(raw, "truth case")
        try:
            values.append(
                V7HoldoutAcceptanceTruth(
                    case_id=_text(item.get("caseId"), "caseId"),
                    corpus_case_id=_text(item.get("corpusCaseId"), "corpusCaseId"),
                    split=V7CorpusSplit(_text(item.get("split"), "split")),
                    expected_range_start=_integer(
                        item.get("expectedRangeStart"), "expectedRangeStart"
                    ),
                    expected_range_end=_integer(item.get("expectedRangeEnd"), "expectedRangeEnd"),
                    evidence_sources=tuple(
                        _source_reference(source, "evidenceSource")
                        for source in _items(item.get("evidenceSources"), "evidenceSources")
                    ),
                    acceptable_representative_sources=tuple(
                        _source_reference(source, "acceptableRepresentativeSource")
                        for source in _items(
                            item.get("acceptableRepresentativeSources"),
                            "acceptableRepresentativeSources",
                        )
                    ),
                    automatically_recoverable=_boolean(
                        item.get("automaticallyRecoverable"), "automaticallyRecoverable"
                    ),
                    eligible_acceptable_representative=_boolean(
                        item.get("eligibleAcceptableRepresentative"),
                        "eligibleAcceptableRepresentative",
                    ),
                )
            )
        except ValueError as error:
            raise ValueError("V7 holdout truth case is invalid.") from error
    return tuple(values)


def _source_observations(
    payload: Mapping[str, object],
) -> tuple[V7HoldoutSourceObservation, ...]:
    values = []
    for raw in _items(payload.get("sourceObservations"), "source observations"):
        item = _mapping(raw, "source observation")
        try:
            values.append(
                V7HoldoutSourceObservation(
                    source=_source_reference(item, "sourceObservation"),
                    represented_range_start=_integer(
                        item.get("representedRangeStart"), "representedRangeStart"
                    ),
                    represented_range_end=_integer(
                        item.get("representedRangeEnd"), "representedRangeEnd"
                    ),
                    top_cropped=_boolean(item.get("topCropped"), "topCropped"),
                    bottom_cropped=_boolean(item.get("bottomCropped"), "bottomCropped"),
                )
            )
        except ValueError as error:
            raise ValueError("V7 holdout source observation is invalid.") from error
    return tuple(values)


def _prediction_snapshots(
    payload: Mapping[str, object],
) -> tuple[V7HoldoutPredictionSnapshot, ...]:
    values = []
    for raw in _items(payload.get("cases"), "prediction cases"):
        item = _mapping(raw, "prediction case")
        if "rangeOutcome" in item or "representativeOutcome" in item:
            raise ValueError(
                "V7 holdout prediction snapshots must contain raw observations, not outcomes."
            )
        try:
            values.append(
                V7HoldoutPredictionSnapshot(
                    case_id=_text(item.get("caseId"), "caseId"),
                    predicted_range_start=(
                        None
                        if item.get("predictedRangeStart") is None
                        else _integer(item["predictedRangeStart"], "predictedRangeStart")
                    ),
                    predicted_range_end=(
                        None
                        if item.get("predictedRangeEnd") is None
                        else _integer(item["predictedRangeEnd"], "predictedRangeEnd")
                    ),
                    selected_source=(
                        None
                        if item.get("selectedSource") is None
                        else _source_reference(item["selectedSource"], "selectedSource")
                    ),
                    top_warning=_boolean(item.get("topWarning"), "topWarning"),
                    bottom_warning=_boolean(item.get("bottomWarning"), "bottomWarning"),
                    manual_review=_boolean(item.get("manualReview"), "manualReview"),
                )
            )
        except ValueError as error:
            raise ValueError("V7 holdout prediction snapshot case is invalid.") from error
    return tuple(values)


def _frozen_inventory(path: Path) -> tuple[str, tuple[dict[str, object], ...]]:
    payload = _read_object(path, "frozen inventory")
    if payload.get("schemaVersion") != 1:
        raise ValueError("V7 frozen inventory schema version is unsupported.")
    fingerprint = _validate_sha256(payload.get("manifestFingerprint"), "manifestFingerprint")
    cases = _items(payload.get("cases"), "inventory cases")
    if not all(isinstance(item, dict) for item in cases):
        raise ValueError("V7 frozen inventory cases are invalid.")
    return fingerprint, tuple(cases)  # type: ignore[arg-type]


def _holdout_case_id(manifest: V7CorpusManifest) -> str:
    values = [item.case_id for item in manifest.cases if item.split is V7CorpusSplit.HOLDOUT]
    if len(values) != 1:
        raise ValueError("V7 holdout evaluation requires exactly one declared holdout case.")
    return _text(values[0], "holdout case ID")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _holdout_source_identities(
    manifest: V7CorpusManifest,
    *,
    holdout_case_id: str,
) -> dict[str, tuple[str, V7CorpusSplit, str]]:
    case = next(item for item in manifest.cases if item.case_id == holdout_case_id)
    directory = manifest.corpus_root / case.directory_name
    result: dict[str, tuple[str, V7CorpusSplit, str]] = {}
    for path in sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
        if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}:
            result[f"{case.case_id}/{path.name}"] = (case.case_id, case.split, _sha256_file(path))
    return result


def _validate_payload_header(
    payload: Mapping[str, object],
    *,
    kind: str,
    manifest_fingerprint: str,
    inventory_fingerprint: str,
) -> None:
    if payload.get("schemaVersion") != _SCHEMA_VERSION:
        raise ValueError(f"V7 holdout {kind} schema version is unsupported.")
    actual_manifest_fingerprint = _validate_sha256(
        payload.get("manifestFingerprint"), "manifestFingerprint"
    )
    if actual_manifest_fingerprint != manifest_fingerprint:
        raise ValueError(f"V7 holdout {kind} manifest fingerprint differs.")
    if (
        _validate_sha256(payload.get("holdoutInventoryFingerprint"), "holdoutInventoryFingerprint")
        != inventory_fingerprint
    ):
        raise ValueError(f"V7 holdout {kind} inventory fingerprint differs.")


def _calibration_fingerprint(
    payload: Mapping[str, object], *, manifest_fingerprint: str
) -> str:
    if payload.get("schemaVersion") != 1:
        raise ValueError("V7 calibration report schema version is unsupported.")
    if payload.get("corpusManifestFingerprint") != manifest_fingerprint:
        raise ValueError("V7 calibration report manifest fingerprint differs.")
    geometry = _mapping(payload.get("geometry"), "calibration geometry")
    if (
        geometry.get("version") != _CALIBRATION_VERSION
        or geometry.get("status") != V7EvaluationStatus.PASSED.value
        or geometry.get("manifestFingerprint") != manifest_fingerprint
    ):
        raise ValueError("V7 calibration report is not a passed calibration for this manifest.")
    _validate_sha256(geometry.get("inputFingerprint"), "calibration inputFingerprint")
    return _fingerprint(geometry)


def _validate_sources(
    *,
    truths: Sequence[V7HoldoutAcceptanceTruth],
    predictions: Sequence[V7HoldoutPredictionSnapshot],
    source_observations: Sequence[V7HoldoutSourceObservation],
    identities: Mapping[str, tuple[str, V7CorpusSplit, str]],
    holdout_case_id: str,
) -> None:
    for observation in source_observations:
        source = observation.source
        if identities.get(source.source_id) != (
            holdout_case_id,
            V7CorpusSplit.HOLDOUT,
            source.source_checksum_sha256,
        ):
            raise ValueError("V7 holdout source observation identity or checksum drifted.")
    for truth in truths:
        if truth.corpus_case_id != holdout_case_id:
            raise ValueError("V7 holdout truth references a different corpus case.")
        for source in (*truth.evidence_sources, *truth.acceptable_representative_sources):
            if identities.get(source.source_id) != (
                holdout_case_id,
                V7CorpusSplit.HOLDOUT,
                source.source_checksum_sha256,
            ):
                raise ValueError("V7 holdout truth source identity or checksum drifted.")
    for prediction in predictions:
        if prediction.selected_source is not None:
            source = prediction.selected_source
            if identities.get(source.source_id) != (
                holdout_case_id,
                V7CorpusSplit.HOLDOUT,
                source.source_checksum_sha256,
            ):
                raise ValueError("V7 holdout prediction source identity or checksum drifted.")


def evaluate_holdout(
    *,
    manifest_path: Path,
    inventory_path: Path,
    calibration_path: Path,
    truth_path: Path,
    predictions_path: Path,
) -> dict[str, object]:
    """Build an immutable T12 report from frozen artifacts; it never executes V7."""

    manifest = load_v7_corpus_manifest(manifest_path)
    current_inventory = tuple(item.as_dict() for item in manifest.freeze_inventory())
    frozen_manifest_fingerprint, frozen_inventory = _frozen_inventory(inventory_path)
    manifest_fingerprint = manifest.fingerprint()
    if frozen_manifest_fingerprint != manifest_fingerprint or frozen_inventory != current_inventory:
        raise ValueError("V7 holdout corpus manifest or inventory drifted.")
    holdout_case_id = _holdout_case_id(manifest)
    inventory_fingerprint = _fingerprint(current_inventory)
    calibration_fingerprint = _calibration_fingerprint(
        _read_object(calibration_path, "calibration report"),
        manifest_fingerprint=manifest_fingerprint,
    )
    truth_payload = _read_object(truth_path, "truth")
    prediction_payload = _read_object(predictions_path, "prediction snapshot")
    _validate_payload_header(
        truth_payload,
        kind="truth",
        manifest_fingerprint=manifest_fingerprint,
        inventory_fingerprint=inventory_fingerprint,
    )
    _validate_payload_header(
        prediction_payload,
        kind="prediction snapshot",
        manifest_fingerprint=manifest_fingerprint,
        inventory_fingerprint=inventory_fingerprint,
    )
    prediction_calibration_fingerprint = _validate_sha256(
        prediction_payload.get("calibrationFingerprint"), "calibrationFingerprint"
    )
    if prediction_calibration_fingerprint != calibration_fingerprint:
        raise ValueError("V7 holdout prediction snapshot calibration fingerprint differs.")
    algorithm_fingerprint = _validate_sha256(
        prediction_payload.get("algorithmFingerprint"), "algorithmFingerprint"
    )
    truths = _truths(truth_payload)
    predictions = _prediction_snapshots(prediction_payload)
    source_observations = _source_observations(truth_payload)
    _validate_sources(
        truths=truths,
        predictions=predictions,
        source_observations=source_observations,
        identities=_holdout_source_identities(manifest, holdout_case_id=holdout_case_id),
        holdout_case_id=holdout_case_id,
    )
    final_inventory = tuple(item.as_dict() for item in manifest.freeze_inventory())
    if final_inventory != frozen_inventory:
        raise ValueError("V7 holdout corpus changed while source identities were checked.")
    acceptance = evaluate_v7_holdout_acceptance(truths, predictions, source_observations)
    return {
        "acceptance": acceptance.as_dict(),
        "algorithmFingerprint": algorithm_fingerprint,
        "calibrationFingerprint": calibration_fingerprint,
        "corpusManifestFingerprint": manifest_fingerprint,
        "holdoutCaseId": holdout_case_id,
        "holdoutInventoryFingerprint": inventory_fingerprint,
        "predictionSnapshotFingerprint": _fingerprint(prediction_payload),
        "productionActivation": {
            "reason": (
                "T13b handler integration, T12 review, and an explicit activation decision "
                "are required."
            ),
            "status": "blocked",
        },
        "schemaVersion": _SCHEMA_VERSION,
        "truthFingerprint": _fingerprint(truth_payload),
    }


def _write_once(path: Path, payload: Mapping[str, object]) -> None:
    content = _canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as target:
            target.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ValueError("V7 holdout report already exists with different content.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        report = evaluate_holdout(
            manifest_path=arguments.manifest,
            inventory_path=arguments.inventory,
            calibration_path=arguments.calibration,
            truth_path=arguments.truth,
            predictions_path=arguments.predictions,
        )
        _write_once(arguments.output, report)
    except (OSError, V7CalibrationError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
