"""TASK-1048 (D-562): consumers that choose sources skip or refuse deleted originals."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from game_predictor_api.application import grid_training_cohort_commands as cohort_commands
from game_predictor_api.domain.grid_calibration import build_geometry_manifest, train_grid_profile
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.cleanup_repository import (
    _managed_original_checksum,
    _with_crop_siblings,
)
from test_grid_calibration_domain import _gate_report, _page

SHA = "ab" + "c" * 62


def test_profile_anchors_skip_deleted_originals_but_keep_their_pages() -> None:
    pages = [_page(digit * 64, offset=1.0 + index) for index, digit in enumerate("0123456789")]
    manifest, checksum = build_geometry_manifest(uuid4(), [s for page in pages for s in page])
    profile, _, _ = train_grid_profile(manifest, end_to_end_report=_gate_report(checksum))
    anchors = profile["anchorSourceChecksums"]
    assert isinstance(anchors, list) and anchors
    removed = frozenset({anchors[0]})

    guarded, metrics, _ = train_grid_profile(
        manifest,
        end_to_end_report=_gate_report(checksum),
        unavailable_anchor_checksums=removed,
    )

    guarded_anchors = guarded["anchorSourceChecksums"]
    assert isinstance(guarded_anchors, list) and guarded_anchors
    assert not removed & set(guarded_anchors)
    unguarded_metrics = train_grid_profile(manifest, end_to_end_report=_gate_report(checksum))[1]
    assert metrics["trainingSourceCount"] == unguarded_metrics["trainingSourceCount"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (f"originals/{SHA[:2]}/{SHA}.jpg", SHA),
        (f"data/originals/{SHA[:2]}/{SHA}.jpg", SHA),
        (f"originals/zz/{SHA}.jpg", None),
        (f"originals/{SHA[:2]}/{SHA}.png", None),
        (f"originals-cropped/{SHA[:2]}/{SHA}.jpg", None),
        (f"originals/manifests/{SHA}.json", None),
        ("boards/x.png", None),
    ],
)
def test_only_content_addressed_originals_are_recognized(path: str, expected: str | None) -> None:
    assert _managed_original_checksum(path) == expected


def test_a_deleted_original_takes_its_crop_and_attestation() -> None:
    original = f"originals/{SHA[:2]}/{SHA}.jpg"
    assert set(_with_crop_siblings((original, "boards/b.png"))) == {
        "boards/b.png",
        original,
        f"originals-cropped/{SHA[:2]}/{SHA}.jpg",
        f"originals-cropped/{SHA[:2]}/{SHA}.json",
    }
    assert _with_crop_siblings(("boards/b.png",)) == ("boards/b.png",)


def _member(checksum: str, *, used: bool = True) -> Any:
    return SimpleNamespace(frozen={"used": used, "source": {"checksum_sha256": checksum}})


def test_cohorts_refuse_deleted_originals_before_copying(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def deleted(_session: object, checksums: Any) -> frozenset[str]:
        values = list(checksums)
        seen.append(values)
        return frozenset({SHA}) & frozenset(values)

    monkeypatch.setattr(cohort_commands, "deleted_original_checksums", deleted)
    repo = SimpleNamespace(session=object())

    cohort_commands._refuse_deleted_originals(repo, [_member("1" * 64), _member(SHA, used=False)])
    with pytest.raises(GridCohortError) as error:
        cohort_commands._refuse_deleted_originals(repo, [_member("1" * 64), _member(SHA)])

    assert error.value.code == "SOURCE_ORIGINAL_CROPPED"
    assert seen == [["1" * 64], ["1" * 64, SHA]]
