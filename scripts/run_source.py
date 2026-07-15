"""Manually crawl+extract one source end-to-end (dev/debug).

Usage: python scripts/run_source.py --source generic_developer_site
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from launch_intel.pipeline.flows import crawl_one_source  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="generic_developer_demo",
        help="Source name as listed in config/sources.yaml",
    )
    args = parser.parse_args()
    asyncio.run(crawl_one_source(args.source))


if __name__ == "__main__":
    main()
