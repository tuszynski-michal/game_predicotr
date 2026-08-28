from datetime import UTC, datetime, timedelta

import pytest
from game_predictor_api.domain.storage_retention import (
    StorageArtifactClass,
    StorageArtifactObservation,
    StorageProtectionReason,
    StorageRetentionPolicy,
    canonical_gc_manifest_bytes,
    evaluate_storage_retention,
    gc_manifest_checksum_sha256,
    gc_preview_token,
    is_safe_managed_relative_path,
    manifest_entry_from_decision,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)
OLD = NOW - timedelta(hours=25)


def _observation(
    *,
    artifact_class: StorageArtifactClass = StorageArtifactClass.NORMALIZATION_WORKING_BITMAP,
    path: str = "working/image-normalization-v1/aa/key/normalized.png",
    modified_at: datetime = OLD,
    statuses: tuple[str, ...] = ("completed",),
    linked_import_exists: bool = False,
    managed_originals_verified: bool = False,
    is_symlink: bool = False,
) -> StorageArtifactObservation:
    return StorageArtifactObservation(
        relative_path=path,
        size_bytes=1234,
        modified_at=modified_at,
        artifact_class=artifact_class,
        dependency_job_statuses=statuses,
        linked_import_exists=linked_import_exists,
        managed_originals_verified=managed_originals_verified,
        is_symlink=is_symlink,
    )


@pytest.mark.parametrize("status", ["created", "processing"])
def test_active_job_dependency_always_protects_artifact(status: str) -> None:
    decision = evaluate_storage_retention(
        _observation(statuses=(status,)),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert decision.eligible is False
    assert StorageProtectionReason.ACTIVE_JOB_DEPENDENCY in decision.protection_reasons


@pytest.mark.parametrize(
    ("status", "eligible"),
    [
        ("waiting_for_review", True),
        ("completed", True),
        ("failed", True),
        ("cancelled", True),
    ],
)
def test_terminal_or_review_job_allows_elapsed_working_retention(
    status: str,
    eligible: bool,
) -> None:
    decision = evaluate_storage_retention(
        _observation(statuses=(status,)),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert decision.eligible is eligible


def test_retention_age_is_measured_after_last_dependency() -> None:
    observation = StorageArtifactObservation(
        relative_path="working/image-normalization-v1/aa/key/normalized.png",
        size_bytes=1,
        modified_at=NOW - timedelta(days=4),
        artifact_class=StorageArtifactClass.NORMALIZATION_WORKING_BITMAP,
        dependency_job_statuses=("completed",),
        last_dependency_at=NOW - timedelta(hours=2),
    )

    decision = evaluate_storage_retention(
        observation,
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert decision.eligible is False
    assert decision.protection_reasons == (StorageProtectionReason.RETENTION_NOT_ELAPSED,)


def test_browser_staging_requires_import_and_verified_managed_originals() -> None:
    protected = evaluate_storage_retention(
        _observation(artifact_class=StorageArtifactClass.BROWSER_STAGING),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )
    eligible = evaluate_storage_retention(
        _observation(
            artifact_class=StorageArtifactClass.BROWSER_STAGING,
            linked_import_exists=True,
            managed_originals_verified=True,
        ),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert protected.eligible is False
    assert protected.protection_reasons == (
        StorageProtectionReason.MANAGED_ORIGINALS_INCOMPLETE,
        StorageProtectionReason.STAGING_IMPORT_MISSING,
    )
    assert eligible.eligible is True


def test_protected_namespace_is_never_eligible() -> None:
    decision = evaluate_storage_retention(
        _observation(
            artifact_class=StorageArtifactClass.PROTECTED_NAMESPACE,
            path="originals/sha256/aa/original.jpg",
        ),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert decision.eligible is False
    assert decision.protection_reasons == (StorageProtectionReason.PROTECTED_NAMESPACE,)


@pytest.mark.parametrize(
    "path",
    ["", "../working/file", "/working/file", "C:/working/file", "working\\file"],
)
def test_unsafe_managed_paths_are_rejected(path: str) -> None:
    assert is_safe_managed_relative_path(path) is False
    decision = evaluate_storage_retention(
        _observation(path=path),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )
    assert StorageProtectionReason.PATH_UNSAFE in decision.protection_reasons


def test_symlink_is_protected_even_when_target_looks_managed() -> None:
    decision = evaluate_storage_retention(
        _observation(is_symlink=True),
        policy=StorageRetentionPolicy(),
        now=NOW,
    )

    assert decision.eligible is False
    assert StorageProtectionReason.SYMBOLIC_LINK in decision.protection_reasons


def test_gc_manifest_and_preview_token_are_deterministic() -> None:
    policy = StorageRetentionPolicy()
    first = manifest_entry_from_decision(
        evaluate_storage_retention(
            _observation(path="working/z/normalized.png"),
            policy=policy,
            now=NOW,
        )
    )
    second = manifest_entry_from_decision(
        evaluate_storage_retention(
            _observation(path="working/a/normalized.png"),
            policy=policy,
            now=NOW,
        )
    )

    forward = canonical_gc_manifest_bytes((first, second), policy=policy)
    reverse = canonical_gc_manifest_bytes((second, first), policy=policy)

    assert forward == reverse
    assert gc_manifest_checksum_sha256(forward) == gc_manifest_checksum_sha256(reverse)
    assert gc_preview_token(forward, policy=policy) == gc_preview_token(reverse, policy=policy)
    assert len(gc_preview_token(forward, policy=policy)) == 64


def test_policy_rejects_incoherent_thresholds() -> None:
    with pytest.raises(ValueError, match="monotonically"):
        StorageRetentionPolicy(
            hard_reserve_bytes=70,
            automatic_gc_free_bytes=60,
            warning_free_bytes=80,
            target_free_bytes=80,
        )
