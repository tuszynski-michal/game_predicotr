from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from game_predictor_api.application import layout_imports
from game_predictor_api.application.layout_imports import (
    LayoutImportSourceInspector,
)
from game_predictor_api.domain.jobs import JobError, JobNotFoundError
from game_predictor_worker.imports import ImportFileFormat


def _write_csv(path: Path, *, sequence_number: int = 1) -> bytes:
    content = (f'schema_version,sequence_number,cells\n1,{sequence_number},"[1,2,3]"\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _write_jsonl(path: Path) -> bytes:
    content = b'{"schemaVersion":1,"sequenceNumber":1,"cells":[1,2,3]}\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _inspector(import_root: Path, *, max_bytes: int = 1024 * 1024) -> LayoutImportSourceInspector:
    return LayoutImportSourceInspector(import_root, max_bytes=max_bytes)


def test_inspector_attests_canonical_csv_metadata(tmp_path: Path) -> None:
    import_root = tmp_path / "imports"
    content = _write_csv(import_root / "game-1" / "layouts.csv")

    source = _inspector(import_root).inspect(
        "game-1/layouts.csv",
        contract_version=1,
    )

    assert source.relative_path == "game-1/layouts.csv"
    assert source.file_format is ImportFileFormat.CSV
    assert source.contract_version == 1
    assert source.size_bytes == len(content)
    assert source.checksum == hashlib.sha256(content).hexdigest()


def test_inspector_attests_jsonl_and_skips_leading_blank_lines(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = b'\n\n{"schemaVersion":1,"sequenceNumber":1,"cells":[1]}\n'
    import_root.mkdir()
    (import_root / "layouts.jsonl").write_bytes(content)

    source = _inspector(import_root).inspect(
        "layouts.jsonl",
        contract_version=1,
    )

    assert source.file_format is ImportFileFormat.JSONL
    assert source.checksum == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "source_path",
    [
        "../outside.csv",
        "/absolute.csv",
        "C:/absolute.csv",
        r"nested\layouts.csv",
        "./layouts.csv",
        "nested/../layouts.csv",
        " layouts.csv",
        "layouts.csv ",
        "",
    ],
)
def test_inspector_rejects_unsafe_paths(
    tmp_path: Path,
    source_path: str,
) -> None:
    import_root = tmp_path / "imports"
    import_root.mkdir()

    with pytest.raises(JobError) as captured:
        _inspector(import_root).inspect(source_path, contract_version=1)

    assert captured.value.code == "INVALID_IMPORT_SOURCE_PATH"


def test_inspector_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    import_root = tmp_path / "imports"
    import_root.mkdir()
    outside = tmp_path / "outside.csv"
    _write_csv(outside)
    link = import_root / "link.csv"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("The current Windows account cannot create symbolic links.")

    with pytest.raises(JobError) as captured:
        _inspector(import_root).inspect("link.csv", contract_version=1)

    assert captured.value.code == "INVALID_IMPORT_SOURCE_PATH"


def test_inspector_rejects_missing_directory_and_non_file_sources(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    with pytest.raises(JobError) as missing_root_error:
        _inspector(missing_root).inspect("layouts.csv", contract_version=1)
    assert missing_root_error.value.code == "IMPORT_ROOT_UNAVAILABLE"

    import_root = tmp_path / "imports"
    (import_root / "directory.csv").mkdir(parents=True)
    with pytest.raises(JobError) as directory_error:
        _inspector(import_root).inspect("directory.csv", contract_version=1)
    assert directory_error.value.code == "IMPORT_SOURCE_NOT_FILE"

    with pytest.raises(JobNotFoundError) as missing_file_error:
        _inspector(import_root).inspect("missing.csv", contract_version=1)
    assert missing_file_error.value.code == "IMPORT_SOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    ("name", "content", "max_bytes", "expected_code"),
    [
        ("layouts.txt", b"data", 1024, "IMPORT_SOURCE_FORMAT_UNSUPPORTED"),
        ("layouts.csv", b"", 1024, "IMPORT_SOURCE_EMPTY"),
        ("layouts.csv", b"12345", 4, "IMPORT_SOURCE_TOO_LARGE"),
        (
            "layouts.csv",
            b'wrong,header\n1,1,"[1]"\n',
            1024,
            "import_header_invalid",
        ),
        (
            "layouts.jsonl",
            b'{"schemaVersion":2,"sequenceNumber":1,"cells":[1]}\n',
            1024,
            "import_schema_version_unsupported",
        ),
        (
            "layouts.jsonl",
            b"\n\n",
            1024,
            "IMPORT_SOURCE_NO_RECORDS",
        ),
    ],
)
def test_inspector_rejects_invalid_source_boundaries(
    tmp_path: Path,
    name: str,
    content: bytes,
    max_bytes: int,
    expected_code: str,
) -> None:
    import_root = tmp_path / "imports"
    import_root.mkdir()
    (import_root / name).write_bytes(content)

    with pytest.raises(JobError) as captured:
        _inspector(import_root, max_bytes=max_bytes).inspect(
            name,
            contract_version=1,
        )

    assert captured.value.code == expected_code


def test_inspector_rejects_unsupported_contract_before_reading_file(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    import_root.mkdir()

    with pytest.raises(JobError) as captured:
        _inspector(import_root).inspect("missing.csv", contract_version=2)

    assert captured.value.code == "UNSUPPORTED_LAYOUT_IMPORT_CONTRACT_VERSION"


def test_inspector_reads_checksum_in_bounded_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_root = tmp_path / "imports"
    _write_jsonl(import_root / "layouts.jsonl")
    observed_sizes: list[int] = []
    original_open = Path.open

    class TrackingReader:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self._wrapped.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def read(self, size: int = -1):
            observed_sizes.append(size)
            return self._wrapped.read(size)

    def tracked_open(path: Path, *args, **kwargs):
        return TrackingReader(original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", tracked_open)

    _inspector(import_root).inspect("layouts.jsonl", contract_version=1)

    assert observed_sizes
    assert set(observed_sizes) == {1024 * 1024}


def test_inspector_rejects_file_changed_during_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_root = tmp_path / "imports"
    source_path = import_root / "layouts.jsonl"
    _write_jsonl(source_path)
    original_sha256_stream = layout_imports._sha256_stream

    def changing_sha256_stream(source) -> str:
        result = original_sha256_stream(source)
        current = source_path.stat()
        os.utime(
            source_path,
            ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000_000),
        )
        return result

    monkeypatch.setattr(
        layout_imports,
        "_sha256_stream",
        changing_sha256_stream,
    )

    with pytest.raises(JobError) as captured:
        _inspector(import_root).inspect("layouts.jsonl", contract_version=1)

    assert captured.value.code == "IMPORT_SOURCE_CHANGED"
