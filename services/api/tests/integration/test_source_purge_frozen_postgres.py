"""Frozen evidence survives physical purge; only owned PostgreSQL and temporary files."""

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.schemas.source_replacement import (
    SourcePurgeCommand,
    SourcePurgePreviewRequest,
    SourceReplacementCreateRequest,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from game_predictor_api.storage.models import (
    GameSymbolModelActivationModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
    SymbolModel,
    SymbolModelIterationModel,
    SymbolReferenceImageModel,
    VerifiedTrainingCohortCellModel,
    VerifiedTrainingCohortItemModel,
    VerifiedTrainingCohortModel,
)
from game_predictor_api.storage.source_purge_retention import SourcePurgeRetention
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_source_replacement_postgres import database as _owned_database
from test_source_replacement_postgres import pytestmark as pytestmark
from test_source_replacement_postgres import test_exact_alias_manifest_and_lost_response as _seed
from test_source_replacement_purge_postgres import service


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    # Reuse the CREATE/DROP name, OID and recording-capability guards, not another test's DB.
    yield from _owned_database.__wrapped__()


def _copy_values(row: Any) -> dict[str, Any]:
    return {
        column.key: getattr(row, column.key)
        for column in inspect(type(row)).columns
        if column.key != "id" and getattr(row, column.key) is not None
    }


def _nine_boards(session: Session) -> tuple[Any, Any, Any]:
    board = session.scalar(
        select(RecognizedBoardModel).where(RecognizedBoardModel.sequence_number == 1)
    )
    assert board is not None
    review = session.scalar(
        select(ImageReviewItemModel).where(ImageReviewItemModel.recognized_board_id == board.id)
    )
    assert review is not None
    cells = list(
        session.scalars(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.review_item_id == review.id
            )
        )
    )
    assert len(cells) == 15
    for sequence in range(3, 10):
        new_board = RecognizedBoardModel(
            **{
                **_copy_values(board),
                "position_index": sequence - 1,
                "sequence_number": sequence,
                "sequence_number_raw": str(sequence),
            }
        )
        session.add(new_board)
        session.flush()
        new_review = ImageReviewItemModel(
            **{
                **_copy_values(review),
                "recognized_board_id": new_board.id,
                "sequence_number": sequence,
                "snapshot": {"sequenceNumber": sequence},
            }
        )
        session.add(new_review)
        session.flush()
        for cell in cells:
            session.add(
                ImageSymbolReviewCellModel(
                    **{
                        **_copy_values(cell),
                        "recognized_board_id": new_board.id,
                        "review_item_id": new_review.id,
                        "sequence_number": sequence,
                    }
                )
            )
    session.flush()
    return board, review, cells[0]


