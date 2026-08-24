from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessService,
    RemoteManualSelectionAuthenticationError,
    RemoteManualSelectionLeaseConflictError,
)
from game_predictor_api.application.remote_manual_selection_host import (
    OWNERSHIP_DIRECTORY,
    OWNERSHIP_MARKER_NAME,
    OWNERSHIP_VERSION_DIRECTORY,
    ConsumedRemoteManualSelectionBase,
    RemoteManualSelectionHostService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionError,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionHostActionType,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
    RemoteSourceKind,
    RemoteSourceManifestEntryV1,
    build_remote_source_manifest,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.models import (
    RemoteManualSelectionAuditEventModel,
    RemoteManualSelectionBatchModel,
    RemoteManualSelectionFileModel,
    RemoteManualSelectionHostActionModel,
    RemoteManualSelectionOperationModel,
    RemoteManualSelectionSessionModel,
)
from game_predictor_api.storage.remote_manual_selection_access_repository import (
    SqlAlchemyRemoteManualSelectionAccessRepository,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionHostActionRecord,
    SqlAlchemyRemoteManualSelectionRepository,
)
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import DBAPIError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_remote_selection_test"
NOW = datetime(2026, 8, 23, 20, tzinfo=UTC)
SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
COLLECTION_ID = UUID("20000000-0000-0000-0000-000000000002")
BATCH_ID = UUID("30000000-0000-0000-0000-000000000003")
FILE_ID = UUID("40000000-0000-0000-0000-000000000004")
CLIENT_ID = UUID("50000000-0000-0000-0000-000000000005")
OPERATION_ID = UUID("60000000-0000-0000-0000-000000000006")
BINDING_ID = UUID("70000000-0000-0000-0000-000000000007")

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture(scope="module")
def remote_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        command.upgrade(_migration_config(database_url), "head")
        yield database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


@pytest.fixture(autouse=True)
def clean_remote_tables(remote_database: URL) -> Iterator[None]:
    engine = create_engine(remote_database, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE remote_manual_selection_sessions CASCADE"))
        yield
    finally:
        engine.dispose()


def _session(session_id: UUID = SESSION_ID) -> RemoteManualSelectionSessionV1:
    return RemoteManualSelectionSessionV1(
        id=session_id,
        status=RemoteManualSelectionSessionStatus.ACTIVE,
        revision=0,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )


def _collection(
    session_id: UUID = SESSION_ID,
    collection_id: UUID = COLLECTION_ID,
) -> RemoteManualSelectionCollectionV1:
    return RemoteManualSelectionCollectionV1(
        id=collection_id,
        session_id=session_id,
        name="777",
        normalized_name="777",
        status=RemoteManualSelectionCollectionStatus.ACTIVE,
        revision=0,
    )


def _batch(
    session_id: UUID = SESSION_ID,
    collection_id: UUID = COLLECTION_ID,
    batch_id: UUID = BATCH_ID,
) -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=batch_id,
        session_id=session_id,
        collection_id=collection_id,
        name="1-19809",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=0,
        last_client_sequence=0,
    )


def _file() -> RemoteManualSelectionFileV1:
    return RemoteManualSelectionFileV1(
        id=FILE_ID,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="source/1.jpg",
        size_bytes=1024,
        last_modified_ms=1_700_000_000_000,
        mime_type="image/jpeg",
        desired_selected=False,
        selection_generation=0,
        status=RemoteManualSelectionFileStatus.UNSELECTED,
    )


def _command(
    *,
    operation_id: UUID = OPERATION_ID,
    client_sequence: int = 1,
    expected_revision: int = 0,
) -> RemoteManualSelectionOperationCommandV1:
    return RemoteManualSelectionOperationCommandV1(
        operation_id=operation_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=client_sequence,
        expected_server_revision=expected_revision,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=1,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=FILE_ID,
        image_path="source/1.jpg",
        source_index=0,
        image_checksum_sha256="b" * 64,
        output_name="seq_1-9.jpg",
        visible_milliseconds=400,
        decoded=True,
    )


def _seed(
    engine: Engine,
    *,
    include_file: bool = True,
    total_file_count: int = 1,
) -> None:
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        repository = SqlAlchemyRemoteManualSelectionRepository(session)
        repository.add_session(
            _session(),
            base_binding_id=BINDING_ID,
            host_base_path=r"C:\Users\user\Documents",
            display_name="Documents",
        )
        repository.add_collection(_collection())
        repository.add_batch(
            _batch(),
            base_binding_id=BINDING_ID,
            normalized_collection_name="777",
            normalized_batch_name="1-19809",
            total_file_count=total_file_count,
        )
        if include_file:
            repository.add_files((_file(),))
        session.commit()


def test_host_monitor_aggregates_bounded_batch_state_without_paths(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    action_id = uuid4()
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.add_host_action(
                RemoteManualSelectionHostActionV1(
                    id=action_id,
                    session_id=SESSION_ID,
                    batch_id=BATCH_ID,
                    file_id=FILE_ID,
                    transfer_id=None,
                    generation=1,
                    action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
                    status=RemoteManualSelectionHostActionStatus.RETRY,
                    attempt=1,
                )
            )
            batch = session.get(RemoteManualSelectionBatchModel, BATCH_ID)
            file = session.get(RemoteManualSelectionFileModel, FILE_ID)
            action = session.get(RemoteManualSelectionHostActionModel, action_id)
            assert batch is not None and file is not None and action is not None
            batch.selected_file_count = 1
            file.status = RemoteManualSelectionFileStatus.FAILED.value
            action.last_error_code = "REMOTE_SELECTION_SYNTHETIC_FAILURE"
            session.commit()

        with session_factory() as session:
            monitor = SqlAlchemyRemoteManualSelectionAccessRepository(
                session
            ).list_batch_monitors(session_id=SESSION_ID, limit=1)

        assert len(monitor) == 1
        assert monitor[0].selected_file_count == 1
        assert monitor[0].synced_file_count == 0
        assert monitor[0].failed_file_count == 1
        assert monitor[0].pending_host_action_count == 1
        assert monitor[0].last_error_codes == (
            "REMOTE_SELECTION_SYNTHETIC_FAILURE",
        )
        assert "path" not in repr(monitor[0]).casefold()
    finally:
        engine.dispose()


def test_sql_repository_roundtrip_and_exact_retry(remote_database: URL) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            first = repository.apply_operation(_command())
            replay = repository.apply_operation(_command())
            transfer = RemoteManualSelectionTransferV1(
                id=uuid4(),
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                attempt=1,
                declared_bytes=1024,
                received_bytes=0,
                status=RemoteManualSelectionTransferStatus.QUEUED,
            )
            action = RemoteManualSelectionHostActionV1(
                id=uuid4(),
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                transfer_id=transfer.id,
                generation=1,
                action_type=RemoteManualSelectionHostActionType.VERIFY,
                status=RemoteManualSelectionHostActionStatus.QUEUED,
                attempt=0,
            )
            assert repository.add_transfer(transfer) == transfer
            assert repository.add_host_action(action) == action
            session.commit()

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            persisted_batch = repository.get_batch(BATCH_ID)
            persisted_file = repository.get_file(batch_id=BATCH_ID, file_id=FILE_ID)
            public_session = repository.get_session(SESSION_ID)

        assert first.batch.server_revision == 1
        assert replay.exact_retry is True
        assert persisted_batch is not None and persisted_batch.server_revision == 1
        assert persisted_file is not None and persisted_file.desired_selected is True
        assert public_session == _session()
        assert not hasattr(public_session, "host_base_path")
        assert not hasattr(public_session, "token_hash")
    finally:
        engine.dispose()


def test_materialization_claim_is_skip_locked_and_completion_is_atomic(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    transfer_id = uuid4()
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.apply_operation(_command())
            transfer = RemoteManualSelectionTransferV1(
                id=transfer_id,
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                attempt=1,
                declared_bytes=1024,
                received_bytes=0,
                status=RemoteManualSelectionTransferStatus.QUEUED,
                declared_checksum_sha256="b" * 64,
            )
            repository.add_transfer(transfer)
            repository.update_transfer(
                replace(transfer, status=RemoteManualSelectionTransferStatus.UPLOADING),
                temp_relative_path=None,
            )
            repository.update_file_transfer_status(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                status=RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
            )
            repository.update_file_transfer_status(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                status=RemoteManualSelectionFileStatus.UPLOADING,
            )
            repository.update_transfer(
                replace(
                    transfer,
                    received_bytes=1024,
                    status=RemoteManualSelectionTransferStatus.STORED_TEMP,
                ),
                temp_relative_path="private.part",
            )
            repository.update_file_transfer_status(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                status=RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
                temp_relative_path="private.part",
            )
            verified = replace(
                transfer,
                received_bytes=1024,
                status=RemoteManualSelectionTransferStatus.VERIFIED,
                verified_checksum_sha256="b" * 64,
            )
            repository.update_transfer(
                verified,
                temp_relative_path="private.verified",
            )
            repository.update_file_transfer_status(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                status=RemoteManualSelectionFileStatus.VERIFIED,
                temp_relative_path="private.verified",
                host_checksum_sha256="b" * 64,
            )
            assert repository.enqueue_missing_materialization_actions(limit=4) == 1
            assert repository.enqueue_missing_materialization_actions(limit=4) == 0
            action = repository.ensure_materialization_action(
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                transfer_id=transfer_id,
                generation=1,
            )
            session.commit()

        barrier = Barrier(2)

        def claim(worker: str) -> RemoteManualSelectionHostActionRecord | None:
            with session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                barrier.wait(timeout=5)
                result = repository.claim_next_materialization_action(
                    lease_owner=worker,
                    lease_duration=timedelta(seconds=30),
                    claimed_at=NOW,
                )
                session.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = tuple(executor.map(claim, ("worker-a", "worker-b")))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        winner = winners[0]
        assert winner.lease_token is not None

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            context = repository.lock_materialization_context(
                action_id=action.id,
                lease_token=winner.lease_token,
                locked_at=NOW,
            )
            assert context is not None
            result = repository.complete_materialization_action(
                context,
                lease_token=winner.lease_token,
                final_relative_path="seq_1-9.jpg",
                completed_at=NOW,
            )
            session.commit()
            assert result.status is RemoteManualSelectionFileStatus.SYNCED

        with session_factory() as session:
            action_record = session.get(RemoteManualSelectionHostActionModel, action.id)
            batch_record = session.get(RemoteManualSelectionBatchModel, BATCH_ID)
            file_record = session.get(RemoteManualSelectionFileModel, FILE_ID)
            assert action_record is not None and action_record.status == "completed"
            assert action_record.lease_token is None
            assert batch_record is not None and batch_record.transferred_file_count == 1
            assert file_record is not None and file_record.final_relative_path == "seq_1-9.jpg"
    finally:
        engine.dispose()


def test_deselect_tombstone_cancels_stale_work_and_removal_claim_is_skip_locked(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    transfer_id = uuid4()
    materialization_id = uuid4()
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.apply_operation(_command())
            repository.add_transfer(
                RemoteManualSelectionTransferV1(
                    id=transfer_id,
                    session_id=SESSION_ID,
                    batch_id=BATCH_ID,
                    file_id=FILE_ID,
                    generation=1,
                    attempt=1,
                    declared_bytes=1024,
                    received_bytes=1024,
                    status=RemoteManualSelectionTransferStatus.MATERIALIZED,
                    declared_checksum_sha256="b" * 64,
                    verified_checksum_sha256="b" * 64,
                ),
                temp_relative_path="private.verified",
            )
            repository.add_host_action(
                RemoteManualSelectionHostActionV1(
                    id=materialization_id,
                    session_id=SESSION_ID,
                    batch_id=BATCH_ID,
                    file_id=FILE_ID,
                    transfer_id=transfer_id,
                    generation=1,
                    action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
                    status=RemoteManualSelectionHostActionStatus.COMPLETED,
                    attempt=1,
                )
            )
            file_record = session.get(RemoteManualSelectionFileModel, FILE_ID)
            batch_record = session.get(RemoteManualSelectionBatchModel, BATCH_ID)
            assert file_record is not None and batch_record is not None
            file_record.status = RemoteManualSelectionFileStatus.SYNCED.value
            file_record.host_checksum_sha256 = "b" * 64
            file_record.final_relative_path = "seq_1-9.jpg"
            batch_record.transferred_file_count = 1
            deselect = replace(
                _command(
                    operation_id=uuid4(),
                    client_sequence=2,
                    expected_revision=1,
                ),
                operation_type=RemoteManualSelectionOperationType.DESELECT,
                selection_generation=2,
                image_path=None,
                source_index=None,
                output_name=None,
                target_operation_id=OPERATION_ID,
            )
            applied = repository.apply_operation(deselect)
            session.commit()
            assert applied.file is not None
            assert applied.file.status is RemoteManualSelectionFileStatus.DESELECT_PENDING

        barrier = Barrier(2)

        def claim(worker: str) -> RemoteManualSelectionHostActionRecord | None:
            with session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                barrier.wait(timeout=5)
                result = repository.claim_next_removal_action(
                    lease_owner=worker,
                    lease_duration=timedelta(seconds=30),
                    claimed_at=NOW,
                )
                session.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = tuple(executor.map(claim, ("remover-a", "remover-b")))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0].lease_token is not None

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            assert (
                repository.claim_next_materialization_action(
                    lease_owner="materializer",
                    lease_duration=timedelta(seconds=30),
                    claimed_at=NOW,
                )
                is None
            )
    finally:
        engine.dispose()


def test_source_manifest_pages_resume_after_restart_and_freeze_on_activation(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    entries = tuple(
        RemoteSourceManifestEntryV1(
            ordinal=index,
            relative_path=f"source/{index + 1}.jpg",
            name=f"{index + 1}.jpg",
            size_bytes=100 + index,
            last_modified_ms=1_700_000_000_000 + index,
            mime_type="image/jpeg",
        )
        for index in range(2)
    )
    manifest = build_remote_source_manifest(
        entries,
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
    )
    files = tuple(
        replace(
            _file(),
            id=UUID(int=FILE_ID.int + index),
            source_index=index,
            relative_path=entry.relative_path,
            size_bytes=entry.size_bytes,
            last_modified_ms=entry.last_modified_ms,
        )
        for index, entry in enumerate(entries)
    )
    try:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.add_session(
                _session(),
                base_binding_id=BINDING_ID,
                host_base_path=r"C:\Users\user\Documents",
                display_name="Documents",
            )
            repository.add_collection(_collection())
            repository.add_batch(
                replace(
                    _batch(),
                    status=RemoteManualSelectionBatchStatus.INDEXING,
                    source_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
                ),
                base_binding_id=BINDING_ID,
                normalized_collection_name="777",
                normalized_batch_name="1-19809",
                total_file_count=2,
            )
            first = repository.register_source_files(
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                values=files[:1],
                source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
                complete=False,
            )
            assert first.batch.status is RemoteManualSelectionBatchStatus.INDEXING
            session.commit()

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            completed = repository.register_source_files(
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                values=files[1:],
                source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
                complete=True,
            )
            session.commit()
            assert completed.batch.status is RemoteManualSelectionBatchStatus.ACTIVE

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            exact_retry = repository.register_source_files(
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                values=files,
                source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
                complete=True,
            )
            assert exact_retry.created_count == 0
            with pytest.raises(RemoteManualSelectionConflictError) as immutable:
                repository.register_source_files(
                    session_id=SESSION_ID,
                    batch_id=BATCH_ID,
                    values=(
                        replace(
                            files[0],
                            id=UUID(int=999),
                            source_index=2,
                            relative_path="source/3.jpg",
                        ),
                    ),
                    source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
                    complete=False,
                )
            assert immutable.value.code == "REMOTE_SELECTION_SOURCE_MANIFEST_IMMUTABLE"
    finally:
        engine.dispose()


def test_transfer_state_roundtrip_is_generation_scoped_and_reaches_verified(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    transfer_id = uuid4()
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.apply_operation(_command())
            transfer = RemoteManualSelectionTransferV1(
                id=transfer_id,
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                attempt=repository.next_transfer_attempt(file_id=FILE_ID, generation=1),
                declared_bytes=1024,
                received_bytes=0,
                status=RemoteManualSelectionTransferStatus.QUEUED,
                declared_checksum_sha256="b" * 64,
            )
            repository.add_transfer(transfer)
            for status in (
                RemoteManualSelectionTransferStatus.UPLOADING,
                RemoteManualSelectionTransferStatus.STORED_TEMP,
                RemoteManualSelectionTransferStatus.VERIFIED,
            ):
                transfer = replace(
                    transfer,
                    received_bytes=(
                        1024 if status is not RemoteManualSelectionTransferStatus.UPLOADING else 0
                    ),
                    status=status,
                    verified_checksum_sha256=(
                        "b" * 64 if status is RemoteManualSelectionTransferStatus.VERIFIED else None
                    ),
                )
                repository.update_transfer(
                    transfer,
                    temp_relative_path="internal/file.verified",
                )
            for status in (
                RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
                RemoteManualSelectionFileStatus.UPLOADING,
                RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
                RemoteManualSelectionFileStatus.VERIFIED,
            ):
                repository.update_file_transfer_status(
                    batch_id=BATCH_ID,
                    file_id=FILE_ID,
                    generation=1,
                    status=status,
                    temp_relative_path="internal/file.verified",
                    host_checksum_sha256=(
                        "b" * 64 if status is RemoteManualSelectionFileStatus.VERIFIED else None
                    ),
                )
            session.commit()

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            record = repository.get_transfer_record(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                transfer_id=transfer_id,
            )
            verified = repository.get_verified_transfer_record(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
            )
            selected = repository.get_applied_select_operation(
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
            )
            file = repository.get_file(batch_id=BATCH_ID, file_id=FILE_ID)
        assert record is not None and record.temp_relative_path == "internal/file.verified"
        assert verified == record
        assert selected is not None and selected.command.image_checksum_sha256 == "b" * 64
        assert file is not None and file.status is RemoteManualSelectionFileStatus.VERIFIED
        assert file.host_checksum_sha256 == "b" * 64
    finally:
        engine.dispose()


@pytest.mark.skipif(os.name != "nt", reason="Windows host path boundary")
def test_host_binding_marker_recovers_rollback_and_survives_service_restart(
    remote_database: URL,
    tmp_path: Path,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    base = tmp_path / "remote-output"
    base.mkdir()
    try:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.add_session(
                _session(),
                base_binding_id=BINDING_ID,
                host_base_path=str(base),
                display_name=base.name,
            )
            session.commit()

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            orphaned = RemoteManualSelectionHostService(lambda: None).provision_batch_mapping(
                repository,
                session_id=SESSION_ID,
                collection=_collection(),
                batch=_batch(),
                total_file_count=2201,
            )
            session.rollback()  # Crash window: marker persisted, DB transaction did not.

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            recovered = RemoteManualSelectionHostService(lambda: None).provision_batch_mapping(
                repository,
                session_id=SESSION_ID,
                collection=_collection(),
                batch=_batch(),
                total_file_count=2201,
            )
            session.commit()

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            resumed = RemoteManualSelectionHostService(lambda: None).provision_batch_mapping(
                repository,
                session_id=SESSION_ID,
                collection=_collection(),
                batch=_batch(),
                total_file_count=2201,
            )
            session.commit()

        marker = (
            base
            / "777"
            / "1-19809"
            / OWNERSHIP_DIRECTORY
            / OWNERSHIP_VERSION_DIRECTORY
            / OWNERSHIP_MARKER_NAME
        )
        assert orphaned.created is True and orphaned.resumed is False
        assert recovered.created is True and recovered.resumed is True
        assert resumed.created is False and resumed.resumed is True
        assert marker.is_file()
        assert str(base).lower() not in marker.read_text(encoding="utf-8").lower()
    finally:
        engine.dispose()


def test_concurrent_exact_retry_is_serialized_by_batch_row_lock(remote_database: URL) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    barrier = Barrier(2)
    _seed(engine)

    def apply_once() -> tuple[bool, int]:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            barrier.wait(timeout=10)
            result = repository.apply_operation(_command())
            session.commit()
            return result.exact_retry, result.batch.server_revision

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _index: apply_once(), range(2)))
        assert sorted(results) == [(False, 1), (True, 1)]
    finally:
        engine.dispose()


def test_sequence_and_revision_conflicts_leave_persisted_revision_unchanged(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    try:
        _seed(engine)
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.apply_operation(_command())
            session.commit()

        cases = (
            (_command(operation_id=uuid4()), "REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY"),
            (
                _command(operation_id=uuid4(), client_sequence=2, expected_revision=0),
                "REMOTE_SELECTION_REVISION_CONFLICT",
            ),
            (
                _command(operation_id=uuid4(), client_sequence=3, expected_revision=1),
                "REMOTE_SELECTION_CLIENT_SEQUENCE_GAP",
            ),
        )
        for command_value, expected_code in cases:
            with session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                with pytest.raises(RemoteManualSelectionConflictError) as error:
                    repository.apply_operation(command_value)
                assert error.value.code == expected_code
                session.rollback()

        with session_factory() as session:
            persisted = SqlAlchemyRemoteManualSelectionRepository(session).get_batch(BATCH_ID)
        assert persisted is not None and persisted.server_revision == 1
        assert persisted.last_client_sequence == 1
    finally:
        engine.dispose()


def test_concurrent_sessions_cannot_claim_the_same_base_mapping(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    second_session_id = uuid4()
    second_collection_id = uuid4()
    second_batch_id = uuid4()
    barrier = Barrier(2)
    try:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.add_session(
                _session(),
                base_binding_id=BINDING_ID,
                host_base_path=r"C:\Users\user\Documents",
                display_name="Documents",
            )
            repository.add_collection(_collection())
            repository.add_session(
                _session(second_session_id),
                base_binding_id=BINDING_ID,
                host_base_path=r"C:\Users\user\Documents",
                display_name="Documents",
            )
            repository.add_collection(_collection(second_session_id, second_collection_id))
            session.commit()

        def claim(
            session_id: UUID,
            collection_id: UUID,
            batch_id: UUID,
        ) -> str:
            with session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                barrier.wait(timeout=10)
                try:
                    repository.add_batch(
                        _batch(session_id, collection_id, batch_id),
                        base_binding_id=BINDING_ID,
                        normalized_collection_name="777",
                        normalized_batch_name="1-19809",
                        total_file_count=1,
                    )
                    session.commit()
                    return "created"
                except RemoteManualSelectionConflictError as error:
                    session.rollback()
                    return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(
                executor.map(
                    lambda arguments: claim(*arguments),
                    (
                        (SESSION_ID, COLLECTION_ID, BATCH_ID),
                        (second_session_id, second_collection_id, second_batch_id),
                    ),
                )
            )
        assert sorted(results) == ["REMOTE_SELECTION_BASE_MAPPING_CONFLICT", "created"]
    finally:
        engine.dispose()


def test_composite_foreign_keys_reject_cross_scope(remote_database: URL) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    _seed(engine)
    try:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            foreign = replace(
                _file(),
                id=uuid4(),
                session_id=uuid4(),
                source_index=1,
                relative_path="source/2.jpg",
            )
            with pytest.raises(RemoteManualSelectionError) as scope_error:
                repository.add_files((foreign,))
            assert scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"
            session.rollback()
    finally:
        engine.dispose()


def test_operations_and_audit_are_append_only_in_postgres(remote_database: URL) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    _seed(engine)
    event_id = uuid4()
    try:
        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.apply_operation(_command())
            repository.append_audit_event(
                event_id=event_id,
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                event_type="mapping_created",
                actor="local-owner",
                outcome_code="applied",
                payload={"collection": "777", "batch": "1-19809"},
                created_at=NOW,
            )
            session.commit()

        for statement, identifier in (
            (
                "UPDATE remote_manual_selection_operations SET outcome_code='changed' WHERE id=:id",
                OPERATION_ID,
            ),
            ("DELETE FROM remote_manual_selection_audit_events WHERE id=:id", event_id),
        ):
            with pytest.raises(DBAPIError), engine.begin() as connection:
                connection.execute(text(statement), {"id": identifier})
    finally:
        engine.dispose()


def test_delta_indexes_cover_fifteen_thousand_files_and_operations(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    count = 15_000
    _seed(engine, include_file=False, total_file_count=count)
    file_rows = []
    operation_rows = []
    for index in range(count):
        file_id = UUID(int=100_000 + index)
        operation_id = UUID(int=200_000 + index)
        operation_command = RemoteManualSelectionOperationCommandV1(
            operation_id=operation_id,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            client_instance_id=CLIENT_ID,
            client_sequence=index + 1,
            expected_server_revision=index,
            operation_type=RemoteManualSelectionOperationType.SKIP,
            selection_generation=0,
            range_start=index * 9 + 1,
            range_end=index * 9 + 9,
            recorded_at=NOW,
            visible_milliseconds=0,
            decoded=True,
        )
        file_rows.append(
            {
                "id": file_id,
                "session_id": SESSION_ID,
                "batch_id": BATCH_ID,
                "source_index": index,
                "relative_path": f"source/{index}.jpg",
                "size_bytes": 1024,
                "last_modified_ms": index,
                "mime_type": "image/jpeg",
                "desired_selected": False,
                "selection_generation": 0,
                "status": "unselected",
                "last_server_revision": index + 1,
            }
        )
        operation_rows.append(
            {
                "id": operation_id,
                "session_id": SESSION_ID,
                "batch_id": BATCH_ID,
                "file_id": None,
                "client_instance_id": CLIENT_ID,
                "client_sequence": index + 1,
                "expected_server_revision": index,
                "operation_type": "skip",
                "selection_generation": 0,
                "range_start": index * 9 + 1,
                "range_end": index * 9 + 9,
                "recorded_at": NOW,
                "image_path": None,
                "source_index": None,
                "image_checksum_sha256": None,
                "output_name": None,
                "visible_milliseconds": 0,
                "decoded": True,
                "target_operation_id": None,
                "command_checksum_sha256": operation_command.checksum_sha256,
                "status": "superseded",
                "applied_server_revision": index,
                "outcome_code": "scale_fixture",
            }
        )
    try:
        with engine.begin() as connection:
            connection.execute(insert(RemoteManualSelectionFileModel), file_rows)
            connection.execute(insert(RemoteManualSelectionOperationModel), operation_rows)
            connection.execute(text("ANALYZE remote_manual_selection_files"))
            connection.execute(text("ANALYZE remote_manual_selection_operations"))

        with session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            files = repository.list_file_delta(
                batch_id=BATCH_ID,
                after_revision=14_900,
                limit=100,
            )
            operations = repository.list_operations_after_sequence(
                batch_id=BATCH_ID,
                after_client_sequence=14_900,
                limit=100,
            )
            file_plan = "\n".join(
                session.scalars(
                    text(
                        "EXPLAIN SELECT id FROM remote_manual_selection_files "
                        "WHERE batch_id=:batch_id AND last_server_revision > 14900 "
                        "ORDER BY last_server_revision, source_index, id LIMIT 100"
                    ).bindparams(batch_id=BATCH_ID)
                )
            )
            operation_plan = "\n".join(
                session.scalars(
                    text(
                        "EXPLAIN SELECT id FROM remote_manual_selection_operations "
                        "WHERE batch_id=:batch_id AND client_sequence > 14900 "
                        "ORDER BY client_sequence, id LIMIT 100"
                    ).bindparams(batch_id=BATCH_ID)
                )
            )

        assert len(files) == 100
        assert len(operations) == 100
        assert "ix_rms_files_delta" in file_plan
        assert "ix_rms_operations_delta" in operation_plan
    finally:
        engine.dispose()


class _AccessHost:
    def __init__(self) -> None:
        self.used = False

    def consume_base_capability(self, capability: str) -> ConsumedRemoteManualSelectionBase:
        assert capability == "postgres-capability"
        assert self.used is False
        self.used = True
        return ConsumedRemoteManualSelectionBase(
            base_binding_id=uuid4(),
            host_base_path=Path(r"C:\host-only\remote-selection"),
            display_name="remote-selection",
        )


def test_access_session_unlock_restart_and_immediate_revoke_in_postgres(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    host = _AccessHost()
    try:
        with session_factory() as session:
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                host,
                now=lambda: NOW,
            )
            created = service.create(
                base_capability="postgres-capability",
                lifetime_minutes=60,
            )
            session.commit()

        client_id = uuid4()
        with session_factory() as session:
            # A fresh service/repository simulates an API restart.
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                _AccessHost(),
                now=lambda: NOW + timedelta(seconds=1),
            )
            unlocked = service.unlock(
                session_id=created.session.session_id,
                access_code=created.access_code,
                client_instance_id=client_id,
            )
            session.commit()

        with session_factory() as session:
            restarted = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                _AccessHost(),
                now=lambda: NOW + timedelta(seconds=2),
            )
            context = restarted.context(
                access_token=unlocked.access_token,
                client_instance_id=client_id,
            )
            assert context.is_writer is True
            restarted.revoke(created.session.session_id)
            session.commit()

        with session_factory() as session:
            restarted = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                _AccessHost(),
                now=lambda: NOW + timedelta(seconds=3),
            )
            with pytest.raises(RemoteManualSelectionAuthenticationError):
                restarted.context(
                    access_token=unlocked.access_token,
                    client_instance_id=client_id,
                )
            record = session.get(
                RemoteManualSelectionSessionModel,
                created.session.session_id,
            )
            assert record is not None
            assert record.code_hash != created.access_code.encode()
            assert record.token_hash is None
            assert record.writer_lease_token is None
            audit = tuple(
                session.scalars(
                    select(RemoteManualSelectionAuditEventModel).where(
                        RemoteManualSelectionAuditEventModel.session_id
                        == created.session.session_id
                    )
                )
            )
            serialized_audit = repr([event.payload for event in audit])
            assert created.access_code not in serialized_audit
            assert unlocked.access_token not in serialized_audit
            assert record.host_base_path not in serialized_audit
    finally:
        engine.dispose()


def test_concurrent_writer_takeover_has_exactly_one_winner_in_postgres(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    host = _AccessHost()
    try:
        with session_factory() as session:
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                host,
                now=lambda: NOW,
            )
            created = service.create(
                base_capability="postgres-capability",
                lifetime_minutes=60,
            )
            initial = service.unlock(
                session_id=created.session.session_id,
                access_code=created.access_code,
                client_instance_id=uuid4(),
            )
            session.commit()

        contenders = (uuid4(), uuid4())
        barrier = Barrier(2)

        def takeover(client_id: UUID) -> tuple[str, UUID]:
            with session_factory() as session:
                service = RemoteManualSelectionAccessService(
                    SqlAlchemyRemoteManualSelectionAccessRepository(session),
                    _AccessHost(),
                    now=lambda: NOW + timedelta(seconds=46),
                )
                barrier.wait(timeout=5)
                try:
                    service.takeover(
                        session_id=created.session.session_id,
                        access_token=initial.access_token,
                        client_instance_id=client_id,
                    )
                    session.commit()
                    return "won", client_id
                except RemoteManualSelectionLeaseConflictError:
                    session.rollback()
                    return "conflict", client_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(takeover, contenders))

        winners = [client_id for outcome, client_id in results if outcome == "won"]
        assert len(winners) == 1
        assert sorted(outcome for outcome, _client_id in results) == ["conflict", "won"]
        with session_factory() as session:
            record = session.get(
                RemoteManualSelectionSessionModel,
                created.session.session_id,
            )
            assert record is not None
            assert record.writer_client_instance_id == winners[0]
            assert record.writer_lease_token is not None
            assert record.writer_lease_expires_at == NOW + timedelta(seconds=91)
    finally:
        engine.dispose()


def test_concurrent_unlock_rotates_to_one_valid_token_in_postgres(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    host = _AccessHost()
    try:
        with session_factory() as session:
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                host,
                now=lambda: NOW,
            )
            created = service.create(
                base_capability="postgres-capability",
                lifetime_minutes=60,
            )
            session.commit()

        barrier = Barrier(2)

        def unlock(client_id: UUID) -> str:
            with session_factory() as session:
                service = RemoteManualSelectionAccessService(
                    SqlAlchemyRemoteManualSelectionAccessRepository(session),
                    _AccessHost(),
                    now=lambda: NOW + timedelta(seconds=1),
                )
                barrier.wait(timeout=5)
                unlocked = service.unlock(
                    session_id=created.session.session_id,
                    access_code=created.access_code,
                    client_instance_id=client_id,
                )
                session.commit()
                return unlocked.access_token

        clients = (uuid4(), uuid4())
        with ThreadPoolExecutor(max_workers=2) as executor:
            tokens = tuple(executor.map(unlock, clients))

        valid_count = 0
        with session_factory() as session:
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                _AccessHost(),
                now=lambda: NOW + timedelta(seconds=2),
            )
            for token, client_id in zip(tokens, clients, strict=True):
                try:
                    service.context(access_token=token, client_instance_id=client_id)
                except RemoteManualSelectionAuthenticationError:
                    continue
                valid_count += 1
        assert valid_count == 1
    finally:
        engine.dispose()


def test_concurrent_failed_unlocks_cannot_lose_lockout_attempts_in_postgres(
    remote_database: URL,
) -> None:
    engine = create_engine(remote_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    host = _AccessHost()
    try:
        with session_factory() as session:
            service = RemoteManualSelectionAccessService(
                SqlAlchemyRemoteManualSelectionAccessRepository(session),
                host,
                now=lambda: NOW,
            )
            created = service.create(
                base_capability="postgres-capability",
                lifetime_minutes=60,
            )
            session.commit()

        barrier = Barrier(5)

        def rejected(_index: int) -> str:
            with session_factory() as session:
                service = RemoteManualSelectionAccessService(
                    SqlAlchemyRemoteManualSelectionAccessRepository(session),
                    _AccessHost(),
                    now=lambda: NOW + timedelta(seconds=1),
                )
                barrier.wait(timeout=5)
                try:
                    service.unlock(
                        session_id=created.session.session_id,
                        access_code="WRONG-CODE",
                        client_instance_id=uuid4(),
                    )
                except RemoteManualSelectionAuthenticationError as error:
                    session.commit()
                    return error.code
                raise AssertionError("Wrong access code unexpectedly unlocked the session.")

        with ThreadPoolExecutor(max_workers=5) as executor:
            codes = tuple(executor.map(rejected, range(5)))

        assert codes.count("REMOTE_SELECTION_ACCESS_CODE_INVALID") == 4
        assert codes.count("REMOTE_SELECTION_SESSION_LOCKED") == 1
        with session_factory() as session:
            record = session.get(
                RemoteManualSelectionSessionModel,
                created.session.session_id,
            )
            assert record is not None
            assert record.failed_attempts == 5
            assert record.locked_at == NOW + timedelta(seconds=1)
            assert record.token_hash is None
            assert record.writer_lease_token is None
    finally:
        engine.dispose()
