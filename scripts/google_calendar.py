#!/usr/bin/env python3
"""Google Calendar helpers for weekly timesheet generation.

Supports:
1) OAuth Desktop credentials (secrets/credentials.json + secrets/token.json)
2) Pre-exported events JSON (--calendar-json) for offline/testing
3) Optional ICS file parse (minimal VEVENT support, no external deps)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_CREDENTIALS = Path("secrets/credentials.json")
DEFAULT_TOKEN = Path("secrets/token.json")
DEFAULT_MAP = Path("config/calendar-project-map.example.json")


@dataclass
class CalendarEvent:
    event_id: str
    summary: str
    description: str
    location: str
    calendar_id: str
    start: datetime
    end: datetime
    status: str
    attendees: list[str] = field(default_factory=list)
    hangout_link: str = ""
    project: str = ""


@dataclass
class CalendarMapConfig:
    default_project: str = "Internal / Meetings"
    calendars: list[str] = field(default_factory=lambda: ["primary"])
    rules: list[dict[str, Any]] = field(default_factory=list)
    exclude_titles: list[str] = field(default_factory=list)
    include_all_day: bool = False
    include_declined: bool = False


def load_map_config(path: Path | None) -> CalendarMapConfig:
    candidates = []
    if path:
        candidates.append(path)
    candidates.extend(
        [
            Path("config/calendar-project-map.json"),
            Path("config/calendar-project-map.example.json"),
        ]
    )
    for cand in candidates:
        if cand.is_file():
            data = json.loads(cand.read_text(encoding="utf-8"))
            return CalendarMapConfig(
                default_project=data.get("default_project", "Internal / Meetings"),
                calendars=list(data.get("calendars") or ["primary"]),
                rules=list(data.get("rules") or []),
                exclude_titles=[x.lower() for x in data.get("exclude_titles") or []],
                include_all_day=bool(data.get("include_all_day", False)),
                include_declined=bool(data.get("include_declined", False)),
            )
    return CalendarMapConfig()


def parse_dt(value: str, tz: ZoneInfo | None = None) -> datetime:
    if len(value) == 8 and value.isdigit():
        # all-day date YYYYMMDD
        dt = datetime.strptime(value, "%Y%m%d").replace(tzinfo=tz or timezone.utc)
        return dt
    if "T" not in value and len(value) == 10:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz or timezone.utc)
        return dt
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz or timezone.utc)
    return dt


def map_event_to_project(event: CalendarEvent, cfg: CalendarMapConfig) -> str:
    blob = " ".join(
        [
            event.summary,
            event.description,
            event.location,
            event.calendar_id,
            " ".join(event.attendees),
        ]
    ).lower()
    for rule in cfg.rules:
        needles = [str(x).lower() for x in rule.get("match") or []]
        if any(n and n in blob for n in needles):
            return str(rule.get("project") or cfg.default_project)
    return cfg.default_project


def should_skip_event(event: CalendarEvent, cfg: CalendarMapConfig) -> bool:
    title = (event.summary or "").lower()
    if any(x and x in title for x in cfg.exclude_titles):
        return True
    if event.status.lower() == "cancelled":
        return True
    if not cfg.include_declined and event.status.lower() == "declined":
        return True
    # all-day heuristic: midnight-to-midnight spanning >= 1 day with no time component originally
    duration = event.end - event.start
    if not cfg.include_all_day and duration >= timedelta(hours=23):
        return True
    if duration <= timedelta(0):
        return True
    return False


def get_calendar_service(credentials_path: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Missing Google API packages. Install with:\n"
            "  pip install -r requirements-timesheet.txt\n"
            f"Original error: {exc}"
        ) from exc

    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            if not credentials_path.is_file():
                raise SystemExit(
                    f"Missing OAuth client file: {credentials_path}\n"
                    "See secrets/README.md for Google Calendar setup."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            # port=0 picks a free port; works on local Ubuntu/WSL with browser
            creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_events_api(
    since: datetime,
    until: datetime,
    cfg: CalendarMapConfig,
    credentials_path: Path,
    token_path: Path,
    tz: ZoneInfo,
) -> list[CalendarEvent]:
    service = get_calendar_service(credentials_path, token_path)
    time_min = since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    time_max = until.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    events: list[CalendarEvent] = []

    for calendar_id in cfg.calendars:
        page_token = None
        while True:
            result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=250,
                    pageToken=page_token,
                )
                .execute()
            )
            for item in result.get("items") or []:
                start_raw = item.get("start", {})
                end_raw = item.get("end", {})
                if "dateTime" in start_raw:
                    start = parse_dt(start_raw["dateTime"], tz)
                elif "date" in start_raw:
                    if not cfg.include_all_day:
                        continue
                    start = parse_dt(start_raw["date"], tz)
                else:
                    continue
                if "dateTime" in end_raw:
                    end = parse_dt(end_raw["dateTime"], tz)
                elif "date" in end_raw:
                    end = parse_dt(end_raw["date"], tz)
                else:
                    continue

                attendees = []
                self_status = item.get("status") or "confirmed"
                for att in item.get("attendees") or []:
                    email = att.get("email") or ""
                    if email:
                        attendees.append(email)
                    if att.get("self") and att.get("responseStatus"):
                        self_status = att["responseStatus"]

                ev = CalendarEvent(
                    event_id=item.get("id") or f"{calendar_id}:{start.isoformat()}",
                    summary=item.get("summary") or "(No title)",
                    description=item.get("description") or "",
                    location=item.get("location") or "",
                    calendar_id=calendar_id,
                    start=start,
                    end=end,
                    status=self_status,
                    attendees=attendees,
                    hangout_link=item.get("hangoutLink")
                    or (item.get("conferenceData") or {})
                    .get("entryPoints", [{}])[0]
                    .get("uri", ""),
                )
                ev.project = map_event_to_project(ev, cfg)
                if not should_skip_event(ev, cfg):
                    events.append(ev)
            page_token = result.get("nextPageToken")
            if not page_token:
                break
    events.sort(key=lambda e: e.start)
    return events


def load_events_json(path: Path, cfg: CalendarMapConfig, tz: ZoneInfo) -> list[CalendarEvent]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    events: list[CalendarEvent] = []
    for item in items or []:
        start = parse_dt(item["start"], tz)
        end = parse_dt(item["end"], tz)
        ev = CalendarEvent(
            event_id=str(item.get("id") or f"json:{start.isoformat()}"),
            summary=item.get("summary") or "(No title)",
            description=item.get("description") or "",
            location=item.get("location") or "",
            calendar_id=item.get("calendar_id") or "json",
            start=start,
            end=end,
            status=item.get("status") or "confirmed",
            attendees=list(item.get("attendees") or []),
            hangout_link=item.get("hangout_link") or "",
        )
        ev.project = item.get("project") or map_event_to_project(ev, cfg)
        if not should_skip_event(ev, cfg):
            events.append(ev)
    events.sort(key=lambda e: e.start)
    return events


def load_events_ics(path: Path, cfg: CalendarMapConfig, tz: ZoneInfo) -> list[CalendarEvent]:
    """Minimal ICS parser for VEVENT blocks (no recurring expansion)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Unfold lines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n[ \t]", "", text)
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.S)
    events: list[CalendarEvent] = []
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.split(";")[0].upper()
            fields[key] = value
        if "DTSTART" not in fields or "DTEND" not in fields:
            continue
        start = parse_dt(fields["DTSTART"], tz)
        end = parse_dt(fields["DTEND"], tz)
        ev = CalendarEvent(
            event_id=fields.get("UID") or f"ics:{start.isoformat()}",
            summary=fields.get("SUMMARY") or "(No title)",
            description=fields.get("DESCRIPTION") or "",
            location=fields.get("LOCATION") or "",
            calendar_id="ics",
            start=start,
            end=end,
            status=(fields.get("STATUS") or "confirmed").lower(),
        )
        ev.project = map_event_to_project(ev, cfg)
        if not should_skip_event(ev, cfg):
            events.append(ev)
    events.sort(key=lambda e: e.start)
    return events


