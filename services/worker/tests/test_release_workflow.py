from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError, JobType, create_job
from game_predictor_api.domain.mobile_releases import (
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseGame,
    MobileReleaseStatus,
    complete_mobile_release,
    fail_mobile_release,
    mark_mobile_release_building,
    record_mobile_release_snapshot,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.payouts.readiness import PayoutReadinessError
from game_predictor_worker.releases import android as android_module
from game_predictor_worker.releases.android import (
    AndroidReleaseError,
    PowerShellAndroidReleaseBuilder,
)
from game_predictor_worker.releases.contracts import (
    AndroidReleaseArtifact,
    AndroidReleaseBuildSpec,
)
from game_predictor_worker.releases.handler import ReleaseWorkflowHandler
from game_predictor_worker.snapshots import SnapshotArtifactError


class FakeReleaseStore:
    def __init__(self, release: MobileRelease) -> None:
        self.release = release
        self.fail_at: str | None = None
        self.mark_failed_calls = 0

    def _raise_if_requested(self, stage: str) -> None:
        if self.fail_at == stage:
            raise MobileReleaseConflictError(
                f"TEST_{stage.upper()}_FAILED",
                f"Controlled {stage} failure.",
            )

    def load_release(self, mobile_release_id: object) -> MobileRelease | None:
        return self.release if mobile_release_id == self.release.id else None

    def require_current_sources(self, release: MobileRelease) -> None:
        assert release == self.release
        self._raise_if_requested("sources")

    def mark_building(
        self,
        mobile_release_id: object,
        *,
        build_job_id: object,
    ) -> MobileRelease:
        assert mobile_release_id == self.release.id
        self.release = mark_mobile_release_building(
            self.release,
            build_job_id=build_job_id,  # type: ignore[arg-type]
        )
        return self.release

    def record_snapshot(
        self,
        mobile_release_id: object,
        *,
        build_job_id: object,
        relative_path: str,
        checksum: str,
    ) -> MobileRelease:
        assert mobile_release_id == self.release.id
        self._raise_if_requested("snapshot_record")
        self.release = record_mobile_release_snapshot(
            self.release,
            build_job_id=build_job_id,  # type: ignore[arg-type]
            relative_path=relative_path,
            checksum=checksum,
        )
        return self.release

    def mark_ready(
        self,
        mobile_release_id: object,
        *,
        build_job_id: object,
        apk_relative_path: str,
        apk_checksum: str,
    ) -> MobileRelease:
        assert mobile_release_id == self.release.id
        self._raise_if_requested("mark_ready")
        self.release = complete_mobile_release(
            self.release,
            build_job_id=build_job_id,  # type: ignore[arg-type]
            apk_relative_path=apk_relative_path,
            apk_checksum=apk_checksum,
        )
        return self.release

    def mark_failed(
        self,
        mobile_release_id: object,
        *,
        build_job_id: object,
    ) -> MobileRelease:
        assert mobile_release_id == self.release.id
        self.mark_failed_calls += 1
        self.release = fail_mobile_release(
            self.release,
            build_job_id=build_job_id,  # type: ignore[arg-type]
        )
        return self.release


class FakeContext:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []
        self.fail_stage: str | None = None
        self.fail_with_lease_loss = False

    def checkpoint(self, **values: object) -> None:
        if values["stage"] == self.fail_stage:
            if self.fail_with_lease_loss:
                raise JobConflictError(
                    "JOB_LEASE_LOST",
                    "Controlled lease loss.",
                )
            raise RuntimeError("Controlled checkpoint failure.")
        self.checkpoints.append(values)


class FakeReadiness:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready
        self.require_count = 0

    def assess(self, *_args: object) -> SimpleNamespace:
        return SimpleNamespace(ready=self.ready)

    def require(self, *_args: object) -> SimpleNamespace:
        self.require_count += 1
        assert self.ready
        return SimpleNamespace(ready=True)


class FakePayoutHandler:
    def __init__(self, readiness: FakeReadiness) -> None:
        self.readiness = readiness
        self.calls = 0
        self.fail = False

    def __call__(self, context: object, job: object) -> None:
        self.calls += 1
        if self.fail:
            raise PayoutReadinessError(
                "PAYOUT_TEST_FAILURE",
                "Controlled payout failure.",
            )
        context.checkpoint(  # type: ignore[attr-defined]
            checkpoint_payload={
                "schema_version": 1,
                "workflow": "payout",
                "last_sequence_number": 2,
                "processed_count": 2,
            },
            stage="calculating_payouts",
            current=2,
            total=2,
            success_count=2,
            failure_count=0,
            review_count=0,
        )
        self.readiness.ready = True


class FakePublisher:
    def __init__(self, artifact: object) -> None:
        self.artifact = artifact
        self.calls = 0
        self.fail = False

    def publish(self, _spec: object) -> object:
        self.calls += 1
        if self.fail:
            raise SnapshotArtifactError(
                "SNAPSHOT_TEST_FAILURE",
                "Controlled snapshot failure.",
            )
        return self.artifact


class FakeAndroidBuilder:
    def __init__(self, artifact: AndroidReleaseArtifact) -> None:
        self.artifact = artifact
        self.calls = 0
        self.fail = False

    def build(self, _spec: AndroidReleaseBuildSpec) -> AndroidReleaseArtifact:
        self.calls += 1
        if self.fail:
            raise AndroidReleaseError(
                "ANDROID_BUILD_FAILED",
                "Controlled test failure.",
            )
        return self.artifact


def _release_and_job() -> tuple[MobileRelease, object]:
    game_id = uuid4()
    release_id = uuid4()
    job = create_job(
        JobType.ANDROID_BUILD,
        game_id=None,
        input_payload={
            "schema_version": 1,
            "mobile_release_id": str(release_id),
        },
    )
    release = MobileRelease(
        id=release_id,
        version="m3.4-test",
        status=MobileReleaseStatus.BUILDING,
        algorithm_version="payout-v2",
        snapshot_schema_version=2,
        snapshot_path=None,
        snapshot_checksum=None,
        apk_path=None,
        apk_checksum=None,
        build_job_id=job.id,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
        ready_at=None,
        games=(
            MobileReleaseGame(
                game_id=game_id,
                game_code="game-1",
                dataset_version_id=uuid4(),
                dataset_version=2,
                rules_version_id=uuid4(),
                rules_version=3,
                rows=3,
                columns=5,
                layout_count=2,
            ),
        ),
    )
    return release, job


def _handler_fixture(
    tmp_path: Path,
    *,
    payouts_ready: bool,
) -> tuple[
    ReleaseWorkflowHandler,
    FakeReleaseStore,
    FakeContext,
    FakePayoutHandler,
    FakePublisher,
    FakeAndroidBuilder,
    object,
]:
    release, job = _release_and_job()
    snapshot_path = tmp_path / "snapshots" / release.version / "logical" / "snapshot.db"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(b"snapshot")
    manifest_path = snapshot_path.with_name("manifest.json")
    manifest_path.write_text("{}", encoding="utf-8")
    snapshot_checksum = hashlib.sha256(b"snapshot").hexdigest()
    snapshot = SimpleNamespace(
        directory=snapshot_path.parent,
        database_path=snapshot_path,
        manifest_path=manifest_path,
        manifest=SimpleNamespace(
            release_version=release.version,
            snapshot_file_sha256=snapshot_checksum,
            logical_content_sha256="c" * 64,
        ),
    )
    apk_path = (
        tmp_path / "android-releases" / release.version / "logical" / "apk" / "app-release.apk"
    )
    apk_path.parent.mkdir(parents=True)
    apk_path.write_bytes(b"apk")
    apk_checksum = hashlib.sha256(b"apk").hexdigest()
    readiness = FakeReadiness(payouts_ready)
    payout_handler = FakePayoutHandler(readiness)
    builder = FakeAndroidBuilder(
        AndroidReleaseArtifact(
            apk_path=apk_path,
            apk_sha256=apk_checksum,
            snapshot_sha256=snapshot_checksum,
        )
    )
    store = FakeReleaseStore(release)
    context = FakeContext()
    publisher = FakePublisher(snapshot)
    handler = ReleaseWorkflowHandler(
        store,  # type: ignore[arg-type]
        payout_handler,  # type: ignore[arg-type]
        readiness,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        builder,
        tmp_path,
    )
    return handler, store, context, payout_handler, publisher, builder, job


def test_release_workflow_completes_missing_payouts_and_marks_ready(
    tmp_path: Path,
) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=False,
    )

    handler(context, job)  # type: ignore[arg-type]

    assert payouts.calls == 1
    assert publisher.calls == 1
    assert builder.calls == 1
    assert store.release.status is MobileReleaseStatus.READY
    assert store.release.snapshot_checksum is not None
    assert store.release.apk_checksum is not None
    assert context.checkpoints[-1]["stage"] == "apk_verified"
    nested = context.checkpoints[0]["checkpoint_payload"]
    assert isinstance(nested, dict)
    assert nested["active_game_id"] == str(store.release.games[0].game_id)


