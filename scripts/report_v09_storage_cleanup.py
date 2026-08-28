r"""Report v0.9 cleanup relation sizes without changing the database.

Run immediately before and after migration 0075 and retain both JSON outputs::

    .venv\Scripts\python.exe scripts\report_v09_storage_cleanup.py --label before
    .venv\Scripts\python.exe scripts\report_v09_storage_cleanup.py --label after
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine
from sqlalchemy import text

_RELATIONS = (
    "image_board_search_candidates",
    "image_board_search_documents",
    "image_board_search_fast_documents",
    "image_symbol_review_cells",
    "image_symbol_review_events",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, choices=("before", "after"))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def build_report(*, label: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    relations = {
        str(row["relation_name"]): {
            "exists": bool(row["exists"]),
            "tableBytes": int(row["table_bytes"] or 0),
            "indexBytes": int(row["index_bytes"] or 0),
            "totalBytes": int(row["total_bytes"] or 0),
        }
        for row in rows
    }
    return {
        "label": label,
        "relations": relations,
        "totalBytes": sum(item["totalBytes"] for item in relations.values()),
    }


def main() -> int:
    arguments = _arguments()
    engine = create_database_engine(ApiSettings.from_environment())
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    """
                    SELECT relation_name,
                           to_regclass(relation_name) IS NOT NULL AS exists,
                           CASE WHEN to_regclass(relation_name) IS NULL THEN 0
                                ELSE pg_relation_size(to_regclass(relation_name))
                           END AS table_bytes,
                           CASE WHEN to_regclass(relation_name) IS NULL THEN 0
                                ELSE pg_indexes_size(to_regclass(relation_name))
                           END AS index_bytes,
                           CASE WHEN to_regclass(relation_name) IS NULL THEN 0
                                ELSE pg_total_relation_size(to_regclass(relation_name))
                           END AS total_bytes
                    FROM unnest(CAST(:relations AS text[])) AS relation_name
                    ORDER BY relation_name
                    """
                ),
                {"relations": list(_RELATIONS)},
            ).mappings()
        )
    report = build_report(label=arguments.label, rows=rows)
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
