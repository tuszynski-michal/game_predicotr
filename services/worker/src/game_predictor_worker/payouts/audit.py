"""Deterministic, streaming-friendly payout audit artifacts."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

from game_predictor_worker.domain.contracts import PayoutEvaluation
from game_predictor_worker.payouts.contracts import AuditedPayout, PayoutSource

AUDIT_SCHEMA_VERSION = 1


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
