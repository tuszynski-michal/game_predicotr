"""TASK-0757: per-board render manifest building, checksums and migration 0131 shape."""

from __future__ import annotations

import hashlib
import json
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.domain.board_render_manifests import (
    BOARD_RENDER_MANIFEST_SCHEMA_VERSION,
    BoardRenderManifestError,
    ObservedRenderCell,
    build_observation_render_manifest,
    crop_sample_id,
    revision_render_manifest,
    sha256_canonical_json,
)
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.storage.game_partition_lifecycle import partition_name

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0131_board_render_manifests"
PREVIOUS = "0130_board_search_share_sessions"
BOARD_ID = UUID("11111111-2222-4333-8444-555555555555")


def _spec(index: int) -> dict[str, object]:
    return {"cellIndex": index, "quad": [[0.5, 1.25], [10.0, 1.0]], "scale": 1e-07, "id": "é"}


def _cell(index: int, **overrides: object) -> ObservedRenderCell:
    spec = _spec(index)
    values: dict[str, object] = {
        "cell_index": index,
        "render_spec": spec,
        "render_spec_checksum_sha256": sha256_canonical_json(spec),
        "rendered_pixel_checksum_sha256": hashlib.sha256(f"px{index}".encode()).hexdigest(),
        "logical_cell_key": hashlib.sha256(f"key{index}".encode()).hexdigest(),
        "logical_cell_key_v2": hashlib.sha256(f"key2{index}".encode()).hexdigest(),
        "render_identity_v2_sha256": hashlib.sha256(f"id2{index}".encode()).hexdigest(),
    }
    values.update(overrides)
    return ObservedRenderCell(**values)  # type: ignore[arg-type]


