"""Application guard for image-producing operations under disk pressure."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.storage_capacity import (
    StorageCapacityDecision,
    StorageCapacityPolicy,
    conservative_image_storage_estimate,
    evaluate_storage_capacity,
)


class StorageCapacityGuard:
    def __init__(
        self,
        roots: Mapping[str, Path],
        *,
        policy: StorageCapacityPolicy,
        ensure_automatic_gc: Callable[[], object] | None = None,
    ) -> None:
        self._roots = dict(roots)
        self._policy = policy
        self._ensure_automatic_gc = ensure_automatic_gc

    @property
    def policy(self) -> StorageCapacityPolicy:
        return self._policy

    def check_image_write(self, input_bytes: int) -> StorageCapacityDecision:
        decision = evaluate_storage_capacity(
            self._roots,
            estimated_bytes=conservative_image_storage_estimate(
                input_bytes, policy=self._policy
            ),
            policy=self._policy,
        )
        if decision.automatic_gc_required and self._ensure_automatic_gc is not None:
            self._ensure_automatic_gc()
        if not decision.permitted:
            raise JobConflictError(
                "STORAGE_CAPACITY_INSUFFICIENT",
                "There is not enough managed storage capacity to start this image operation.",
                details={
                    "estimatedBytes": decision.estimated_bytes,
                    "hardReserveBytes": self._policy.hard_reserve_bytes,
                    "volumes": [
                        {
                            "root": str(item.root),
                            "freeBytes": item.free_bytes,
                            "requiredBytes": item.required_bytes,
                        }
                        for item in decision.volumes
                    ],
                },
            )
        return decision


__all__ = ["StorageCapacityGuard"]
