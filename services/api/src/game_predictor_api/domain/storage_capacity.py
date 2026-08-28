"""Constant-time capacity decisions for managed image storage."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


@dataclass(frozen=True, slots=True)
class StorageCapacityPolicy:
    warning_bytes: int = 80 * GIB
    automatic_gc_bytes: int = 60 * GIB
    target_bytes: int = 80 * GIB
    hard_reserve_bytes: int = 30 * GIB
    conservative_multiplier: int = 8
    safety_percent: int = 20

    def __post_init__(self) -> None:
        if not (
            0 < self.hard_reserve_bytes < self.automatic_gc_bytes <= self.warning_bytes
            and self.target_bytes >= self.warning_bytes
            and self.conservative_multiplier >= 1
            and self.safety_percent >= 0
        ):
            raise ValueError("Storage capacity thresholds are inconsistent.")


@dataclass(frozen=True, slots=True)
class StorageVolumeCapacity:
    key: str
    root: Path
    free_bytes: int
    required_bytes: int


@dataclass(frozen=True, slots=True)
class StorageCapacityDecision:
    volumes: tuple[StorageVolumeCapacity, ...]
    warning: bool
    automatic_gc_required: bool
    permitted: bool
    estimated_bytes: int


def conservative_image_storage_estimate(input_bytes: int, *, policy: StorageCapacityPolicy) -> int:
    if input_bytes < 0:
        raise ValueError("input_bytes must not be negative.")
    base = input_bytes * policy.conservative_multiplier
    return base + (base * policy.safety_percent + 99) // 100


def evaluate_storage_capacity(
    roots: Mapping[str, Path],
    *,
    estimated_bytes: int,
    policy: StorageCapacityPolicy,
) -> StorageCapacityDecision:
    """Evaluate each distinct volume once and never double-count shared roots."""

    if estimated_bytes < 0:
        raise ValueError("estimated_bytes must not be negative.")
    distinct: dict[str, tuple[Path, int]] = {}
    for root in roots.values():
        resolved = root.resolve()
        key = (resolved.drive or resolved.anchor).casefold()
        if key not in distinct:
            distinct[key] = (resolved, shutil.disk_usage(resolved).free)
    volumes = tuple(
        StorageVolumeCapacity(key=key, root=root, free_bytes=free, required_bytes=estimated_bytes)
        for key, (root, free) in sorted(distinct.items())
    )
    warning = any(item.free_bytes < policy.warning_bytes for item in volumes)
    automatic_gc_required = any(
        item.free_bytes < policy.automatic_gc_bytes for item in volumes
    )
    permitted = all(
        item.free_bytes - item.required_bytes >= policy.hard_reserve_bytes
        for item in volumes
    )
    return StorageCapacityDecision(
        volumes=volumes,
        warning=warning,
        automatic_gc_required=automatic_gc_required,
        permitted=permitted,
        estimated_bytes=estimated_bytes,
    )


__all__ = [
    "GIB",
    "StorageCapacityDecision",
    "StorageCapacityPolicy",
    "StorageVolumeCapacity",
    "conservative_image_storage_estimate",
    "evaluate_storage_capacity",
]
