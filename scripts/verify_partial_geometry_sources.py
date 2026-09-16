"""Read-only, bounded render/replay smoke test on up to three existing JPEGs.

The edge quads are protocol fixtures, not annotations of actual board locations.
This checks decoding, source support and exact replay, not detector accuracy.
No output images, manifests, database rows or user files are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    derive_virtual_cells,
    unavailable_source_cell_indices,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    VirtualCellRenderer,
    render_persisted_virtual_cell_rgb,
)


def verify_source(path: Path) -> dict[str, object]:
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = CanonicalSourceLoader().load(path, expected_source_checksum_sha256=checksum)
    height, width = frame.rgb.shape[:2]
    results = []
    for side, left, right, missing in (
        ("left", -0.08, 0.92, (0, 5, 10)),
        ("right", 0.08, 1.08, (4, 9, 14)),
    ):
        quad = SourceQuad(
            cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(
                    SourcePoint(round(x * width), round(y * height))
                    for x, y in (
                        (left, 0.15),
                        (right, 0.2),
                        (right, 0.85),
                        (left, 0.8),
                    )
                ),
            )
        )
        topology = BoardTopology(3, 5)
        mask = unavailable_source_cell_indices(quad, source=frame.source, topology=topology)
        if mask != missing:
            raise AssertionError((side, mask, missing))
        geometry = VirtualBoardGeometry(
            source=frame.source,
            source_occurrence=SourceOccurrence(UUID(int=1), "a" * 64),
            slot=ActiveBoardSlot(1, 9, 0, 1),
            topology=topology,
            topology_rules_version_id=UUID(int=2),
            geometry_revision=1,
            geometry_version="manual-source-geometry-partial-v2",
            engine_kind=GeometryEngineKind.MANUAL_V1,
            symbol_grid_quad=quad,
            geometry_qualification=GeometryQualification(
                "pending_partial", mask, True, "missing_pixels"
            ),
        )
        configuration = DirectCellRenderConfiguration(
            extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version="rgb-v1",
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=64,
            output_height=64,
            padding_fraction=0.08,
        )
        cells = derive_virtual_cells(geometry=geometry, configuration=configuration)
        renders = VirtualCellRenderer().render(frame, cells)
        if len(renders) != 12:
            raise AssertionError("A side fixture must retain twelve real crops.")
        for render in renders:
            replay = render_persisted_virtual_cell_rgb(
                frame,
                render_spec=render.render_spec,
                expected_render_spec_checksum_sha256=render.render_spec_checksum_sha256,
                expected_rendered_pixel_checksum_sha256=render.rendered_pixel_checksum_sha256,
                expected_cell_index=render.cell_index,
                expected_row_index=render.row_index,
                expected_column_index=render.column_index,
                expected_logical_cell_key_sha256=render.logical_cell_key_sha256,
                expected_logical_cell_key_v2_sha256=render.logical_cell_key_v2_sha256,
                expected_extractor_version=render.extractor_version,
            )
            if not np.array_equal(replay, render.rgb):
                raise AssertionError("Replay changed the rendered pixels.")
        results.append(
            {"side": side, "missing": mask, "rendered": len(renders), "replayExact": True}
        )
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise AssertionError("Source changed during read-only verification.")
    return {
        "file": path.name,
        "checksum": checksum,
        "width": width,
        "height": height,
        "fixtures": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    args = parser.parse_args()
    if not 1 <= len(args.sources) <= 3:
        parser.error("Provide one to three existing JPEGs; this is not a catalog benchmark.")
    print(
        json.dumps(
            {
                "schemaVersion": 1,
                "purpose": "manual-edge-protocol-not-detector-quality",
                "sources": [verify_source(path) for path in args.sources],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
