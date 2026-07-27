from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_worker.domain.contracts import (
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.payouts.audit import (
    ExpectedAuditPayout,
    JsonlPayoutAuditWriter,
    PayoutAuditError,
    verify_payout_audit_batch,
)
from game_predictor_worker.payouts.contracts import (
    AuditedPayout,
    CalculatedLayoutPayout,
    PayoutLayout,
    PayoutSource,
)
from game_predictor_worker.payouts.handler import PayoutBatchHandler

GAME_ID = UUID("11111111-1111-4111-8111-111111111111")
DATASET_ID = UUID("22222222-2222-4222-8222-222222222222")
RULES_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 7, 27, 20, tzinfo=UTC)
GOLDEN_PATH = (
    Path(__file__).parents[3]
    / "packages"
    / "domain-fixtures"
    / "payout-golden-cases.json"
)


class FakePayoutStore:
    def __init__(
        self,
        source: PayoutSource | None,
        layouts: tuple[PayoutLayout, ...],
    ) -> None:
        self.source = source
        self.layouts = layouts
        self.queries: list[tuple[int, int]] = []
        self.records: dict[tuple[UUID, UUID, int, str], CalculatedLayoutPayout] = {}

    def load_source(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
    ) -> PayoutSource | None:
        assert dataset_version_id == DATASET_ID
        assert rules_version_id == RULES_ID
        return self.source

    def list_layout_batch(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[PayoutLayout, ...]:
        assert dataset_version_id == DATASET_ID
        self.queries.append((after_sequence_number, limit))
        return tuple(
            layout for layout in self.layouts if layout.sequence_number > after_sequence_number
        )[:limit]

    def upsert_payouts(
        self,
        payouts: tuple[CalculatedLayoutPayout, ...],
    ) -> None:
        for payout in payouts:
            key = (
                payout.dataset_version_id,
                payout.rules_version_id,
                payout.sequence_number,
                payout.algorithm_version,
            )
            self.records[key] = payout


class FakeAuditWriter:
    def __init__(self) -> None:
        self.batches: list[tuple[int, ...]] = []

    def write_batch(
        self,
        source: PayoutSource,
        *,
        algorithm_version: str,
        payouts: tuple[AuditedPayout, ...],
    ) -> str:
        assert source.dataset_version_id == DATASET_ID
        assert algorithm_version == "payout-v2"
        numbers = tuple(item.layout.sequence_number for item in payouts)
        self.batches.append(numbers)
        return f"payout-audits/{numbers[0]}-{numbers[-1]}.jsonl"


class FakeContext:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)


class CrashingContext:
    def checkpoint(self, **_values: object) -> None:
        raise RuntimeError("simulated process crash after payout upsert")


def _source(**changes: object) -> PayoutSource:
    source = PayoutSource(
        dataset_version_id=DATASET_ID,
        rules_version_id=RULES_ID,
        game_id=GAME_ID,
        rules_game_id=GAME_ID,
        dataset_status=DatasetVersionStatus.PUBLISHED,
        rules_status=RulesVersionStatus.PUBLISHED,
        dataset_rows=2,
        dataset_columns=3,
        layout_count=3,
        game=GameConfig(
            id=str(GAME_ID),
            code="game",
            name="Game",
            rows=2,
            columns=3,
            spin_cost=10,
            signature_cell_width=2,
            symbols=(
                SymbolDefinition(1, "a", "A", False, 0),
                SymbolDefinition(2, "b", "B", False, 1),
                SymbolDefinition(9, "wild", "Wild", True, 2),
            ),
        ),
        paylines=(PaylineDefinition("top", (0, 0, 0)),),
        payout_symbols=(
            PayoutSymbolDefinition(1, 2),
            PayoutSymbolDefinition(2, 2),
        ),
        payout_rules=(
            PayoutRuleDefinition(1, 2, 10),
            PayoutRuleDefinition(1, 3, 20),
            PayoutRuleDefinition(2, 2, 15),
            PayoutRuleDefinition(2, 3, 30),
        ),
    )
    return replace(source, **changes)


