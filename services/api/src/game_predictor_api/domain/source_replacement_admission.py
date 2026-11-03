"""A local selection describes bytes; only transactional server checks authorize them."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import digest


def admission_error(code: str, message: str) -> SourceReplacementError:
    return SourceReplacementError(f"SOURCE_REPLACEMENT_{code}", message)


def selected_replacement_files(selection: dict[str, Any], game: UUID) -> list[dict[str, Any]]:
    """Validate the complete request, but select only explicitly committed output files."""
    try:
        request = selection["request"]
        body = {key: value for key, value in request.items() if key != "digest"}
        if (
            request["schemaVersion"] != "source-replacement-request-v1"
            or request["gameId"] != str(game)
            or digest(body) != request["digest"]
        ):
            raise ValueError("request")
        UUID(request["batchId"])
        entries = {item["entryId"]: item for item in request["entries"]}
        ranges = {item["entryId"]: item for item in request["allowedRanges"]}
        selected = selection["selectedEntryIds"]
        files = {item["entryId"]: item for item in selection["files"]}
        if (
            not 1 <= len(selected) <= 50
            or len(set(selected)) != len(selected)
            or len(entries) != len(request["entries"])
            or len(ranges) != len(request["allowedRanges"])
            or len(files) != len(selection["files"])
            or set(files) != set(selected)
            or set(entries) != set(ranges)
            or not set(selected).issubset(entries)
            or len({item["fileName"] for item in files.values()}) != len(files)
        ):
            raise ValueError("selection")
        result = []
        for entry_id in sorted(selected):
            UUID(entry_id)
            file, scope, entry = files[entry_id], ranges[entry_id], entries[entry_id]
            start, end = scope["sequenceStart"], scope["sequenceEnd"]
            sha = file["checksumSha256"]
            if (
                type(start) is not int
                or type(end) is not int
                or start < 1
                or end < start
                or end - start >= 9
                or entry["sequenceNumbers"] != list(range(start, end + 1))
                or file["rangeStart"] != start
                or file["rangeEnd"] != end
                or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or sha == entry["sourceSha256"]
                or type(entry["revision"]) is not int
                or entry["revision"] < 1
            ):
                raise ValueError("scope")
            result.append(
                {
                    **file,
                    "revision": entry["revision"],
                    "scopeDigest": entry["digest"],
                    "oldSha256": entry["sourceSha256"],
                    "sequenceNumbers": entry["sequenceNumbers"],
                }
            )
        if len({item["checksumSha256"] for item in result}) != len(result):
            raise ValueError("ambiguous SHA")
        return result
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise admission_error(
            "ADMISSION_INVALID", "Wybór zamienników nie pasuje do requestu."
        ) from error
