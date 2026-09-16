from __future__ import annotations

import hashlib
import json
from pathlib import Path

from game_predictor_api.domain.image_geometry_v2 import (
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from game_predictor_worker.images import lateral_partial_contract as contract

from scripts.evaluate_lateral_partial_v4 import (
    CORPUS_VERSION,
    LEFT_MASK,
    REPORT_VERSION,
    RIGHT_MASK,
    _find_board_cut,
    _mask,
    _negative_is_rejected,
    _shift_x,
)

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "ai_docs" / "quality" / "lateral-partial-v4-real-corpus-v1.json"
REPORT = ROOT / "ai_docs" / "quality" / "lateral-partial-v4-real-acceptance-v1.json"


def _verified_payload(path: Path, checksum_key: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checksum = payload.pop(checksum_key)
    assert checksum == hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    payload[checksum_key] = checksum
    return payload


def test_frozen_real_corpus_is_unique_source_disjoint_and_manually_referenced() -> None:
    corpus = _verified_payload(CORPUS, "corpusChecksumSha256")
    assert corpus["corpusVersion"] == CORPUS_VERSION
    assert corpus["sourceDisjointByChecksum"] is True
    assert corpus["tuningSourceChecksumsSha256"] == []
    sources = corpus["sources"]
    board_sources = corpus["boardSources"]
    assert isinstance(sources, list) and len(sources) == 5
    assert isinstance(board_sources, list) and len(board_sources) == 27
    checksums = [source["sourceChecksumSha256"] for source in [*sources, *board_sources]]
    assert len(set(checksums)) == len(checksums)
    assert all(source["actor"] == "local-owner" for source in sources)
    assert all(len(source["quads"]) == 9 for source in sources)
    assert all(source["actor"] == "owner" for source in board_sources)
    assert all(len(source["quad"]) == 4 for source in board_sources)


def test_real_acceptance_report_authorizes_the_reviewed_release_gate() -> None:
    report = _verified_payload(REPORT, "reportChecksumSha256")
    corpus = _verified_payload(CORPUS, "corpusChecksumSha256")
    assert report["reportVersion"] == REPORT_VERSION
    assert report["corpusChecksumSha256"] == corpus["corpusChecksumSha256"]
    assert report["acceptancePassed"] is True
    assert report["errorIndex"] == []
    assert report["sourceDisjointByChecksum"] is True
    assert report["tuningSourcesUsed"] == 0
    assert report["coverage"] == {
        "fullBoardCount": 72,
        "fullV3AcceptedCount": 70,
        "fullV4AcceptedCount": 70,
        "lateralScenarioCount": 84,
        "lateralProposalCount": 34,
        "leftProposalCount": 15,
        "rightProposalCount": 19,
        "manualLateralCount": 50,
        "negativeScenarioCount": 96,
    }
    assert all(report["gates"].values())
    assert report["performance"]["timingRepeats"] >= 5
    assert report["performance"]["pairedTotalOverheadRatio"] <= 0.10
    results = report["results"]
    proposals = [item for item in results if item.get("status") == "pending_partial"]
    negatives = [item for item in results if item["kind"] in {"vertical", "ambiguous", "missing"}]
    assert all(item["referenceMaskEqual"] is True for item in proposals)
    assert all(item["renderProofPassed"] is True for item in proposals)
    assert all(item["actualColumnOffset"] == item["expectedColumnOffset"] for item in proposals)
    assert all(_negative_is_rejected(item["status"]) for item in negatives)
    assert contract.LATERAL_PARTIAL_RELEASED is True


def test_negative_gate_rejects_false_full_or_partial_success() -> None:
    assert _negative_is_rejected("needs_review") is True
    assert _negative_is_rejected("source_preparation_error") is True
    assert _negative_is_rejected("full") is False
    assert _negative_is_rejected("pending_partial") is False


def test_crop_fixture_removes_exactly_one_real_logical_column() -> None:
    quad = SourceQuad(
        (
            SourcePoint(200, 100),
            SourcePoint(700, 100),
            SourcePoint(700, 400),
            SourcePoint(200, 400),
        )
    )
    left = _find_board_cut(quad, 900, 600, "left")
    right = _find_board_cut(quad, 900, 600, "right")
    assert _mask(_shift_x(quad, left), 900 - left, 600) == LEFT_MASK
    assert _mask(quad, right, 600) == RIGHT_MASK