def _layouts() -> tuple[PayoutLayout, ...]:
    return (
        PayoutLayout(1, (1, 1, 1, 2, 2, 2)),
        PayoutLayout(2, (2, 9, 2, 1, 1, 1)),
        PayoutLayout(3, (9, 9, 9, 1, 2, 1)),
    )


def _job():
    return create_job(
        JobType.PAYOUT,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 1,
            "dataset_version_id": str(DATASET_ID),
            "rules_version_id": str(RULES_ID),
            "algorithm_version": "payout-v2",
        },
        created_at=NOW,
    )


def test_handler_calculates_bounded_batches_and_checkpoints_safe_writes() -> None:
    store = FakePayoutStore(_source(), _layouts())
    audits = FakeAuditWriter()
    context = FakeContext()
    handler = PayoutBatchHandler(store, audits, batch_size=2, clock=lambda: NOW)

    handler(context, _job())  # type: ignore[arg-type]

    assert store.queries == [(0, 2), (2, 2)]
    assert audits.batches == [(1, 2), (3,)]
    assert [
        store.records[(DATASET_ID, RULES_ID, sequence, "payout-v2")].total_payout
        for sequence in (1, 2, 3)
    ] == [20, 30, 0]
    assert [checkpoint["current"] for checkpoint in context.checkpoints] == [2, 3]
    assert context.checkpoints[-1]["checkpoint_payload"] == {
        "schema_version": 1,
        "workflow": "payout",
        "dataset_version_id": str(DATASET_ID),
        "rules_version_id": str(RULES_ID),
        "algorithm_version": "payout-v2",
        "last_sequence_number": 3,
        "processed_count": 3,
    }


def test_handler_resumes_after_checkpoint_and_upsert_is_idempotent() -> None:
    store = FakePayoutStore(_source(), _layouts())
    audits = FakeAuditWriter()
    handler = PayoutBatchHandler(store, audits, batch_size=2, clock=lambda: NOW)
    first_context = FakeContext()
    handler(first_context, _job())  # type: ignore[arg-type]

    resumed_job = replace(
        _job(),
        progress_current=2,
        progress_total=3,
        success_count=2,
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "payout",
            "dataset_version_id": str(DATASET_ID),
            "rules_version_id": str(RULES_ID),
            "algorithm_version": "payout-v2",
            "last_sequence_number": 2,
            "processed_count": 2,
        },
    )
    resumed_context = FakeContext()
    handler(resumed_context, resumed_job)  # type: ignore[arg-type]

    assert store.queries[-1] == (2, 2)
    assert len(store.records) == 3
    assert resumed_context.checkpoints[0]["current"] == 3


def test_crash_after_upsert_before_checkpoint_repeats_batch_without_duplicates() -> None:
    store = FakePayoutStore(_source(), _layouts())
    audits = FakeAuditWriter()
    handler = PayoutBatchHandler(store, audits, batch_size=2, clock=lambda: NOW)

    with pytest.raises(RuntimeError, match="simulated process crash"):
        handler(CrashingContext(), _job())  # type: ignore[arg-type]

    assert len(store.records) == 2
    retry_context = FakeContext()
    handler(retry_context, _job())  # type: ignore[arg-type]

    assert len(store.records) == 3
    assert audits.batches == [(1, 2), (1, 2), (3,)]
    assert retry_context.checkpoints[-1]["current"] == 3


