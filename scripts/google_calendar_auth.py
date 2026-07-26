#!/usr/bin/env python3
"""One-time Google Calendar OAuth login for the timesheet agent.

Usage (on your Ubuntu/WSL machine with a browser):
  pip install -r requirements-timesheet.txt
  # place OAuth Desktop client JSON at secrets/credentials.json
  python3 scripts/google_calendar_auth.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google_calendar import DEFAULT_CREDENTIALS, DEFAULT_TOKEN, fetch_calendar_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--timezone", default="Asia/Jakarta")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    events, notes = fetch_calendar_events(
        now - timedelta(days=7),
        now,
        tz_name=args.timezone,
        credentials_path=args.credentials,
        token_path=args.token,
    )
    print("Authorization OK.")
    for n in notes:
        print("-", n)
    print(f"Fetched {len(events)} events in the last 7 days (sample):")
    for ev in events[:10]:
        print(
            f"  [{ev.project}] {ev.start.isoformat()} → {ev.end.isoformat()} | {ev.summary}"
        )
    if len(events) > 10:
        print(f"  ... +{len(events) - 10} more")
    print(f"\nToken saved to: {args.token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
