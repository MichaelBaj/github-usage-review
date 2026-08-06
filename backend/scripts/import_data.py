#!/usr/bin/env python3
"""CLI tool to import a Copilot usage file into the local database.

Supports the same formats as the web UI: .json, .jsonl, .ndjson, .csv,
.db, .sqlite, .sqlite3, and .db.gz (database exports).

Usage:
    python -m scripts.import_data --file path/to/export.csv
    python -m scripts.import_data --file backup.db.gz --mode replace
    python -m scripts.import_data --file data.json --db-path ./data/copilot.db
"""
import sys
from argparse import ArgumentParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import db
from app.importer import ImportValidationError, import_usage_file


DB_EXPORT_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _is_db_export(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".db.gz"):
        return True
    return path.suffix.lower() in DB_EXPORT_SUFFIXES


def main() -> None:
    parser = ArgumentParser(description="Import a Copilot usage file into the local database.")
    parser.add_argument("--file", "-f", required=True, help="Path to the file to import.")
    parser.add_argument(
        "--mode",
        choices=["merge", "replace"],
        default="merge",
        help="For database exports: merge (default) or replace existing data.",
    )
    parser.add_argument("--db-path", help="Override the database path (default: from DB_PATH env/settings).")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    if args.db_path:
        from app.config import settings
        settings.db_path = args.db_path

    db.init()
    content = file_path.read_bytes()

    if _is_db_export(file_path):
        if not db.is_database_export(content):
            print("Error: file does not appear to be a valid database export.", file=sys.stderr)
            sys.exit(1)
        result = db.import_database(content, args.mode)
        tables = result["tables"]
        print(f"Database import ({result['mode']}): {sum(tables.values())} rows across {len(tables)} table(s)")
        for table, count in tables.items():
            print(f"  {table}: {count} rows")
    else:
        try:
            result = import_usage_file(file_path.name, content)
        except ImportValidationError as exc:
            print(f"Validation error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Imported {result['rows_imported']} rows from {result['source_type']}")
        if result.get("date_range"):
            dr = result["date_range"]
            print(f"  Date range: {dr['start']} to {dr['end']}")
        if result.get("skipped_rows"):
            print(f"  Skipped: {result['skipped_rows']} rows")
        if result.get("warnings"):
            for w in result["warnings"][:10]:
                print(f"  Warning: {w}")

    print("Done.")


if __name__ == "__main__":
    main()
