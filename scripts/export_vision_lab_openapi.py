"""Generate the standalone laboratory contract without reading a snapshot or database."""

import argparse
import json
from pathlib import Path

from game_predictor_worker.vision_lab.api import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = (
        Path(__file__).resolve().parents[1] / "packages/vision-lab-api-client/openapi/openapi.json"
    )
    data = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != data:
            raise SystemExit("Vision lab OpenAPI is stale; run npm run vision-lab:openapi:generate")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
