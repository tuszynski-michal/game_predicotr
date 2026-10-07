"""Shared management ownership, independent of the frozen game-store manifests."""

VERSION = "management-control-plane-v1"
SHARED_TABLES = frozenset(
    {
        "public.management_points",
        "public.management_machines",
        "public.management_assignments",
        "public.management_operations",
        "public.management_journal",
    }
)


def ownership(table: str) -> str:
    if table in SHARED_TABLES:
        return "shared"
    raise ValueError(f"MANAGEMENT_UNKNOWN_TABLE: {table}")
