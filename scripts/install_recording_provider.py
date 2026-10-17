"""Install one trusted recording ancestor provider; print the server config SHA.

Explicit owner deployment only. Commits trusted DB proof before publishing the
file index. An index failure is visible and can be retried with the exact input.
"""

import argparse
import sys
from pathlib import Path

# Deployment must use this checkout even when the shared venv is editable elsewhere.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_directory in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(REPOSITORY_ROOT / source_directory))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.domain.source_recording_groups import recording_sha256  # noqa: E402
from game_predictor_api.storage.source_recording_lab_import import (  # noqa: E402
    install_provider_proof,
)
from game_predictor_api.storage.source_recording_providers import (  # noqa: E402
    install_recording_provider,
    read_provider,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--expected-index-sha256")
    options = parser.parse_args()
    provider = read_provider(options.source, options.sha256)
    engine = create_engine(
        ApiSettings.from_environment().owner_database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.begin() as connection:
            install_provider_proof(connection, provider, recording_sha256(provider))
    finally:
        engine.dispose()
    checksum = install_recording_provider(
        options.artifact_root, options.source, options.sha256, options.expected_index_sha256
    )
    print(f"GAME_PREDICTOR_RECORDING_PROVIDER_INDEX_SHA256={checksum}")


if __name__ == "__main__":
    main()
