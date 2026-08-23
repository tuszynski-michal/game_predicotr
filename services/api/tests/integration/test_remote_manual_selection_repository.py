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
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.models import (
    RemoteManualSelectionFileModel,
    RemoteManualSelectionOperationModel,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    SqlAlchemyRemoteManualSelectionRepository,
)
from sqlalchemy import create_engine, insert, text
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
