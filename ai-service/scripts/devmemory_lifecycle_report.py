"""Print a read-only aggregate lifecycle report for a local AI SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lifecycle_report import build_devmemory_lifecycle_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="Optional AI SQLite path; defaults to AI_NOTES_DB.")
    args = parser.parse_args()
    print(json.dumps(build_devmemory_lifecycle_report(args.database), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