def test_release_workflow_failure_never_marks_ready(tmp_path: Path) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=True,
    )
    builder.fail = True

    with pytest.raises(JobHandlerError) as error:
        handler(context, job)  # type: ignore[arg-type]

    assert error.value.code == "ANDROID_BUILD_FAILED"
    assert payouts.calls == 0
    assert publisher.calls == 1
    assert store.release.status is MobileReleaseStatus.FAILED
    assert store.release.apk_path is None


@pytest.mark.parametrize(
    ("failure_stage", "expected_code", "expected_publisher_calls", "expected_builder_calls"),
    (
        ("sources", "TEST_SOURCES_FAILED", 0, 0),
        ("payout", "PAYOUT_TEST_FAILURE", 0, 0),
        ("snapshot_publish", "SNAPSHOT_TEST_FAILURE", 1, 0),
        ("snapshot_record", "TEST_SNAPSHOT_RECORD_FAILED", 1, 0),
        ("snapshot_verified", "JOB_EXECUTION_FAILED", 1, 0),
        ("mark_ready", "TEST_MARK_READY_FAILED", 1, 1),
    ),
)
def test_release_workflow_controlled_stage_failures_never_mark_ready(
    tmp_path: Path,
    failure_stage: str,
    expected_code: str,
    expected_publisher_calls: int,
    expected_builder_calls: int,
) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=failure_stage != "payout",
    )
    if failure_stage in {"sources", "snapshot_record", "mark_ready"}:
        store.fail_at = failure_stage
    elif failure_stage == "payout":
        payouts.fail = True
    elif failure_stage == "snapshot_publish":
        publisher.fail = True
    else:
        context.fail_stage = failure_stage

    with pytest.raises(Exception) as error:
        handler(context, job)  # type: ignore[arg-type]

    if isinstance(error.value, JobHandlerError):
        assert error.value.code == expected_code
    else:
        assert expected_code == "JOB_EXECUTION_FAILED"
        assert isinstance(error.value, RuntimeError)
    assert store.release.status is MobileReleaseStatus.FAILED
    assert store.release.apk_path is None
    assert publisher.calls == expected_publisher_calls
    assert builder.calls == expected_builder_calls


