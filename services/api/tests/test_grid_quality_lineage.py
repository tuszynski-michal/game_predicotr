"""Real proposal validation over explicit source edges, with no mocked resolver method."""

import copy
from types import SimpleNamespace
from uuid import UUID, uuid4

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.storage.grid_quality_observations import original_target


def test_latest_proven_auto_parent_wins_over_older_immutable_snapshot_and_missing_edge_is_gap():
    game, source, board, review, older, newer, manual = (str(uuid4()) for _ in range(7))
    nodes = [
        {"x": float(10 + column * 30), "y": float(10 + row * 30)}
        for row in range(4)
        for column in range(6)
    ]
    quads = lattice_cell_quads(nodes, width=500, height=300)

    def make(configuration):
        snapshot = NeuralGridSnapshot.for_game(1000, grid_engine_profile_for(configuration).current)
        proposal = build_neural_source_proposal(
            game_id=game,
            source_selection_id=str(uuid4()),
            source_checksum_sha256="a" * 64,
            source_width=500,
            source_height=300,
            original_range=AttestedSequenceRange(start=101, end=101),
            snapshot=snapshot,
            detections=[
                {
                    "detectionId": "one",
                    "score": 0.8,
                    "latticeNodes": nodes,
                    "cellQuads": [quad.to_dict() for quad in quads],
                    "cellVisibility": lattice_visibility(quads, width=500, height=300),
                    "structurallyValid": True,
                    "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
                }
            ],
        )
        binding = build_neural_source_binding(
            proposal,
            confirmed_range=AttestedSequenceRange(start=101, end=101),
            assignments=[{"positionIndex": 0, "detectionId": "one"}],
        )
        geometry = {
            "latticeNodes": nodes,
            "detectionId": "one",
            "neuralProposalChecksumSha256": proposal["proposalChecksumSha256"],
            "neuralProposalBinding": binding,
        }
        return proposal, binding, geometry

    old_p, old_b, old_g = make(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1)
    new_p, new_b, new_g = make(GameShapeGeometryConfiguration.GRID_PROFILE_777_V2)

    def revision(identity, number, origin, proof):
        return {
            "id": identity,
            "revision": number,
            "source_checksum_sha256": "a" * 64,
            "normalized_pixel_checksum_sha256": "b" * 64,
            "geometry_source": origin,
            "board_geometries": [{"positionIndex": 0, "sequenceNumber": 101}],
            "global_initialization": proof,
        }

    rows = {
        older: revision(
            older, 0, "auto", {"v3EngineAcceptance": {"proposal": old_p, "binding": old_b}}
        ),
        newer: revision(
            newer,
            1,
            "auto",
            {
                "gridReinference": {
                    "operationId": str(uuid4()),
                    "proposal": new_p,
                    "binding": new_b,
                    "modelSnapshot": new_p["engineSnapshot"],
                }
            },
        ),
        manual: revision(manual, 2, "manual", {}),
    }

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def all(self):
            return self.value

    class Session:
        edges = True

        def execute(self, statement, parameters):
            sql = str(statement)
            if "image_symbol_review_events" in sql:
                assert parameters["review"] == review and parameters["pointer"] == manual
                return Result(
                    [
                        SimpleNamespace(
                            cell_review_id=str(uuid4()), previous_source_geometry_revision_id=newer
                        )
                        for _ in range(15)
                    ]
                    if self.edges
                    else []
                )
            if "image_board_geometry_revisions" in sql:
                assert parameters["board"] == board and parameters["parent"] == newer
                return Result({"geometry": new_g})
            assert parameters["source"] == source
            return Result(rows[parameters["id"]])

    target = {
        "board": {
            "id": board,
            "geometry_revision": 2,
            "source_geometry_revision_id": manual,
            "board_geometry": {"manual": True},
            "position_index": 0,
            "sequence_number": 101,
        },
        "review": {
            "id": review,
            "snapshot": {
                "geometry": old_g,
                "geometryChecksumSha256": "c" * 64,
                "sourceChecksumSha256": "a" * 64,
            },
        },
    }
    metadata = {
        "id": source,
        "checksum_sha256": "a" * 64,
        "normalized_pixel_checksum_sha256": "b" * 64,
        "import_job_id": str(uuid4()),
    }
    session = Session()
    geometry, producer, _ = original_target(session, UUID(game), metadata, target)
    assert geometry == new_g and producer["engineSnapshot"] == new_p["engineSnapshot"]
    assert producer["engineSnapshot"] != old_p["engineSnapshot"]
    session.edges = False
    assert original_target(session, UUID(game), metadata, target) == (None, None, [])
    current_auto = copy.deepcopy(target)
    current_auto["board"].update(
        source_geometry_revision_id=newer, geometry_revision=1, board_geometry=new_g
    )
    assert (
        original_target(session, UUID(game), metadata, current_auto)[1]["sourceRevisionId"] == newer
    )
