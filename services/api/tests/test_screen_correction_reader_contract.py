"""Real split/label reader/capture; only database/publication boundaries are fixtures.

No capture/approval/render/hash output is substituted. These rows model qualified
manual labels; the existing disposable PG tests cover persisted roles/transactions.
"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application import grid_training_cohort_commands as commands
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest, exact_lattice
from game_predictor_api.domain.image_geometry_v2 import SOURCE_COORDINATE_SPACE
from game_predictor_api.storage import grid_correction_split as adapter
from game_predictor_api.storage import grid_training_cohort_evidence as evidence
from game_predictor_api.storage import source_replacement_guards


@pytest.mark.parametrize("drift_role", [None, "TRAIN", "VALIDATION", "REGRESSION"])
def test_real_reader_split_hash_matches_capture_and_rejects_changed_human_gt(
    monkeypatch, tmp_path, drift_role
):
    game = uuid4()
    sources, targets, revisions, roles, rows, by_board = {}, {}, {}, {}, [], {}
    imports = {role: str(uuid4()) for role in ("TRAIN", "VALIDATION", "REGRESSION")}

    def refresh(target):
        board = target["board"]
        board["geometry_checksum_sha256"] = digest(board["board_geometry"])
        nodes, cells = exact_lattice(board["board_geometry"], 100, 100)
        revision = revisions[board["source_image_id"]]
        revision["geometry_checksum_sha256"] = board["geometry_checksum_sha256"]
        # All targets of one source share a source revision checksum in these rows.
        for sibling in targets[board["source_image_id"]].values():
            sibling["board"]["geometry_checksum_sha256"] = revision["geometry_checksum_sha256"]
        revision["board_geometries"] = [
            {
                "positionIndex": t["board"]["position_index"],
                "sequenceNumber": t["board"]["sequence_number"],
                "latticeNodes": t["board"]["board_geometry"]["latticeNodes"],
            }
            for t in targets[board["source_image_id"]].values()
        ]
        entries = []
        for index, quad in enumerate(cells):
            spec = {"sourceQuad": quad, "configuration": {"fixture": "same-pinned-render"}}
            entries.append(
                {
                    "cellIndex": index,
                    "renderSpec": spec,
                    "renderSpecChecksumSha256": sha256_canonical_json(spec),
                }
            )
        target["renders"] = [{"cells": {"cells": entries}}]

    for index in range(20):
        role = "TRAIN" if index < 10 else "VALIDATION" if index < 15 else "REGRESSION"
        sid, revision_id = str(uuid4()), str(uuid4())
        source = {
            "id": sid,
            "import_job_id": imports[role],
            "checksum_sha256": f"{index + 1:064x}",
            "normalized_pixel_checksum_sha256": f"{index + 101:064x}",
            "oriented_width": 100,
            "oriented_height": 100,
            "exif_orientation": 1,
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "normalization_adapter_version": "fixture-normalization",
            "relative_path": f"{index:03}.jpg",
        }
        sources[sid], roles[sid], targets[sid] = source, role, {}
        revisions[sid] = {
            **source,
            "status": "active",
            "source_checksum_sha256": source["checksum_sha256"],
        }
        count = 3 if role == "REGRESSION" else 9
        for position in range(count):
            x, y = 5 + 30 * (position % 3), 5 + 30 * (position // 3)
            nodes = [
                {"x": float(x + c * 4), "y": float(y + r * 5)} for r in range(4) for c in range(6)
            ]
            board = {
                "id": str(uuid4()),
                "source_image_id": sid,
                "position_index": position,
                "sequence_number": index * 9 + position,
                "geometry_revision": 2,
                "source_geometry_revision_id": revision_id,
                "board_geometry": {"latticeNodes": nodes},
                "grid_rows": 3,
                "grid_columns": 5,
                "completeness_status": "complete",
                "unavailable_cell_indices": [],
                "geometry_qualification": {},
                "status": "pending",
                "approved_geometry_revision": 2,
                "geometry_approved_by": "operator:fixture",
                "geometry_approved_at": "2026-11-04T00:00:00Z",
            }
            target = {
                "board": board,
                "review": {"id": str(uuid4()), "status": "pending"},
                "owner": None,
                "foreignOwner": None,
                "cells": [],
                "pending": None,
            }
            targets[sid][position], by_board[board["id"]] = target, target
        for target in targets[sid].values():
            refresh(target)
        rows.append(
            {
                "source": source,
                "logicalName": source["relative_path"],
                "approved": True,
                "revisions": [],
                "bindings": [],
            }
        )

    def database_row(self, sql, **parameters):
        if "FROM image_source_geometry_revisions" in sql:
            return deepcopy(revisions[str(parameters["source"])])
        board = by_board[parameters["board"]]["board"]
        if "FROM image_board_geometry_review_events" in sql:
            return {
                "id": board["id"],
                "action": "geometry_saved",
                "actor": board["geometry_approved_by"],
                "created_at": board["geometry_approved_at"],
                "board_checksum_sha256": board["geometry_checksum_sha256"],
            }
        if "FROM image_board_geometry_revisions" in sql:
            return {"id": board["source_geometry_revision_id"]}
        raise AssertionError(sql)

    # Exact persisted-row boundaries; the actual reader, approvals, render proof,
    # lattice checks, split solver and capture hash guard remain production code.
    monkeypatch.setattr(evidence.GridCohortEvidenceReader, "_row", database_row)
    monkeypatch.setattr(
        evidence, "read_source", lambda session, game, sid: deepcopy(sources[str(sid)])
    )
    monkeypatch.setattr(
        evidence, "current_targets", lambda session, game, sid: deepcopy(targets[str(sid)])
    )
    monkeypatch.setattr(source_replacement_guards, "require_active_source", lambda *args: None)
    monkeypatch.setattr(adapter, "population", lambda *args: deepcopy(rows))
    monkeypatch.setattr(
        adapter,
        "contexts",
        lambda *args, **kwargs: {
            sid: {
                "priorRoles": [role],
                "allowedRoles": [role],
                "componentIds": [],
                "proofSha256": "a" * 64,
            }
            for sid, role in roles.items()
        },
    )
    repo = SimpleNamespace(session=object(), artifact_root=tmp_path)
    deadline = SimpleNamespace(check=lambda *args: None)
    split = adapter.prepare_split(
        repo, game, sorted(imports.values()), deadline, policy="application-grid-corrections-v3"
    )
    assert [(r["photos"], r["boards"]) for r in split["roleCounts"]] == [(10, 90), (5, 45), (5, 15)]
    assert all(p["qualifiedLabelsSha256"] != digest([]) for p in split["sources"])
    assert all(p["role"] == roles[p["sourceId"]] for p in split["sources"])
    members = [
        SimpleNamespace(source_id=UUID(p["sourceId"]), ordinal=i)
        for i, p in enumerate(sorted(split["sources"], key=lambda p: p["sourceId"]))
    ]
    row = SimpleNamespace(
        id=uuid4(),
        status="preparing",
        document={
            "policyVersion": "application-grid-corrections-v3",
            "mode": "screen+grid",
            "photoSplit": split,
        },
    )
    repo.next_capture = lambda *args: 0
    repo.members = lambda *args: members
    published = []

    class PublicationReached(Exception):
        pass

    def publish(*args):
        published.append(args[-1])
        raise PublicationReached  # Stop before database writes; all guards have executed.

    service = SimpleNamespace(
        repository=repo, artifacts=SimpleNamespace(root=tmp_path, publish_json=publish)
    )
    if drift_role:
        sid = next(sid for sid, role in roles.items() if role == drift_role)
        target = targets[sid][0]
        target["board"]["board_geometry"]["latticeNodes"][7]["x"] += 0.25
        target["board"]["geometry_revision"] += 1
        target["board"]["approved_geometry_revision"] += 1
        refresh(target)
        with pytest.raises(GridCohortError) as caught:
            commands._capture(service, game, row, {"cursor": 0}, deadline)
        assert caught.value.code == "GRID_CORRECTION_LABELS_CHANGED"
        assert published == []
    else:
        with pytest.raises(PublicationReached):
            commands._capture(service, game, row, {"cursor": 0}, deadline)
        captured = published[0]["members"]
        expected = {p["sourceId"]: p["qualifiedLabelsSha256"] for p in split["sources"]}
        assert all(m["used"] for m in captured)
        for member in captured:
            labels = [p["label"] for p in member["positions"] if p["label"] is not None]
            assert digest(labels) == expected[member["sourceId"]]
            assert member["screenEligible"] == (member["role"] != "REGRESSION")
            assert len(labels) == (3 if member["role"] == "REGRESSION" else 9)