def fetch_calendar_events(
    since: datetime,
    until: datetime,
    *,
    tz_name: str = "Asia/Jakarta",
    map_path: Path | None = None,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    calendar_json: Path | None = None,
    calendar_ics: Path | None = None,
) -> tuple[list[CalendarEvent], list[str]]:
    notes: list[str] = []
    tz = ZoneInfo(tz_name)
    cfg = load_map_config(map_path)

    if calendar_json:
        events = load_events_json(calendar_json, cfg, tz)
        notes.append(f"Calendar source: JSON export ({calendar_json})")
        return events, notes
    if calendar_ics:
        events = load_events_ics(calendar_ics, cfg, tz)
        notes.append(f"Calendar source: ICS export ({calendar_ics})")
        return events, notes

    cred_path = credentials_path or Path(
        os.environ.get("GOOGLE_CREDENTIALS", DEFAULT_CREDENTIALS)
    )
    tok_path = token_path or Path(os.environ.get("GOOGLE_TOKEN", DEFAULT_TOKEN))
    events = fetch_events_api(since, until, cfg, cred_path, tok_path, tz)
    notes.append(
        f"Calendar source: Google Calendar API "
        f"(calendars={', '.join(cfg.calendars)}; events={len(events)})"
    )
    return events, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--timezone", default="Asia/Jakarta")
    parser.add_argument("--map", type=Path, default=None)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--calendar-json", type=Path, default=None)
    parser.add_argument("--calendar-ics", type=Path, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.days)
    events, notes = fetch_calendar_events(
        since,
        now,
        tz_name=args.timezone,
        map_path=args.map,
        credentials_path=args.credentials,
        token_path=args.token,
        calendar_json=args.calendar_json,
        calendar_ics=args.calendar_ics,
    )
    payload = {
        "notes": notes,
        "count": len(events),
        "items": [
            {
                **asdict(e),
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
            }
            for e in events
        ],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    for n in notes:
        print(n, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
