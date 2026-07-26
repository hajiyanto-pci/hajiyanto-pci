#!/usr/bin/env python3
"""Weekly professional timesheet from git activity + Google Calendar.

Scans a git home directory (default: /home/haji/git — Ubuntu-22.04/WSL),
optionally merges Google Calendar meetings, groups work by project/workspace,
and emits timesheet lines with a hard maximum of 2.0 hours per line.
Longer sessions/meetings are broken down into multiple detailed entries.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google_calendar import CalendarEvent, fetch_calendar_events  # noqa: E402


# User's WSL/Ubuntu git workspace + cloud fallbacks
DEFAULT_GIT_HOME_CANDIDATES = (
    Path("/home/haji/git"),
    Path("/git"),
    Path("/workspace"),
)

SESSION_GAP = timedelta(minutes=90)
PRE_BUFFER = timedelta(minutes=25)
POST_BUFFER = timedelta(minutes=20)
MAX_LINE_HOURS = 2.0
MIN_LINE_HOURS = 0.25
HOUR_STEP = 0.25


@dataclass
class CommitEvent:
    sha: str
    dt: datetime
    author: str
    subject: str
    insertions: int = 0
    deletions: int = 0


@dataclass
class WorkSession:
    project: str
    repo_path: str
    start: datetime
    end: datetime
    commits: list[CommitEvent]
    branches: list[str] = field(default_factory=list)


@dataclass
class TimesheetLine:
    date: str
    project: str
    workspace: str
    start_time: str
    end_time: str
    hours: float
    description: str
    evidence: str
    part: int
    parts_total: int
    source: str = "git"  # git | calendar


@dataclass
class ProjectBundle:
    project: str
    repo_path: str
    remote: str
    commit_count: int
    meeting_count: int = 0
    lines: list[TimesheetLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class TimesheetReport:
    generated_at: str
    since: str
    until: str
    timezone: str
    git_home: str
    max_line_hours: float
    total_hours: float
    calendar_enabled: bool = False
    calendar_event_count: int = 0
    projects: list[ProjectBundle] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def normalize_git_home_arg(raw: str | None) -> Path | None:
    """Accept Linux, WSL, or Windows-style paths for the user's git folder."""
    if not raw:
        return None
    text = raw.strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    # Ubuntu-22.04/home/haji/git or \\wsl$\Ubuntu-22.04\home\haji\git
    m = re.search(r"(?:Ubuntu-[\d.]+/)?home/[^/]+/git/?$", text, re.I)
    if m and not text.startswith("/"):
        # Map WSL-style to Linux path
        home_git = "/" + text.split("home/", 1)[1] if "home/" in text.lower() else text
        if not home_git.startswith("/home/"):
            home_git = "/home/" + text.split("home/", 1)[1]
        return Path(home_git)
    if text.lower().startswith("ubuntu-") and "/home/" in text.lower():
        idx = text.lower().index("/home/")
        return Path(text[idx:])
    return Path(text).expanduser()


def resolve_git_home(explicit: str | None = None) -> tuple[Path, list[str]]:
    notes: list[str] = []
    candidates: list[Path] = []
    norm = normalize_git_home_arg(explicit or os.environ.get("GIT_HOME"))
    if norm:
        candidates.append(norm)
    candidates.extend(DEFAULT_GIT_HOME_CANDIDATES)

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_dir():
            return cand.resolve(), notes

    # Last resort: current repo root's parent if named git, else cwd
    proc = run(["git", "rev-parse", "--show-toplevel"])
    if proc.returncode == 0 and proc.stdout.strip():
        root = Path(proc.stdout.strip()).resolve()
        notes.append(
            f"GIT_HOME tidak ditemukan di path user; fallback ke repo aktif: {root}"
        )
        return root, notes

    raise SystemExit(
        "Tidak menemukan folder git home. Set --git-home /home/haji/git "
        "atau environment GIT_HOME."
    )


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists() or (path / ".git").is_file()


