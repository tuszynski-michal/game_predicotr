"""Read-only inventory of legacy paths in stored user-table text/JSON columns."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Error, sql

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.legacy_job_path_migration import connect  # noqa: E402


def normalize_path(value: str) -> str:
    return value.casefold().replace("\\", "/").replace("//", "/").rstrip("/")


def scan(
    prefix: str,
    *,
    seconds: int = 90,
    previous: dict[str, Any] | None = None,
    partition: int = 0,
    partitions: int = 1,
    operational: bool = False,
) -> dict[str, Any]:
    if not 0 <= partition < partitions:
        raise ValueError("Invalid scan partition")
    deadline = time.monotonic() + seconds
    result: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "prefix": prefix,
        "columns": [],
        "matches": [],
        "errors": [],
        "complete": False,
        "table_progress": {},
        "snapshot_scope": "repeatable-read per invocation",
        "scope": "operational-path-columns" if operational else "all-text-json",
    }
    if previous:
        if previous["prefix"] != prefix:
            raise ValueError("Cannot resume a different path inventory")
        if previous.get("scope") != result["scope"]:
            raise ValueError("Cannot resume a different scan scope")
        result["table_progress"] = previous.get("table_progress", {})
        result["started_at"] = previous["started_at"]
    with connect(readonly=True) as connection:
        connection.execute("set transaction isolation level repeatable read")
        result["read_only"] = connection.execute("show transaction_read_only").fetchone()[
            "transaction_read_only"
        ]
        if result["read_only"] != "on":
            raise ValueError("Database scan must be read-only")
        rows = connection.execute("""
            select n.nspname as schema,c.relname as table,a.attname as column,
                   (pg_relation_size(c.oid)/current_setting('block_size')::int)::bigint as pages,
                   b.typname in ('json','jsonb') as json_value
            from pg_attribute a join pg_class c on c.oid=a.attrelid
            join pg_namespace n on n.oid=c.relnamespace
            join pg_type t on t.oid=a.atttypid
            join pg_type b on b.oid=coalesce(nullif(t.typbasetype,0),t.oid)
            left join pg_type e on e.oid=b.typelem
            where c.relkind in ('r','m') and a.attnum>0 and not a.attisdropped
            and n.nspname not like 'pg_%' and n.nspname<>'information_schema'
            and (b.typcategory='S' or b.typname in ('json','jsonb')
                 or e.typcategory='S' or e.typname in ('json','jsonb'))
            order by (n.nspname='public') desc,n.nspname,c.relname,a.attnum
        """).fetchall()
        if operational:
            rows = [
                row
                for row in rows
                if not row["json_value"]
                and re.search(
                    r"(^|_)(paths?|director(?:y|ies)|root|filename|file_name|uri|url|location)($|_)",
                    row["column"],
                    re.IGNORECASE,
                )
            ]
        foreign = connection.execute("""
            select n.nspname,c.relname from pg_class c
            join pg_namespace n on n.oid=c.relnamespace
            where c.relkind='f' and n.nspname not like 'pg_%'
        """).fetchall()
        if foreign:
            result["errors"].append("Foreign tables require a separate path inventory")
        tables: dict[tuple[str, str], list[str]] = {}
        table_pages = {}
        json_columns = set()
        for row in rows:
            tables.setdefault((row["schema"], row["table"]), []).append(row["column"])
            table_pages[(row["schema"], row["table"])] = row["pages"]
            if row["json_value"]:
                json_columns.add((row["schema"], row["table"], row["column"]))
        result["catalog_columns"] = len(rows)
        result["catalog_tables"] = len(tables)
        tables = {
            key: value
            for index, (key, value) in enumerate(tables.items())
            if index % partitions == partition
        }
        result["partition"] = partition
        result["partitions"] = partitions
        expected_columns = sum(len(value) for value in tables.values())
        result["expected_columns"] = expected_columns
        result["expected_tables"] = len(tables)
        last_progress = time.monotonic()
        for (schema, table), columns in tables.items():
            if time.monotonic() >= deadline:
                result["errors"].append("Time budget exhausted")
                break
            key = schema + "." + table
            pages = table_pages[(schema, table)]
            progress = result["table_progress"].setdefault(
                key, {"columns": columns, "next_block": 0, "counts": dict.fromkeys(columns, 0)}
            )
            if progress["columns"] != columns or progress["next_block"] > max(pages, 1):
                raise ValueError("Table changed during resumed scan; start a fresh inventory")
            expressions = []
            parameters = []
            pattern = r"[\\/]+".join(re.escape(part) for part in normalize_path(prefix).split("/"))
            match = "@ like_regex " + json.dumps(pattern) + ' flag "i"'
            for column in columns:
                if (schema, table, column) in json_columns:
                    expressions.append(
                        sql.SQL(
                            "count(*) filter (where jsonb_path_exists({}::jsonb,%s::jsonpath) "
                            "or jsonb_path_exists({}::jsonb,%s::jsonpath)) as {}"
                        ).format(
                            sql.Identifier(column), sql.Identifier(column), sql.Identifier(column)
                        )
                    )
                    parameters.extend(
                        [
                            'strict $.** ? (@.type() == "string" && ' + match + ")",
                            'strict $.** ? (@.type() == "object").keyvalue().key ? (' + match + ")",
                        ]
                    )
                else:
                    expressions.append(
                        sql.SQL(
                            "count(*) filter (where case when {}::text ~* %s then "
                            "strpos(lower(replace(replace({}::text,chr(92),'/'),'//','/')),%s)>0 "
                            "else false end) as {}"
                        ).format(
                            sql.Identifier(column), sql.Identifier(column), sql.Identifier(column)
                        )
                    )
                    parameters.extend(
                        [re.escape(normalize_path(prefix).split("/")[-1]), normalize_path(prefix)]
                    )
            statement = sql.SQL(
                "select {} from only {}.{} where ctid >= %s::tid and ctid < %s::tid"
            ).format(sql.SQL(",").join(expressions), sql.Identifier(schema), sql.Identifier(table))
            try:
                while progress["next_block"] < max(pages, 1) and time.monotonic() < deadline:
                    start = progress["next_block"]
                    end = min(start + (4096 if operational else 32), max(pages, 1))
                    with connection.transaction():
                        counts = connection.execute(
                            statement, parameters + [f"({start},0)", f"({end},0)"]
                        ).fetchone()
                    for column in columns:
                        progress["counts"][column] += counts[column]
                    progress["next_block"] = end
                    if time.monotonic() - last_progress >= 5:
                        print(
                            f"scanned_columns={len(result['columns'])}/{expected_columns} "
                            f"table={key} block={end}/{pages}",
                            flush=True,
                        )
                        last_progress = time.monotonic()
                if progress["next_block"] >= max(pages, 1):
                    for column in columns:
                        location = {"schema": schema, "table": table, "column": column}
                        result["columns"].append(location)
                        if progress["counts"][column]:
                            result["matches"].append(
                                {**location, "count": progress["counts"][column]}
                            )
            except Error as error:
                # Preserve a failed table explicitly; do not label partial coverage complete.
                result["errors"].append(
                    {"schema": schema, "table": table, "error_type": type(error).__name__}
                )
        result["complete"] = not result["errors"] and len(result["columns"]) == expected_columns
    result["finished_at"] = datetime.now(UTC).isoformat()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=90, choices=range(1, 106))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--partition", type=int, default=0)
    parser.add_argument("--partitions", type=int, default=1)
    parser.add_argument("--operational", action="store_true")
    args = parser.parse_args()
    previous = json.loads(args.output.read_text(encoding="utf-8")) if args.resume else None
    result = scan(
        args.prefix,
        seconds=args.seconds,
        previous=previous,
        partition=args.partition,
        partitions=args.partitions,
        operational=args.operational,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("complete", "expected_columns", "expected_tables", "matches", "errors")
            }
        )
    )
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