def test_handler_persists_every_m1_golden_total() -> None:
    fixture = cast(
        Mapping[str, Any],
        json.loads(GOLDEN_PATH.read_text(encoding="utf-8")),
    )
    game_data = fixture["game"]
    game = GameConfig(
        id=game_data["id"],
        code=game_data["code"],
        name=game_data["name"],
        rows=game_data["rows"],
        columns=game_data["columns"],
        spin_cost=game_data["spinCost"],
        signature_cell_width=game_data["signatureCellWidth"],
        symbols=tuple(
            SymbolDefinition(
                symbol["mobileCode"],
                symbol["code"],
                symbol["name"],
                symbol["isWildcard"],
                symbol["displayOrder"],
            )
            for symbol in fixture["game"]["symbols"]
        ),
    )
    paylines = {
        payline["id"]: PaylineDefinition(
            payline["id"],
            tuple(payline["rowPath"]),
        )
        for payline in fixture["paylines"]
    }
    payout_symbols = tuple(
        PayoutSymbolDefinition(
            value["symbolMobileCode"],
            value["minimumMatchLength"],
        )
        for value in fixture["payoutSymbols"]
    )
    payout_rules = tuple(
        PayoutRuleDefinition(
            value["symbolMobileCode"],
            value["matchLength"],
            value["payoutCredits"],
        )
        for value in fixture["payoutRules"]
    )

    for case in fixture["cases"]:
        source = PayoutSource(
            dataset_version_id=DATASET_ID,
            rules_version_id=RULES_ID,
            game_id=GAME_ID,
            rules_game_id=GAME_ID,
            dataset_status=DatasetVersionStatus.PUBLISHED,
            rules_status=RulesVersionStatus.PUBLISHED,
            dataset_rows=game.rows,
            dataset_columns=game.columns,
            layout_count=1,
            game=game,
            paylines=tuple(paylines[value] for value in case["paylineIds"]),
            payout_symbols=payout_symbols,
            payout_rules=payout_rules,
        )
        layout = PayoutLayout(
            1,
            tuple(cell for row in case["rows"] for cell in row),
        )
        store = FakePayoutStore(source, (layout,))
        handler = PayoutBatchHandler(
            store,
            FakeAuditWriter(),
            clock=lambda: NOW,
        )

        handler(FakeContext(), _job())  # type: ignore[arg-type]

        persisted = store.records[
            (DATASET_ID, RULES_ID, 1, "payout-v2")
        ]
        assert persisted.total_payout == case["expected"]["totalPayout"], case[
            "id"
        ]


@pytest.mark.parametrize(
    ("job", "source", "code"),
    [
        (
            create_job(
                JobType.VALIDATE,
                game_id=GAME_ID,
                input_payload={
                    "schema_version": 1,
                    "dataset_version_id": str(DATASET_ID),
                },
                created_at=NOW,
            ),
            _source(),
            "INVALID_PAYOUT_JOB_TYPE",
        ),
        (
            replace(
                _job(),
                input_payload={
                    **_job().input_payload,
                    "algorithm_version": "payout-v1",
                },
            ),
            _source(),
            "UNSUPPORTED_PAYOUT_ALGORITHM",
        ),
        (
            _job(),
            _source(dataset_status=DatasetVersionStatus.STAGING),
            "PAYOUT_DATASET_NOT_PUBLISHED",
        ),
        (
            _job(),
            _source(rules_status=RulesVersionStatus.DRAFT),
            "PAYOUT_RULES_NOT_PUBLISHED",
        ),
        (
            _job(),
            _source(dataset_columns=4),
            "PAYOUT_DIMENSIONS_MISMATCH",
        ),
        (
            _job(),
            _source(
                rules_game_id=UUID(
                    "44444444-4444-4444-8444-444444444444"
                )
            ),
            "PAYOUT_GAME_MISMATCH",
        ),
    ],
)
def test_handler_rejects_invalid_job_or_source(job, source, code: str) -> None:
    handler = PayoutBatchHandler(
        FakePayoutStore(source, _layouts()),
        FakeAuditWriter(),
        clock=lambda: NOW,
    )

    with pytest.raises(JobHandlerError) as captured:
        handler(FakeContext(), job)  # type: ignore[arg-type]

    assert captured.value.code == code


def test_handler_rejects_sequence_gap_and_mismatched_checkpoint() -> None:
    gap_handler = PayoutBatchHandler(
        FakePayoutStore(_source(), (_layouts()[0], _layouts()[2])),
        FakeAuditWriter(),
        clock=lambda: NOW,
    )
    with pytest.raises(JobHandlerError) as gap:
        gap_handler(FakeContext(), _job())  # type: ignore[arg-type]
    assert gap.value.code == "PAYOUT_SEQUENCE_GAP"

    mismatch = replace(
        _job(),
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "payout",
            "dataset_version_id": str(UUID(int=0)),
            "rules_version_id": str(RULES_ID),
            "algorithm_version": "payout-v2",
            "last_sequence_number": 1,
            "processed_count": 1,
        },
    )
    with pytest.raises(JobHandlerError) as checkpoint:
        gap_handler(FakeContext(), mismatch)  # type: ignore[arg-type]
    assert checkpoint.value.code == "PAYOUT_CHECKPOINT_MISMATCH"


