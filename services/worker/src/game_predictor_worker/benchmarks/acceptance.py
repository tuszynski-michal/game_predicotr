"""Pure evaluation of M3.5 benchmark and G3 release evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeGuard

type CheckStatus = Literal["passed", "failed", "missing"]

EXPECTED_LAYOUT_COUNT = 500_000
EXPECTED_RELEASE_VERSION = "m35-benchmark.1"
EXPECTED_LOGICAL_CONTENT_SHA256 = "1b03171b268be8ee370151fc1033a7e64cb644d21610a2d4145be0d4e7492d89"
EXPECTED_SNAPSHOT_FILE_SHA256 = "04b4136ca2c9452bc45de09182907e1a0276acb9f4f96b209f8da00a8b0e0f27"
EXPECTED_SNAPSHOT_SIZE_BYTES = 41_025_536
MAX_ACCEPTED_RELEASE_SIZE_BYTES = 5 * 1024**3


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    check_id: str
    status: CheckStatus
    summary: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence": list(self.evidence),
            "id": self.check_id,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class DeviceEvaluation:
    check: AcceptanceCheck
    budget_failed: bool = False


@dataclass(frozen=True, slots=True)
class M35AcceptanceResult:
    status: Literal["passed", "failed", "blocked"]
    architecture_decision: str
    checks: tuple[AcceptanceCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "architectureDecision": {
                "mobileAdapter": self.architecture_decision,
                "signatureRepresentation": (
                    "text-v1"
                    if self.architecture_decision == "retain_text_signature_and_typescript_adapter"
                    else "pending"
                ),
            },
            "checks": [check.to_dict() for check in self.checks],
            "missingEvidence": [
                check.check_id for check in self.checks if check.status == "missing"
            ],
            "schemaVersion": 1,
            "status": self.status,
        }


def _nested(report: Mapping[str, object], *keys: str) -> object | None:
    current: object = report
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _all_true(report: Mapping[str, object], paths: Sequence[tuple[str, ...]]) -> bool:
    return all(_nested(report, *path) is True for path in paths)


def _check_dataset(report: Mapping[str, object] | None) -> AcceptanceCheck:
    if report is None:
        return AcceptanceCheck(
            "dataset_500k",
            "missing",
            "Brak raportu deterministycznego datasetu 500 000.",
        )

    expected_values = (
        (_nested(report, "layoutCount"), EXPECTED_LAYOUT_COUNT, "layoutCount"),
        (
            _nested(report, "releaseVersion"),
            EXPECTED_RELEASE_VERSION,
            "releaseVersion",
        ),
        (
            _nested(report, "logicalContentSha256"),
            EXPECTED_LOGICAL_CONTENT_SHA256,
            "logicalContentSha256",
        ),
        (
            _nested(report, "snapshotFileSha256"),
            EXPECTED_SNAPSHOT_FILE_SHA256,
            "snapshotFileSha256",
        ),
        (
            _nested(report, "snapshotSizeBytes"),
            EXPECTED_SNAPSHOT_SIZE_BYTES,
            "snapshotSizeBytes",
        ),
    )
    mismatches = [
        f"{name}={actual!r}, expected={expected!r}"
        for actual, expected, name in expected_values
        if actual != expected
    ]
    validation_paths = (
        ("validation", "everyLayoutRecomputed"),
        ("validation", "productionSnapshotValidatorPassed"),
    )
    if not _all_true(report, validation_paths):
        mismatches.append("pełna walidacja datasetu nie jest potwierdzona")

    estimated_size = _nested(report, "estimatedSnapshotSize", "fifteenGamesBytes")
    if not _is_number(estimated_size):
        return AcceptanceCheck(
            "dataset_500k",
            "missing",
            "Raport datasetu nie zawiera estymacji snapshotu dla 15 gier.",
        )
    if estimated_size > MAX_ACCEPTED_RELEASE_SIZE_BYTES:
        mismatches.append(f"estymacja 15 gier {estimated_size} B przekracza 5 GiB")

    if mismatches:
        return AcceptanceCheck(
            "dataset_500k",
            "failed",
            "; ".join(mismatches),
        )
    return AcceptanceCheck(
        "dataset_500k",
        "passed",
        "Dataset ma 500 000 layoutów, oczekiwane checksumy i estymację poniżej 5 GiB.",
    )


def _check_repository(report: Mapping[str, object] | None) -> AcceptanceCheck:
    if report is None:
        return AcceptanceCheck(
            "desktop_sqlite_baseline",
            "missing",
            "Brak raportu baseline SQLite.",
        )
    required = (
        ("budgetResults", "exact"),
        ("budgetResults", "prefix"),
        ("budgetResults", "cyclic"),
    )
    mismatches: list[str] = []
    if not _all_true(report, required):
        mismatches.append("co najmniej jeden budżet baseline SQLite nie przeszedł")
    if _nested(report, "dataset", "layoutCount") != EXPECTED_LAYOUT_COUNT:
        mismatches.append("layoutCount nie wynosi 500 000")
    if _nested(report, "dataset", "logicalContentSha256") != EXPECTED_LOGICAL_CONTENT_SHA256:
        mismatches.append("logiczny checksum nie odpowiada datasetowi M3.5")
    if _nested(report, "dataset", "snapshotFileSha256") != EXPECTED_SNAPSHOT_FILE_SHA256:
        mismatches.append("checksum pliku SQLite nie odpowiada datasetowi M3.5")
    if _nested(report, "measurements", "cyclicNMinusOne", "rowCount") != EXPECTED_LAYOUT_COUNT - 1:
        mismatches.append("pełny cykl nie zawiera dokładnie 499 999 rekordów")
    if mismatches:
        return AcceptanceCheck(
            "desktop_sqlite_baseline",
            "failed",
            "; ".join(mismatches),
        )
    return AcceptanceCheck(
        "desktop_sqlite_baseline",
        "passed",
        "Baseline SQLite przechodzi exact, prefix i cykl N-1 z właściwym datasetem.",
    )


def _check_worker(report: Mapping[str, object] | None) -> AcceptanceCheck:
    if report is None:
        return AcceptanceCheck(
            "bounded_worker",
            "missing",
            "Brak raportu wydajności i pamięci workera.",
        )
    mismatches: list[str] = []
    if _nested(report, "dataset", "layoutCount") != EXPECTED_LAYOUT_COUNT:
        mismatches.append("worker nie raportuje 500 000 layoutów")
    if _nested(report, "dataset", "logicalContentSha256") != EXPECTED_LOGICAL_CONTENT_SHA256:
        mismatches.append("worker użył innego logicznego checksumu")
    maximum_batch = _nested(report, "generation", "maximumGeneratedBatchSize")
    if not _is_number(maximum_batch):
        return AcceptanceCheck(
            "bounded_worker",
            "missing",
            "Raport workera nie zawiera maksymalnego rozmiaru partii.",
        )
    if maximum_batch > 1000:
        mismatches.append(f"partia workera {maximum_batch} przekracza 1000")
    for path in (
        ("generation", "elapsedSeconds"),
        ("generation", "throughputLayoutsPerSecond"),
        ("generation", "memory", "peakRssBytes"),
        ("validation", "elapsedSeconds"),
        ("validation", "throughputLayoutsPerSecond"),
    ):
        value = _nested(report, *path)
        if not _is_number(value) or value <= 0:
            mismatches.append(f"brak dodatniej miary {'.'.join(path)}")
    if mismatches:
        return AcceptanceCheck("bounded_worker", "failed", "; ".join(mismatches))
    return AcceptanceCheck(
        "bounded_worker",
        "passed",
        "Worker przetwarza dane partiami do 1000 i raportuje czas, throughput oraz RSS.",
    )


def _device_identity(report: Mapping[str, object]) -> str | None:
    manufacturer = str(_nested(report, "collection", "manufacturer") or "").lower()
    model = str(_nested(report, "collection", "model") or "").lower()
    if "pixel 10 pro xl" in model:
        return "pixel_10_pro_xl"
    if "samsung" in manufacturer and ("s21 ultra" in model or model.startswith("sm-g998")):
        return "galaxy_s21_ultra"
    return None


def _select_device_reports(
    reports: Sequence[tuple[str, Mapping[str, object]]],
) -> dict[str, tuple[str, Mapping[str, object]]]:
    selected: dict[str, tuple[str, Mapping[str, object]]] = {}
    for source, report in reports:
        identity = _device_identity(report)
        if identity is None:
            continue
        previous = selected.get(identity)
        captured_at = str(report.get("capturedAt") or "")
        previous_captured_at = "" if previous is None else str(previous[1].get("capturedAt") or "")
        if previous is None or (captured_at, source) > (previous_captured_at, previous[0]):
            selected[identity] = (source, report)
    return selected


def _check_device(
    device_id: str,
    selected: Mapping[str, tuple[str, Mapping[str, object]]],
) -> DeviceEvaluation:
    selected_report = selected.get(device_id)
    if selected_report is None:
        return DeviceEvaluation(
            AcceptanceCheck(
                f"android_{device_id}",
                "missing",
                f"Brak raportu offline dla {device_id}.",
            )
        )
    source, report = selected_report
    missing: list[str] = []
    failures: list[str] = []
    budget_failed = False

    expected_values = (
        (
            _nested(report, "benchmark", "buildVariant"),
            "release",
            "buildVariant",
        ),
        (
            _nested(report, "benchmark", "report", "dataset", "layoutCount"),
            EXPECTED_LAYOUT_COUNT,
            "layoutCount",
        ),
        (
            _nested(report, "benchmark", "report", "dataset", "releaseVersion"),
            EXPECTED_RELEASE_VERSION,
            "releaseVersion",
        ),
        (
            _nested(
                report,
                "benchmark",
                "report",
                "dataset",
                "logicalContentSha256",
            ),
            EXPECTED_LOGICAL_CONTENT_SHA256,
            "logicalContentSha256",
        ),
        (
            _nested(
                report,
                "benchmark",
                "report",
                "dataset",
                "snapshotFileSha256",
            ),
            EXPECTED_SNAPSHOT_FILE_SHA256,
            "snapshotFileSha256",
        ),
        (
            _nested(report, "benchmark", "report", "dataset", "snapshotSizeBytes"),
            EXPECTED_SNAPSHOT_SIZE_BYTES,
            "snapshotSizeBytes",
        ),
        (_nested(report, "collection", "airplaneMode"), "1", "airplaneMode"),
        (_nested(report, "collection", "wifiEnabled"), "0", "wifiEnabled"),
    )
    for actual, expected, name in expected_values:
        if actual is None:
            missing.append(name)
        elif actual != expected:
            failures.append(f"{name}={actual!r}, expected={expected!r}")

    timing_budgets = (
        (
            ("benchmark", "report", "measurements", "exactUnique", "p95Ms"),
            200,
            "exact p95",
        ),
        (
            ("benchmark", "report", "measurements", "exactDuplicate", "p95Ms"),
            200,
            "exact duplicate p95",
        ),
        (
            ("benchmark", "report", "measurements", "exactNotFound", "p95Ms"),
            200,
            "exact not found p95",
        ),
        (
            ("benchmark", "report", "measurements", "prefixFiveCells", "p95Ms"),
            300,
            "prefix p95",
        ),
        (
            ("benchmark", "report", "measurements", "cyclicRead", "p95Ms"),
            5_000,
            "cyclic read p95",
        ),
        (
            ("benchmark", "report", "measurements", "targetEndToEnd", "p95Ms"),
            10_000,
            "Target E2E p95",
        ),
        (
            ("benchmark", "progressIndicatorReadyMs"),
            500,
            "widoczny postęp",
        ),
    )
    for path, maximum, name in timing_budgets:
        value = _nested(report, *path)
        if not _is_number(value):
            missing.append(name)
        elif value > maximum if name == "widoczny postęp" else value >= maximum:
            failures.append(f"{name} {value} ms nie jest poniżej {maximum} ms")
            budget_failed = True

    for path, name in (
        (("collection", "peakTotalPssKb"), "peak TOTAL PSS"),
        (("collection", "peakTotalRssKb"), "peak TOTAL RSS"),
    ):
        value = _nested(report, *path)
        if not _is_number(value) or value <= 0:
            missing.append(name)

    scrolling = _nested(
        report,
        "manualAcceptance",
        "virtualizedTargetTableScrollingPassed",
    )
    if scrolling is None:
        missing.append("ręczny odbiór przewijania tabeli")
    elif scrolling is not True:
        failures.append("ręczny odbiór przewijania tabeli nie przeszedł")

    if failures:
        return DeviceEvaluation(
            AcceptanceCheck(
                f"android_{device_id}",
                "failed",
                "; ".join(failures),
                (source,),
            ),
            budget_failed=budget_failed,
        )
    if missing:
        return DeviceEvaluation(
            AcceptanceCheck(
                f"android_{device_id}",
                "missing",
                "Brak pól: " + ", ".join(sorted(set(missing))),
                (source,),
            )
        )
    return DeviceEvaluation(
        AcceptanceCheck(
            f"android_{device_id}",
            "passed",
            "Urządzenie przechodzi offline, pamięć, budżety i ręczne przewijanie.",
            (source,),
        )
    )


def _check_architecture(report: Mapping[str, object] | None) -> AcceptanceCheck:
    if report is None:
        return AcceptanceCheck(
            "architecture_dependency_guard",
            "missing",
            "Brak inspekcji bezpośrednich zależności.",
        )
    unexpected = _nested(report, "unexpectedDirectDependencies")
    adapter_present = _nested(report, "expoSqliteDirectDependencyPresent")
    if not isinstance(unexpected, Sequence) or isinstance(unexpected, str):
        return AcceptanceCheck(
            "architecture_dependency_guard",
            "missing",
            "Inspekcja zależności ma niepełny kontrakt.",
        )
    if unexpected:
        return AcceptanceCheck(
            "architecture_dependency_guard",
            "failed",
            "Wykryto niedozwolone zależności: " + ", ".join(str(value) for value in unexpected),
        )
    if adapter_present is not True:
        return AcceptanceCheck(
            "architecture_dependency_guard",
            "failed",
            "Brakuje deklarowanego adaptera expo-sqlite.",
        )
    return AcceptanceCheck(
        "architecture_dependency_guard",
        "passed",
        "Brak bezpośrednich zależności Redis/Celery i alternatywnego adaptera SQLite.",
    )


def _check_release_evidence(
    report: Mapping[str, object] | None,
) -> tuple[AcceptanceCheck, AcceptanceCheck, AcceptanceCheck]:
    if report is None:
        return (
            AcceptanceCheck(
                "release_panel_to_ready_apk",
                "missing",
                "Brak m35-release-workflow-acceptance.json z TASK-0039.",
            ),
            AcceptanceCheck(
                "release_reproducibility_immutability",
                "missing",
                "Brak fizycznego dowodu odtwarzalności i niezmienności wydania.",
            ),
            AcceptanceCheck(
                "release_sizes_and_device_update",
                "missing",
                "Brak rozmiarów PostgreSQL/SQLite/APK i odbioru aktualizacji in-place.",
            ),
        )

    report_status = report.get("status")

    def evidence_check(
        check_id: str,
        summary: str,
        paths: Sequence[tuple[str, ...]],
    ) -> AcceptanceCheck:
        missing = [".".join(path) for path in paths if _nested(report, *path) is None]
        if report_status is None:
            missing.insert(0, "status")
        failed = [
            ".".join(path)
            for path in paths
            if _nested(report, *path) is not None and _nested(report, *path) is not True
        ]
        if report_status is not None and report_status != "passed":
            failed.insert(0, f"status={report_status!r}")
        if failed:
            return AcceptanceCheck(
                check_id,
                "failed",
                "Negatywny dowód: " + ", ".join(failed),
            )
        if missing:
            return AcceptanceCheck(
                check_id,
                "missing",
                "Brak pól: " + ", ".join(missing),
            )
        return AcceptanceCheck(check_id, "passed", summary)

    workflow = evidence_check(
        "release_panel_to_ready_apk",
        "Panel uruchamia pełny workflow do zweryfikowanego i pobieralnego APK.",
        (
            ("workflow", "panelToReadyApkPassed"),
            ("artifact", "ready"),
            ("artifact", "adminDownloadPassed"),
            ("artifact", "offlineAuditPassed"),
            ("artifact", "snapshotMatchesRelease"),
        ),
    )
    reproducibility = evidence_check(
        "release_reproducibility_immutability",
        "Te same wejścia są odtwarzalne, a historyczne artefakty niezmienne.",
        (
            ("workflow", "sameInputsReproducible"),
            ("workflow", "historicalArtifactsImmutable"),
            ("workflow", "failureMatrixPassed"),
        ),
    )

    size_paths = (
        ("sizes", "postgresqlBytes"),
        ("sizes", "sqliteBytes"),
        ("sizes", "apkBytes"),
        ("sizes", "estimatedFifteenGamesReleaseBytes"),
    )
    missing_sizes = [
        ".".join(path) for path in size_paths if not _is_number(_nested(report, *path))
    ]
    update_paths = (
        ("deviceUpdate", "inPlacePassed"),
        ("deviceUpdate", "newSnapshotActivated"),
    )
    missing_updates = [".".join(path) for path in update_paths if _nested(report, *path) is None]
    failed_updates = [
        ".".join(path)
        for path in update_paths
        if _nested(report, *path) is not None and _nested(report, *path) is not True
    ]
    estimated_release_size = _nested(report, "sizes", "estimatedFifteenGamesReleaseBytes")
    if failed_updates:
        sizes_and_update = AcceptanceCheck(
            "release_sizes_and_device_update",
            "failed",
            "Negatywny dowód: " + ", ".join(failed_updates),
        )
    elif (
        _is_number(estimated_release_size)
        and estimated_release_size > MAX_ACCEPTED_RELEASE_SIZE_BYTES
    ):
        sizes_and_update = AcceptanceCheck(
            "release_sizes_and_device_update",
            "failed",
            f"Estymowane wydanie {estimated_release_size} B przekracza 5 GiB.",
        )
    elif missing_sizes or missing_updates:
        sizes_and_update = AcceptanceCheck(
            "release_sizes_and_device_update",
            "missing",
            "Brak pól: " + ", ".join(missing_sizes + missing_updates),
        )
    else:
        sizes_and_update = AcceptanceCheck(
            "release_sizes_and_device_update",
            "passed",
            "Rozmiary mieszczą się w limicie, a aktualizacja aktywuje nowy snapshot.",
        )
    return workflow, reproducibility, sizes_and_update


def evaluate_m35_acceptance(
    *,
    dataset_report: Mapping[str, object] | None,
    repository_report: Mapping[str, object] | None,
    worker_report: Mapping[str, object] | None,
    device_reports: Sequence[tuple[str, Mapping[str, object]]],
    release_evidence: Mapping[str, object] | None,
    architecture_evidence: Mapping[str, object] | None,
) -> M35AcceptanceResult:
    selected_devices = _select_device_reports(device_reports)
    pixel = _check_device("pixel_10_pro_xl", selected_devices)
    checks = (
        _check_dataset(dataset_report),
        _check_repository(repository_report),
        _check_worker(worker_report),
        pixel.check,
        _check_architecture(architecture_evidence),
        *_check_release_evidence(release_evidence),
    )

    if pixel.budget_failed:
        decision = "adapter_change_required"
    elif pixel.check.status == "passed":
        decision = "retain_text_signature_and_typescript_adapter"
    else:
        decision = "pending_device_evidence"

    if any(check.status == "failed" for check in checks):
        status: Literal["passed", "failed", "blocked"] = "failed"
    elif any(check.status == "missing" for check in checks):
        status = "blocked"
    else:
        status = "passed"
    return M35AcceptanceResult(
        status=status,
        architecture_decision=decision,
        checks=checks,
    )
