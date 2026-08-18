from pathlib import Path
from uuid import uuid4

import pytest

from game_predictor_api.domain.image_sequence_canonical import (
    ImageSequenceCanonicalService,
)
from game_predictor_api.domain.jobs import JobConflictError


class _Repository:
    def __init__(self, numbers: set[int]) -> None:
        self.numbers = numbers

    def canonical_numbers(self, _game_id):  # type: ignore[no-untyped-def]
        return set(self.numbers)


def _touch(root: Path, name: str) -> None:
    (root / name).write_bytes(b"jpeg")


def test_preflight_counts_reused_and_partial_seq_ranges(tmp_path: Path) -> None:
    _touch(tmp_path, "seq_1-9.jpg")
    _touch(tmp_path, "seq_10-18.jpg")
    service = ImageSequenceCanonicalService(_Repository({1, 2, 3, 10, 11}))

    result = service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert result.new_sequence_count == 13
    assert result.reused_sequence_count == 5
    assert result.skipped_source_count == 0
    assert result.partial_source_count == 2
    assert result.first_unresolved_sequence == 4
    assert result.last_unresolved_sequence == 18


def test_preflight_skips_fully_canonical_source(tmp_path: Path) -> None:
    _touch(tmp_path, "seq_1-9.jpeg")
    service = ImageSequenceCanonicalService(_Repository(set(range(1, 10))))

    result = service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert result.new_sequence_count == 0
    assert result.reused_sequence_count == 9
    assert result.skipped_source_count == 1
    assert result.first_unresolved_sequence is None


def test_preflight_rejects_overlapping_ranges(tmp_path: Path) -> None:
    _touch(tmp_path, "seq_1-9.jpg")
    _touch(tmp_path, "seq_9-17.jpg")
    service = ImageSequenceCanonicalService(_Repository(set()))

    with pytest.raises(JobConflictError) as error:
        service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert error.value.code == "IMAGE_SEQUENCE_PREFLIGHT_RANGE_OVERLAP"


def test_preflight_reports_non_attested_folder(tmp_path: Path) -> None:
    _touch(tmp_path, "photo.jpg")
    service = ImageSequenceCanonicalService(_Repository(set()))

    result = service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert result.attested_file_count == 0
    assert "IMAGE_SEQUENCE_FILENAME_NOT_ATTESTED" in result.warnings
