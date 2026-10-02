"""Explicit isolated symbol backup/restore; no application database."""

import argparse
from pathlib import Path

from .annotations import AnnotationStore
from .catalog import Catalog
from .symbol_store import SymbolLabelStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--symbols", required=True, type=Path)
    parser.add_argument("--backup-id")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("action", choices=["backup", "restore"])
    args = parser.parse_args()
    store = SymbolLabelStore(
        args.symbols, AnnotationStore(args.annotations, Catalog(args.snapshot))
    )
    if args.action == "backup":
        print(store.backup().model_dump_json())
    else:
        if not args.backup_id or not args.destination:
            parser.error("restore requires --backup-id and --destination")
        restored = store.restore(args.backup_id, args.destination)
        print(restored.list_labels().model_dump_json())


if __name__ == "__main__":
    main()
