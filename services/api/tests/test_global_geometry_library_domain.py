from __future__ import annotations

from copy import deepcopy

import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryError,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)


def _topology() -> GlobalGeometryTopology:
    return GlobalGeometryTopology(3, 3, 3, 5)


def _template() -> dict[str, object]:
    return {
        "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
        "topology": _topology().to_dict(),
        "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        "aspectRatioRange": {"minimum": 0.5, "maximum": 2.0},
    }


def _appearance() -> dict[str, object]:
    return {
        "schemaVersion": FRAME_APPEARANCE_SCHEMA_VERSION,
        "sides": {
            "top": {
                "clusters": [{"lab": [44.0, 12.0, -8.0], "hsv": [23.0, 0.5, 0.7]}],
                "contrast": {"minimum": 0.2, "median": 0.4, "maximum": 0.8},
                "continuity": 0.9,
            }
        },
    }


def _summary() -> dict[str, object]:
    return {
        "schemaVersion": EVIDENCE_SUMMARY_SCHEMA_VERSION,
        "fullSourceCount": 1,
        "partialSourceCount": 0,
        "sourceGameRefs": ["mummies"],
        "extractorVersion": "shape-geometry-v2-core-v1",
        "qualityMetrics": {"candidateCount": 1},
    }


def _evidence(*, coverage_kind: str = "full") -> dict[str, object]:
    return {
        "schemaVersion": GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
        "coverageKind": coverage_kind,
        "visibleFrameSides": ["top", "right", "bottom", "left"],
        "extractorVersion": "shape-geometry-v2-core-v1",
        "metrics": {"frameSupport": 0.91},
    }


def _candidate(
    *,
    template: dict[str, object] | None = None,
    evidence: list[tuple[str, dict[str, object]]] | None = None,
):
    evidence = evidence or [("mummies", _evidence())]
    summary = _summary()
    summary["fullSourceCount"] = sum(payload["coverageKind"] == "full" for _, payload in evidence)
    summary["partialSourceCount"] = sum(
        payload["coverageKind"] == "partial" for _, payload in evidence
    )
    summary["sourceGameRefs"] = sorted({source_game_ref for source_game_ref, _ in evidence})
    return build_global_geometry_candidate(
        geometry_family=SUPPORTED_GEOMETRY_FAMILY,
        topology=_topology(),
        normalized_template=template or _template(),
        frame_appearance=_appearance(),
        evidence_summary=summary,
        evidence=evidence,
    )


def test_candidate_checksum_is_canonical_and_covers_descriptor_evidence() -> None:
    first = _candidate(
        evidence=[("gang", _evidence()), ("mummies", _evidence(coverage_kind="partial"))]
    )
    second = _candidate(
        evidence=[("mummies", _evidence(coverage_kind="partial")), ("gang", _evidence())]
    )

    assert first.profile_checksum_sha256 == second.profile_checksum_sha256
    assert tuple(item.source_game_ref for item in first.evidence) == ("gang", "mummies")
    assert first.command_sha256() == second.command_sha256()


@pytest.mark.parametrize("forbidden_key", ["imageBytes", "game_id", "symbolCode", "sequenceNumber"])
def test_candidate_rejects_game_semantics_and_image_payloads(forbidden_key: str) -> None:
    template = deepcopy(_template())
    template[forbidden_key] = "forbidden"

    with pytest.raises(GlobalGeometryLibraryError) as error:
        _candidate(template=template)

    assert error.value.code == "GLOBAL_GEOMETRY_PAYLOAD_FORBIDDEN_FIELD"


def test_full_evidence_cannot_claim_incomplete_frame_coverage() -> None:
    evidence = _evidence()
    evidence["visibleFrameSides"] = ["top", "left"]

    with pytest.raises(GlobalGeometryLibraryError) as error:
        _candidate(evidence=[("mummies", evidence)])

    assert error.value.code == "GLOBAL_GEOMETRY_EVIDENCE_FULL_COVERAGE_INCOMPLETE"


def test_invalid_topology_is_rejected_before_profile_build() -> None:
    with pytest.raises(GlobalGeometryLibraryError) as error:
        GlobalGeometryTopology(3, 3, 3, 4)

    assert error.value.code == "GLOBAL_GEOMETRY_TOPOLOGY_UNSUPPORTED"


def test_candidate_snapshot_is_deeply_immutable() -> None:
    candidate = _candidate()

    with pytest.raises(TypeError):
        candidate.normalized_template["unexpected"] = "value"
    with pytest.raises(TypeError):
        candidate.normalized_template["frameQuad"][0][0] = 0.2  # type: ignore[index]


def test_candidate_accepts_numeric_game_provenance_ref() -> None:
    candidate = _candidate(evidence=[("777", _evidence())])

    assert candidate.evidence[0].source_game_ref == "777"


def test_candidate_rejects_degenerate_or_out_of_contract_descriptors() -> None:
    degenerate = _template()
    degenerate["frameQuad"] = [[0.0, 0.0]] * 4
    image_like = _evidence()
    image_like["metrics"] = {"data": "data:image/png;base64,AAAA"}

    with pytest.raises(GlobalGeometryLibraryError) as quad_error:
        _candidate(template=degenerate)
    with pytest.raises(GlobalGeometryLibraryError) as descriptor_error:
        _candidate(evidence=[("mummies", image_like)])

    assert quad_error.value.code == "GLOBAL_GEOMETRY_TEMPLATE_QUAD_ORDER_INVALID"
    assert descriptor_error.value.code == "GLOBAL_GEOMETRY_NUMERIC_DESCRIPTOR_INVALID"


def test_candidate_accepts_core_ordered_sloped_quad_and_rejects_rotated_input() -> None:
    sloped = _template()
    sloped["frameQuad"] = [[0.1, 0.2], [0.8, 0.1], [0.9, 0.8], [0.2, 0.9]]
    rotated = deepcopy(sloped)
    rotated["frameQuad"] = rotated["frameQuad"][1:] + rotated["frameQuad"][:1]  # type: ignore[index]

    accepted = _candidate(template=sloped)
    with pytest.raises(GlobalGeometryLibraryError) as error:
        _candidate(template=rotated)

    assert accepted.normalized_template["frameQuad"] == sloped["frameQuad"]
    assert error.value.code == "GLOBAL_GEOMETRY_TEMPLATE_QUAD_ORDER_INVALID"
