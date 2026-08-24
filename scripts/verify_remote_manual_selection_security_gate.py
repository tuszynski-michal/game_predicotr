"""Verify the immutable remote manual selection security-gate report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "remote-manual-selection-security-gate-v1"
REQUIRED_CONTROL_IDS = frozenset(
    {
        "SG-01",
        "SG-02",
        "SG-03",
        "SG-04",
        "SG-05",
        "SG-06",
        "SG-07",
        "SG-08",
    }
)
BLOCKING_SEVERITIES = frozenset({"critical", "high"})


class SecurityGateReportError(ValueError):
    """The security report is incomplete, unsafe or not content-addressed."""


def report_checksum(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("contentChecksumSha256", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_report(payload: dict[str, Any], *, repository_root: Path) -> str:
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise SecurityGateReportError("Unsupported security gate report schema.")
    if payload.get("decision") != "passed":
        raise SecurityGateReportError("The security gate decision is not passed.")
    controls = payload.get("controls")
    if not isinstance(controls, list):
        raise SecurityGateReportError("Security controls must be a list.")
    control_ids = {item.get("id") for item in controls if isinstance(item, dict)}
    if control_ids != REQUIRED_CONTROL_IDS:
        raise SecurityGateReportError("The security control set is incomplete or unexpected.")
    for control in controls:
        if not isinstance(control, dict) or control.get("status") != "passed":
            raise SecurityGateReportError("Every security control must be passed.")
        evidence = control.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise SecurityGateReportError("Every security control needs repository evidence.")
        for relative_path in evidence:
            if not isinstance(relative_path, str) or Path(relative_path).is_absolute():
                raise SecurityGateReportError("Evidence paths must be repository-relative.")
            resolved = (repository_root / relative_path).resolve()
            try:
                resolved.relative_to(repository_root.resolve())
            except ValueError as error:
                raise SecurityGateReportError("Evidence escapes the repository.") from error
            if not resolved.is_file():
                raise SecurityGateReportError(f"Missing security evidence: {relative_path}")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise SecurityGateReportError("Security findings must be a list.")
    open_blocking = [
        finding
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("status") == "open"
        and finding.get("severity") in BLOCKING_SEVERITIES
    ]
    if open_blocking or payload.get("openCriticalHighCount") != 0:
        raise SecurityGateReportError("The security gate has an open critical/high finding.")
    checksum = report_checksum(payload)
    if payload.get("contentChecksumSha256") != checksum:
        raise SecurityGateReportError("The security gate report checksum is invalid.")
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "report",
        nargs="?",
        default="ai_docs/quality/remote-manual-selection-security-gate-v1.json",
    )
    parser.add_argument("--print-checksum", action="store_true")
    arguments = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    report_path = (repository_root / arguments.report).resolve()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SecurityGateReportError("Security gate report must be a JSON object.")
    if arguments.print_checksum:
        print(report_checksum(payload))
        return 0
    checksum = validate_report(payload, repository_root=repository_root)
    print(f"Remote manual selection security gate passed: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
