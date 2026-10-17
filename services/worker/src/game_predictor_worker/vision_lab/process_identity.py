"""Compatibility re-export: the PID identity moved to the neutral training core (TASK-1005)."""

from ..training_core.process_identity import own_identity, process_created

__all__ = ["own_identity", "process_created"]
