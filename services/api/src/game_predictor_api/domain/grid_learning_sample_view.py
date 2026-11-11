"""Compact projection of the existing frozen-policy sample preview, without selection."""

from collections.abc import Mapping
from typing import Any


def learning_test_sample(report: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if report is None or report.get("version") != "stratified-fresh-content-regression-v2":
        return None
    ordinary, hard = report["strata"]["ordinary"], report["strata"]["hard"]
    return {
        "version": "effective-grid-test-sample-v1",
        "seed": report["seed"],
        "state": report["state"],
        "baseVersionId": report.get("baseVersionId"),
        "ordinaryGeometryPhotos": ordinary["geometryFullPhotos"],
        "ordinaryContentPhotos": ordinary["contentFullPhotos"],
        "hardGeometryPhotos": hard["geometryFullPhotos"],
        "hardContentPhotos": hard["contentFullPhotos"],
        "missingContentSources": len(report["missingContentSourceIds"]),
        "annotationSourceIds": list(report["missingContentSourceIds"]),
        "unknownReferencePhotos": report["unknownReferencePhotos"],
        "categoryCounts": report["categoryCounts"],
        "unrepresentedCategories": report["unrepresentedCategories"],
        "reasonCounts": report["reasonCounts"],
    }
