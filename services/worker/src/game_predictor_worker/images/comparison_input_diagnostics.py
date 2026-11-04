"""Bind optional file-backed input diagnostics to exact report targets and models."""

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from game_predictor_worker.geometry_core.input_diagnostics import (
    SUPPORTED_PREPROCESSING_VERSION,
    InputDiagnostic,
    array_sha256,
    digest,
)
from game_predictor_worker.geometry_core.input_diagnostics_v2 import (
    decode_input_record,
    replay_request_input,
)
from game_predictor_worker.geometry_core.settings import BoardPreset, ScreenPreset


def _inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("DIAGNOSTIC_ASSET_OUTSIDE_REPORT")
    return path


def diagnostic_inputs(
    root: Path, source: dict[str, Any], board: dict[str, Any], versions: dict[str, str]
) -> dict[str, Any]:
    """Missing/mismatched diagnostics stay explicit; other report views remain usable."""
    missing: dict[str, dict[str, Any]] = {
        key: {"state": "unavailable", "reason": "Brak zapisanego rekordu wejścia."}
        for key in versions
    }
    index = root / "diagnostics/index.json"
    if not index.exists():
        return missing
    records = json.loads(index.read_text(encoding="utf-8"))
    for key, version in versions.items():
        matches = [
            x
            for x in records
            if x.get("sourceId") == source["id"]
            and x.get("positionIndex") == board["position_index"]
            and x.get("modelVersionId") == version
        ]
        if len(matches) != 1:
            missing[key]["reason"] = (
                "Brak jednoznacznego rekordu dla tego źródła, pozycji i modelu."
            )
            continue
        try:
            entry = matches[0]
            record = decode_input_record(
                json.loads(_inside(root, entry["record"]).read_text(encoding="utf-8"))
            )
            if (
                record.source.source_id != source["id"]
                or record.source.source_sha256 != source["checksum_sha256"]
                or record.model.version_id != version
            ):
                raise ValueError("DIAGNOSTIC_TARGET_MODEL_MISMATCH")
            margin: float | None
            if isinstance(record, InputDiagnostic):
                stage_label = "wejście planszy"
                if (
                    digest(record.archived_preset) != record.model.preset_sha256
                    or record.model.preprocessing_version != SUPPORTED_PREPROCESSING_VERSION
                    or record.archived_preset.get("preprocessing_version")
                    != record.model.preprocessing_version
                    or BoardPreset.model_validate(record.archived_preset.get("board"))
                    != record.board_preset
                    or ScreenPreset.model_validate(record.archived_preset.get("screen"))
                    != record.screen_preset
                ):
                    raise ValueError("DIAGNOSTIC_PRESET_CONTRACT_MISMATCH")
                if (
                    record.position_index != board["position_index"]
                    or record.sequence_number != board["sequence_number"]
                ):
                    raise ValueError("DIAGNOSTIC_TARGET_SEQUENCE_MISMATCH")
                # Archived stage pixels are also sufficient: validate the exact saved
                # RGB and derived float32 tensor, never a visually similar crop.
                pixels = np.asarray(
                    Image.open(_inside(root, entry["inputRgb"])).convert("RGB"), dtype=np.uint8
                )
                stage = record.board
                if (
                    pixels.shape != (stage.height, stage.width, 3)
                    or array_sha256(pixels) != stage.rgb_sha256
                    or array_sha256(pixels.transpose(2, 0, 1).astype("<f4")) != stage.tensor_sha256
                ):
                    raise ValueError("DIAGNOSTIC_INPUT_REPLAY_MISMATCH")
                margin = record.board_preset.margin
                unavailable = record.raw_nodes.unavailable_reason
            else:
                stage_label = (
                    "wejście ekranu" if record.attempt == "redetect" else "wejście planszy"
                )
                # The index is an archived target binding, independent of the
                # board currently selected by this report. Missing legacy-v2
                # bindings cannot prove the current sequence identity.
                if (
                    type(entry.get("sequenceNumber")) is not int
                    or entry["sequenceNumber"] != board["sequence_number"]
                ):
                    raise ValueError("DIAGNOSTIC_TARGET_SEQUENCE_MISMATCH")
                if board["position_index"] not in record.expected_positions:
                    raise ValueError("DIAGNOSTIC_FOREIGN_SLOT_SCOPE")
                if (
                    record.attempt.startswith("crop-")
                    and record.attempt != f"crop-{board['position_index']}"
                ):
                    raise ValueError("DIAGNOSTIC_FOREIGN_SLOT_SCOPE")
                rgb = np.load(_inside(root, entry["actualRaster"]), allow_pickle=False)
                pixels = replay_request_input(record, rgb)
                stage = record.stage
                request = next(
                    x["request"]
                    for x in record.execution["attempts"]
                    if x["attempt"] == record.attempt
                )
                margin = (
                    None
                    if record.attempt == "redetect"
                    else (request["geometry"] or {}).get(
                        "margin", record.archived_preset["board"]["margin"]
                    )
                )
                unavailable = "Brak zapisanego GT/raw dla tego żądania."
            relative = f"diagnostic-inputs/{source['id']}-{board['position_index']}-{key}.png"
            destination = _inside(root, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(pixels).save(destination)
            missing[key] = {
                "state": "available",
                "image": relative,
                "width": stage.width,
                "height": stage.height,
                "margin": margin,
                "rgbSha256": stage.rgb_sha256,
                "tensorSha256": stage.tensor_sha256,
                "tensorShape": list(stage.tensor_shape),
                "sourceToInput": stage.source_to_input,
                "rawUnavailable": unavailable,
                "humanReference": "unavailable",
                "schemaVersion": record.schema_version,
                "stageLabel": stage_label,
            }
        except (FileNotFoundError, ValueError, KeyError, StopIteration) as error:
            missing[key] = {"state": "unavailable", "reason": str(error)}
    return missing