def _frozen_evidence(session: Session, root: Path) -> UUID:
    board, review, cell = _nine_boards(session)
    cohort = VerifiedTrainingCohortModel(
        game_id=GAME_ID,
        iteration_number=1,
        manifest_schema_version=2,
        dataset_kind="verified-training-cohort-v2",
        manifest_checksum_sha256="1" * 64,
        idempotency_key=uuid4(),
        command_sha256="2" * 64,
        resolved_layout_count=1,
        cell_sample_count=1,
        source_image_count=1,
        pending_item_count=0,
        rejected_item_count=0,
        incomplete_item_count=0,
        artifact_relative_path="datasets/frozen/manifest.json",
        created_by="owned-test",
    )
    session.add(cohort)
    session.flush()
    session.add(
        VerifiedTrainingCohortItemModel(
            cohort_id=cohort.id,
            item_order=0,
            review_item_id=review.id,
            recognized_board_id=board.id,
            source_image_id=board.source_image_id,
            import_job_id=review.import_job_id,
            sequence_number=1,
            decision_status="accepted",
            resolution_revision=1,
            geometry_revision=board.geometry_revision,
            source_checksum_sha256="a" * 64,
            board_checksum_sha256="3" * 64,
            pipeline_fingerprint=board.pipeline_fingerprint,
            item_checksum_sha256="4" * 64,
            board_manifest={"cells": [{"symbolCode": "FROZEN"}] * 15},
        )
    )
    session.add(
        VerifiedTrainingCohortCellModel(
            cohort_id=cohort.id,
            sample_order=0,
            cell_review_id=cell.id,
            review_item_id=review.id,
            recognized_board_id=board.id,
            source_image_id=board.source_image_id,
            sequence_number=1,
            cell_index=cell.cell_index,
            symbol_code="FROZEN",
            asset_mode="virtual_source",
            source_geometry_revision_id=board.source_geometry_revision_id,
            logical_cell_key="5" * 64,
            render_spec={"sourceChecksumSha256": "a" * 64, "cellIndex": cell.cell_index},
            render_spec_checksum_sha256="6" * 64,
            rendered_pixel_checksum_sha256="7" * 64,
            extractor_version="frozen-test-v1",
            crop_checksum_sha256="7" * 64,
            sample_checksum_sha256="8" * 64,
            cell_manifest={"symbolCode": "FROZEN", "qualityIssue": "historical"},
        )
    )
    symbol = SymbolModel(
        game_id=GAME_ID, mobile_code=1, code="FROZEN", name="Frozen", display_order=0
    )
    session.add(symbol)
    session.flush()
    reference = root / "catalog" / "frozen-reference.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"independent catalog reference pixels")
    session.add(
        SymbolReferenceImageModel(
            symbol_id=symbol.id,
            game_id=GAME_ID,
            source_review_item_id=review.id,
            source_recognized_board_id=board.id,
            sequence_number=1,
            cell_index=cell.cell_index,
            resolution_revision=1,
            geometry_revision=board.geometry_revision,
            image_relative_path=reference.relative_to(root).as_posix(),
            image_checksum_sha256=sha256(reference.read_bytes()).hexdigest(),
            selected_by="owned-test",
        )
    )
    weights = root / "models" / "frozen" / "checkpoint.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"owned immutable model weights")
    model = SymbolModelIterationModel(
        game_id=GAME_ID,
        cohort_id=cohort.id,
        job_id=review.import_job_id,
        iteration_number=1,
        status="candidate_ready",
        configuration_fingerprint="9" * 64,
        configuration_payload={},
        checkpoint_relative_path=weights.relative_to(root).as_posix(),
        checkpoint_checksum_sha256=sha256(weights.read_bytes()).hexdigest(),
        candidate_manifest_relative_path="models/frozen/candidate.json",
    )
    session.add(model)
    session.flush()
    session.add(
        GameSymbolModelActivationModel(
            game_id=GAME_ID,
            model_iteration_id=model.id,
            action="activate",
            activation_number=1,
            actor="owned-test",
            idempotency_key=uuid4(),
            command_sha256="b" * 64,
        )
    )
    session.flush()
    cohort_id: UUID = cohort.id
    return cohort_id


FROZEN_TABLES = (
    "verified_training_cohorts",
    "verified_training_cohort_items",
    "verified_training_cohort_cells",
    "symbol_reference_images",
    "symbol_model_iterations",
    "game_symbol_model_activations",
)


def _rows(session: Session, table: str) -> list[Any]:
    assert table in FROZEN_TABLES
    return list(
        session.scalars(
            text(f"SELECT to_jsonb(t) FROM {table} t WHERE game_id=:game"), {"game": GAME_ID}
        )
    )


