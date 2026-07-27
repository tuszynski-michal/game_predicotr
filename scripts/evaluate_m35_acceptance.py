"""Evaluate all available M3.5 and G3 evidence without inventing missing results."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks import evaluate_m35_acceptance  # noqa: E402

DEFAULT_DATASET_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-benchmark-dataset-report.json"
)
DEFAULT_REPOSITORY_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-repository-benchmark.json"
)
DEFAULT_WORKER_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-worker-benchmark.json"
)
DEFAULT_DEVICE_DIRECTORY = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "device-benchmarks"
)
DEFAULT_RELEASE_EVIDENCE = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-release-workflow-acceptance.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-acceptance-report.json"

FORBIDDEN_DIRECT_DEPENDENCIES = frozenset(
    {
        "@op-engineering/op-sqlite",
        "celery",
        "react-native-nitro-sqlite",
        "react-native-quick-sqlite",
        "redis",
    }
)


def _load_optional_report(path: Path) -> Mapping[str, object] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Report root must be an object: {path}")
    return cast(dict[str, object], value)


def _device_reports(directory: Path) -> list[tuple[str, Mapping[str, object]]]:
    if not directory.is_dir():
        return []
    reports: list[tuple[str, Mapping[str, object]]] = []
    for path in sorted(directory.glob("*.json")):
        report = _load_optional_report(path)
        if report is not None:
            reports.append((path.relative_to(REPOSITORY_ROOT).as_posix(), report))
    return reports


def _dependency_name(requirement: str) -> str:
    match = re.match(r"^[A-Za-z0-9_.-]+", requirement)
    if match is None:
        raise RuntimeError(f"Cannot parse Python dependency: {requirement!r}")
    return match.group(0).lower()


def _architecture_evidence() -> dict[str, object]:
    dependencies: set[str] = set()
    package_paths = [
        REPOSITORY_ROOT / "package.json",
        *sorted((REPOSITORY_ROOT / "apps").glob("*/package.json")),
        *sorted((REPOSITORY_ROOT / "packages").glob("*/package.json")),
    ]
    for path in package_paths:
        package = _load_optional_report(path)
        if package is None:
            continue
        for section_name in ("dependencies", "optionalDependencies"):
            section = package.get(section_name)
            if isinstance(section, dict):
                dependencies.update(str(name).lower() for name in section)

    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject.get("project")
    if isinstance(project, dict):
        requirements = project.get("dependencies")
        if isinstance(requirements, list):
            dependencies.update(
                _dependency_name(requirement)
                for requirement in requirements
                if isinstance(requirement, str)
            )

    return {
        "directDependencies": sorted(dependencies),
        "expoSqliteDirectDependencyPresent": "expo-sqlite" in dependencies,
        "unexpectedDirectDependencies": sorted(
            dependencies.intersection(FORBIDDEN_DIRECT_DEPENDENCIES)
        ),
    }


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-report", type=Path, default=DEFAULT_DATASET_REPORT)
    parser.add_argument(
        "--repository-report",
        type=Path,
        default=DEFAULT_REPOSITORY_REPORT,
    )
    parser.add_argument("--worker-report", type=Path, default=DEFAULT_WORKER_REPORT)
    parser.add_argument(
        "--device-directory",
        type=Path,
        default=DEFAULT_DEVICE_DIRECTORY,
    )
    parser.add_argument(
        "--release-evidence",
        type=Path,
        default=DEFAULT_RELEASE_EVIDENCE,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Return exit code 1 unless every G3 check passes.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = evaluate_m35_acceptance(
        dataset_report=_load_optional_report(args.dataset_report),
        repository_report=_load_optional_report(args.repository_report),
        worker_report=_load_optional_report(args.worker_report),
        device_reports=_device_reports(args.device_directory),
        release_evidence=_load_optional_report(args.release_evidence),
        architecture_evidence=_architecture_evidence(),
    )
    report = {
        "capturedAt": datetime.now(UTC).isoformat(),
        "inputs": {
            "datasetReport": _display_path(args.dataset_report),
            "deviceDirectory": _display_path(args.device_directory),
            "releaseEvidence": _display_path(args.release_evidence),
            "repositoryReport": _display_path(args.repository_report),
            "workerReport": _display_path(args.worker_report),
        },
        **result.to_dict(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.require_pass and result.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
