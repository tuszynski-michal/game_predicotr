"""Deterministic, streaming-friendly payout audit artifacts."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from game_predictor_worker.domain.contracts import PayoutEvaluation
from game_predictor_worker.payouts.contracts import AuditedPayout, PayoutSource

AUDIT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExpectedAuditPayout:
    sequence_number: int
    total_payout: int


@dataclass(frozen=True, slots=True)
class VerifiedPayoutAudit:
    record_count: int
    total_payout: int


class PayoutAuditError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JsonlPayoutAuditWriter:
    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()

    def write_batch(
        self,
        source: PayoutSource,
        *,
        algorithm_version: str,
        payouts: Sequence[AuditedPayout],
    ) -> str:
        if not payouts:
            raise ValueError("An audit batch must contain at least one payout.")
        first = payouts[0].layout.sequence_number
        last = payouts[-1].layout.sequence_number
        relative_path = (
            Path("payout-audits")
            / str(source.dataset_version_id)
            / str(source.rules_version_id)
            / algorithm_version
            / f"{first:012d}-{last:012d}.jsonl"
        )
        destination = (self._artifact_root / relative_path).resolve()
        if self._artifact_root not in destination.parents:
            raise ValueError("Audit path escaped the configured artifact root.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            _json_line(
                {
                    "algorithmVersion": algorithm_version,
                    "datasetVersionId": str(source.dataset_version_id),
                    "firstSequenceNumber": first,
                    "layoutCount": len(payouts),
                    "lastSequenceNumber": last,
                    "recordType": "header",
                    "rulesVersionId": str(source.rules_version_id),
                    "schemaVersion": AUDIT_SCHEMA_VERSION,
                }
            ),
            *(
                _json_line(
                    {
                        "audit": _serialize_evaluation(item.evaluation),
                        "recordType": "layoutPayout",
                        "sequenceNumber": item.layout.sequence_number,
                    }
                )
                for item in payouts
            ),
        ]
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.writelines(lines)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
        return relative_path.as_posix()


def verify_payout_audit_batch(
    artifact_root: Path,
    audit_path: str,
    source: PayoutSource,
    *,
    algorithm_version: str,
    expected_payouts: Sequence[ExpectedAuditPayout],
) -> VerifiedPayoutAudit:
    if not expected_payouts:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_EXPECTATION_EMPTY",
            "Audit verification requires at least one expected payout.",
        )
    root = artifact_root.resolve()
    candidate = (root / Path(audit_path)).resolve()
    if root not in candidate.parents:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_PATH_INVALID",
            "The payout audit path escapes the artifact root.",
        )
    try:
        with candidate.open("r", encoding="utf-8") as audit_file:
            header = _read_json_object(audit_file.readline())
            _verify_header(
                header,
                source,
                algorithm_version=algorithm_version,
                expected_payouts=expected_payouts,
            )
            total_payout = 0
            for expected in expected_payouts:
                record = _read_json_object(audit_file.readline())
                total_payout += _verify_record(record, expected)
            if audit_file.readline():
                raise PayoutAuditError(
                    "PAYOUT_AUDIT_RECORD_COUNT_MISMATCH",
                    "The payout audit contains unexpected extra records.",
                )
    except PayoutAuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_UNREADABLE",
            "The payout audit cannot be read as valid UTF-8 JSONL.",
        ) from error
    return VerifiedPayoutAudit(
        record_count=len(expected_payouts),
        total_payout=total_payout,
    )


def _json_line(value: Mapping[str, object]) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _serialize_evaluation(evaluation: PayoutEvaluation) -> dict[str, object]:
    return {
        "matches": [
            {
                "interpretation": [
                    {
                        "asSymbolMobileCode": interpretation.as_symbol_mobile_code,
                        "cellIndex": interpretation.cell_index,
                    }
                    for interpretation in match.interpretation
                ],
                "jokerCells": list(match.joker_cells),
                "matchedCells": list(match.matched_cells),
                "matchedLength": match.matched_length,
                "paylineId": match.payline_id,
                "payoutCredits": match.payout_credits,
                "startColumn": match.start_column,
                "symbolMobileCode": match.symbol_mobile_code,
            }
            for match in evaluation.matches
        ],
        "totalPayout": evaluation.total_payout,
    }


def _read_json_object(line: str) -> Mapping[str, Any]:
    if not line:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_RECORD_COUNT_MISMATCH",
            "The payout audit ended before all expected records.",
        )
    value = json.loads(line)
    if not isinstance(value, dict):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "Every payout audit line must be a JSON object.",
        )
    return value


def _verify_header(
    header: Mapping[str, Any],
    source: PayoutSource,
    *,
    algorithm_version: str,
    expected_payouts: Sequence[ExpectedAuditPayout],
) -> None:
    expected_header: dict[str, object] = {
        "algorithmVersion": algorithm_version,
        "datasetVersionId": str(source.dataset_version_id),
        "firstSequenceNumber": expected_payouts[0].sequence_number,
        "layoutCount": len(expected_payouts),
        "lastSequenceNumber": expected_payouts[-1].sequence_number,
        "recordType": "header",
        "rulesVersionId": str(source.rules_version_id),
        "schemaVersion": AUDIT_SCHEMA_VERSION,
    }
    if any(header.get(key) != value for key, value in expected_header.items()):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_HEADER_MISMATCH",
            "The payout audit header does not match the selected versions and range.",
        )


def _verify_record(
    record: Mapping[str, Any],
    expected: ExpectedAuditPayout,
) -> int:
    if (
        record.get("recordType") != "layoutPayout"
        or record.get("sequenceNumber") != expected.sequence_number
    ):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SEQUENCE_MISMATCH",
            "The payout audit records are not in the expected sequence.",
        )
    audit = record.get("audit")
    if not isinstance(audit, dict):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "A payout audit record requires an audit object.",
        )
    total_payout = _require_nonnegative_int(audit.get("totalPayout"))
    if total_payout != expected.total_payout:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_TOTAL_MISMATCH",
            "The payout audit total does not match the persisted payout.",
        )
    matches = audit.get("matches")
    if not isinstance(matches, list):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "A payout audit record requires a matches array.",
        )
    reconstructed_total = sum(_verify_match(match) for match in matches)
    if reconstructed_total != total_payout:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_RECONSTRUCTION_MISMATCH",
            "The payout audit matches do not reconstruct totalPayout.",
        )
    return total_payout


def _verify_match(value: object) -> int:
    if not isinstance(value, dict):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "Every payout match must be an object.",
        )
    payout = _require_nonnegative_int(value.get("payoutCredits"))
    matched_cells = _require_int_list(value.get("matchedCells"))
    joker_cells = _require_int_list(value.get("jokerCells"))
    if not set(joker_cells).issubset(matched_cells):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_INTERPRETATION_INVALID",
            "Every joker cell must belong to the matched cells.",
        )
    interpretation = value.get("interpretation")
    if not isinstance(interpretation, list):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "Every payout match requires an interpretation array.",
        )
    interpretation_cells: list[int] = []
    for item in interpretation:
        if not isinstance(item, dict):
            raise PayoutAuditError(
                "PAYOUT_AUDIT_SCHEMA_INVALID",
                "Every joker interpretation must be an object.",
            )
        interpretation_cells.append(_require_nonnegative_int(item.get("cellIndex")))
        _require_nonnegative_int(item.get("asSymbolMobileCode"))
    if interpretation_cells != joker_cells:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_INTERPRETATION_INVALID",
            "Joker interpretations must exactly follow jokerCells.",
        )
    _require_nonnegative_int(value.get("symbolMobileCode"))
    _require_nonnegative_int(value.get("startColumn"))
    matched_length = _require_nonnegative_int(value.get("matchedLength"))
    if matched_length != len(matched_cells):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "matchedLength must equal the number of matchedCells.",
        )
    if not isinstance(value.get("paylineId"), str):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "Every payout match requires a paylineId.",
        )
    return payout


def _require_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "The payout audit contains an invalid non-negative integer.",
        )
    return value


def _require_int_list(value: object) -> list[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise PayoutAuditError(
            "PAYOUT_AUDIT_SCHEMA_INVALID",
            "The payout audit contains an invalid integer array.",
        )
    return value
