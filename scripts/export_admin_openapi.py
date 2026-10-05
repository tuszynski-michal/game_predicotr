"""Export or verify the deterministic FastAPI OpenAPI artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
# A shared editable virtualenv can point at a different checkout. Export the
# contract belonging to this script, including from a managed Git worktree.
for source_directory in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(REPOSITORY_ROOT / source_directory))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.main import create_app  # noqa: E402

OPENAPI_PATH: Final = REPOSITORY_ROOT / "packages" / "admin-api-client" / "openapi" / "openapi.json"


def render_openapi() -> str:
    """Render OpenAPI from deterministic default settings."""

    application = create_app(ApiSettings.from_environment({}))
    return (
        json.dumps(
            application.openapi(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the checked-in OpenAPI artifact is stale.",
    )
    arguments = parser.parse_args()
    expected = render_openapi()

    if arguments.check:
        if not OPENAPI_PATH.exists() or OPENAPI_PATH.read_text(encoding="utf-8") != expected:
            print("OpenAPI artifact is stale. Run: npm run openapi:generate")
            return 1
        print(f"OpenAPI artifact is current: {OPENAPI_PATH.relative_to(REPOSITORY_ROOT)}")
        return 0

    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Exported OpenAPI: {OPENAPI_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