def test_checksum_is_the_virtual_cell_canonical_json_sha256() -> None:
    spec = _spec(3)
    expected = hashlib.sha256(
        json.dumps(
            spec, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    assert sha256_canonical_json(spec) == expected
    # A JSONB round trip (parse of the canonical text) keeps the checksum.
    assert sha256_canonical_json(json.loads(canonical_json_bytes(spec))) == expected


def test_observation_manifest_has_virtual_render_spec_shape_and_stable_checksum() -> None:
    cells = [_cell(index) for index in (14, 0, *range(1, 14))]
    manifest = build_observation_render_manifest(
        recognized_board_id=BOARD_ID,
        cells=cells,
        expected_cell_indices=frozenset(range(15)),
    )
    document = manifest.document
    assert manifest.geometry_revision == 0 and manifest.cell_count == 15
    assert document["assetMode"] == "virtual_source"
    assert document["schemaVersion"] == BOARD_RENDER_MANIFEST_SCHEMA_VERSION
    entries = document["cells"]
    assert isinstance(entries, list)
    assert [entry["cellIndex"] for entry in entries] == list(range(15))
    first = entries[0]
    assert first["renderSpec"] == _spec(0)
    assert first["renderSpecChecksumSha256"] == sha256_canonical_json(_spec(0))
    assert first["cropSampleId"] == crop_sample_id(
        recognized_board_id=BOARD_ID,
        render_spec_checksum_sha256=sha256_canonical_json(_spec(0)),
    )
    assert manifest.checksum_sha256 == sha256_canonical_json(document)
    again = build_observation_render_manifest(recognized_board_id=BOARD_ID, cells=cells[::-1])
    assert again.checksum_sha256 == manifest.checksum_sha256


@pytest.mark.parametrize(
    ("cells", "expected", "code"),
    (
        (
            [_cell(0, render_spec_checksum_sha256="f" * 64), _cell(1)],
            None,
            "BOARD_RENDER_MANIFEST_CELL_CHECKSUM_MISMATCH",
        ),
        ([_cell(0), _cell(0)], None, "BOARD_RENDER_MANIFEST_CELL_DUPLICATE"),
        ([_cell(0)], frozenset({0, 1}), "BOARD_RENDER_MANIFEST_CELLS_INCOMPLETE"),
        (
            [_cell(0, logical_cell_key_v2=None)],
            None,
            "BOARD_RENDER_MANIFEST_CELL_IDENTITY_INVALID",
        ),
        ([_cell(0, logical_cell_key="x")], None, "BOARD_RENDER_MANIFEST_CELL_IDENTITY_INVALID"),
        ([], None, "BOARD_RENDER_MANIFEST_EMPTY"),
    ),
)
def test_observation_manifest_refuses_inconsistent_boards(
    cells: list[ObservedRenderCell], expected: frozenset[int] | None, code: str
) -> None:
    with pytest.raises(BoardRenderManifestError) as error:
        build_observation_render_manifest(
            recognized_board_id=BOARD_ID, cells=cells, expected_cell_indices=expected
        )
    assert error.value.code == code


def test_revision_manifest_is_verbatim_copy_with_revision_checksum() -> None:
    spec = {
        "assetMode": "virtual_source",
        "cells": [
            {
                "cellIndex": index,
                "renderSpec": _spec(index),
                "renderSpecChecksumSha256": sha256_canonical_json(_spec(index)),
            }
            for index in range(15)
        ],
        "geometryChecksumSha256": "a" * 64,
        "schemaVersion": "virtual-board-render-manifest-v2-dual-identity-v1",
    }
    checksum = hashlib.sha256(canonical_json_bytes(spec)).hexdigest()
    manifest = revision_render_manifest(
        recognized_board_id=BOARD_ID,
        geometry_revision=2,
        virtual_render_spec=spec,
        virtual_render_spec_checksum_sha256=checksum,
    )
    assert manifest.document == spec and manifest.checksum_sha256 == checksum
    with pytest.raises(BoardRenderManifestError) as mismatch:
        revision_render_manifest(
            recognized_board_id=BOARD_ID,
            geometry_revision=2,
            virtual_render_spec=spec,
            virtual_render_spec_checksum_sha256="0" * 64,
        )
    assert mismatch.value.code == "BOARD_RENDER_MANIFEST_REVISION_CHECKSUM_MISMATCH"
    tampered = json.loads(json.dumps(spec))
    tampered["cells"][3]["renderSpec"]["scale"] = 2.0
    with pytest.raises(BoardRenderManifestError) as cell_mismatch:
        revision_render_manifest(
            recognized_board_id=BOARD_ID,
            geometry_revision=2,
            virtual_render_spec=tampered,
            virtual_render_spec_checksum_sha256=sha256_canonical_json(tampered),
        )
    assert cell_mismatch.value.code == "BOARD_RENDER_MANIFEST_CELL_CHECKSUM_MISMATCH"
    assert cell_mismatch.value.cell_index == 3


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_migration_0131_adds_one_rls_partitioned_table_and_manifest_v3() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert sql.count("PARTITION BY LIST (game_id)") == 1
    assert "CREATE TABLE game_data_v2.board_render_manifests" in sql
    assert "ON DELETE CASCADE" in sql
    assert "CREATE POLICY game_scope_v1 ON game_data_v2.board_render_manifests" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "SET LOCAL lock_timeout" in sql and "SET LOCAL statement_timeout" in sql
    assert "CHECK (manifest_version = 'game-data-v2-manifest-v3')" in sql
    assert "GAME_STORAGE_LIFECYCLE_IN_PROGRESS" in sql
    # Partition names follow the lifecycle derivation.
    game_id = uuid4()
    expected = partition_name(game_id, "board_render_manifests")
    assert (
        expected.endswith("_" + hashlib.sha256(b"board_render_manifests").hexdigest()[:12])
        and ("_" + expected.rsplit("_", 1)[1]) in sql
    )
    assert "DELETE FROM" not in sql
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS


def test_migration_0131_downgrade_restores_v1_and_drops_without_cascade() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "DROP TABLE game_data_v2.board_render_manifests" in sql
    assert "CASCADE" not in sql
    assert "CHECK (manifest_version = 'game-data-v2-manifest-v1')" in sql
    assert sql.index("DROP CONSTRAINT") < sql.index("UPDATE public.game_storage_locations")


def test_manual_geometry_writer_adds_the_revision_manifest_in_the_same_session() -> None:
    from unittest.mock import Mock

    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
    from game_predictor_api.storage.models import (
        BoardRenderManifestModel,
        ImageBoardGeometryRevisionModel,
    )
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    spec = {
        "assetMode": "virtual_source",
        "cells": [
            {
                "cellIndex": index,
                "renderSpec": _spec(index),
                "renderSpecChecksumSha256": sha256_canonical_json(_spec(index)),
            }
            for index in range(15)
        ],
    }
    record = ImageBoardGeometryRevisionModel(
        recognized_board_id=BOARD_ID,
        revision=3,
        asset_mode="virtual_source",
        source_geometry_revision_id=uuid4(),
        virtual_render_spec=spec,
        virtual_render_spec_checksum_sha256=sha256_canonical_json(spec),
        cropper_version="virtual-cell-renderer-test-v1",
    )
    session = Mock()
    game_id = uuid4()
    SqlAlchemyVirtualGridGeometryRepository(session)._add_render_manifest(record, game_id=game_id)
    added = session.add.call_args.args[0]
    assert isinstance(added, BoardRenderManifestModel)
    assert (added.game_id, added.recognized_board_id, added.geometry_revision) == (
        game_id,
        BOARD_ID,
        3,
    )
    assert added.cells == spec
    assert added.manifest_checksum_sha256 == record.virtual_render_spec_checksum_sha256
    assert added.source_geometry_revision_id == record.source_geometry_revision_id
    assert added.extractor_version == "virtual-cell-renderer-test-v1"

    record.virtual_render_spec_checksum_sha256 = "0" * 64
    with pytest.raises(ImageGridReviewError) as error:
        SqlAlchemyVirtualGridGeometryRepository(Mock())._add_render_manifest(
            record, game_id=game_id
        )
    assert error.value.code == "BOARD_RENDER_MANIFEST_REVISION_CHECKSUM_MISMATCH"


def test_rollout_backfill_refuses_to_mutate_observations_behind_a_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from game_predictor_api.domain.board_topology import BoardTopology
    from game_predictor_api.storage import image_geometry_rollout_backfill_repository as module
    from game_predictor_api.storage.models import CellObservationModel

    monkeypatch.setattr(
        module,
        "derive_v2_render_identity_from_legacy_spec",
        lambda *_args, **_kwargs: SimpleNamespace(
            logical_cell_key_v2="a" * 64, render_identity_v2_sha256="b" * 64
        ),
    )
    source = SimpleNamespace(id=uuid4(), import_job_id=uuid4(), file_execution_key="k")
    geometry = SimpleNamespace(topology_rules_version_id=uuid4())
    board = SimpleNamespace(id=BOARD_ID, position_index=0)

    def call(manifest_revision: int | None) -> tuple[int, CellObservationModel]:
        session = Mock()
        session.scalar.return_value = manifest_revision
        cell = CellObservationModel(row_index=0, column_index=1, render_spec={})
        updated = module.SqlAlchemyImageGeometryRolloutBackfillRepository(
            session
        )._backfill_render_identity(
            source=source,  # type: ignore[arg-type]
            geometry=geometry,  # type: ignore[arg-type]
            topology=BoardTopology(rows=3, columns=5),
            board=board,  # type: ignore[arg-type]
            cell=cell,
        )
        return updated, cell

    updated, cell = call(None)
    assert updated == 1 and cell.logical_cell_key_v2 == "a" * 64
    with pytest.raises(module.ImageGeometryRolloutBackfillError) as error:
        call(0)
    assert error.value.code == "BOARD_RENDER_MANIFEST_PRESENT"


def test_writers_and_backfill_skip_boards_without_renderable_cells() -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from game_predictor_api.storage.board_render_manifest_backfill import (
        _Board,
        _NoCells,
        _prepare_zero_board,
    )
    from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )
    from game_predictor_worker.images.pipeline_store import _ensure_import_render_manifest

    session = Mock()
    _ensure_import_render_manifest(
        session,
        SimpleNamespace(id=BOARD_ID, grid_columns=5),  # type: ignore[arg-type]
        [],
        cropper_version="v",
        game_id=uuid4(),
        source_geometry_revision_id=uuid4(),
    )
    empty_spec: dict[str, object] = {"assetMode": "virtual_source", "cells": []}
    record = ImageBoardGeometryRevisionModel(
        recognized_board_id=BOARD_ID,
        revision=1,
        source_geometry_revision_id=uuid4(),
        virtual_render_spec=empty_spec,
        virtual_render_spec_checksum_sha256=sha256_canonical_json(empty_spec),
        cropper_version="v",
    )
    SqlAlchemyVirtualGridGeometryRepository(session)._add_render_manifest(record, game_id=uuid4())
    assert session.method_calls == []

    def board(unavailable: tuple[int, ...]) -> _Board:
        return _Board(
            id=BOARD_ID,
            geometry_revision=0,
            asset_mode="virtual_source",
            rows=3,
            columns=5,
            unavailable_cell_indices=unavailable,
            geometry_qualification=None,
        )

    assert isinstance(_prepare_zero_board(board(tuple(range(15))), []), _NoCells)
    missing = _prepare_zero_board(board(()), [])
    assert not isinstance(missing, _NoCells)
    assert missing.code == "BOARD_RENDER_MANIFEST_OBSERVATIONS_MISSING"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("column", "value"),
    (("cropper_version", "other-cropper"), ("crop_checksum_sha256", "0" * 64)),
)
def test_backfill_refuses_crop_provenance_that_differs_from_the_render(
    column: str, value: str
) -> None:
    from game_predictor_api.storage.board_render_manifest_backfill import (
        _Board,
        _prepare_zero_board,
    )

    rows = []
    for index in range(15):
        cell = _cell(index)
        row: dict[str, object] = {
            "row_index": index // 5,
            "column_index": index % 5,
            "asset_mode": "virtual_source",
            "source_geometry_revision_id": BOARD_ID,
            "logical_cell_key": cell.logical_cell_key,
            "logical_cell_key_v2": cell.logical_cell_key_v2,
            "render_identity_v2_sha256": cell.render_identity_v2_sha256,
            "render_spec": dict(cell.render_spec),
            "render_spec_checksum_sha256": cell.render_spec_checksum_sha256,
            "rendered_pixel_checksum_sha256": cell.rendered_pixel_checksum_sha256,
            "extractor_version": "x",
            "cropper_version": "x",
            "crop_checksum_sha256": cell.rendered_pixel_checksum_sha256,
        }
        rows.append(row)
    board = _Board(
        id=BOARD_ID,
        geometry_revision=0,
        asset_mode="virtual_source",
        rows=3,
        columns=5,
        unavailable_cell_indices=(),
        geometry_qualification=None,
    )
    assert not hasattr(_prepare_zero_board(board, rows), "code")
    rows[4][column] = value
    refused = _prepare_zero_board(board, rows)
    assert refused.code == "BOARD_RENDER_MANIFEST_CROP_PROVENANCE_MISMATCH"  # type: ignore[union-attr]
    assert refused.cell_index == 4  # type: ignore[union-attr]


def test_import_writer_requires_extractor_equal_to_cropper_version() -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from game_predictor_worker.images.pipeline_store import (
        ImagePipelineStoreError,
        _ensure_import_render_manifest,
    )

    cell = _cell(0)
    crop = {
        "rowIndex": 0,
        "columnIndex": 0,
        "renderSpec": dict(cell.render_spec),
        "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
        "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
        "logicalCellKeySha256": cell.logical_cell_key,
        "extractorVersion": "renderer-v1",
    }
    with pytest.raises(ImagePipelineStoreError) as error:
        _ensure_import_render_manifest(
            Mock(),
            SimpleNamespace(id=BOARD_ID, grid_columns=5),  # type: ignore[arg-type]
            [crop],
            cropper_version="renderer-v2",
            game_id=uuid4(),
            source_geometry_revision_id=uuid4(),
        )
    assert error.value.code == "BOARD_RENDER_MANIFEST_PROVENANCE_INVALID"
