"""Shared V7 scan-run fixtures for the API and worker test suites.

TASK-0940: these helpers used to live in the worker test module
`test_v7_run_state` and were imported from an API test by bare module name,
which only resolved when the worker tests directory happened to be on
`sys.path`. Both suites now import them from here (`services/test_support` is
on pytest's `pythonpath`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionSource,
    fingerprint_sources,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    LocalSourceManifest,
)
from game_predictor_worker.semi_automatic_selection.v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7DecorationVisibility,
    V7FrameQuality,
    V7OcclusionSeverity,
    V7SymbolContentLoss,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7ScanRunState

SELECTION_ID = UUID("00000000-0000-0000-0000-000000000701")


def manifest(*contents: bytes) -> LocalSourceManifest:
    return manifest_with_paths(
        tuple((f"frame-{index}.jpg", content) for index, content in enumerate(contents))
    )


def manifest_with_paths(entries: tuple[tuple[str, bytes], ...]) -> LocalSourceManifest:
    sources = tuple(
        SemiAutomaticSelectionSource(
            source_index=index,
            relative_path=relative_path,
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )
        for index, (relative_path, content) in enumerate(entries)
    )
    fingerprint = fingerprint_sources(sources)
    payload = json.dumps(
        {"sources": [item.as_dict() for item in sources]}, sort_keys=True, separators=(",", ":")
    ).encode()
    return LocalSourceManifest(
        selection_id=SELECTION_ID,
        display_name="v7 fixture",
        source_root=Path("C:/v7-fixture"),
        sources=sources,
        source_fingerprint=fingerprint,
        total_bytes=sum(item.size_bytes for item in sources),
        content=payload,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )


def quality(
    state: V7ScanRunState, source_index: int, *, major_loss: bool = False
) -> V7FrameQuality:
    boards = tuple(
        V7BoardQuality(
            position_index=position,
            symbol_content_loss=(
                V7SymbolContentLoss.MAJOR
                if major_loss and position == 4
                else V7SymbolContentLoss.NONE
            ),
            readability=V7BoardReadability.CLEAR,
            visibility=V7BoardVisibility.FULL,
            blur=V7BlurSeverity.NONE,
            occlusion=V7OcclusionSeverity.NONE,
            decoration=V7DecorationVisibility.COMPLETE,
        )
        for position in range(9)
    )
    source = state.source_manifest.sources[source_index]
    return V7FrameQuality(source.source_id, source_index, boards)