def discover_repos(git_home: Path) -> list[Path]:
    """Discover project workspaces under git home (depth 1–2)."""
    if is_git_repo(git_home):
        return [git_home]

    repos: list[Path] = []
    try:
        children = sorted(git_home.iterdir())
    except OSError:
        return []

    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        if is_git_repo(child):
            repos.append(child)
            continue
        # One more level for grouped workspaces: git/client/project
        try:
            for nested in sorted(child.iterdir()):
                if nested.is_dir() and not nested.name.startswith(".") and is_git_repo(nested):
                    repos.append(nested)
        except OSError:
            continue
    return repos


def redact_remote(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def collect_commits(repo: Path, since: str, until: str) -> list[CommitEvent]:
    fmt = "%H|%ad|%an <%ae>|%s"
    proc = run(
        [
            "git",
            "log",
            "--all",
            f"--since={since}",
            f"--until={until}",
            f"--pretty=format:{fmt}",
            "--date=iso-strict",
            "--numstat",
        ],
        cwd=repo,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    events: list[CommitEvent] = []
    current: CommitEvent | None = None
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        if "|" in line and re.match(r"^[0-9a-f]{7,40}\|", line):
            if current:
                events.append(current)
            sha, date, author, subject = line.split("|", 3)
            current = CommitEvent(
                sha=sha[:8],
                dt=parse_dt(date),
                author=author,
                subject=subject,
            )
            continue
        if current and "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 2:
                ins, deleted = parts[0], parts[1]
                if ins.isdigit():
                    current.insertions += int(ins)
                if deleted.isdigit():
                    current.deletions += int(deleted)
    if current:
        events.append(current)

    events.sort(key=lambda e: e.dt)
    return events


def collect_pushed_branches(repo: Path, since: str, until: str) -> list[str]:
    proc = run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)|%(committerdate:iso-strict)",
            "refs/remotes/origin",
        ],
        cwd=repo,
    )
    if proc.returncode != 0:
        return []
    since_dt = parse_dt(since)
    until_dt = parse_dt(until)
    names: list[str] = []
    for line in proc.stdout.splitlines():
        if "|" not in line:
            continue
        name, date = line.split("|", 1)
        try:
            tip = parse_dt(date)
        except ValueError:
            continue
        if since_dt <= tip <= until_dt and not name.endswith("/HEAD"):
            names.append(name)
    return names


def round_hours(hours: float) -> float:
    if hours <= 0:
        return MIN_LINE_HOURS
    steps = max(1, int(round(hours / HOUR_STEP)))
    value = steps * HOUR_STEP
    return max(MIN_LINE_HOURS, min(value, 24.0))


def cluster_sessions(
    project: str,
    repo: Path,
    commits: list[CommitEvent],
    branches: list[str],
) -> list[WorkSession]:
    if not commits:
        return []

    sessions: list[WorkSession] = []
    bucket: list[CommitEvent] = [commits[0]]
    for commit in commits[1:]:
        if commit.dt - bucket[-1].dt > SESSION_GAP:
            sessions.append(_session_from_bucket(project, repo, bucket, branches))
            bucket = [commit]
        else:
            bucket.append(commit)
    sessions.append(_session_from_bucket(project, repo, bucket, branches))
    return sessions


def _session_from_bucket(
    project: str,
    repo: Path,
    bucket: list[CommitEvent],
    branches: list[str],
) -> WorkSession:
    start = bucket[0].dt - PRE_BUFFER
    end = bucket[-1].dt + POST_BUFFER
    if end <= start:
        end = start + timedelta(minutes=30)
    return WorkSession(
        project=project,
        repo_path=str(repo),
        start=start,
        end=end,
        commits=list(bucket),
        branches=branches,
    )


