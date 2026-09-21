from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionSourceManifest,
    create_semi_automatic_selection_run,
)
from game_predictor_api.storage.models import SemiAutomaticImageSelectionRunModel
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
    _v7_configuration_from_record,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session


class _ForeignKeyOrderingSession:
    """Small unit double which rejects child rows before their run is flushed."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self._parent_pending = False
        self._parent_flushed = False
        self._children_pending = False

    def begin_nested(self) -> Any:
        return nullcontext()

    def add(self, value: object) -> None:
        self.events.append(type(value).__name__)
        if type(value).__name__ == "SemiAutomaticImageSelectionRunModel":
            self._parent_pending = True

    def add_all(self, values: Iterable[object]) -> None:
        self.events.append("ranges")
        self._children_pending = bool(tuple(values))

    def flush(self) -> None:
        self.events.append("flush")
        if self._children_pending and not self._parent_flushed:
            raise AssertionError("range rows would violate their run foreign key")
        if self._parent_pending:
            self._parent_flushed = True

    def get(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_add_flushes_the_run_before_its_foreign_key_ranges() -> None:
    source = _source_manifest()
    run, ranges = create_semi_automatic_selection_run(
        source=source,
        first_sequence_number=1,
        last_sequence_number=18,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
        recognizer_fingerprint="a" * 64,
        grouping_policy_fingerprint="b" * 64,
    )
    session = _ForeignKeyOrderingSession()
    repository = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, session))
    repository.get = lambda _run_id: run  # type: ignore[method-assign]

    stored = repository.add(run, ranges, identity_key="c" * 64)

    assert stored is run
    assert session.events == [
        "JobModel",
        "SemiAutomaticImageSelectionRunModel",
        "flush",
        "ranges",
        "flush",
    ]


def _source_manifest() -> SemiAutomaticSelectionSourceManifest:
    return SemiAutomaticSelectionSourceManifest(
        upload_id=UUID("00000000-0000-0000-0000-000000000001"),
        display_name="seq",
        manifest_checksum_sha256="d" * 64,
        source_fingerprint="e" * 64,
        source_count=2,
        source_total_bytes=20,
    )


def test_legacy_v7_metadata_none_binds_as_sql_null() -> None:
    column = SemiAutomaticImageSelectionRunModel.__table__.c.v7_configuration
    processor = column.type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(None) is None


def test_v7_configuration_read_rejects_version_or_calibration_fingerprint_drift() -> None:
    configuration = {
        "version": "v7-selection-configuration-v1",
        "mode": "semi_automatic",
        "direction": "ascending",
        "firstSequenceNumber": 1,
        "lastSequenceNumber": 18,
        "borderStyle": "top_and_sides",
        "localizerFingerprint": "a" * 64,
        "calibrationFingerprint": "b" * 64,
    }
    record = SimpleNamespace(
        v7_configuration=configuration,
        v7_calibration_fingerprint="b" * 64,
    )
    assert _v7_configuration_from_record(cast(SemiAutomaticImageSelectionRunModel, record))

    for invalid_configuration, fingerprint in (
        ({**configuration, "version": "v7-selection-configuration-v0"}, "b" * 64),
        (configuration, "c" * 64),
    ):
        invalid_record = SimpleNamespace(
            v7_configuration=invalid_configuration,
            v7_calibration_fingerprint=fingerprint,
        )
        with pytest.raises(SemiAutomaticSelectionConflictError) as raised:
            _v7_configuration_from_record(
                cast(SemiAutomaticImageSelectionRunModel, invalid_record)
            )
        assert raised.value.code == "SEMI_AUTOMATIC_SELECTION_V7_CONFIGURATION_INVALID"
