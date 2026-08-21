from __future__ import annotations

from typing import cast

from game_predictor_worker.benchmarks.acceptance import (
    EXPECTED_LAYOUT_COUNT,
    EXPECTED_LOGICAL_CONTENT_SHA256,
    EXPECTED_RELEASE_VERSION,
    EXPECTED_SNAPSHOT_FILE_SHA256,
    EXPECTED_SNAPSHOT_SIZE_BYTES,
    evaluate_m35_acceptance,
)


def dataset_report() -> dict[str, object]:
    return {
        "estimatedSnapshotSize": {"fifteenGamesBytes": 600_000_000},
        "layoutCount": EXPECTED_LAYOUT_COUNT,
        "logicalContentSha256": EXPECTED_LOGICAL_CONTENT_SHA256,
        "releaseVersion": EXPECTED_RELEASE_VERSION,
        "snapshotFileSha256": EXPECTED_SNAPSHOT_FILE_SHA256,
        "snapshotSizeBytes": EXPECTED_SNAPSHOT_SIZE_BYTES,
        "validation": {
            "everyLayoutRecomputed": True,
            "productionSnapshotValidatorPassed": True,
        },
    }


def repository_report() -> dict[str, object]:
    return {
        "budgetResults": {"cyclic": True, "exact": True, "prefix": True},
        "dataset": {
            "layoutCount": EXPECTED_LAYOUT_COUNT,
            "logicalContentSha256": EXPECTED_LOGICAL_CONTENT_SHA256,
            "snapshotFileSha256": EXPECTED_SNAPSHOT_FILE_SHA256,
        },
        "measurements": {"cyclicNMinusOne": {"rowCount": EXPECTED_LAYOUT_COUNT - 1}},
    }


def worker_report() -> dict[str, object]:
    return {
        "dataset": {
            "layoutCount": EXPECTED_LAYOUT_COUNT,
            "logicalContentSha256": EXPECTED_LOGICAL_CONTENT_SHA256,
        },
        "generation": {
            "elapsedSeconds": 10,
            "maximumGeneratedBatchSize": 1000,
            "memory": {"peakRssBytes": 100_000_000},
            "throughputLayoutsPerSecond": 50_000,
        },
        "validation": {
            "elapsedSeconds": 5,
            "throughputLayoutsPerSecond": 100_000,
        },
    }


def device_report(*, pixel: bool, e2e_p95_ms: float = 4000) -> dict[str, object]:
    manufacturer = "Google" if pixel else "Samsung"
    model = "Pixel 10 Pro XL" if pixel else "SM-G998B"
    timing = {"iterations": 5, "p95Ms": 10}
    return {
        "capturedAt": "2026-07-27T12:00:00+00:00",
        "collection": {
            "airplaneMode": "1",
            "manufacturer": manufacturer,
            "model": model,
            "peakTotalPssKb": 100_000,
            "peakTotalRssKb": 150_000,
            "wifiEnabled": "0",
        },
        "manualAcceptance": {
            "virtualizedTargetTableScrollingPassed": True,
        },
        "benchmark": {
            "buildVariant": "release",
            "progressIndicatorReadyMs": 25,
            "report": {
                "dataset": {
                    "layoutCount": EXPECTED_LAYOUT_COUNT,
                    "logicalContentSha256": EXPECTED_LOGICAL_CONTENT_SHA256,
                    "releaseVersion": EXPECTED_RELEASE_VERSION,
                    "snapshotFileSha256": EXPECTED_SNAPSHOT_FILE_SHA256,
                    "snapshotSizeBytes": EXPECTED_SNAPSHOT_SIZE_BYTES,
                },
                "measurements": {
                    "cyclicRead": timing,
                    "exactDuplicate": timing,
                    "exactNotFound": timing,
                    "exactUnique": timing,
                    "prefixFiveCells": timing,
                    "targetEndToEnd": {
                        "iterations": 5,
                        "p95Ms": e2e_p95_ms,
                    },
                },
            },
        },
    }


def release_evidence() -> dict[str, object]:
    return {
        "artifact": {
            "adminDownloadPassed": True,
            "offlineAuditPassed": True,
            "ready": True,
            "snapshotMatchesRelease": True,
        },
        "deviceUpdate": {
            "inPlacePassed": True,
            "newSnapshotActivated": True,
        },
        "sizes": {
            "apkBytes": 50_000_000,
            "estimatedFifteenGamesReleaseBytes": 700_000_000,
            "postgresqlBytes": 200_000_000,
            "sqliteBytes": EXPECTED_SNAPSHOT_SIZE_BYTES,
        },
        "status": "passed",
        "workflow": {
            "failureMatrixPassed": True,
            "historicalArtifactsImmutable": True,
            "panelToReadyApkPassed": True,
            "sameInputsReproducible": True,
        },
    }


def architecture_evidence() -> dict[str, object]:
    return {
        "expoSqliteDirectDependencyPresent": True,
        "unexpectedDirectDependencies": [],
    }


def evaluate(
    *,
    devices: list[tuple[str, dict[str, object]]],
    release: dict[str, object] | None,
):
    return evaluate_m35_acceptance(
        dataset_report=dataset_report(),
        repository_report=repository_report(),
        worker_report=worker_report(),
        device_reports=devices,
        release_evidence=release,
        architecture_evidence=architecture_evidence(),
    )


def test_missing_physical_evidence_blocks_without_inventing_a_decision() -> None:
    result = evaluate(devices=[], release=None)

    assert result.status == "blocked"
    assert result.architecture_decision == "pending_device_evidence"
    assert {check.check_id for check in result.checks if check.status == "missing"} >= {
        "android_pixel_10_pro_xl",
        "release_panel_to_ready_apk",
    }


def test_complete_evidence_retains_existing_adapter_and_passes() -> None:
    result = evaluate(
        devices=[("pixel.json", device_report(pixel=True))],
        release=release_evidence(),
    )

    assert result.status == "passed"
    assert result.architecture_decision == "retain_text_signature_and_typescript_adapter"
    assert all(check.status == "passed" for check in result.checks)


def test_device_budget_failure_requires_adapter_change() -> None:
    result = evaluate(
        devices=[
            (
                "pixel.json",
                device_report(pixel=True, e2e_p95_ms=10_000),
            ),
        ],
        release=release_evidence(),
    )

    assert result.status == "failed"
    assert result.architecture_decision == "adapter_change_required"
    pixel = next(check for check in result.checks if check.check_id == "android_pixel_10_pro_xl")
    assert pixel.status == "failed"
    assert "Target E2E" in pixel.summary


def test_checksum_mismatch_is_failed_not_missing() -> None:
    pixel = device_report(pixel=True)
    benchmark = cast(dict[str, object], pixel["benchmark"])
    report = cast(dict[str, object], benchmark["report"])
    dataset = cast(dict[str, object], report["dataset"])
    dataset["snapshotFileSha256"] = "f" * 64

    result = evaluate(
        devices=[("pixel.json", pixel)],
        release=release_evidence(),
    )

    assert result.status == "failed"
    pixel_check = next(
        check for check in result.checks if check.check_id == "android_pixel_10_pro_xl"
    )
    assert pixel_check.status == "failed"
    assert "snapshotFileSha256" in pixel_check.summary
