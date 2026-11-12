"""Selection is a strict subset of a signed-scope-shaped request, never authorization."""

from copy import deepcopy
from uuid import uuid4

import pytest
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.source_replacement_admission import selected_replacement_files
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.storage.sequence_ownership_lock import SequenceOwnershipLockMode
from sqlalchemy.exc import OperationalError


def selection_fixture():
    game, batch, first, second = (uuid4() for _ in range(4))
    request = {
        "schemaVersion": "source-replacement-request-v1",
        "gameId": str(game),
        "batchId": str(batch),
        "entries": [
            {
                "entryId": str(entry),
                "revision": 2,
                "digest": "a" * 64,
                "sourceSha256": "b" * 64,
                "sequenceNumbers": list(range(start, start + 2)),
            }
            for entry, start in ((first, 101), (second, 103))
        ],
        "allowedRanges": [
            {"entryId": str(entry), "sequenceStart": start, "sequenceEnd": start + 1}
            for entry, start in ((first, 101), (second, 103))
        ],
    }
    request["digest"] = digest(request)
    return game, {
        "request": request,
        "selectedEntryIds": [str(first)],
        "files": [
            {
                "entryId": str(first),
                "fileName": "seq_101-102.jpg",
                "checksumSha256": "c" * 64,
                "rangeStart": 101,
                "rangeEnd": 102,
                "operationId": str(uuid4()),
            }
        ],
    }


def test_partial_output_keeps_original_request_and_selects_only_completed_file():
    game, selection = selection_fixture()
    prior = deepcopy(selection)
    files = selected_replacement_files(selection, game)
    assert len(files) == 1
    assert files[0]["sequenceNumbers"] == [101, 102]
    assert selection == prior


@pytest.mark.parametrize("case", ["digest", "missing", "duplicate", "range", "old_sha", "game"])
def test_selection_rejects_claims_that_do_not_identify_exact_output(case):
    game, selection = selection_fixture()
    if case == "digest":
        selection["request"]["entries"][0]["revision"] += 1
    elif case == "missing":
        selection["selectedEntryIds"].append(selection["request"]["entries"][1]["entryId"])
    elif case == "duplicate":
        selection["files"].append(deepcopy(selection["files"][0]))
    elif case == "range":
        selection["files"][0]["rangeEnd"] = 103
    elif case == "old_sha":
        selection["files"][0]["checksumSha256"] = "b" * 64
    else:
        game = uuid4()
    with pytest.raises(SourceReplacementError, match="Wybór"):
        selected_replacement_files(selection, game)


class _LockTimeout(Exception):
    sqlstate = "55P03"


class _OtherDriverError(Exception):
    sqlstate = "57014"


def _ordinary_manifest():
    from game_predictor_api.domain.image_sequence_canonical import BrowserSequenceManifest

    return BrowserSequenceManifest(files=(), warnings=(), checksum_sha256="a" * 64)


def _patch_lock(monkeypatch, failure=None):
    """Replace binding and the advisory lock; record the requested lock mode."""

    from game_predictor_api.storage import source_replacement_admission as admission

    modes = []

    def acquire(session, *, game_id, mode):
        modes.append(mode)
        if failure is not None:
            raise OperationalError("SELECT pg_advisory_xact_lock(:k)", {}, failure)
        return mode

    monkeypatch.setattr(admission.SourceReplacementRepository, "bind", lambda self, game: None)
    monkeypatch.setattr(admission, "acquire_sequence_ownership_lock", acquire)
    return admission, modes


def test_ordinary_staging_lock_timeout_is_a_retryable_conflict(monkeypatch):
    """TASK-1190: a busy game must not surface as an opaque HTTP 500."""

    admission, modes = _patch_lock(monkeypatch, failure=_LockTimeout("lock timeout"))
    with pytest.raises(SourceReplacementError) as error:
        admission.validate_ordinary_staging(object(), game=uuid4(), manifest=_ordinary_manifest())
    assert error.value.code == "IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY"
    assert "Spróbuj ponownie" in error.value.message
    assert modes == [SequenceOwnershipLockMode.EXCLUSIVE]


def test_ordinary_staging_other_driver_errors_are_not_masked(monkeypatch):
    admission, _ = _patch_lock(monkeypatch, failure=_OtherDriverError("statement timeout"))
    with pytest.raises(OperationalError):
        admission.validate_ordinary_staging(object(), game=uuid4(), manifest=_ordinary_manifest())


def test_ordinary_staging_preview_requests_the_shared_lock(monkeypatch):
    admission, modes = _patch_lock(monkeypatch)
    admission.validate_ordinary_staging(
        object(),
        game=uuid4(),
        manifest=_ordinary_manifest(),
        lock_mode=SequenceOwnershipLockMode.SHARED,
    )
    assert modes == [SequenceOwnershipLockMode.SHARED]