def professional_description(
    project: str,
    commits: list[CommitEvent],
    branches: list[str],
    part: int,
    parts_total: int,
    tz: ZoneInfo,
) -> str:
    subjects = [c.subject.rstrip(".") for c in commits]
    unique_subjects: list[str] = []
    for s in subjects:
        if s not in unique_subjects:
            unique_subjects.append(s)

    focus = "; ".join(unique_subjects[:4])
    if len(unique_subjects) > 4:
        focus += f"; and {len(unique_subjects) - 4} related follow-up changes"

    ins = sum(c.insertions for c in commits)
    deleted = sum(c.deletions for c in commits)
    branch_txt = ", ".join(branches[:3]) if branches else "feature branches"
    sha_txt = ", ".join(c.sha for c in commits[:5])
    if len(commits) > 5:
        sha_txt += f", +{len(commits) - 5} more"

    local_start = commits[0].dt.astimezone(tz).strftime("%H:%M")
    local_end = commits[-1].dt.astimezone(tz).strftime("%H:%M")
    part_note = (
        f" (segment {part}/{parts_total} of a longer delivery block; each timesheet "
        f"line capped at {MAX_LINE_HOURS:g} hours for billing clarity)"
        if parts_total > 1
        else ""
    )

    return (
        f"Project workspace `{project}`: continued hands-on engineering on the active "
        f"codebase, covering implementation, validation, and remote synchronization for "
        f"the workstream reflected by commits [{sha_txt}]. Primary delivery focus included "
        f"{focus}. "
        f"Activities in this block spanned requirements clarification with AI-assisted "
        f"prompts, iterative coding against `{branch_txt}`, local verification of behavior, "
        f"and preparing/pushing changes for review. "
        f"Observed code churn in-scope for this segment: approximately +{ins}/-{deleted} "
        f"lines across the touched files. "
        f"Commit timestamps (local {tz.key}) clustered around {local_start}–{local_end}"
        f"{part_note}. "
        f"Documentation of intent was kept aligned with the commit messages to support "
        f"traceability for weekly timesheet reporting and stakeholder status updates."
    )


def allocate_hour_chunks(total_hours: float, max_line_hours: float) -> list[float]:
    """Split hours into <= max_line_hours chunks, preferring balanced parts."""
    total_hours = round_hours(min(total_hours, 8.0))
    if total_hours <= max_line_hours:
        return [total_hours]

    parts = max(2, int(math.ceil(total_hours / max_line_hours)))
    # Prefer balanced chunks (e.g. 2.25 -> 1.25 + 1.00, not 2.00 + 0.25)
    raw = total_hours / parts
    chunks = [round_hours(raw) for _ in range(parts)]
    # Fix rounding drift on the last chunk
    drift = round(total_hours - sum(chunks), 2)
    chunks[-1] = round(chunks[-1] + drift, 2)
    if chunks[-1] <= 0:
        chunks[-1] = MIN_LINE_HOURS
    # Enforce ceiling; if last exceeds max, redistribute
    fixed: list[float] = []
    carry = 0.0
    for h in chunks:
        h = round(h + carry, 2)
        carry = 0.0
        if h > max_line_hours:
            carry = round(h - max_line_hours, 2)
            h = max_line_hours
        fixed.append(float(f"{h:.2f}"))
    while carry >= MIN_LINE_HOURS:
        piece = min(max_line_hours, carry)
        fixed.append(float(f"{piece:.2f}"))
        carry = round(carry - piece, 2)
    return [h for h in fixed if h > 0]


def overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0.0
    return (end - start).total_seconds()


def subtract_meetings_from_session(
    session: WorkSession,
    meetings: list[CalendarEvent],
) -> list[WorkSession]:
    """Remove calendar-occupied ranges from git-estimated sessions for accuracy."""
    relevant = [
        m
        for m in meetings
        if m.end > session.start and m.start < session.end
    ]
    if not relevant:
        return [session]

    points = sorted(
        {session.start, session.end, *[m.start for m in relevant], *[m.end for m in relevant]}
    )
    free_ranges: list[tuple[datetime, datetime]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if b <= a:
            continue
        if a < session.start or b > session.end:
            continue
        covered = any(overlap_seconds(a, b, m.start, m.end) > 0 for m in relevant)
        if not covered:
            free_ranges.append((a, b))

    # Merge contiguous free ranges
    merged: list[tuple[datetime, datetime]] = []
    for a, b in free_ranges:
        if not merged or a > merged[-1][1]:
            merged.append((a, b))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))

    result: list[WorkSession] = []
    for a, b in merged:
        if (b - a) < timedelta(minutes=15):
            continue
        commits = [c for c in session.commits if a <= c.dt <= b]
        if not commits:
            # keep a slice only if original session had nearby commits
            commits = [
                c
                for c in session.commits
                if abs((c.dt - a).total_seconds()) < 3 * 3600
                or abs((c.dt - b).total_seconds()) < 3 * 3600
            ][:1]
        if not commits:
            continue
        result.append(
            WorkSession(
                project=session.project,
                repo_path=session.repo_path,
                start=a,
                end=b,
                commits=commits or session.commits[:1],
                branches=session.branches,
            )
        )
    return result or [session]


