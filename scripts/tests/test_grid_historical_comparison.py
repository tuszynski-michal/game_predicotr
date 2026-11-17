import hashlib
import json

import numpy as np
import pytest

from scripts.compare_grid_historical_models import (
    LastFrameEngine,
    choose_historical,
    frozen_funnel,
    write_funnel_evidence,
)


def metric(correct, error):
    return {
        "photo_complete_correct_rate": correct,
        "board_correct_rate": correct,
        "normalized_error": error,
    }


def test_historical_selection_uses_only_declared_validation_results():
    values = {"older": {"metrics": metric(1, 0.01)}, "newer": {"metrics": metric(0.8, 0.001)}}
    assert choose_historical(values, ["older", "newer"]) == "older"
    values["older"]["REGRESSION"] = {"boards_correct": 0}
    assert choose_historical(values, ["older", "newer"]) == "older"
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        choose_historical(values, ["older", "older"])


def test_self_measurement_cache_is_exact_and_invalidates_changed_pixels():
    class Engine:
        calls = 0

        def analyse(self, rgb):
            self.calls += 1
            return [int(rgb.sum())]

    source = Engine()
    cached = LastFrameEngine(source)
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    assert cached.analyse(rgb) == cached.analyse(rgb.copy()) == [0]
    assert source.calls == 1
    rgb[0, 0, 0] = 1
    assert cached.analyse(rgb) == [1] and source.calls == 2


def test_funnel_separates_roles_aliases_and_actual_consumed_counts():
    manifest = {
        "counts": {"TRAIN": {"photos": 1}},
        "photoSplit": {
            "sources": [
                {
                    "role": "TRAIN",
                    "representative": True,
                    "qualifiedBoards": 9,
                    "eligibleBoards": 9,
                },
                {
                    "role": "TRAIN",
                    "representative": True,
                    "qualifiedBoards": 2,
                    "eligibleBoards": 0,
                },
                {
                    "role": "TRAIN",
                    "representative": False,
                    "qualifiedBoards": 2,
                    "eligibleBoards": 0,
                },
                {
                    "role": "REGRESSION",
                    "representative": True,
                    "qualifiedBoards": 2,
                    "eligibleBoards": 2,
                },
                {
                    "role": "TRAIN",
                    "representative": True,
                    "eligibleBoards": 0,
                    "pendingCorrection": True,
                },
                {
                    "role": "TRAIN",
                    "representative": True,
                    "eligibleBoards": 0,
                    "qualifiedBoards": 0,
                    "pendingCorrection": True,
                },
            ]
        },
    }
    value = frozen_funnel(manifest)
    assert value["assignedTrainPhotos"] == 5 and value["representativeTrainPhotos"] == 4
    assert value["partialTrainPhotos"] == 1
    assert value["partialQualifiedBoards"] == 2
    assert value["fullTrainRepresentatives"] == 1 and value["emptyTrainRepresentatives"] == 2
    assert value["emptyTrainPendingCorrectionPhotos"] == 2
    assert value["trainAssignmentsReconciled"] and value["screenTrainCountReconciled"]
    assert value["trainOmissionCounts"] == {
        "nonRepresentativeAliases": 1,
        "partialPhotosExcludedFromScreen": 1,
        "noQualifiedBoards": 2,
    }
    assert "not stored" in value["reasonProvenance"]


def test_funnel_receipt_binds_source_and_manifest_bytes(tmp_path):
    manifest = {"counts": {"TRAIN": {"photos": 0}}, "photoSplit": {"sources": []}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    cohort = {
        "manifestPath": "manifest.json",
        "manifestSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    output = tmp_path / "funnel.json"
    write_funnel_evidence(tmp_path, cohort, output)
    receipt = json.loads(output.read_text())
    assert (
        hashlib.sha256(output.with_suffix(".source.txt").read_bytes()).hexdigest()
        == receipt["sourceSha256"]
    )
    path.write_text("{}")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        write_funnel_evidence(tmp_path, cohort, tmp_path / "corrupt.json")
    assert not (tmp_path / "corrupt.json").exists()
