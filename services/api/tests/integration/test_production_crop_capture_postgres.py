"""Owned PostgreSQL: real board decision events, current A pins and read-only protection.

Small synthetic annotation records test the reader contract, not operator quality.
"""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_cell_content import oracle_qualification
from game_predictor_api.domain.grid_content_repeatability import repeatability_report
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewResolutionCell,
    validate_image_review_resolution,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentRevisionModel,
    GridCellContentSessionModel,
)
from game_predictor_api.storage.grid_cell_content_pins import content_pin
from game_predictor_api.storage.grid_content_preview import protected_source
from game_predictor_api.storage.grid_quality_observations import current_targets, read_source
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    RecognizedBoardModel,
    SymbolModel,
)
from game_predictor_api.storage.production_crop_capture import _classes, _measurement
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_grid_cell_content import revision, target
from test_grid_training_cohort_e2e_postgres import _install_base, _save_source
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


def test_real_human_board_decision_and_current_frozen_a_pin(tmp_path):
    with application_role_database("t1171crop", ("crop",)) as db:
        print("T1171 disposable database migrated", flush=True)
        game = db.games["crop"]
        _install_base(db, game)
        with Session(db.owner_engine) as session, session.begin():
            for code, number in (("A", 1), ("B", 2)):
                session.add(
                    SymbolModel(
                        game_id=game,
                        code=code,
                        name=code,
                        mobile_code=number,
                        display_order=number,
                        status="active",
                    )
                )
        source_id, _, import_id = _save_source(db, tmp_path, game, 1, 1, {})
        owner_factory = create_session_factory(db.owner_engine)
        with game_storage_scope(game), owner_factory.begin() as session:
            repository = SqlAlchemyOperationalImageReviewRepository(session)
            review_id = session.scalar(
                select(ImageReviewItemModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .where(RecognizedBoardModel.source_image_id == source_id)
            )
            item = repository.get_item(review_id, game_id=game, import_job_id=import_id)
            command = validate_image_review_resolution(
                item=item,
                action=ImageReviewAction.CORRECTED,
                sequence_number=110,
                geometry_revision=item.geometry_revision,
                cells=tuple(
                    ImageReviewResolutionCell(c.cell_index, c.crop_sample_id, "A")
                    for c in item.cells
                ),
                rejection_reason=None,
                resolved_by="local-owner",
                active_symbol_codes=("A", "B"),
            )
            repository.save_resolution(
                review_item_id=review_id,
                game_id=game,
                import_job_id=import_id,
                idempotency_key=uuid4(),
                expected_revision=item.resolution_revision,
                resolution=command,
                resolved_at=datetime.now(UTC),
            )
        print("T1171 actual human board resolution committed", flush=True)
        app_factory = create_session_factory(db.app_engine)
        with game_storage_scope(game), app_factory() as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            current = current_targets(session, game, source_id)[0]
            classes = _classes(session, game, current)
            assert len(classes) == 15 and all(c["state"] == "available" for c in classes), classes
            assert all(
                c["event"]["action"] == "board_synchronized" and c["code"] == "A" for c in classes
            )
            source = repo.current_source(game, source_id)
            metadata = read_source(session, game, source_id)
            assert not protected_source(repo, game, source)

        cohort, frozen_session = uuid4(), uuid4()
        # Author-produced repeatability/qualification payload on 30 small
        # metadata fixtures. Only one target has live SQL/source records; this
        # is a reader test and never a qualification report for operator data.
        targets = [
            target(photo, slot, "A", game=game) for photo in range(1, 11) for slot in range(3)
        ]
        targets[0] = targets[0].model_copy(update={"source": source, "sequenceNumber": 110})
        first = [revision(t, 1).model_copy(update={"sessionId": frozen_session}) for t in targets]
        second = [revision(t, 2).model_copy(update={"sessionId": frozen_session}) for t in targets]
        report = repeatability_report(targets, first, second, [game])
        report.update(oracle_qualification(["checked"] * len(targets)))
        report["sha256"] = digest({k: v for k, v in report.items() if k != "sha256"})
        assert report["state"] == report["qualificationState"] == "ready"
        annotation = second[0]
        progress = {"pass1": {}, "pass2": {f"{source.sourceRepresentativeSha256}:0": 2}}
        with game_storage_scope(game), owner_factory.begin() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game, write=True)
            session.add(
                GridTrainingCohortModel(
                    game_id=game,
                    id=cohort,
                    status="frozen",
                    manifest_path="test-fixture/manifest.json",
                    manifest_sha256="f" * 64,
                    document={},
                    summary={},
                    created_by="fixture",
                )
            )
            session.flush()
            session.add(
                GridCellContentSessionModel(
                    game_id=game,
                    id=frozen_session,
                    cohort_id=cohort,
                    revision=3,
                    phase="frozen",
                    document={"targets": [t.model_dump(mode="json") for t in targets]},
                    progress=progress,
                    report=report,
                )
            )
            session.add(
                GridCellContentSessionModel(
                    game_id=game,
                    id=uuid4(),
                    cohort_id=cohort,
                    revision=1,
                    phase="pass1",
                    document={"targets": [targets[0].model_dump(mode="json")]},
                    progress={"pass1": {}, "pass2": {}},
                    report=None,
                )
            )
            session.add(
                GridCellContentRevisionModel(
                    game_id=game,
                    source_id=source_id,
                    live_source_image_id=source_id,
                    pixel_sha256=source.sourceRepresentativeSha256,
                    position_index=0,
                    revision=2,
                    document=annotation.model_dump(mode="json"),
                    document_sha256=annotation.sha256,
                    oracle=None,
                )
            )
        with game_storage_scope(game), app_factory() as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            pin = content_pin(
                session, game, metadata, {"positionIndex": 0, "sequenceNumber": 110}, purpose="A"
            )
            assert pin["contentAnnotation"]["sessionId"] == str(frozen_session)
            assert _measurement(session, game, {str(frozen_session)}) == report
            assert protected_source(
                repo, game, source
            )  # whole source remains excluded from TRAIN hints
            assert all(
                c["state"] == "available"
                for c in _classes(session, game, current_targets(session, game, source_id)[0])
            )
            assert session.scalar(text("SHOW transaction_read_only")) == "on"
        print(
            "T1171 current A pin ignores old blank; "
            "TRAIN source protection and classes READ ONLY PASS",
            flush=True,
        )