def split_session_to_lines(
    session: WorkSession,
    tz: ZoneInfo,
    max_line_hours: float = MAX_LINE_HOURS,
) -> list[TimesheetLine]:
    total_seconds = (session.end - session.start).total_seconds()
    total_hours = round_hours(total_seconds / 3600.0)
    chunk_hours = allocate_hour_chunks(total_hours, max_line_hours)
    parts_total = len(chunk_hours)

    # Distribute commits across parts proportionally
    n = len(session.commits)
    lines: list[TimesheetLine] = []
    cursor = session.start
    commit_idx = 0
    for part_i, hours in enumerate(chunk_hours, start=1):
        end = cursor + timedelta(hours=hours)
        # Slice commits for this part
        target_end_idx = int(round(part_i * n / parts_total)) if parts_total else n
        target_end_idx = max(commit_idx + 1, min(n, target_end_idx))
        part_commits = session.commits[commit_idx:target_end_idx] or session.commits[-1:]
        commit_idx = target_end_idx

        local_start = cursor.astimezone(tz)
        local_end = end.astimezone(tz)
        evidence = "; ".join(f"{c.sha} {c.subject}" for c in part_commits[:6])
        lines.append(
            TimesheetLine(
                date=local_start.strftime("%Y-%m-%d"),
                project=session.project,
                workspace=session.repo_path,
                start_time=local_start.strftime("%H:%M"),
                end_time=local_end.strftime("%H:%M"),
                hours=float(f"{hours:.2f}"),
                description=professional_description(
                    session.project,
                    part_commits,
                    session.branches,
                    part_i,
                    parts_total,
                    tz,
                ),
                evidence=evidence,
                part=part_i,
                parts_total=parts_total,
                source="git",
            )
        )
        cursor = end
    return lines


def meeting_description(
    event: CalendarEvent,
    part: int,
    parts_total: int,
    tz: ZoneInfo,
) -> str:
    attendees = ", ".join(event.attendees[:8]) if event.attendees else "internal participants"
    if event.attendees and len(event.attendees) > 8:
        attendees += f", +{len(event.attendees) - 8} more"
    agenda = re.sub(r"<[^>]+>", " ", event.description or "")
    agenda = re.sub(r"\s+", " ", agenda).strip()
    if len(agenda) > 420:
        agenda = agenda[:417] + "..."
    if not agenda:
        agenda = (
            "Working session / meeting aligned to the scheduled calendar agenda, "
            "including discussion of progress, decisions, and follow-up actions."
        )
    location = event.location or event.hangout_link or "online/offline per invite"
    local_start = event.start.astimezone(tz).strftime("%H:%M")
    local_end = event.end.astimezone(tz).strftime("%H:%M")
    part_note = (
        f" This timesheet line is segment {part}/{parts_total} of a longer meeting "
        f"(each line capped at {MAX_LINE_HOURS:g} hours)."
        if parts_total > 1
        else ""
    )
    return (
        f"Calendar meeting for project `{event.project}`: participated in "
        f"\"{event.summary}\" ({local_start}–{local_end} {tz.key}). "
        f"Location/channel: {location}. Attendees: {attendees}. "
        f"Agenda and discussion notes: {agenda} "
        f"Outcomes from this block include alignment on priorities, clarification of "
        f"requirements/blockers, and agreed next actions for delivery follow-up."
        f"{part_note}"
    )


