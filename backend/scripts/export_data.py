#!/usr/bin/env python3
"""CLI tool to export the Copilot usage database.

Exports the SQLite database as a gzip-compressed file, identical to
the /api/data/export endpoint.

Usage:
    python -m scripts.export_data --output /tmp/backup.db.gz
    python -m scripts.export_data  # writes to copilot-usage-export-<timestamp>.db.gz
"""
import sys
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import db


def main() -> None:
    parser = ArgumentParser(description="Export the Copilot usage database as gzip'd SQLite.")
    parser.add_argument(
        "--output", "-o",
        help="Output file path. Defaults to timestamped filename in current directory.",
    )
    parser.add_argument("--db-path", help="Override the database path (default: from DB_PATH env/settings).")
    args = parser.parse_args()

    if args.db_path:
        from app.config import settings
        settings.db_path = args.db_path

    db.init()
    payload = db.export_database_gzip()

    if args.output:
        out_path = Path(args.output)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(f"copilot-usage-export-{stamp}.db.gz")

    out_path.write_bytes(payload)
    size_kb = len(payload) / 1024
    print(f"Exported to {out_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
