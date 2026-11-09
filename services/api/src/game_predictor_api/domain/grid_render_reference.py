"""Closed, immutable render choices; historical import evidence is never rewritten."""

from collections.abc import Mapping
from typing import Any

from .grid_cell_content import ContentError
from .grid_training_cohorts import digest
from .image_geometry_v2 import DirectCellRenderConfiguration
from .symbol_model_snapshots import SymbolModelJobSnapshot

CONTRACT_VERSION = "active-symbol-render-contract-v1"
REFERENCE_V2 = "production-cell-evaluation-reference-v2"
POLICY = "active-symbol-render-v2"


def require_evaluation_contract(value: Mapping[str, Any], game: str | None = None) -> None:
    if (
        set(value)
        != {
            "version",
            "gameId",
            "classifier",
            "renderConfiguration",
            "renderConfigurationSha256",
            "sha256",
        }
        or value.get("version") != CONTRACT_VERSION
        or value.get("sha256") != digest({k: v for k, v in value.items() if k != "sha256"})
        or (game is not None and value.get("gameId") != str(game))
        or value.get("renderConfigurationSha256") != digest(value.get("renderConfiguration"))
    ):
        raise ContentError("CONTENT_EVALUATION_CONTRACT_INVALID", "The render choice changed.")
    try:
        model = SymbolModelJobSnapshot.from_payload(value["classifier"])
        raw = value["renderConfiguration"]
        configuration = DirectCellRenderConfiguration(
            extractor_version=raw["extractorVersion"],
            preprocessing_version=raw["preprocessingVersion"],
            interpolation=raw["interpolation"],
            output_width=raw["outputWidth"],
            output_height=raw["outputHeight"],
            padding_fraction=raw["paddingFraction"],
        )
        if (
            configuration.to_dict() != raw
            or raw["outputWidth"] != model.crop_output_size
            or raw["outputHeight"] != model.crop_output_size
            or raw["paddingFraction"] != model.crop_padding_fraction
        ):
            raise ValueError("classifier/render mismatch")
    except (ValueError, TypeError, KeyError) as error:
        raise ContentError("CONTENT_EVALUATION_CONTRACT_INVALID", str(error)) from error


def execution_context(provenance: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require_evaluation_contract(contract)
    if provenance.get("state") != "available":
        raise ContentError(
            "CONTENT_IMPORT_PROVENANCE_REQUIRED", "Original import evidence is missing."
        )
    return {
        **provenance,
        "classifier": contract["classifier"],
        "renderConfiguration": contract["renderConfiguration"],
    }


def require_reference_v2(pin: Mapping[str, Any], game: str | None = None) -> None:
    if (
        set(pin)
        != {
            "version",
            "sourceContext",
            "sourceContextSha256",
            "measurement",
            "sha256",
            "importProvenance",
            "importProvenanceSha256",
            "evaluationContract",
        }
        or pin.get("version") != REFERENCE_V2
        or pin.get("sha256") != digest({k: v for k, v in pin.items() if k != "sha256"})
        or pin.get("importProvenanceSha256") != digest(pin.get("importProvenance"))
        or pin.get("sourceContextSha256") != digest(pin.get("sourceContext"))
    ):
        raise ContentError("CONTENT_PRODUCTION_REFERENCE_INVALID", "The reference changed.")
    contract = pin["evaluationContract"]
    require_evaluation_contract(contract, game)
    provenance = pin["importProvenance"]
    expected_context = (
        execution_context(provenance, contract)
        if provenance.get("state") == "available"
        else provenance
    )
    if (
        provenance.get("state") not in {"available", "unavailable"}
        or pin["sourceContext"] != expected_context
        or (provenance.get("state") != "available" and pin.get("measurement") is not None)
    ):
        raise ContentError(
            "CONTENT_PRODUCTION_REFERENCE_INVALID", "Execution differs from its pin."
        )
    measurement = pin.get("measurement")
    if measurement is not None and measurement["report"].get("evaluationContract") != contract:
        raise ContentError(
            "CONTENT_MEASUREMENT_CONTRACT_CHANGED", "The oracle used another render."
        )