def test_purge_preserves_frozen_evidence_active_model_and_shared_reference(
    database: Engine, tmp_path: Path
) -> None:
    _seed(database)
    factory = create_session_factory(database)
    original = tmp_path / "seq_1-9.jpg"
    original.write_bytes(b"owned original pixels")
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        cohort_id = _frozen_evidence(session, tmp_path)
        session.execute(
            text("UPDATE public.jobs SET status='completed',finished_at=now() WHERE game_id=:game"),
            {"game": GAME_ID},
        )
        sources = list(session.scalars(text("SELECT id FROM source_images")))
        preview = repo.preview(GAME_ID, sources, mode="replace_delete_source")
        manifest = repo.create(
            GAME_ID,
            SourceReplacementCreateRequest(
                mode="replace_delete_source",
                source_ids=sources,
                idempotency_key=uuid4(),
                expected_revision=0,
                preview_token=preview["preview_token"],
            ),
        )
        session.commit()
    batch, entry = UUID(manifest["id"]), UUID(manifest["entries"][0]["id"])
    request = SourcePurgePreviewRequest(
        mode="replace_delete_source",
        action="purge",
        batch_id=batch,
        entry_id=entry,
        expected_revision=1,
    )
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        before = {table: _rows(session, table) for table in FROZEN_TABLES}
        assert all(len(rows) == 1 for rows in before.values())
        assert (
            SqlAlchemySymbolCellReviewQueryRepository(session).active_model_cohort_id(GAME_ID)
            == cohort_id
        )
        cleanup = service(session, factory, tmp_path)
        preview = cleanup.physical_sources.preview(GAME_ID, request)
        assert preview["record_counts"]["boards"] == 9
        assert preview["shared_file_count"] == 1
        assert SourcePurgeRetention.retained(
            session, ["catalog/frozen-reference.png"], sources, GAME_ID
        ) == {"catalog/frozen-reference.png"}
        assert preview["file_count"] == 1
        assert preview["retained_metadata"]["symbol_frozen_items"] == 1
        assert preview["retained_metadata"]["symbol_frozen_cells"] == 1
        command = SourcePurgeCommand(
            **request.model_dump(),
            idempotency_key=uuid4(),
            confirmed=True,
            preview_token=preview["preview_token"],
        )
        # A model which still needs its frozen pixels blocks before quarantine or DB mutation.
        session.execute(text("UPDATE symbol_model_iterations SET status='trained'"))
        with pytest.raises(SourceReplacementError) as blocked:
            cleanup.physical_sources.execute(GAME_ID, command)
        assert blocked.value.code == "SOURCE_REPLACEMENT_PURGE_MODEL_BUSY"
        assert original.read_bytes() == b"owned original pixels"
        assert session.scalar(text("SELECT count(*) FROM recognized_boards")) == 9
        assert session.scalar(text("SELECT count(*) FROM image_review_items")) == 9
        assert session.scalar(text("SELECT count(*) FROM image_symbol_review_cells")) == 135
        assert session.scalar(text("SELECT count(*) FROM source_replacement_retired")) == 0
        assert session.scalar(text("SELECT count(*) FROM source_replacement_slots")) == 0
        session.rollback()
    with factory() as session:
        cleanup = service(session, factory, tmp_path)
        cleanup.physical_sources.execute(GAME_ID, command)
        session.commit()
        cleanup.finalize_committed_artifacts()
    # New connection proves persisted evidence/activation, independently of ORM identity maps.
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        assert {table: _rows(session, table) for table in FROZEN_TABLES} == before
        assert (
            SqlAlchemySymbolCellReviewQueryRepository(session).active_model_cohort_id(GAME_ID)
            == cohort_id
        )
        assert not original.exists()
        for table, field in (
            ("symbol_model_iterations", "checkpoint"),
            ("symbol_reference_images", "image"),
        ):
            row = before[table][0]
            assert (
                sha256((tmp_path / row[f"{field}_relative_path"]).read_bytes()).hexdigest()
                == row[f"{field}_checksum_sha256"]
            )
        for table in (
            "recognized_boards",
            "image_review_items",
            "image_symbol_review_cells",
            "image_source_geometry_revisions",
        ):
            assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_images "
                    "WHERE purged_at IS NOT NULL AND status='rejected'"
                )
            )
            == 2
        )
        assert session.scalar(text("SELECT count(*) FROM source_replacement_retired")) == 2
        assert list(
            session.scalars(
                text(
                    "SELECT sequence_number FROM source_replacement_slots ORDER BY sequence_number"
                )
            )
        ) == list(range(1, 10))
        exported = repo.replacement_request(GAME_ID, batch, [entry])
        assert exported["entries"][0]["sequenceNumbers"] == list(range(1, 10))
        assert repo.get(GAME_ID, batch)["entries"][0]["boards"] == []
        # Detached historical UUIDs must not permit a new cohort/reference using purged parents.
        for table in (
            "verified_training_cohort_items",
            "verified_training_cohort_cells",
            "symbol_reference_images",
        ):
            with (
                pytest.raises(DBAPIError, match="SOURCE_REPLACEMENT_FROZEN_PARENT_MISSING"),
                session.begin_nested(),
            ):
                session.execute(text(f"INSERT INTO {table} SELECT * FROM {table}"))
            assert _rows(session, table) == before[table]