def test_jsonl_audit_is_structured_deterministic_and_atomically_replaced(
    tmp_path: Path,
) -> None:
    source = _source(layout_count=1)
    layout = _layouts()[1]
    from game_predictor_worker.domain.payout import evaluate_payout

    evaluation = evaluate_payout(
        source.game,
        layout.cells,
        source.paylines,
        source.payout_symbols,
        source.payout_rules,
    )
    writer = JsonlPayoutAuditWriter(tmp_path)

    first = writer.write_batch(
        source,
        algorithm_version="payout-v2",
        payouts=(AuditedPayout(layout, evaluation),),
    )
    first_bytes = (tmp_path / first).read_bytes()
    second = writer.write_batch(
        source,
        algorithm_version="payout-v2",
        payouts=(AuditedPayout(layout, evaluation),),
    )

    assert first == second
    assert (tmp_path / second).read_bytes() == first_bytes
    lines = [
        json.loads(line) for line in (tmp_path / second).read_text(encoding="utf-8").splitlines()
    ]
    assert lines[0]["recordType"] == "header"
    assert lines[1]["sequenceNumber"] == 2
    assert lines[1]["audit"]["totalPayout"] == 30
    assert lines[1]["audit"]["matches"][0]["jokerCells"] == [1]
    verified = verify_payout_audit_batch(
        tmp_path,
        second,
        source,
        algorithm_version="payout-v2",
        expected_payouts=(ExpectedAuditPayout(2, 30),),
    )
    assert verified.record_count == 1
    assert verified.total_payout == 30


def test_audit_verifier_rejects_wrong_version_total_and_interpretation(
    tmp_path: Path,
) -> None:
    source = _source(layout_count=1)
    layout = _layouts()[1]
    from game_predictor_worker.domain.payout import evaluate_payout

    evaluation = evaluate_payout(
        source.game,
        layout.cells,
        source.paylines,
        source.payout_symbols,
        source.payout_rules,
    )
    writer = JsonlPayoutAuditWriter(tmp_path)
    audit_path = writer.write_batch(
        source,
        algorithm_version="payout-v2",
        payouts=(AuditedPayout(layout, evaluation),),
    )

    with pytest.raises(PayoutAuditError) as wrong_version:
        verify_payout_audit_batch(
            tmp_path,
            audit_path,
            source,
            algorithm_version="payout-v3",
            expected_payouts=(ExpectedAuditPayout(2, 30),),
        )
    assert wrong_version.value.code == "PAYOUT_AUDIT_HEADER_MISMATCH"

    path = tmp_path / audit_path
    lines = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    lines[1]["audit"]["totalPayout"] = 31
    path.write_text(
        "".join(
            json.dumps(line, separators=(",", ":"), sort_keys=True) + "\n"
            for line in lines
        ),
        encoding="utf-8",
    )
    with pytest.raises(PayoutAuditError) as wrong_total:
        verify_payout_audit_batch(
            tmp_path,
            audit_path,
            source,
            algorithm_version="payout-v2",
            expected_payouts=(ExpectedAuditPayout(2, 30),),
        )
    assert wrong_total.value.code == "PAYOUT_AUDIT_TOTAL_MISMATCH"

    lines[1]["audit"]["totalPayout"] = 30
    lines[1]["audit"]["matches"][0]["interpretation"] = []
    path.write_text(
        "".join(
            json.dumps(line, separators=(",", ":"), sort_keys=True) + "\n"
            for line in lines
        ),
        encoding="utf-8",
    )
    with pytest.raises(PayoutAuditError) as interpretation:
        verify_payout_audit_batch(
            tmp_path,
            audit_path,
            source,
            algorithm_version="payout-v2",
            expected_payouts=(ExpectedAuditPayout(2, 30),),
        )
    assert interpretation.value.code == "PAYOUT_AUDIT_INTERPRETATION_INVALID"
