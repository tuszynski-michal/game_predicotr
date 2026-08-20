"""Build the deterministic 100-page pre-editor audit for v19 geometry."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from game_predictor_worker.images.board_cell_geometry_audit import (
    BoardCellGeometryAuditError,
    render_audit_contact_sheets,
    render_audit_overlays,
    run_board_cell_geometry_audit,
    write_content_addressed_audit,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-geometry-manifest", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--sample-size", default=100, type=int)
    parser.add_argument("--sample-seed")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    started = time.perf_counter()
    try:
        if arguments.sample_seed is None:
            audit = run_board_cell_geometry_audit(
                page_geometry_manifest_path=arguments.page_geometry_manifest,
                sample_size=arguments.sample_size,
                source_root=arguments.source_root,
            )
        else:
            audit = run_board_cell_geometry_audit(
                page_geometry_manifest_path=arguments.page_geometry_manifest,
                sample_seed=arguments.sample_seed,
                sample_size=arguments.sample_size,
                source_root=arguments.source_root,
            )
        report_path = write_content_addressed_audit(audit, arguments.output_root / "reports")
        overlays = render_audit_overlays(audit, arguments.output_root / "overlays")
        sheets = render_audit_contact_sheets(audit, arguments.output_root / "contact-sheets")
    except BoardCellGeometryAuditError as error:
        print(json.dumps({"code": error.code, "message": str(error)}), file=sys.stderr)
        return 1
    summary = audit.document["summary"]
    print(
        json.dumps(
            {
                "auditChecksumSha256": audit.checksum_sha256,
                "elapsedSeconds": round(time.perf_counter() - started, 3),
                "contactSheetCount": len(sheets),
                "overlayCount": len(overlays),
                "reportPath": str(report_path),
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
