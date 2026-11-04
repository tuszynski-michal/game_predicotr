from copy import deepcopy
from uuid import UUID

import pytest
from game_predictor_worker.geometry_core.diagnostic_registration import (
    registration_request,
    require_registration,
    stage_registration,
)
from game_predictor_worker.geometry_core.input_diagnostics import digest, encode_record
from test_full_board_input_diagnostics import sample  # noqa: F401


def test_registration_is_stable_deduplicated_and_not_claimed_executed(sample):  # noqa: F811
    document = encode_record(sample[1])
    result = stage_registration(UUID(int=1), [document, document])
    assert len(result["requests"]) == 1
    assert result["status"] == "staged_not_registered"
    assert result["readinessAccessIncluded"] is False
    assert require_registration(result) == result
    tampered = deepcopy(result)
    tampered["requests"][0]["idempotencyKey"] = str(UUID(int=2))
    with pytest.raises(ValueError, match="MANIFEST_MISMATCH"):
        require_registration(tampered)


@pytest.mark.parametrize("mutation", ["archive", "hash", "version", "contract"])
def test_metadata_registration_requires_strict_complete_preset_even_with_new_envelope_sha(
    sample,  # noqa: F811
    mutation,
):
    document = deepcopy(encode_record(sample[1]))
    payload = document["payload"]
    if mutation == "archive":
        del payload["archived_preset"]
    elif mutation == "hash":
        payload["model"]["preset_sha256"] = "d" * 64
    elif mutation == "version":
        payload["model"]["preprocessing_version"] = "future"
    else:
        payload["board_preset"]["margin"] += 0.01
    document["sha256"] = digest(payload)
    with pytest.raises(ValueError):
        registration_request(document)
