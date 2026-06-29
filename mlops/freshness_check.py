"""
Advisory freshness monitor.

scripts/ingest.py writes mlops/last_ingested.json after every successful run.
This module reads that file to compute and report staleness.

Usage:
    python mlops/freshness_check.py          # prints a report
    python mlops/freshness_check.py --alert  # exits with code 1 if stale
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

FRESHNESS_FILE = os.path.join(os.path.dirname(__file__), "last_ingested.json")
STALE_THRESHOLD_HOURS = float(os.environ.get("FRESHNESS_THRESHOLD_HOURS", "24"))


def read_freshness_hours() -> float | None:
    """Return hours since last ingestion, or None if the record doesn't exist."""
    if not os.path.exists(FRESHNESS_FILE):
        return None
    try:
        with open(FRESHNESS_FILE) as f:
            data = json.load(f)
        ts = datetime.fromisoformat(data["timestamp"])
        now = datetime.now(tz=timezone.utc)
        return (now - ts).total_seconds() / 3600
    except Exception:
        return None


def write_freshness(chunks_total: int) -> None:
    """Write the current UTC timestamp to the freshness file."""
    os.makedirs(os.path.dirname(FRESHNESS_FILE), exist_ok=True)
    with open(FRESHNESS_FILE, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "chunks_ingested": chunks_total,
            },
            f,
            indent=2,
        )


def main():
    parser = argparse.ArgumentParser(description="Check advisory knowledge-base freshness")
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Exit with code 1 if the knowledge base is stale",
    )
    args = parser.parse_args()

    hours = read_freshness_hours()

    if hours is None:
        print("WARNING: No ingestion record found at", FRESHNESS_FILE)
        print("         Run  python scripts/ingest.py  to populate the knowledge base.")
        if args.alert:
            sys.exit(1)
        return

    status = "STALE" if hours > STALE_THRESHOLD_HOURS else "OK"
    print(f"Advisory freshness: {hours:.1f} hours since last ingestion  [{status}]")
    print(f"Threshold: {STALE_THRESHOLD_HOURS:.0f} hours")

    if status == "STALE":
        print(f"ACTION REQUIRED: Re-run  python scripts/ingest.py  to refresh the knowledge base.")
        if args.alert:
            sys.exit(1)


if __name__ == "__main__":
    main()