def calendar_event_to_lines(
    event: CalendarEvent,
    tz: ZoneInfo,
    max_line_hours: float,
) -> list[TimesheetLine]:
    total_hours = round_hours((event.end - event.start).total_seconds() / 3600.0)
    chunk_hours = allocate_hour_chunks(total_hours, max_line_hours)
    parts_total = len(chunk_hours)
    lines: list[TimesheetLine] = []
    cursor = event.start
    for part_i, hours in enumerate(chunk_hours, start=1):
        end = min(event.end, cursor + timedelta(hours=hours))
        # Keep wall-clock aligned to real meeting where possible for first/last parts
        if part_i == parts_total:
            end = event.end
            hours = round_hours((end - cursor).total_seconds() / 3600.0)
            hours = min(hours, max_line_hours)
        local_start = cursor.astimezone(tz)
        local_end = end.astimezone(tz)
        evidence = (
            f"gcal:{event.event_id} | {event.summary} | "
            f"{event.start.isoformat()} → {event.end.isoformat()}"
        )
        lines.append(
            TimesheetLine(
                date=local_start.strftime("%Y-%m-%d"),
                project=event.project,
                workspace=f"calendar:{event.calendar_id}",
                start_time=local_start.strftime("%H:%M"),
                end_time=local_end.strftime("%H:%M"),
                hours=float(f"{hours:.2f}"),
                description=meeting_description(event, part_i, parts_total, tz),
                evidence=evidence,
                part=part_i,
                parts_total=parts_total,
                source="calendar",
            )
        )
        cursor = end
    return lines


def remote_repo_name(repo: Path) -> str | None:
    proc = run(["git", "remote", "get-url", "origin"], cwd=repo)
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip().rstrip("/")
    if not url:
        return None
    name = url.split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or None


def project_name(repo: Path, git_home: Path) -> str:
    repo_r = repo.resolve()
    home_r = git_home.resolve()
    if repo_r == home_r:
        # Single-repo fallback (cloud often mounts one repo at /workspace)
        return remote_repo_name(repo_r) or repo_r.name or "workspace"
    try:
        rel = repo_r.relative_to(home_r)
        text = str(rel).replace("\\", "/")
        if text not in {".", ""}:
            return text
        return remote_repo_name(repo_r) or repo_r.name
    except ValueError:
        return remote_repo_name(repo_r) or repo_r.name


def build_project_bundle(
    repo: Path,
    git_home: Path,
    since: str,
    until: str,
    tz: ZoneInfo,
    max_line_hours: float,
    meetings: list[CalendarEvent] | None = None,
) -> ProjectBundle | None:
    commits = collect_commits(repo, since, until)
    if not commits:
        return None

    remote_proc = run(["git", "remote", "get-url", "origin"], cwd=repo)
    remote = redact_remote(remote_proc.stdout.strip()) if remote_proc.returncode == 0 else ""
    branches = collect_pushed_branches(repo, since, until)
    name = project_name(repo, git_home)
    sessions = cluster_sessions(name, repo, commits, branches)

    lines: list[TimesheetLine] = []
    for session in sessions:
        adjusted = (
            subtract_meetings_from_session(session, meetings or [])
            if meetings
            else [session]
        )
        for piece in adjusted:
            lines.extend(split_session_to_lines(piece, tz, max_line_hours=max_line_hours))

    notes: list[str] = []
    if branches:
        notes.append("Remote tips updated (push activity): " + ", ".join(branches))
    if meetings:
        notes.append(
            "Git session estimates reduced where they overlapped Google Calendar meetings."
        )

    return ProjectBundle(
        project=name,
        repo_path=str(repo),
        remote=remote,
        commit_count=len(commits),
        meeting_count=0,
        lines=lines,
        notes=notes,
    )


def merge_meeting_lines(
    projects: list[ProjectBundle],
    meeting_lines: list[TimesheetLine],
) -> list[ProjectBundle]:
    by_name = {p.project.lower(): p for p in projects}
    for line in meeting_lines:
        key = line.project.lower()
        if key not in by_name:
            bundle = ProjectBundle(
                project=line.project,
                repo_path=line.workspace,
                remote="",
                commit_count=0,
                meeting_count=0,
                lines=[],
                notes=["Project created from Google Calendar meetings only."],
            )
            projects.append(bundle)
            by_name[key] = bundle
        bundle = by_name[key]
        bundle.lines.append(line)
        bundle.meeting_count += 1 if line.part == 1 else 0

    for bundle in projects:
        bundle.lines.sort(key=lambda l: (l.date, l.start_time, l.source, l.part))
    projects.sort(key=lambda p: p.project.lower())
    return projects


