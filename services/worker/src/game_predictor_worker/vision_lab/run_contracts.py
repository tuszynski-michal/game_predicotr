"""Public run contracts. Paths, process commands and leases are never client inputs."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .contracts import Contract, Topology


class TrainingConfiguration(Contract):
    epochs: int = Field(default=20, ge=1, le=20)
    batch_size: int = Field(default=8, ge=1, le=64)
    learning_rate: float = Field(default=0.001, gt=0, le=1)
    max_steps: int = Field(default=10000, ge=1, le=100000)
    max_seconds: float = Field(default=1800, ge=1, le=1800)


class StartRunRequest(Contract):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    manifest_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str = Field(min_length=1, max_length=100)
    preprocessing_version: str = Field(min_length=1, max_length=100)
    protocol_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    topology: Topology = Field(default_factory=Topology)
    seed: int = Field(ge=0, le=2147483647)
    purpose: Literal["smoke", "train"]
    configuration: TrainingConfiguration

    @model_validator(mode="after")
    def smoke_budget(self) -> Self:
        if self.purpose == "smoke" and self.configuration.max_steps > 50:
            raise ValueError("SMOKE_STEP_LIMIT")
        return self


class RunMutation(Contract):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_attempt: int = Field(ge=1)


class Artifact(Contract):
    relative_path: str
    sha256: str


class RunState(Contract):
    id: str
    request: StartRunRequest
    fingerprint: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    attempt: int = 1
    fence: int = 1
    lease: str
    created_at: float
    launch_deadline: float
    pid: int | None = None
    process_created: str | None = None
    heartbeat_at: float | None = None
    started_at: float | None = None
    last_accounted_at: float | None = None
    attempt_deadline: float | None = None
    used_seconds: float = 0
    conservative_seconds: float = 0
    reserved_steps: int = 0
    cancel_requested: bool = False
    checkpoint: Artifact | None = None
    checkpoint_epoch: int = 0
    report: Artifact | None = None
    artifacts: dict[str, Artifact] = Field(default_factory=dict)
    best_epoch: int | None = None
    error: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class RunPage(Contract):
    runs: list[RunState]
    total: int
