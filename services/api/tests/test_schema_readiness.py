"""TASK-0757 cutover guard: the code head constant tracks Alembic."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage import schema_readiness

ROOT = Path(__file__).resolve().parents[3]


def test_expected_head_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == [schema_readiness.EXPECTED_ALEMBIC_HEAD]
    assert schema_readiness.EXPECTED_ALEMBIC_HEAD == "0153_merge_compact_super_games"


def test_v7_merge_preserves_both_main_and_v7_migration_histories() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    merged = script.get_revision("0147_merge_v7_main")
    assert merged is not None
    assert set(merged.down_revision) == {
        "0146_symbol_review_import_filter_index",
        "0146_v7_operator_sources",
    }
    ancestors = {revision.revision for revision in script.walk_revisions()}
    assert {
        "0144_lab_symbol_candidate_registry",
        "0145_neural_page_geometry_binding",
        "0146_symbol_review_import_filter_index",
        "0144_v7_reviewed_delivery",
        "0145_v7_pilot_acceptances",
        "0146_v7_operator_sources",
    } <= ancestors
    # Joining histories is metadata only; both branches keep their own DDL.
    merged.module.upgrade()
    merged.module.downgrade()


def test_compact_merge_preserves_super_game_and_management_branches() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    merged = script.get_revision(schema_readiness.EXPECTED_ALEMBIC_HEAD)
    assert merged is not None
    assert set(merged.down_revision) == {"0152_super_game_series", "0152_management_compact_panel"}
    for parent in merged.down_revision:
        assert script.get_revision(parent).down_revision == "0151_super_game_roles"
    merged.module.upgrade()
    merged.module.downgrade()


@pytest.mark.parametrize(
    "found",
    (
        None,
        "0131_board_render_manifests",
        "0132_symbol_reference_images_cell_identity",
        "0133_virtual_only_import_policies",
        "0135_virtual_only_asset_modes",
        "0136_drop_cell_render_spec",
        "0146_symbol_review_import_filter_index",
        "0146_v7_operator_sources",
        "9999_future",
    ),
)
def test_guard_refuses_any_other_schema(monkeypatch: pytest.MonkeyPatch, found: str | None) -> None:
    monkeypatch.setattr(schema_readiness, "database_alembic_revision", lambda _engine: found)
    with pytest.raises(schema_readiness.AlembicHeadMismatchError) as error:
        schema_readiness.require_alembic_head(object())  # type: ignore[arg-type]
    assert error.value.code == "ALEMBIC_HEAD_MISMATCH"
    assert str(error.value).startswith("ALEMBIC_HEAD_MISMATCH")


def test_guard_accepts_the_code_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        schema_readiness,
        "database_alembic_revision",
        lambda _engine: schema_readiness.EXPECTED_ALEMBIC_HEAD,
    )
    schema_readiness.require_alembic_head(object())  # type: ignore[arg-type]