def build_timesheet(
    days: int,
    git_home_arg: str | None,
    tz_name: str,
    max_line_hours: float,
    *,
    calendar: bool = False,
    calendar_map: str | None = None,
    calendar_json: str | None = None,
    calendar_ics: str | None = None,
    credentials: str | None = None,
    token: str | None = None,
) -> TimesheetReport:
    git_home, notes = resolve_git_home(git_home_arg)
    tz = ZoneInfo(tz_name)
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)
    since = since_dt.isoformat().replace("+00:00", "Z")
    until = now.isoformat().replace("+00:00", "Z")

    repos = discover_repos(git_home)
    if not repos:
        notes.append(f"Tidak ada repository git di bawah {git_home}")

    # Prefer expected user path messaging
    expected = Path("/home/haji/git")
    if git_home != expected and not expected.exists():
        notes.append(
            "Path target user `/home/haji/git` (Ubuntu-22.04\\\\home\\\\haji\\\\git) "
            f"tidak tersedia di environment ini; memakai `{git_home}`."
        )

    meetings: list[CalendarEvent] = []
    calendar_enabled = False
    if calendar or calendar_json or calendar_ics:
        calendar_enabled = True
        try:
            meetings, cal_notes = fetch_calendar_events(
                since_dt,
                now,
                tz_name=tz_name,
                map_path=Path(calendar_map) if calendar_map else None,
                credentials_path=Path(credentials) if credentials else None,
                token_path=Path(token) if token else None,
                calendar_json=Path(calendar_json) if calendar_json else None,
                calendar_ics=Path(calendar_ics) if calendar_ics else None,
            )
            notes.extend(cal_notes)
        except SystemExit as exc:
            notes.append(f"Google Calendar unavailable: {exc}")
            meetings = []
        except Exception as exc:  # noqa: BLE001 - keep timesheet usable offline
            notes.append(f"Google Calendar error: {exc}")
            meetings = []

    projects: list[ProjectBundle] = []
    for repo in repos:
        bundle = build_project_bundle(
            repo,
            git_home,
            since,
            until,
            tz,
            max_line_hours=max_line_hours,
            meetings=meetings,
        )
        if bundle:
            projects.append(bundle)

    meeting_lines: list[TimesheetLine] = []
    for event in meetings:
        meeting_lines.extend(calendar_event_to_lines(event, tz, max_line_hours))
    projects = merge_meeting_lines(projects, meeting_lines)

    total = round(sum(line.hours for p in projects for line in p.lines), 2)

    # Validate max line constraint
    for p in projects:
        for line in p.lines:
            if line.hours > max_line_hours + 1e-9:
                notes.append(
                    f"WARNING: line exceeds max hours in {p.project}: {line.hours}"
                )

    return TimesheetReport(
        generated_at=until,
        since=since,
        until=until,
        timezone=tz_name,
        git_home=str(git_home),
        max_line_hours=max_line_hours,
        total_hours=total,
        calendar_enabled=calendar_enabled,
        calendar_event_count=len(meetings),
        projects=projects,
        notes=notes,
    )


def render_markdown(report: TimesheetReport) -> str:
    lines = [
        "# Weekly Timesheet",
        "",
        f"- Period (UTC): `{report.since}` → `{report.until}`",
        f"- Display timezone: `{report.timezone}`",
        f"- Git home / workspace root: `{report.git_home}`",
        f"- Google Calendar: "
        f"{'enabled (' + str(report.calendar_event_count) + ' events)' if report.calendar_enabled else 'disabled'}",
        f"- Max hours per timesheet line: **{report.max_line_hours:g}h** "
        "(longer blocks are split)",
        f"- Total hours: **{report.total_hours:g}**",
        f"- Projects with activity: **{len(report.projects)}**",
        "",
        "## Summary by project",
        "",
    ]
    if not report.projects:
        lines.append("_No project activity found in this period._")
    else:
        lines.append("| Project | Commits | Meetings | Hours | Lines |")
        lines.append("|---|---:|---:|---:|---:|")
        for p in report.projects:
            hours = round(sum(l.hours for l in p.lines), 2)
            lines.append(
                f"| `{p.project}` | {p.commit_count} | {p.meeting_count} | "
                f"{hours:g} | {len(p.lines)} |"
            )

    for p in report.projects:
        proj_hours = round(sum(l.hours for l in p.lines), 2)
        git_hours = round(sum(l.hours for l in p.lines if l.source == "git"), 2)
        cal_hours = round(sum(l.hours for l in p.lines if l.source == "calendar"), 2)
        lines.extend(
            [
                "",
                f"## Project: `{p.project}`",
                "",
                f"- Workspace: `{p.repo_path}`",
                f"- Remote: `{p.remote or '(none)'}`",
                f"- Commits in period: **{p.commit_count}**",
                f"- Meetings in period: **{p.meeting_count}**",
                f"- Hours breakdown: git **{git_hours:g}h** + calendar **{cal_hours:g}h** "
                f"= **{proj_hours:g}h**",
                "",
                "| Date | Start | End | Hours | Source | Description |",
                "|---|---|---|---:|---|---|",
            ]
        )
        for line in p.lines:
            desc = line.description.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {line.date} | {line.start_time} | {line.end_time} | "
                f"{line.hours:g} | `{line.source}` | {desc} |"
            )
        lines.extend(["", "### Evidence", ""])
        for line in p.lines:
            label = (
                f"Part {line.part}/{line.parts_total}"
                if line.parts_total > 1
                else "Entry"
            )
            lines.append(
                f"- **{line.date} {line.start_time}–{line.end_time}** "
                f"(`{line.source}`, {label}, {line.hours:g}h): {line.evidence}"
            )
        if p.notes:
            lines.extend(["", "### Notes", ""])
            for n in p.notes:
                lines.append(f"- {n}")

    if report.notes:
        lines.extend(["", "## Generator notes", ""])
        for n in report.notes:
            lines.append(f"- {n}")

    lines.append("")
    return "\n".join(lines)


