"""Record neural sources that a V3 import skips because no slot binding exists.

`bound_neural_originals` admits only sources whose detections were bound to the
board slots of their attested filename range.  A `slot_binding_required`
source therefore never seeds boards.  This module makes that skip durable: an
immutable per-job report lists every skipped source and the job checkpoint
carries a bounded summary of it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from uuid import UUID

from game_predictor_worker.jobs.runtime import JobHandlerError

from .source_ingestion import ManagedOriginal

NEURAL_UNBOUND_SOURCES_REPORT_VERSION = "neural-unbound-sources-v1"
NEURAL_UNBOUND_SOURCES_SAMPLE_LIMIT = 20
NEURAL_UNBOUND_DEFAULT_REASON = "NEURAL_GRID_SLOT_BINDING_REQUIRED"


def unbound_neural_sources(
    originals: Sequence[ManagedOriginal], entries: Mapping[str, object]
) -> tuple[dict[str, object], ...]:
    """List imported sources whose neural detections have no slot binding."""

    result: list[dict[str, object]] = []
    for original in originals:
        entry = entries.get(original.checksum_sha256)
        if not isinstance(entry, Mapping) or entry.get("status") != "slot_binding_required":
            continue
        reason = entry.get("reasonCode")
        result.append(
            {
                "sourceChecksumSha256": original.checksum_sha256,
                "sourceRelativePath": original.source_relative_path,
                "sequenceRangeStart": original.sequence_range_start,
                "sequenceRangeEnd": original.sequence_range_end,
                "reasonCode": reason
                if isinstance(reason, str) and reason
                else NEURAL_UNBOUND_DEFAULT_REASON,
            }
        )
    return tuple(result)


def record_neural_unbound_sources(
    artifact_root: Path,
    *,
    job_id: UUID,
    page_geometry_manifest_checksum_sha256: str,
    originals: Sequence[ManagedOriginal],
    entries: Mapping[str, object],
) -> dict[str, object] | None:
    """Write the immutable skip report and return its checkpoint summary.

    The report is deterministic for a job, so a resumed run rewrites the same
    bytes.  Different content under the same job is a collision, never an
    overwrite.  Returns ``None`` when every source is bound.
    """

    sources = unbound_neural_sources(originals, entries)
    if not sources:
        return None
    reason_counts = Counter(str(item["reasonCode"]) for item in sources)
    attested_board_count = sum(
        end - start + 1
        for start, end in (
            (item["sequenceRangeStart"], item["sequenceRangeEnd"]) for item in sources
        )
        if isinstance(start, int) and isinstance(end, int) and end >= start
    )
    report = {
        "version": NEURAL_UNBOUND_SOURCES_REPORT_VERSION,
        "jobId": str(job_id),
        "pageGeometryManifestChecksumSha256": page_geometry_manifest_checksum_sha256,
        "sourceCount": len(sources),
        "attestedBoardCount": attested_board_count,
        "reasonCounts": dict(sorted(reason_counts.items())),
        "sources": list(sources),
    }
    content = (json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    relative_path = f"data/image-import-unbound-sources/{job_id}.json"
    _write_immutable(artifact_root.resolve().joinpath(*PurePosixPath(relative_path).parts), content)
    return {
        "version": NEURAL_UNBOUND_SOURCES_REPORT_VERSION,
        "sourceCount": len(sources),
        "attestedBoardCount": attested_board_count,
        "reasonCounts": dict(sorted(reason_counts.items())),
        "reportChecksumSha256": hashlib.sha256(content).hexdigest(),
        "reportRelativePath": relative_path,
        "sample": [
            {
                key: item[key]
                for key in (
                    "sourceRelativePath",
                    "sequenceRangeStart",
                    "sequenceRangeEnd",
                    "reasonCode",
                )
            }
            for item in sources[:NEURAL_UNBOUND_SOURCES_SAMPLE_LIMIT]
        ],
    }


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise JobHandlerError(
                "NEURAL_GRID_UNBOUND_SOURCES_REPORT_COLLISION",
                "The immutable unbound-source report already has different content.",
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-unbound-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise JobHandlerError(
                    "NEURAL_GRID_UNBOUND_SOURCES_REPORT_COLLISION",
                    "The immutable unbound-source report already has different content.",
                ) from None
    finally:
        temporary.unlink(missing_ok=True)