def test_release_workflow_rejects_apk_with_different_snapshot(
    tmp_path: Path,
) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=True,
    )
    builder.artifact = replace(
        builder.artifact,
        snapshot_sha256="0" * 64,
    )

    with pytest.raises(JobHandlerError) as error:
        handler(context, job)  # type: ignore[arg-type]

    assert error.value.code == "ANDROID_SNAPSHOT_MISMATCH"
    assert store.release.status is MobileReleaseStatus.FAILED
    assert store.release.snapshot_path is not None
    assert store.release.apk_path is None
    assert publisher.calls == 1
    assert builder.calls == 1


def test_release_workflow_lease_loss_does_not_mutate_release_to_failed(
    tmp_path: Path,
) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=True,
    )
    context.fail_stage = "snapshot_verified"
    context.fail_with_lease_loss = True

    with pytest.raises(JobConflictError) as error:
        handler(context, job)  # type: ignore[arg-type]

    assert error.value.code == "JOB_LEASE_LOST"
    assert store.release.status is MobileReleaseStatus.BUILDING
    assert store.release.snapshot_path is not None
    assert store.release.apk_path is None
    assert store.mark_failed_calls == 0
    assert publisher.calls == 1
    assert builder.calls == 0


def test_release_workflow_rejects_checkpoint_from_another_release(
    tmp_path: Path,
) -> None:
    handler, store, context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=True,
    )
    job = replace(
        job,
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "mobile_release",
            "mobile_release_id": str(uuid4()),
            "completed_game_ids": [],
        },
    )

    with pytest.raises(JobHandlerError) as error:
        handler(context, job)  # type: ignore[arg-type]

    assert error.value.code == "RELEASE_CHECKPOINT_MISMATCH"
    assert store.release.status is MobileReleaseStatus.FAILED
    assert payouts.calls == 0
    assert publisher.calls == 0
    assert builder.calls == 0


