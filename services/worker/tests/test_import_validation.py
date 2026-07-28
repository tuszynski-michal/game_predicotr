from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_worker.imports.contracts import (
    LayoutImportNormalizationSource,
    NormalizedLayoutImportRow,
    RawLayoutImportRow,
)
from game_predictor_worker.imports.normalization import normalize_layout_import_row
from game_predictor_worker.imports.validation_handler import (
    LayoutImportValidationHandler,
)

GAME_ID = UUID("11111111-1111-4111-8111-111111111111")
IMPORT_JOB_ID = UUID("22222222-2222-4222-8222-222222222222")
RULES_VERSION_ID = UUID("33333333-3333-4333-8333-333333333333")


def _source(row_count: int = 4) -> LayoutImportNormalizationSource:
    return LayoutImportNormalizationSource(
        import_job_id=IMPORT_JOB_ID,
        rules_version_id=RULES_VERSION_ID,
        rows=2,
        columns=2,
        signature_cell_width=2,
        allowed_mobile_codes=frozenset({1, 12}),
        row_count=row_count,
    )


def _job() -> Job:
    return create_job(
        JobType.VALIDATE,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 1,
            "validation_kind": "layout_import",
            "import_job_id": str(IMPORT_JOB_ID),
            "rules_version_id": str(RULES_VERSION_ID),
        },
    )


class FakeStore:
    def __init__(self) -> None:
        self.source = _source()
        self.raw_rows = (
            RawLayoutImportRow(1, 1, (1, 12, 1, 12), None, None),
            RawLayoutImportRow(2, 2, (1, 12, 1), None, None),
            RawLayoutImportRow(4, 3, (1, 99, 1, 12), None, None),
            RawLayoutImportRow(
                5,
                None,
                None,
                "import_record_invalid",
                "Record is invalid.",
            ),
        )
        self.rows: dict[int, NormalizedLayoutImportRow] = {}
        self.upsert_calls: list[tuple[int, ...]] = []

    def load_normalization_source(self, **_values: object) -> LayoutImportNormalizationSource:
        return self.source

    def fetch_raw_rows(
        self,
        _import_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
    ) -> tuple[RawLayoutImportRow, ...]:
        return tuple(row for row in self.raw_rows if row.line_number > after_line_number)[:limit]

    def upsert_normalized_rows(
        self,
        _validation_job_id: UUID,
        _source: LayoutImportNormalizationSource,
        rows: tuple[NormalizedLayoutImportRow, ...],
    ) -> None:
        self.upsert_calls.append(tuple(row.line_number for row in rows))
        self.rows.update({row.line_number: row for row in rows})


class FakeContext:
    def __init__(self, *, fail_after_first: bool = False) -> None:
        self.checkpoints: list[dict[str, object]] = []
        self._fail_after_first = fail_after_first

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)
        if self._fail_after_first and len(self.checkpoints) == 1:
            raise RuntimeError("controlled checkpoint failure")


def _resumed_job(job: Job, checkpoint: dict[str, object]) -> Job:
    payload = checkpoint["checkpoint_payload"]
    assert isinstance(payload, dict)
    return replace(
        job,
        checkpoint_payload=payload,
        stage=str(checkpoint["stage"]),
        progress_current=int(checkpoint["current"]),  # type: ignore[arg-type]
        progress_total=int(checkpoint["total"]),  # type: ignore[arg-type]
        success_count=int(checkpoint["success_count"]),  # type: ignore[arg-type]
        failure_count=int(checkpoint["failure_count"]),  # type: ignore[arg-type]
        review_count=0,
    )


def test_normalization_validates_dimensions_alphabet_and_signature() -> None:
    source = _source()
    valid = normalize_layout_import_row(
        RawLayoutImportRow(1, 7, (1, 12, 1, 12), None, None),
        source,
    )
    wrong_size = normalize_layout_import_row(
        RawLayoutImportRow(2, 8, (1, 12, 1), None, None),
        source,
    )
    foreign = normalize_layout_import_row(
        RawLayoutImportRow(3, 9, (1, 99, 1, 12), None, None),
        source,
    )

    assert valid.signature == "01120112"
    assert valid.is_success is True
    assert wrong_size.error_code == "import_cell_count_mismatch"
    assert foreign.error_code == "import_symbol_not_in_rules"
    assert foreign.sequence_number == 9
    assert foreign.cells == (1, 99, 1, 12)


def test_validation_handler_isolates_errors_and_finishes_bounded_batches() -> None:
    store = FakeStore()
    context = FakeContext()

    LayoutImportValidationHandler(store, batch_size=2)(
        context,  # type: ignore[arg-type]
        _job(),
    )

    assert store.upsert_calls == [(1, 2), (4, 5)]
    assert store.rows[1].signature == "01120112"
    assert store.rows[2].error_code == "import_cell_count_mismatch"
    assert store.rows[4].error_code == "import_symbol_not_in_rules"
    assert store.rows[5].error_code == "import_record_invalid"
    assert context.checkpoints[-1]["stage"] == "validated_import_rows"
    assert context.checkpoints[-1]["current"] == 4
    assert context.checkpoints[-1]["success_count"] == 1
    assert context.checkpoints[-1]["failure_count"] == 3


def test_validation_retry_replays_upsert_without_duplicate_rows() -> None:
    store = FakeStore()
    job = _job()
    interrupted = FakeContext(fail_after_first=True)

    with pytest.raises(RuntimeError, match="controlled checkpoint failure"):
        LayoutImportValidationHandler(store, batch_size=2)(
            interrupted,  # type: ignore[arg-type]
            job,
        )
    assert set(store.rows) == {1, 2}

    retry = FakeContext()
    LayoutImportValidationHandler(store, batch_size=2)(
        retry,  # type: ignore[arg-type]
        job,
    )
    assert set(store.rows) == {1, 2, 4, 5}
    assert store.upsert_calls[:2] == [(1, 2), (1, 2)]

    durable = FakeContext()
    first_handler = LayoutImportValidationHandler(FakeStore(), batch_size=2)
    with pytest.raises(RuntimeError):
        first_handler(FakeContext(fail_after_first=True), _job())  # type: ignore[arg-type]

    checkpoint = retry.checkpoints[0]
    resumed_store = FakeStore()
    resumed_store.rows = {1: store.rows[1], 2: store.rows[2]}
    LayoutImportValidationHandler(resumed_store, batch_size=2)(
        durable,  # type: ignore[arg-type]
        _resumed_job(job, checkpoint),
    )
    assert durable.checkpoints[-1]["stage"] == "validated_import_rows"
