"""Unit tests for partition-aware unique constraint resolution (catalog mocked)."""

from types import SimpleNamespace
from unittest.mock import Mock

from game_predictor_api.storage.models import (
    ImageImportGeometryGuardDecisionModel,
    ImagePageGeometryOverrideModel,
    ReviewBatchModel,
    ReviewerWorkAssignmentModel,
)
from game_predictor_api.storage.partition_constraints import (
    ParentUniqueIndex,
    declared_unique_names,
    match_declared_unique_name,
    resolve_unique_constraint_name,
)
from sqlalchemy.exc import IntegrityError


def _error(constraint: str | None, schema: str | None = "game_data_v2") -> IntegrityError:
    diag = SimpleNamespace(constraint_name=constraint, schema_name=schema)
    return IntegrityError("INSERT", {}, SimpleNamespace(diag=diag))  # type: ignore[arg-type]


def _session_returning(parent: ParentUniqueIndex | None) -> Mock:
    session = Mock()
    row = (
        None
        if parent is None
        else SimpleNamespace(
            index_name=parent.index_name,
            table_name=parent.table_name,
            is_unique=parent.is_unique,
            key_columns=list(parent.key_columns),
            predicate=parent.predicate,
        )
    )
    session.execute.return_value.one_or_none.return_value = row
    return session


def test_partial_unique_index_matches_orm_name_ignoring_partition_column() -> None:
    parent = ParentUniqueIndex(
        "v2_ix_fa8cf5eef7574f8e7690",
        "reviewer_work_assignments",
        True,
        ("game_id", "import_job_id"),
        "(closed_at IS NULL)",
    )
    table = ReviewerWorkAssignmentModel.__table__
    assert match_declared_unique_name(table, parent) == "uq_reviewer_work_assignments_active_import"
    session = _session_returning(parent)
    assert (
        resolve_unique_constraint_name(session, _error("gpv2_x_game_id_import_job_id_idx1"), table)
        == "uq_reviewer_work_assignments_active_import"
    )


def test_unique_constraints_match_by_columns() -> None:
    cases = (
        (
            ReviewBatchModel.__table__,
            "review_batches",
            ("game_id", "source_report_sha256"),
            "uq_review_batches_source_report_sha256",
        ),
        (
            ImagePageGeometryOverrideModel.__table__,
            "image_page_geometry_overrides",
            ("game_id", "source_checksum_sha256", "revision"),
            "uq_image_page_geometry_overrides_revision",
        ),
        (
            ImageImportGeometryGuardDecisionModel.__table__,
            "image_import_geometry_guard_decisions",
            ("game_id", "guard_job_id", "decision_checksum_sha256"),
            "uq_image_import_guard_decisions_checksum",
        ),
    )
    for table, table_name, columns, expected in cases:
        parent = ParentUniqueIndex("v2_uq_x", table_name, True, columns, None)
        assert match_declared_unique_name(table, parent) == expected


def test_non_matching_or_non_unique_parent_is_not_mapped() -> None:
    table = ReviewerWorkAssignmentModel.__table__
    wrong_predicate = ParentUniqueIndex(
        "v2_ix_a", "reviewer_work_assignments", True, ("game_id", "import_job_id"), None
    )
    not_unique = ParentUniqueIndex(
        "v2_ix_b",
        "reviewer_work_assignments",
        False,
        ("game_id", "import_job_id"),
        "(closed_at IS NULL)",
    )
    other_table = ParentUniqueIndex(
        "v2_ix_c", "review_batches", True, ("game_id", "import_job_id"), "(closed_at IS NULL)"
    )
    for parent in (wrong_predicate, not_unique, other_table):
        assert match_declared_unique_name(table, parent) is None


def test_unknown_violation_keeps_reported_name() -> None:
    table = ReviewerWorkAssignmentModel.__table__
    unknown = ParentUniqueIndex(
        "v2_pk_z", "reviewer_work_assignments", True, ("game_id", "id"), None
    )
    assert (
        resolve_unique_constraint_name(_session_returning(unknown), _error("part_pkey"), table)
        == "part_pkey"
    )
    assert resolve_unique_constraint_name(_session_returning(None), _error("gone"), table) == "gone"
    assert resolve_unique_constraint_name(Mock(), _error(None), table) is None


def test_declared_name_short_circuits_catalog_lookup() -> None:
    session = Mock()
    name = "uq_review_batches_source_report_sha256"
    assert name in declared_unique_names(ReviewBatchModel.__table__)
    assert resolve_unique_constraint_name(session, _error(name), ReviewBatchModel.__table__) == name
    session.execute.assert_not_called()
