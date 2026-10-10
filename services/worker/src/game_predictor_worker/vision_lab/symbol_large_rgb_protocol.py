"""D-506 local RGB contract; public and generation1–4 budgets stay unchanged."""

from typing import Any, Self

from pydantic import Field, model_validator

from .annotations import digest
from .run_contracts import RunState, StartRunRequest, TrainingConfiguration

MODEL = "mumie-symbol-rgb-v5-large-ai"
PREPROCESSING = "rgb-resize64-normalize-half-v1"
PURPOSE = "symbol_large_ai_experiment"
SEED = 20261005
PROTOCOL = {
    "format": "lab-large-symbol-rgb-protocol-v1",
    "model": MODEL,
    "purpose": PURPOSE,
    "preprocessing": PREPROCESSING,
    "seed": SEED,
    "epochs": 20,
    "batch_size": 32,
    "learning_rate": 0.001,
    "max_seconds": 7200,
    "max_steps": 50000,
    "human_feedback_weight": 4,
    "ai_weight": 1,
    "maximum_references": 20,
    "maximum_cases_per_reference": 100,
    "selection": "unchanged-human-validation-only",
    "admission": "one-training-run-in-immutable-root",
}
PROTOCOL_DIGEST = digest(PROTOCOL)


class LargeRgbConfiguration(TrainingConfiguration):
    max_steps: int = Field(default=50000, ge=1, le=50000)
    max_seconds: float = Field(default=7200, ge=1, le=7200)


class LargeRgbRequest(StartRunRequest):
    configuration: LargeRgbConfiguration
    symbol_protocol_digest: str = Field(default=PROTOCOL_DIGEST, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def fixed_protocol(self) -> Self:
        if (
            self.symbol_protocol_digest != PROTOCOL_DIGEST
            or self.protocol_digest is not None
            or self.model_version != MODEL
            or self.preprocessing_version != PREPROCESSING
            or self.topology.columns != 5
            or self.topology.rows != 3
            or self.purpose != "train"
            or self.seed != PROTOCOL["seed"]
            or self.configuration.epochs != PROTOCOL["epochs"]
            or self.configuration.batch_size != PROTOCOL["batch_size"]
            or self.configuration.learning_rate != PROTOCOL["learning_rate"]
        ):
            raise ValueError("LARGE_RGB_PROTOCOL_INVALID")
        return self


class LargeRgbRunState(RunState):
    request: LargeRgbRequest


def validate_request(request: StartRunRequest) -> LargeRgbRequest:
    # model_copy bypasses Pydantic validators, so always reconstruct the contract.
    return LargeRgbRequest.model_validate(request.model_dump())


def admit(data: dict[str, Any], request: StartRunRequest) -> None:
    validate_request(request)
    if any(row["request"]["purpose"] == "train" for row in data["runs"].values()):
        raise ValueError("LARGE_RGB_TRAIN_ALREADY_ADMITTED")
