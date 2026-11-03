"""Small owned database: immutable dataset lineage survives replacement restoration."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import provision_game
from game_predictor_api.application.mobile_releases import MobileReleaseService
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseConflictError,
    MobileReleaseGameInput,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.schemas.source_replacement import (
    SourceReplacementCreateRequest,
    SourceRetirementCommand,
    SourceRetirementPreviewRequest,
)
from game_predictor_api.storage.database import (
    create_cross_game_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.layout_import_report_repository import (
    SqlAlchemyLayoutImportReportRepository,
)
from game_predictor_api.storage.mobile_release_repository import SqlAlchemyMobileReleaseRepository
from game_predictor_api.storage.mobile_source_proof import require_current_dataset_sources
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    ImageLayoutStagingRowModel,
    ImageSequenceCanonicalModel,
    LayoutImportNormalizedRowModel,
    LayoutImportRowModel,
    LayoutModel,
    RulesVersionModel,
)
from game_predictor_api.storage.sequence_ownership_lock import sequence_ownership_lock_key
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_worker.releases.store import SqlAlchemyReleaseWorkflowStore
from sqlalchemy import text
from test_source_replacement_postgres import database as _owned_database
from test_source_replacement_postgres import pytestmark as pytestmark
from test_source_replacement_postgres import test_exact_alias_manifest_and_lost_response as _seed
from test_source_retirement_postgres import _photo


@pytest.fixture(scope="module")
def database():
    yield from _owned_database.__wrapped__()


def _dataset(session, version, board, *, seq=1, game_id=GAME_ID):
    value = DatasetVersionModel(
        game_id=game_id,
        version=version,
        rows=3,
        columns=5,
        signature_cell_width=1,
        expected_layout_count=1,
        layout_count=1,
        status=DatasetVersionStatus.PUBLISHED,
        generation_seed=0,
        generator_version="fixture",
    )
    session.add(value)
    session.flush()
    session.add(
        LayoutModel(
            dataset_version_id=value.id,
            sequence_number=seq,
            signature="1" * 15,
            cells=[1] * 15,
            source_board_id=board,
        )
    )
    session.flush()
    return value.id


def _release(factory, dataset, rules, version):
    with factory() as session:
        service = MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
        release = service.create_mobile_release(
            version=version,
            games=(
                MobileReleaseGameInput(
                    game_id=GAME_ID, dataset_version_id=dataset, rules_version_id=rules
                ),
            ),
        )
        job = service.start_mobile_release_build(release.id)
        session.commit()
    return release.id, job.id


def _processing(factory, job_id):
    with factory() as session:
        session.execute(
            text(
                "UPDATE public.jobs SET status='processing',execution_slot=1,lease_owner='fixture',"
                "lease_token=:token,lease_expires_at=now()+interval '5 minutes',heartbeat_at=now() "
                "WHERE id=:id"
            ),
            {"id": job_id, "token": uuid4()},
        )
        session.commit()


def test_old_dataset_stays_stale_after_restored_new_capture_and_history_replay(database):
    _seed(database)
    factory = create_cross_game_owner_session_factory(database)
    with factory() as session:
        board = session.scalar(
            text(
                "SELECT id FROM recognized_boards WHERE game_id=:game "
                "ORDER BY sequence_number LIMIT 1"
            ),
            {"game": GAME_ID},
        )
        old = _dataset(session, 1, board)
        legacy = _dataset(session, 2, None)
        outside = _dataset(session, 3, None, seq=42)
        rules = RulesVersionModel(
            game_id=GAME_ID,
            version=42,
            rows=3,
            columns=5,
            spin_cost=10,
            status=RulesVersionStatus.PUBLISHED,
        )
        session.add(rules)
        session.commit()
        rules_id = rules.id
    published_id, published_job = _release(factory, old, rules_id, "mobile-proof-published")
    active_id, active_job = _release(factory, old, rules_id, "mobile-proof-building")
    store = SqlAlchemyReleaseWorkflowStore(factory)
    store.record_snapshot(
        published_id, build_job_id=published_job, relative_path="old/snapshot.db", checksum="1" * 64
    )
    _processing(factory, published_job)
    ready = store.mark_ready(
        published_id,
        build_job_id=published_job,
        apk_relative_path="old/app.apk",
        apk_checksum="2" * 64,
    )
    with factory() as session:
        session.execute(
            text(
                "UPDATE public.jobs SET status='completed',execution_slot=NULL,lease_owner=NULL,"
                "lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=:id"
            ),
            {"id": published_job},
        )
        session.commit()
    recorded = store.record_snapshot(
        active_id, build_job_id=active_job, relative_path="building/snapshot.db", checksum="3" * 64
    )
    with factory() as session:
        repo = SourceReplacementRepository(session)
        sources = list(
            session.scalars(
                text("SELECT id FROM source_images WHERE game_id=:game"), {"game": GAME_ID}
            )
        )
        preview = repo.preview(GAME_ID, sources)
        plan = repo.create(
            GAME_ID,
            SourceReplacementCreateRequest(
                mode="replace_preserve_history",
                source_ids=sources,
                idempotency_key=uuid4(),
                expected_revision=0,
                preview_token=preview["preview_token"],
            ),
        )
        request = SourceRetirementPreviewRequest(
            mode="replace_preserve_history",
            action="retire",
            batch_id=UUID(plan["id"]),
            entry_id=UUID(plan["entries"][0]["id"]),
            expected_revision=1,
        )
        fresh = repo.retirement_preview(GAME_ID, request)
        repo.retirement_command(
            GAME_ID,
            SourceRetirementCommand(
                **request.model_dump(),
                confirmed=True,
                idempotency_key=uuid4(),
                preview_token=fresh["preview_token"],
            ),
        )
        session.commit()
    with pytest.raises(MobileReleaseConflictError) as error, store.publication_fence(recorded):
        pytest.fail("open replacement must block")
    assert error.value.code == "SOURCE_REPLACEMENT_RESERVED"
    other_game = provision_game(database, "mobile-proof-other")
    with factory() as session:
        other_dataset = _dataset(session, 1, None, game_id=other_game)
        session.commit()
    other_release = SimpleNamespace(
        games=(SimpleNamespace(game_id=other_game, dataset_version_id=other_dataset),)
    )
    with store.publication_fence(other_release):
        pass  # Same sequence in another game stays usable, even while this game's gap is open.
    with factory() as session:
        # Fixture models the terminal state. The C2 core suite tests actual completeness,
        # readability and orphan closure; this suite specifically tests post-release proof.
        session.execute(
            text("DELETE FROM source_replacement_slots WHERE game_id=:game"), {"game": GAME_ID}
        )
        session.execute(
            text(
                "UPDATE source_replacement_entries SET phase='restored',revision=revision+1 "
                "WHERE id=:id"
            ),
            {"id": request.entry_id},
        )
        session.commit()
    new_source, new_review, new_board, new_job = _photo(
        create_session_factory(database), 1, "f" * 64, status="accepted"
    )
    with factory() as session:
        session.add(
            ImageSequenceCanonicalModel(
                game_id=GAME_ID,
                sequence_number=1,
                review_item_id=new_review,
                recognized_board_id=new_board,
                import_job_id=new_job,
                source_image_id=new_source,
                source_checksum_sha256="f" * 64,
                board_checksum_sha256="f" * 64,
                status="accepted",
                resolution_revision=1,
                geometry_revision=1,
            )
        )
        session.add(
            ImageLayoutStagingRowModel(
                import_job_id=new_job,
                recognized_board_id=new_board,
                review_item_id=new_review,
                sequence_number=1,
                cells=[1] * 15,
            )
        )
        session.commit()
    # Restart: no memory state, slot or timestamp can authorize the old immutable layouts.
    store = SqlAlchemyReleaseWorkflowStore(factory)
    for dataset in (old, legacy):
        with factory() as session, pytest.raises(MobileReleaseConflictError) as error:
            require_current_dataset_sources(session, game_id=GAME_ID, dataset_version_id=dataset)
        assert error.value.code == "MOBILE_RELEASE_SOURCE_PROOF_STALE"
    for action in ("fence", "record", "ready"):
        with pytest.raises(MobileReleaseConflictError) as error:
            if action == "fence":
                with store.publication_fence(recorded):
                    pytest.fail("old snapshot must not publish")
            elif action == "record":
                store.record_snapshot(
                    active_id,
                    build_job_id=active_job,
                    relative_path="different/snapshot.db",
                    checksum="4" * 64,
                )
            else:
                store.mark_ready(
                    active_id,
                    build_job_id=active_job,
                    apk_relative_path="building/app.apk",
                    apk_checksum="5" * 64,
                )
        assert error.value.code == "MOBILE_RELEASE_SOURCE_PROOF_STALE"
    assert store.load_release(published_id) == ready
    assert (
        store.mark_ready(
            published_id,
            build_job_id=published_job,
            apk_relative_path="old/app.apk",
            apk_checksum="2" * 64,
        )
        == ready
    )
    assert (
        store.record_snapshot(
            active_id,
            build_job_id=active_job,
            relative_path="building/snapshot.db",
            checksum="3" * 64,
        )
        == recorded
    )
    with factory() as session:
        require_current_dataset_sources(session, game_id=GAME_ID, dataset_version_id=outside)
        # Exact current capture through the real dataset publication path. The immutable
        # old datasets retain their old board/NULL even when the symbols happen to match.
        GameStorageRouter().bind(session, GAME_ID, intent=GameStorageIntent.WRITE)
        session.add(
            LayoutImportRowModel(
                job_id=new_job,
                line_number=1,
                byte_offset_end=16,
                sequence_number=1,
                cells=[1] * 15,
                error_code=None,
                error_message=None,
            )
        )
        session.flush()
        session.add(
            LayoutImportNormalizedRowModel(
                validation_job_id=new_job,
                import_job_id=new_job,
                rules_version_id=rules_id,
                line_number=1,
                sequence_number=1,
                cells=[1] * 15,
                signature="1" * 15,
                error_code=None,
                error_message=None,
            )
        )
        session.flush()
        source = SimpleNamespace(
            game_id=GAME_ID,
            signature_cell_width=1,
            expected_layout_count=1,
            reference=SimpleNamespace(rows=3, columns=5, validation_job_id=new_job),
            integrity_source=SimpleNamespace(valid_row_count=1),
        )
        fresh_dataset = SqlAlchemyLayoutImportReportRepository(session).publish_staging(source)
        session.commit()
    with factory() as session:
        assert (
            session.scalar(
                text("SELECT source_board_id FROM layouts WHERE dataset_version_id=:id"),
                {"id": fresh_dataset.id},
            )
            == new_board
        )
        require_current_dataset_sources(
            session, game_id=GAME_ID, dataset_version_id=fresh_dataset.id
        )
    fresh_id, fresh_job = _release(factory, fresh_dataset.id, rules_id, "mobile-proof-current")
    current = store.load_release(fresh_id)
    with store.publication_fence(current):
        with factory() as contender:
            assert (
                contender.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": sequence_ownership_lock_key(GAME_ID)},
                )
                is False
            )
        # Nested record uses the same already-proven scope, not another lock connection.
        store.record_snapshot(
            fresh_id, build_job_id=fresh_job, relative_path="new/snapshot.db", checksum="6" * 64
        )
    _processing(factory, fresh_job)
    completed = store.mark_ready(
        fresh_id, build_job_id=fresh_job, apk_relative_path="new/app.apk", apk_checksum="7" * 64
    )
    assert completed.status.value == "ready"
    assert ready.snapshot_path == "old/snapshot.db" and ready.apk_path == "old/app.apk"
    # Same symbols do not hide changed canonical lineage, and mutable current cells
    # cannot silently alter the immutable dataset's semantics.
    with factory() as session:
        session.execute(
            text("UPDATE image_layout_staging_rows SET cells=:cells WHERE review_item_id=:id"),
            {"cells": [2] * 15, "id": new_review},
        )
        with pytest.raises(MobileReleaseConflictError):
            require_current_dataset_sources(
                session, game_id=GAME_ID, dataset_version_id=fresh_dataset.id
            )
        session.rollback()
