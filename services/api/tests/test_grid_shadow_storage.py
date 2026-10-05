"""Lease publication tests against a recording session, without any database."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_shadow import GridShadowError, GridShadowResult, shadow_digest
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.grid_shadow import SqlAlchemyGridShadowRepository, _result
from game_predictor_api.storage.models import ImageGeometryShadowResultModel, JobModel
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session


class RecordingSession:
    def __init__(self, job: JobModel) -> None:
        self.job = job
        self.records: list[object] = []
        self.lock_order: list[str] = []
        self.game_exists = True
        self.game_lock_sql = ""

    def scalar(self, statement: Any) -> JobModel | UUID | None:
        if "FROM games" in str(statement):
            self.lock_order.append("game")
            self.game_lock_sql = str(statement.compile(dialect=postgresql.dialect()))
            return self.job.game_id if self.game_exists else None
        self.lock_order.append("job")
        return self.job

    def execute(self, statement: Any) -> None:
        self.lock_order.append(
            "sequence" if "pg_advisory_xact_lock" in str(statement) else "source"
        )

    def add(self, record: object) -> None:
        self.records.append(record)

    def flush(self) -> None:
        pass

    def connection(self) -> Any:
        class Connection:
            class Dialect:
                name = "sqlite"

            dialect = Dialect()

        return Connection()


class Repository(SqlAlchemyGridShadowRepository):
    def __init__(self, session: RecordingSession, pinned: dict[str, object]) -> None:
        super().__init__(cast(Session, session))
        self.pinned = pinned
        self.existing: GridShadowResult | None = None
        self.drift = False

    def pin_source(self, game_id: UUID, source_image_id: UUID) -> dict[str, object]:
        return {**self.pinned, "bindings_sha256": "drift"} if self.drift else self.pinned

    def get_result_for_source(
        self, game_id: UUID, job_id: UUID, source_image_id: UUID
    ) -> GridShadowResult | None:
        return self.existing


def setup() -> tuple[Repository, RecordingSession, dict[str, Any]]:
    game_id, job_id, token = uuid4(), uuid4(), uuid4()
    pinned: dict[str, object] = {
        "source_image_id": str(uuid4()),
        "checksum_sha256": "a" * 64,
        "source_geometry_revision_id": str(uuid4()),
        "source_geometry_revision": 1,
        "geometry_checksum_sha256": "b" * 64,
        "width": 100,
        "height": 100,
        "sequence_range_start": 1,
        "sequence_range_end": 1,
        "active_board_slots": [0],
        "bindings_sha256": "bound",
    }
    model = {
        "profile": "grid_profile_mumie_v1",
        "version": "v1",
        "manifest_checksum_sha256": "c" * 64,
    }
    pinned_without_digest = {
        key: value for key, value in pinned.items() if key != "bindings_sha256"
    }
    pinned["bindings_sha256"] = shadow_digest(pinned_without_digest)
    output = {
        "schemaVersion": 1,
        "status": "needs_review",
        "reasons": [],
        "slots": [
            {
                "positionIndex": 0,
                "sequenceNumber": 1,
                "baselineNodes24": None,
                "neuralNodes24": None,
                "state": "missing",
                "reasonCodes": [],
                "cellVisibility": ["outside"] * 15,
            }
        ],
        "unassignedDetections": [],
    }
    job = JobModel(
        id=job_id,
        game_id=game_id,
        status=JobStatus.PROCESSING,
        lease_owner="worker",
        lease_token=token,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        cancel_requested_at=None,
        input_payload={
            "validation_kind": "grid_geometry_shadow_v3",
            "sources": [pinned],
            "model": model,
        },
    )
    session = RecordingSession(job)
    args: dict[str, Any] = {
        "game_id": game_id,
        "job_id": job_id,
        "lease_owner": "worker",
        "lease_token": token,
        "pinned_source": pinned,
        "model": model,
        "output": output,
    }
    return Repository(session, pinned), session, args


@pytest.mark.parametrize("change", ["token", "owner", "expired", "cancelled", "status"])
def test_old_or_cancelled_writer_cannot_publish(change: str) -> None:
    repository, session, args = setup()
    if change == "token":
        session.job.lease_token = uuid4()
    elif change == "owner":
        session.job.lease_owner = "new-worker"
    elif change == "expired":
        session.job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "cancelled":
        session.job.cancel_requested_at = datetime.now(UTC)
    else:
        session.job.status = JobStatus.FAILED
    with pytest.raises(GridShadowError) as error:
        repository.publish_result(**args)
    assert error.value.code == "GRID_SHADOW_LEASE_LOST" and not session.records


def test_restart_recovers_identical_result_and_rejects_changed_output() -> None:
    repository, session, args = setup()
    first = repository.publish_result(**args)
    assert session.lock_order[:4] == ["game", "sequence", "source", "job"]
    assert "FOR KEY SHARE" in session.game_lock_sql
    assert first.output_checksum_sha256 == shadow_digest(args["output"])
    repository.existing = first
    assert repository.publish_result(**args).id == first.id
    assert len(session.records) == 1
    args["output"]["reasons"] = ["changed"]
    with pytest.raises(GridShadowError) as error:
        repository.publish_result(**args)
    assert error.value.code == "GRID_SHADOW_RESULT_CONFLICT" and len(session.records) == 1


def test_deleted_game_prevents_source_or_job_lock_and_publication() -> None:
    repository, session, args = setup()
    session.game_exists = False
    with pytest.raises(GridShadowError) as error:
        repository.publish_result(**args)
    assert error.value.code == "GAME_NOT_FOUND"
    assert session.lock_order == ["game"]
    assert not session.records


def test_source_drift_or_unpinned_model_prevents_publication() -> None:
    repository, session, args = setup()
    repository.drift = True
    with pytest.raises(GridShadowError) as error:
        repository.publish_result(**args)
    assert error.value.code == "GRID_SHADOW_SOURCE_STALE" and not session.records
    repository.drift = False
    args["model"] = {**args["model"], "version": "replaced"}
    with pytest.raises(GridShadowError) as error:
        repository.publish_result(**args)
    assert error.value.code == "GRID_SHADOW_JOB_BINDING_INVALID" and not session.records


@pytest.mark.parametrize("change", ["output", "source", "model", "identity"])
def test_read_detects_corrupted_outputs_bindings_and_identities(change: str) -> None:
    repository, session, args = setup()
    repository.publish_result(**args)
    row = cast(ImageGeometryShadowResultModel, session.records[0])
    if change == "output":
        row.output = {**row.output, "reasons": ["tampered"]}
    elif change == "source":
        row.source_binding = {**row.source_binding, "source_geometry_revision": 9}
    elif change == "model":
        row.model_binding = {**row.model_binding, "version": "unbound"}
    else:
        row.source_image_id = uuid4()
    with pytest.raises(GridShadowError):
        _result(row)
