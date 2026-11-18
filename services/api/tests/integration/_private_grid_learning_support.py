"""Frozen private correction cohort for isolated registry and workflow tests."""

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection


def private_frozen_cohort(
    connection: Connection, pin: dict, *, cohort: UUID | None = None, manifest_sha: str = "c" * 64
) -> UUID:
    cohort = cohort or uuid4()
    document = {
        "privateLearning": pin,
        "familyId": pin["targetFamilyId"],
        "baseVersionId": pin["baseVersionId"],
        "base": {"versionId": pin["baseVersionId"], "manifestSha256": pin["baseManifestSha256"]},
        "mode": "grid-only",
        "policyVersion": "application-grid-corrections-v2",
        "cropPolicyVersion": "full-cell-v2",
        "detectorReadiness": {"reasonCodes": []},
        "photoSplit": {"sha256": "b" * 64},
    }
    connection.execute(
        text("""INSERT INTO game_data_v2.grid_training_cohorts
         (game_id,id,status,document,manifest_path,manifest_sha256,created_by)
         VALUES (:game,:id,'frozen',CAST(:doc AS jsonb),'fixture.json',:sha,'fixture:private')"""),
        {"game": pin["gameId"], "id": cohort, "doc": json.dumps(document), "sha": manifest_sha},
    )
    return cohort
