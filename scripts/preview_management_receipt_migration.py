"""Read-only counts for the receipt backfill in management migration 0152."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for source in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(ROOT / source))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.management_receipt_backfill import RECEIPT_SCOPE_SQL  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def main() -> int:
    settings = ApiSettings.from_environment()
    engine = create_engine(settings.owner_database_url, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout=10000"))
            head = (
                connection.execute(text("SELECT version_num FROM public.alembic_version"))
                .scalars()
                .all()
            )
            if len(head) != 1 or head[0] not in {"0151_super_game_roles", "0152_super_game_series"}:
                raise RuntimeError(
                    "Receipt migration preview requires a single pre-compact head "
                    "(0151_super_game_roles or 0152_super_game_series)."
                )
            counts = {"journal": 0, "context": 0, "response": 0, "legacy_redacted": 0}
            for category, count in connection.execute(
                text(
                    RECEIPT_SCOPE_SQL + "SELECT category,count(*) FROM classified GROUP BY category"
                )
            ):
                counts[category] = count
            print(
                json.dumps(
                    {
                        "readOnly": True,
                        "currentRevision": head[0],
                        "migration": "0152_management_compact_panel",
                        "receiptCategories": counts,
                        "totalReceipts": sum(counts.values()),
                    },
                    indent=2,
                )
            )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
