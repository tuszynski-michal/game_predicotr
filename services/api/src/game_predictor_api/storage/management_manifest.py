"""Shared management ownership, independent of the frozen game-store manifests."""

VERSION = "management-control-plane-v2"
SHARED_TABLES = frozenset(
    {
        "public.management_points",
        "public.management_machines",
        "public.management_assignments",
        "public.management_operations",
        "public.management_journal",
        "public.management_stake_slots",
        "public.management_result_versions",
        "public.management_search_contexts",
    }
)


def ownership(table: str) -> str:
    if table in SHARED_TABLES:
        return "shared"
    raise ValueError(f"MANAGEMENT_UNKNOWN_TABLE: {table}")
