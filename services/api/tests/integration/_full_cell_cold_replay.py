"""Fresh interpreter over the task-owned test database; no services or operator DB."""

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app

command_path, game, job, review, output_path = sys.argv[1:]
app = create_app(ApiSettings.from_environment())
try:
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/image-review-items/{review}/geometry-revisions",
            params={"gameId": game, "importJobId": job},
            json=json.loads(Path(command_path).read_text(encoding="utf-8")),
        )
    Path(output_path).write_text(
        json.dumps({"pid": os.getpid(), "status": response.status_code, "body": response.json()}),
        encoding="utf-8",
    )
finally:
    app.state.database_engine.dispose()