def write_csv(report: TimesheetReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "date",
                "project",
                "workspace",
                "start_time",
                "end_time",
                "hours",
                "source",
                "description",
                "evidence",
                "part",
                "parts_total",
            ],
        )
        writer.writeheader()
        for project in report.projects:
            for line in project.lines:
                row = asdict(line)
                writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument(
        "--git-home",
        default=os.environ.get("GIT_HOME", "/home/haji/git"),
        help="Parent folder of project repos (default: /home/haji/git)",
    )
    parser.add_argument(
        "--timezone",
        default=os.environ.get("TIMESHEET_TZ", "Asia/Jakarta"),
        help="Timezone for timesheet display (default: Asia/Jakarta)",
    )
    parser.add_argument(
        "--max-line-hours",
        type=float,
        default=MAX_LINE_HOURS,
        help="Maximum hours per timesheet line (default: 2.0)",
    )
    parser.add_argument(
        "--calendar",
        action="store_true",
        help="Merge Google Calendar meetings (OAuth via secrets/credentials.json)",
    )
    parser.add_argument(
        "--calendar-map",
        default=os.environ.get("CALENDAR_PROJECT_MAP"),
        help="Path to calendar→project mapping JSON",
    )
    parser.add_argument(
        "--calendar-json",
        help="Use exported calendar events JSON instead of live API",
    )
    parser.add_argument(
        "--calendar-ics",
        help="Use exported .ics calendar file instead of live API",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_CREDENTIALS", "secrets/credentials.json"),
        help="OAuth client secrets JSON path",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GOOGLE_TOKEN", "secrets/token.json"),
        help="OAuth token JSON path",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
    )
    parser.add_argument("-o", "--output", help="Write markdown/json report path")
    parser.add_argument("--csv", help="Also write CSV timesheet to this path")
    args = parser.parse_args(argv)

    if args.max_line_hours <= 0 or args.max_line_hours > 2.0001:
        # Allow override below 2, but warn/enforce professional policy default ceiling
        if args.max_line_hours > 2.0001:
            print(
                "Policy: max line hours cannot exceed 2.0; clamping to 2.0",
                file=sys.stderr,
            )
            args.max_line_hours = 2.0

    report = build_timesheet(
        days=args.days,
        git_home_arg=args.git_home,
        tz_name=args.timezone,
        max_line_hours=args.max_line_hours,
        calendar=args.calendar,
        calendar_map=args.calendar_map,
        calendar_json=args.calendar_json,
        calendar_ics=args.calendar_ics,
        credentials=args.credentials,
        token=args.token,
    )

    if args.format == "json":
        text = json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n"
    else:
        text = render_markdown(report)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    if args.csv:
        write_csv(report, Path(args.csv))
        print(f"Wrote {args.csv}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
