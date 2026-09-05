from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.cleanup import CleanupService, ManagedCleanupArtifactStore
from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
    CleanupCommand,
    CleanupConflictError,
    CleanupCount,
    CleanupResult,
    CleanupSnapshot,
    cleanup_preview,
)


class FakeCleanupRepository:
    def __init__(self, snapshot: CleanupSnapshot) -> None:
        self.snapshot = snapshot
        self.deleted = False
        self.completed: CleanupResult | None = None
        self.fail_board_delete = False

    def release_snapshot(self, _target_id: UUID, *, for_update: bool = False) -> CleanupSnapshot:
        del for_update
        return self.snapshot

    def game_snapshot(self, _target_id: UUID, *, for_update: bool = False) -> CleanupSnapshot:
        del for_update
        return self.snapshot

    def completed_result(
        self, _kind: str, _target_id: UUID, _preview_token: str
    ) -> CleanupResult | None:
        return self.completed

    def delete_release(self, _snapshot: CleanupSnapshot, result: CleanupResult) -> None:
        self.deleted = True
        self.completed = result

    def reset_game(self, _snapshot: CleanupSnapshot, result: CleanupResult) -> None:
        self.deleted = True
        self.completed = result

    def board_source_snapshot(
        self,
        _target_id: UUID,
        _selection: BoardSourceCleanupSelection,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot:
        del for_update
        return self.snapshot

    def delete_board_sources(
        self,
        _snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None:
        if self.fail_board_delete:
            raise RuntimeError("database rollback")
        self.deleted = True
        self.completed = result


class FakeArtifacts:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: tuple[str, ...] = ()
        self.quarantined: tuple[str, ...] = ()
        self.restored: tuple[str, ...] = ()
        self.finalized: tuple[str, ...] = ()

    def delete(self, paths: tuple[str, ...]) -> None:
        self.deleted = paths
        if self.fail:
            raise CleanupConflictError("CLEANUP_ARTIFACT_DELETE_FAILED", "failed")

    def quarantine(self, operation_key: str, paths: tuple[str, ...]) -> None:
        self.quarantined = (operation_key, *paths)

    def restore(self, operation_key: str) -> None:
        self.restored = (*self.restored, operation_key)

    def finalize(self, operation_key: str) -> None:
        self.finalized = (*self.finalized, operation_key)

    def recover(self, _completed_operation_keys: set[str]) -> None:
        return


def _snapshot(*, blockers: tuple[str, ...] = ()) -> CleanupSnapshot:
    target_id = uuid4()
    return CleanupSnapshot(
        kind="mobile_release",
        target_id=target_id,
        target_label="0.2-test",
        confirmation_target=str(target_id),
        counts=(CleanupCount("mobile_releases", 1),),
        artifact_paths=("snapshots/0.2-test", "android-releases/0.2-test"),
        retained_shared_artifact_count=1,
        blockers=blockers,
    )


def _command(snapshot: CleanupSnapshot) -> CleanupCommand:
    preview = cleanup_preview(snapshot)
    return CleanupCommand(
        preview_token=preview.preview_token,
        confirmation_target=snapshot.confirmation_target,
        confirmed=True,
    )


def test_cleanup_is_bound_to_exact_preview_and_confirmation() -> None:
    snapshot = _snapshot()
    repository = FakeCleanupRepository(snapshot)
    artifacts = FakeArtifacts()
    service = CleanupService(repository, artifacts)

    result = service.delete_release(snapshot.target_id, _command(snapshot))

    assert repository.deleted is True
    assert artifacts.deleted == snapshot.artifact_paths
    assert result.deleted_artifact_count == 2
    assert result.retained_shared_artifact_count == 1


def test_stale_or_blocked_cleanup_does_not_touch_files_or_database() -> None:
    snapshot = _snapshot()
    repository = FakeCleanupRepository(snapshot)
    artifacts = FakeArtifacts()
    service = CleanupService(repository, artifacts)

    stale = replace(_command(snapshot), preview_token="0" * 64)
    with pytest.raises(CleanupConflictError, match="preview") as stale_error:
        service.delete_release(snapshot.target_id, stale)
    assert stale_error.value.code == "CLEANUP_PREVIEW_STALE"

    repository.snapshot = replace(snapshot, blockers=("ACTIVE_RELEASE_BUILD",))
    blocked_command = _command(repository.snapshot)
    with pytest.raises(CleanupConflictError, match="blocked") as blocked_error:
        service.delete_release(snapshot.target_id, blocked_command)
    assert blocked_error.value.code == "CLEANUP_BLOCKED"
    assert repository.deleted is False
    assert artifacts.deleted == ()


def test_artifact_failure_preserves_database_and_same_receipt_is_idempotent() -> None:
    snapshot = _snapshot()
    repository = FakeCleanupRepository(snapshot)
    failing_artifacts = FakeArtifacts(fail=True)
    service = CleanupService(repository, failing_artifacts)
    command = _command(snapshot)

    with pytest.raises(CleanupConflictError) as failure:
        service.delete_release(snapshot.target_id, command)
    assert failure.value.code == "CLEANUP_ARTIFACT_DELETE_FAILED"
    assert repository.deleted is False

    successful = CleanupService(repository, FakeArtifacts())
    first = successful.delete_release(snapshot.target_id, command)
    second = successful.delete_release(snapshot.target_id, command)
    assert first.already_completed is False
    assert second.already_completed is True


def test_board_source_cleanup_quarantines_until_the_database_commit_finishes() -> None:
    target_id = uuid4()
    snapshot = CleanupSnapshot(
        kind="board_source_ranges",
        target_id=target_id,
        target_label="source range",
        confirmation_target=f"{target_id}:1-9",
        counts=(CleanupCount("source_images", 1),),
        artifact_paths=("data/originals/seq_1-9.jpg",),
        retained_shared_artifact_count=0,
        blockers=(),
    )
    repository = FakeCleanupRepository(snapshot)
    artifacts = FakeArtifacts()
    service = CleanupService(repository, artifacts)
    preview = cleanup_preview(snapshot)

    result = service.delete_board_sources(
        target_id,
        BoardSourceCleanupSelection(tuple(range(1, 10))),
        CleanupCommand(
            preview_token=preview.preview_token,
            confirmation_target=snapshot.confirmation_target,
            confirmed=True,
        ),
    )

    assert repository.deleted is True
    assert artifacts.deleted == ()
    assert artifacts.quarantined == (
        preview.preview_token,
        "data/originals/seq_1-9.jpg",
    )
    assert result.quarantine_key == preview.preview_token
    service.finalize_committed_artifacts()
    assert artifacts.finalized == (preview.preview_token,)


def test_managed_cleanup_quarantine_restores_or_finalizes_after_recovery(tmp_path) -> None:
    operation_key = "a" * 64
    artifact = tmp_path / "data" / "originals" / "seq_1-9.jpg"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"original")
    store = ManagedCleanupArtifactStore(tmp_path)

    store.quarantine(operation_key, ("data/originals/seq_1-9.jpg",))
    assert artifact.exists() is False
    store.recover(set())
    assert artifact.read_bytes() == b"original"

    store.quarantine(operation_key, ("data/originals/seq_1-9.jpg",))
    store.recover({operation_key})
    assert artifact.exists() is False


def test_board_source_cleanup_restores_quarantine_when_database_mutation_fails() -> None:
    target_id = uuid4()
    snapshot = CleanupSnapshot(
        kind="board_source_ranges",
        target_id=target_id,
        target_label="source range",
        confirmation_target=f"{target_id}:1-9",
        counts=(CleanupCount("source_images", 1),),
        artifact_paths=("data/originals/seq_1-9.jpg",),
        retained_shared_artifact_count=0,
        blockers=(),
    )
    repository = FakeCleanupRepository(snapshot)
    repository.fail_board_delete = True
    artifacts = FakeArtifacts()
    service = CleanupService(repository, artifacts)
    preview = cleanup_preview(snapshot)

    with pytest.raises(RuntimeError, match="database rollback"):
        service.delete_board_sources(
            target_id,
            BoardSourceCleanupSelection(tuple(range(1, 10))),
            CleanupCommand(
                preview_token=preview.preview_token,
                confirmation_target=snapshot.confirmation_target,
                confirmed=True,
            ),
        )

    assert artifacts.restored == (preview.preview_token,)
    assert artifacts.finalized == ()


def test_unsafe_cleanup_path_does_not_leave_an_incomplete_quarantine(tmp_path) -> None:
    store = ManagedCleanupArtifactStore(tmp_path)
    operation_key = "b" * 64

    with pytest.raises(CleanupConflictError) as error:
        store.quarantine(operation_key, ("../outside.jpg",))

    assert error.value.code == "CLEANUP_ARTIFACT_PATH_UNSAFE"
    assert (tmp_path / "cleanup-quarantine" / operation_key).exists() is False
