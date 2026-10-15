"""Deploy pinned LAB recording metadata with the owner URL; never read images.

Pages and final proof commit before provider index publication. Repeating the
exact command resumes page receipts and can repair DB-done/index-absent state.
This is explicit deployment provisioning, never an application request or training.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_directory in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(REPOSITORY_ROOT / source_directory))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.source_recording_lab_import import (  # noqa: E402
    finalize_lab_import,
    import_lab_page,
    read_lab_import_manifest,
)
from game_predictor_api.storage.source_recording_providers import (  # noqa: E402
    install_recording_provider,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--expected-index-sha256")
    parser.add_argument(
        "--page-index",
        type=int,
        help="Commit one page only; leave finalization and index unpublished.",
    )
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Verify committed pages and retry final proof/index publication.",
    )
    options = parser.parse_args()
    if options.page_index is not None and options.finalize_only:
        parser.error("--page-index and --finalize-only cannot be combined")
    manifest = read_lab_import_manifest(options.manifest, options.sha256)
    settings = ApiSettings.from_environment()
    engine = create_engine(
        settings.owner_database_url, poolclass=NullPool, connect_args={"connect_timeout": 5}
    )
    try:
        indices = (
            [options.page_index]
            if options.page_index is not None
            else []
            if options.finalize_only
            else range(len(manifest.pages))
        )
        for index in indices:
            key = uuid5(NAMESPACE_URL, f"recording-lab:{manifest.manifest_sha256}:page:{index}")
            with engine.begin() as connection:
                receipt = import_lab_page(connection, manifest, index, key)
            print(json.dumps({"status": "page_committed", **receipt}, sort_keys=True))
        if options.page_index is not None:
            return
        key = uuid5(NAMESPACE_URL, f"recording-lab:{manifest.manifest_sha256}:finalize")
        with engine.begin() as connection:
            receipt = finalize_lab_import(connection, manifest, key)
        # This is deliberately outside the DB transaction. Failure is explicit;
        # replay verifies the immutable DB receipt before retrying publication.
        checksum = install_recording_provider(
            options.artifact_root,
            manifest.provider_pin.path,
            manifest.provider_pin.sha256,
            options.expected_index_sha256,
        )
        print(
            json.dumps({"status": "installed", **receipt, "indexSha256": checksum}, sort_keys=True)
        )
        print(f"GAME_PREDICTOR_RECORDING_PROVIDER_INDEX_SHA256={checksum}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
