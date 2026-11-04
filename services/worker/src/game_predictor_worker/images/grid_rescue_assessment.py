"""Evaluate the exported, admitted path on controls without optimizer access."""

import hashlib
import json
from pathlib import Path
from typing import Any

from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence

from ..geometry_core.rescue import GridRescueVariantV1
from .grid_rescue_strategy import execute_path


class RescueAssessmentEngine:
    def __init__(self, engine: Any, proof: dict[str, Any]) -> None:
        self.engine = engine
        self.path = proof["selection"]["selectedPath"]
        self.variant = GridRescueVariantV1.model_validate(proof["recipe"]["variant"])

    def analyse(self, rgb: Any) -> list[Any]:
        baseline = self.engine.analyse(rgb)
        return execute_path(
            baseline,
            width=rgb.shape[1],
            height=rgb.shape[0],
            variant=self.variant,
            path=self.path,
            expected_positions=set(range(9)),
            detect=lambda geometry: self.engine.detect(rgb, geometry=geometry),
            recrop=lambda position, detection, geometry: self.engine.recrop(
                rgb, detection, geometry=geometry
            ),
        ).detections


def assessment_engine(engine: Any, directory: Path, expected_sha: str) -> Any:
    path = directory / "bundle.json"
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("GRID_RESCUE_PROOF_TOO_LARGE")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("GRID_RESCUE_BUNDLE_CHANGED")
    bundle = json.loads(payload)
    if "rescue" not in bundle:
        return engine
    proof = require_rescue_evidence(bundle)
    return (
        engine
        if proof["selection"]["selectedPath"] is None
        else RescueAssessmentEngine(engine, proof)
    )
