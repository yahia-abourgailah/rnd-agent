"""Collect one source into the catalogue.

    python scripts/collect.py --source nawy
    python scripts/collect.py --source aqarmap --dry-run

--dry-run fetches and maps for real, prints what it would write, and exits
without touching the database. It is the check to run before trusting a new
source or a changed mapping: record counts against the sanity floor, and field
coverage per column.

Exit status is 0 only for a complete run, so a scheduler or CI treats a
below-floor run as the failure it is.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from collect.registry import COLLECTOR_REGISTRY
from pipeline.flows import collect_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(COLLECTOR_REGISTRY), required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and map, report what would be written, write nothing.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap projects collected (smoke test)."
    )
    args = parser.parse_args()

    report = asyncio.run(
        collect_source(args.source, dry_run=args.dry_run, limit=args.limit)
    )

    print(f"\nsource      : {report.source}")
    print(f"stop_reason : {report.stop_reason.value}")
    print(f"counts      : {report.counts}")
    print(f"message     : {report.message}")
    if report.coverage:
        print("coverage    :")
        for field, share in sorted(report.coverage.items(), key=lambda kv: kv[1]):
            print(f"  {field:24} {share:6.1%}")

    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
