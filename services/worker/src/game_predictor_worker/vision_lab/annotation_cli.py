"""Backup/restore and explicit split freeze; never overwrite a restore destination."""

import argparse
from pathlib import Path

from .annotation_contracts import SplitRequest
from .annotations import AnnotationStore
from .catalog import Catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    restore = commands.add_parser("restore")
    restore.add_argument("backup_id")
    restore.add_argument("new_destination", type=Path)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("request", type=Path)
    args = parser.parse_args()
    store = AnnotationStore(args.annotations, Catalog(args.snapshot))
    if args.command == "backup":
        print(store.backup().model_dump_json())
    elif args.command == "restore":
        restored = store.restore(args.backup_id, args.new_destination)
        print(restored.read().model_dump_json())
    else:
        print(
            store.mutate(
                SplitRequest.model_validate_json(args.request.read_bytes())
            ).model_dump_json()
        )


if __name__ == "__main__":
    main()
