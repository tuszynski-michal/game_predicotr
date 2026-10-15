"""Future producer binding errors preserve a typed client refusal."""

from typing import cast

import pytest
from game_predictor_api.domain.source_recording_groups import RecordingError
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def test_invalid_catalog_binding_maps_sql_22023_to_typed_422():
    class InvalidBinding(Exception):
        sqlstate = "22023"

    class SessionWithInvalidBinding:
        def execute(self, statement, values=None):
            if str(statement).startswith("SET LOCAL"):
                return None
            raise DBAPIError(
                "fixed capability statement", {}, InvalidBinding("RECORDING_BINDING_INVALID"), False
            )

    repo = SqlAlchemySourceRecordingRepository(cast(Session, SessionWithInvalidBinding()))
    with pytest.raises(RecordingError) as failure:
        repo._call("fixed capability statement", {})
    assert failure.value.code == "RECORDING_BINDING_INVALID"
    assert failure.value.status == 422
