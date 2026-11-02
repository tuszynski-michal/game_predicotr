"""Human labels, connected source families and pilot admission, without storage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from .readability_features import FrozenBase, ReadabilityError, fingerprint

Split = Literal["train", "validation", "test", "audit"]


@dataclass(frozen=True)
class QualitySample:
    cell_id: str
    sequence_number: int
    source_id: str
    source_sha256: str
    rgb_sha256: str
    geometry_identity: str
    import_id: str
    symbol_class: str
    historical_unreadable: bool
    overlap: bool | None
    unreadable: bool | None
    recording_id: str | None = None
    sharp: bool = False
    similar_readable: bool = False
    top1: float | None = None
    # audit200 selection must predate annotation and preserve its random draw receipt.
    previously_unlabelled: bool = False

    def identity(self) -> str:
        return fingerprint(
            {
                "cell": self.cell_id,
                "rgb": self.rgb_sha256,
                "geometry": self.geometry_identity,
                "source": self.source_sha256,
            }
        )


@dataclass(frozen=True)
class CohortSplit:
    samples: tuple[QualitySample, ...]
    assignments: tuple[Split, ...]
    families: tuple[str, ...]
    base_fingerprint: str

    def binding(self) -> dict[str, object]:
        return {
            "samples": [asdict(sample) for sample in self.samples],
            "assignments": list(self.assignments),
            "families": list(self.families),
            "baseFingerprint": self.base_fingerprint,
        }


def assign_families(
    samples: Sequence[QualitySample],
    base: FrozenBase,
    *,
    assignments: Sequence[Split] | None = None,
) -> CohortSplit:
    """Join aliases transitively, including aliases already known to the base model.

    A2 may supply a frozen stratified assignment. Without one this produces a
    deterministic 60/20/20 proposal, prioritising independent TEST. The pilot
    validator rejects a proposal without sufficient coverage; never retries fits.
    """
    if len(samples) > 800:
        raise ReadabilityError(
            "READABILITY_COHORT_LIMIT", "At most 600 pilot plus 200 natural audit cells."
        )
    if not samples or len({s.cell_id for s in samples}) != len(samples):
        raise ReadabilityError(
            "READABILITY_PROVENANCE_INVALID", "Unique nonempty cell inventory required."
        )
    parents: dict[str, str] = {}

    def root(key: str) -> str:
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    def join(keys: list[str]) -> str:
        roots = sorted({root(key) for key in keys})
        for value in roots:
            parents[value] = roots[0]
        return roots[0]

    base_nodes: list[tuple[str, str]] = []
    for row in base.members:
        node = join(
            [
                "source:" + row["sourceId"],
                "sha:" + row["sourceSha256"],
                "rgb:" + row["rgbSha256"],
                "base-family:" + row["family"],
            ]
        )
        base_nodes.append((node, row["split"]))
    nodes: list[str] = []
    for sample in samples:
        if (
            not all(
                (
                    sample.cell_id,
                    sample.source_id,
                    sample.source_sha256,
                    sample.rgb_sha256,
                    sample.geometry_identity,
                    sample.import_id,
                    sample.symbol_class,
                )
            )
            or sample.sequence_number < 1
            or any(type(v) not in (bool, type(None)) for v in (sample.overlap, sample.unreadable))
            or (sample.top1 is not None and not 0 <= sample.top1 <= 1)
        ):
            raise ReadabilityError(
                "READABILITY_PROVENANCE_INVALID", "Missing/invalid cell provenance."
            )
        keys = [
            "source:" + sample.source_id,
            "sha:" + sample.source_sha256,
            "rgb:" + sample.rgb_sha256,
        ]
        if sample.recording_id:
            keys.append("recording:" + sample.recording_id)
        nodes.append(join(keys))
    families = tuple(root(node) for node in nodes)
    base_splits: dict[str, set[str]] = {}
    for node, split in base_nodes:
        base_splits.setdefault(root(node), set()).add(split)
    if any(len(splits) > 1 for splits in base_splits.values()):
        raise ReadabilityError("READABILITY_BASE_LEAKAGE", "Connected base families cross splits.")
    groups = sorted(set(families), key=lambda f: fingerprint(f))
    proposed: dict[str, Split] = {}
    if assignments is None:
        protected = [f for f in groups if base_splits.get(f, set()) & {"test", "regression"}]
        eligible = [f for f in groups if not base_splits.get(f)]
        for family in protected:
            proposed[family] = "test"
        target = max(1, round(len(groups) * 0.2))
        for family in eligible[: max(0, target - len(protected))]:
            proposed[family] = "test"
        remaining = [f for f in groups if f not in proposed]
        for index, family in enumerate(remaining):
            proposed[family] = "validation" if index < max(1, round(len(groups) * 0.2)) else "train"
        assignments = [proposed[f] for f in families]
    if len(assignments) != len(samples):
        raise ReadabilityError("READABILITY_SPLIT_INVALID", "Split inventory differs.")
    for family, split in zip(families, assignments, strict=True):
        if split not in ("train", "validation", "test", "audit"):
            raise ReadabilityError("READABILITY_SPLIT_INVALID", "Unknown split.")
        if proposed.setdefault(family, split) != split:
            raise ReadabilityError("READABILITY_SPLIT_LEAKAGE", "Family crosses head splits.")
        previous = base_splits.get(family, set())
        if (split in ("test", "audit") and previous & {"train", "validation"}) or (
            split in ("train", "validation") and previous & {"test", "regression"}
        ):
            raise ReadabilityError(
                "READABILITY_SPLIT_LEAKAGE", "Head split conflicts with base exposure."
            )
    return CohortSplit(tuple(samples), tuple(assignments), families, fingerprint(base.binding()))


def pilot_issues(cohort: CohortSplit) -> tuple[str, ...]:
    """No empirical claim: validate the frozen human-labelled <=600 pilot only."""
    selected = [
        s for s, split in zip(cohort.samples, cohort.assignments, strict=True) if split != "audit"
    ]
    issues: list[str] = []
    if len(selected) > 600:
        issues.append("pilot_exceeds_600")
    if sum(s.historical_unreadable for s in selected) * 2 != len(selected):
        issues.append("pilot_not_half_historical_unreadable")
    for split in ("train", "validation", "test"):
        indices = [i for i, value in enumerate(cohort.assignments) if value == split]
        groups = {
            "overlap_unreadable": [
                i
                for i in indices
                if cohort.samples[i].overlap is True and cohort.samples[i].unreadable is True
            ],
            "readable": [i for i in indices if cohort.samples[i].unreadable is False],
            "other_unreadable": [
                i
                for i in indices
                if cohort.samples[i].overlap is False and cohort.samples[i].unreadable is True
            ],
        }
        for kind, members in groups.items():
            minimum = 20 if kind == "other_unreadable" else 40
            if split == "train":
                if len({cohort.families[i] for i in members}) < 10:
                    issues.append(f"train_{kind}_families_below_10")
            elif len(members) < minimum:
                issues.append(f"{split}_{kind}_below_{minimum}")
        if (
            split != "train"
            and sum(cohort.samples[i].similar_readable for i in groups["readable"]) < 10
        ):
            issues.append(f"{split}_similar_readable_below_10")
        if split == "test":
            for label, members in (
                ("sharp", [i for i in groups["overlap_unreadable"] if cohort.samples[i].sharp]),
                (
                    "confident",
                    [
                        i
                        for i in groups["overlap_unreadable"]
                        if (cohort.samples[i].top1 or 0) >= 0.95
                    ],
                ),
            ):
                if len(members) < 10 or len({cohort.families[i] for i in members}) < 5:
                    issues.append(f"test_{label}_overlap_insufficient")
    return tuple(issues)