def test_release_workflow_retry_resumes_same_job_without_repeating_payouts(
    tmp_path: Path,
) -> None:
    handler, store, first_context, payouts, publisher, builder, job = _handler_fixture(
        tmp_path,
        payouts_ready=False,
    )
    publisher.fail = True

    with pytest.raises(JobHandlerError):
        handler(first_context, job)  # type: ignore[arg-type]

    assert store.release.status is MobileReleaseStatus.FAILED
    assert payouts.calls == 1
    persisted_checkpoint = first_context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(persisted_checkpoint, dict)
    assert persisted_checkpoint["completed_game_ids"] == [str(store.release.games[0].game_id)]

    publisher.fail = False
    resumed_job = replace(job, checkpoint_payload=persisted_checkpoint)
    resumed_context = FakeContext()
    handler(resumed_context, resumed_job)  # type: ignore[arg-type]

    assert payouts.calls == 1
    assert publisher.calls == 2
    assert builder.calls == 1
    assert store.release.status is MobileReleaseStatus.READY
    assert store.release.build_job_id == job.id


def test_controlled_android_builder_restores_assets_and_publishes_immutable_apk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    mobile_assets = repository / "apps" / "mobile" / "assets" / "snapshot"
    mobile_assets.mkdir(parents=True)
    baseline_database = b"baseline-db"
    baseline_manifest = b'{"fixture":true}\n'
    (mobile_assets / "m1-snapshot.db").write_bytes(baseline_database)
    (mobile_assets / "manifest.json").write_bytes(baseline_manifest)
    (repository / "scripts").mkdir()

    snapshot_directory = artifact_root / "snapshots" / "release-1" / ("c" * 64)
    snapshot_directory.mkdir(parents=True)
    snapshot_database = b"production-snapshot"
    snapshot_checksum = hashlib.sha256(snapshot_database).hexdigest()
    snapshot_path = snapshot_directory / "snapshot.db"
    snapshot_path.write_bytes(snapshot_database)
    manifest_path = snapshot_directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "releaseVersion": "release-1",
                "snapshotFileSha256": snapshot_checksum,
            }
        ),
        encoding="utf-8",
    )
    snapshot = SimpleNamespace(
        directory=snapshot_directory,
        database_path=snapshot_path,
        manifest_path=manifest_path,
        manifest=SimpleNamespace(
            release_version="release-1",
            snapshot_file_sha256=snapshot_checksum,
            logical_content_sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(
        android_module,
        "validate_snapshot_artifact",
        lambda _directory: snapshot,
    )

    def command_runner(command: object, _cwd: Path) -> None:
        values = list(command)  # type: ignore[arg-type]
        if "build_android_debug.ps1" not in " ".join(values):
            return
        apk_path = (
            repository
            / "apps"
            / "mobile"
            / "android"
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "release"
            / "app-release.apk"
        )
        apk_path.parent.mkdir(parents=True, exist_ok=True)
        apk_path.unlink(missing_ok=True)
        with zipfile.ZipFile(apk_path, "w") as archive:
            archive.writestr(
                "assets/index.android.bundle",
                f"release-1 {snapshot_checksum} local_data_error",
            )
            archive.writestr("assets/snapshot.db", snapshot_database)

    builder = PowerShellAndroidReleaseBuilder(
        repository,
        artifact_root,
        command_runner=command_runner,
    )
    build_spec = AndroidReleaseBuildSpec(
        release_version="release-1",
        version_code=123,
        snapshot=snapshot,  # type: ignore[arg-type]
    )
    artifact = builder.build(build_spec)

    assert artifact.apk_path.is_file()
    assert artifact.snapshot_sha256 == snapshot_checksum
    assert (mobile_assets / "m1-snapshot.db").read_bytes() == baseline_database
    assert (mobile_assets / "manifest.json").read_bytes() == baseline_manifest

    artifact.apk_path.write_bytes(b"corrupt-existing-apk")
    corrupt_bytes = artifact.apk_path.read_bytes()

    with pytest.raises(AndroidReleaseError) as collision:
        builder.build(build_spec)

    assert collision.value.code == "ANDROID_ARTIFACT_COLLISION"
    assert artifact.apk_path.read_bytes() == corrupt_bytes
    assert (mobile_assets / "m1-snapshot.db").read_bytes() == baseline_database
    assert (mobile_assets / "manifest.json").read_bytes() == baseline_manifest
