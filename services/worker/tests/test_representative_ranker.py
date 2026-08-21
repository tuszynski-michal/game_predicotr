from pathlib import Path

from game_predictor_worker.images.selection.contracts import ImageQualityMetrics
from game_predictor_worker.images.selection.ranker import (
    RANKER_COHORT_KIND,
    RANKER_FEATURE_VERSION,
    build_ranking_cohort,
    quality_features,
    shadow_rank,
    train_ranker,
)
from PIL import Image


def _manifests() -> tuple[dict[str, object], dict[str, object]]:
    trace = {
        "schemaVersion": 1,
        "sessionKey": "session-1",
        "events": [
            {
                "decoded": True,
                "eventIndex": 0,
                "gameId": "game-1",
                "imagePath": "a.jpg",
                "kind": "viewed",
                "rangeEnd": 9,
                "rangeStart": 1,
                "sessionKey": "session-1",
                "sourceIndex": 0,
                "visibleMilliseconds": 500,
            },
            {
                "decoded": True,
                "eventIndex": 1,
                "gameId": "game-1",
                "imagePath": "b.jpg",
                "kind": "viewed",
                "rangeEnd": 9,
                "rangeStart": 1,
                "sessionKey": "session-1",
                "sourceIndex": 1,
                "visibleMilliseconds": 500,
            },
            {
                "decoded": True,
                "eventIndex": 2,
                "gameId": "game-1",
                "imagePath": "a.jpg",
                "kind": "accepted",
                "rangeEnd": 9,
                "rangeStart": 1,
                "sessionKey": "session-1",
                "sourceIndex": 0,
                "visibleMilliseconds": 500,
                "checksum": "0" * 64,
            },
        ],
    }
    output = {
        "schemaVersion": 1,
        "sessionKey": "session-1",
        "items": [
            {
                "imageChecksum": "0" * 64,
                "imagePath": "a.jpg",
                "outputName": "seq_1-9.jpg",
                "rangeEnd": 9,
                "rangeStart": 1,
            }
        ],
    }
    return trace, output


def test_quality_features_exclude_overall_score() -> None:
    metrics = ImageQualityMetrics(*(0.25 for _ in range(8)))
    assert quality_features(metrics, 0.75).tolist() == [0.25] * 7 + [0.75]


def test_build_cohort_filters_short_views_and_writes_manifest(tmp_path: Path) -> None:
    trace, output = _manifests()
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (96, 96), (20, 40, 80)).save(source / "a.jpg", "JPEG")
    Image.new("RGB", (96, 96), (20, 40, 80)).save(source / "b.jpg", "JPEG")
    output["items"][0]["imageChecksum"] = __import__("hashlib").sha256(
        (source / "a.jpg").read_bytes()
    ).hexdigest()

    cohort, preview = build_ranking_cohort(trace, output, source_roots=(source,))

    assert cohort["kind"] == RANKER_COHORT_KIND
    assert cohort["featureVersion"] == RANKER_FEATURE_VERSION
    assert preview.group_count == 1
    assert preview.reliable_pair_count == 1


def test_train_ranker_exports_shadow_snapshot(tmp_path: Path) -> None:
    trace, output = _manifests()
    source = tmp_path / "source"
    source.mkdir()
    a = source / "a.jpg"
    b = source / "b.jpg"
    Image.new("RGB", (96, 96), (20, 40, 80)).save(a, "JPEG")
    Image.new("RGB", (96, 96), (20, 40, 80)).save(b, "JPEG")
    output["items"][0]["imageChecksum"] = __import__("hashlib").sha256(a.read_bytes()).hexdigest()
    cohort, _ = build_ranking_cohort(trace, output, source_roots=(source,))
    snapshot, report = train_ranker(cohort, output_directory=tmp_path, epochs=2)

    assert snapshot.status == "shadow"
    assert snapshot.model_version == "representative-quality-mlp-v1"
    assert report["pairCount"] == 1
    assert float(report["onnxParityMaxAbsError"]) < 1e-5
    model_path = tmp_path / snapshot.model_relative_path
    assert model_path.is_file()
    features = [sample["features"] for sample in cohort["samples"]]
    assert sorted(shadow_rank(snapshot, features, model_path=model_path)) == [0, 1]
