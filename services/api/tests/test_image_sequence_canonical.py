from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_sequence_canonical import (
    ImageSequenceCanonicalService,
    parse_browser_sequence_manifest,
)
from game_predictor_api.domain.jobs import JobConflictError


class _Repository:
    def __init__(
        self,
        numbers: set[int],
        *,
        expected_layout_count: int | None = None,
    ) -> None:
        self.numbers = numbers
        self._expected_layout_count = expected_layout_count

    def canonical_numbers(self, _game_id):  # type: ignore[no-untyped-def]
        return set(self.numbers)

    def expected_layout_count(self, _game_id):  # type: ignore[no-untyped-def]
        return self._expected_layout_count


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


def test_preflight_rejects_an_invalid_seq_filename(tmp_path: Path) -> None:
    _touch(tmp_path, "seq_1-10.jpg")
    service = ImageSequenceCanonicalService(_Repository(set()))

    with pytest.raises(JobConflictError) as error:
        service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert error.value.code == "IMAGE_SEQUENCE_PREFLIGHT_RANGE_INVALID"


def test_preflight_reports_non_attested_folder(tmp_path: Path) -> None:
    _touch(tmp_path, "photo.jpg")
    service = ImageSequenceCanonicalService(_Repository(set()))

    result = service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert result.attested_file_count == 0
    assert "IMAGE_SEQUENCE_FILENAME_NOT_ATTESTED" in result.warnings


def test_manifest_preflight_uses_attested_logical_names_not_physical_names() -> None:
    manifest = parse_browser_sequence_manifest(
        {
            "schemaVersion": 1,
            "purpose": "layout_import",
            "orderingPolicy": "natural_relative_path_v1",
            "files": [
                {
                    "orderIndex": 0,
                    "relativePath": "1-18/seq_1-9.jpg",
                    "storedFileName": "00000001.jpg",
                    "sizeBytes": 3,
                    "checksumSha256": "a" * 64,
                },
                {
                    "orderIndex": 1,
                    "relativePath": "1-18/seq_10-18.jpg",
                    "storedFileName": "00000002.jpg",
                    "sizeBytes": 3,
                    "checksumSha256": "b" * 64,
                },
            ],
        },
        checksum_sha256="c" * 64,
    )
    service = ImageSequenceCanonicalService(_Repository(set(range(1, 10))))

    result = service.preflight(game_id=uuid4(), manifest=manifest)

    assert result.source_file_count == 2
    assert result.attested_file_count == 2
    assert result.new_sequence_count == 9
    assert result.reused_sequence_count == 9
    assert result.first_unresolved_sequence == 10


def test_manifest_rejects_mixed_attested_and_unattested_names() -> None:
    with pytest.raises(JobConflictError) as error:
        parse_browser_sequence_manifest(
            {
                "schemaVersion": 1,
                "purpose": "layout_import",
                "orderingPolicy": "natural_relative_path_v1",
                "files": [
                    {
                        "orderIndex": 0,
                        "relativePath": "seq_1-9.jpg",
                        "storedFileName": "00000001.jpg",
                        "sizeBytes": 3,
                        "checksumSha256": "a" * 64,
                    },
                    {
                        "orderIndex": 1,
                        "relativePath": "photo.jpg",
                        "storedFileName": "00000002.jpg",
                        "sizeBytes": 3,
                        "checksumSha256": "b" * 64,
                    },
                ],
            },
            checksum_sha256="c" * 64,
        )

    assert error.value.code == "IMAGE_SEQUENCE_MANIFEST_INVALID"


def test_preflight_accepts_a_bounded_final_sequence_page(tmp_path: Path) -> None:
    _touch(tmp_path, "seq_499996-500000.jpg")
    service = ImageSequenceCanonicalService(_Repository(set(), expected_layout_count=500_000))

    result = service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert result.attested_file_count == 1
    assert result.new_sequence_count == 5
    assert result.last_unresolved_sequence == 500_000


def test_preflight_rejects_a_sequence_page_beyond_the_game_bound(
    tmp_path: Path,
) -> None:
    _touch(tmp_path, "seq_499999-500007.jpg")
    service = ImageSequenceCanonicalService(_Repository(set(), expected_layout_count=500_000))

    with pytest.raises(JobConflictError) as error:
        service.preflight(game_id=uuid4(), source_directory=tmp_path)

    assert error.value.code == "IMAGE_SEQUENCE_PREFLIGHT_OUT_OF_BOUNDS"
    assert error.value.details == {
        "expectedLayoutCount": 500_000,
        "fileName": "seq_499999-500007.jpg",
        "rangeStart": 499_999,
        "rangeEnd": 500_007,
    }
