#!/usr/bin/env python3
"""Weekly activity report from local git history (+ optional GitHub metadata).

Looks for a git root under common cloud paths (/git, /workspace, cwd)
and summarizes commits, branch tips, remotes, and PRs for the last N days.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CANDIDATE_ROOTS = (
    Path("/git"),
    Path("/workspace"),
    Path.cwd(),
)


@dataclass
class CommitInfo:
    sha: str
    date: str
    author: str
    subject: str
    refs: str = ""


@dataclass
class BranchTip:
    name: str
    date: str
    subject: str


@dataclass
class WeeklyReport:
    generated_at: str
    since: str
    until: str
    git_root: str
    remote: str
    commit_count: int
    commits: list[CommitInfo] = field(default_factory=list)
    branch_tips: list[BranchTip] = field(default_factory=list)
    pushes_inferred: list[dict[str, str]] = field(default_factory=list)
    pull_requests: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def find_git_root(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if (p / ".git").exists() or (p / "HEAD").exists():
            # Allow pointing at a bare .git dir or worktree root
            return p if (p / ".git").exists() else p.parent if p.name == ".git" else p
        raise SystemExit(f"No git repository found at {p}")

    for root in CANDIDATE_ROOTS:
        if (root / ".git").exists():
            return root.resolve()
        if root.name == ".git" and (root / "HEAD").exists():
            return root.parent.resolve()

    # Fall back to git rev-parse from cwd
    proc = run(["git", "rev-parse", "--show-toplevel"])
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()

    raise SystemExit(
        "No git repository found. Checked /git, /workspace, and current directory."
    )


def git_lines(root: Path, *args: str) -> list[str]:
    proc = run(["git", *args], cwd=root)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def collect_commits(root: Path, since: str, until: str) -> list[CommitInfo]:
    fmt = "%H|%ad|%an <%ae>|%s|%D"
    lines = git_lines(
        root,
        "log",
        "--all",
        f"--since={since}",
        f"--until={until}",
        f"--pretty=format:{fmt}",
        "--date=iso-strict",
    )
    commits: list[CommitInfo] = []
    for line in lines:
        parts = line.split("|", 4)
        if len(parts) < 4:
            continue
        sha, date, author, subject = parts[:4]
        refs = parts[4] if len(parts) > 4 else ""
        commits.append(
            CommitInfo(
                sha=sha[:8],
                date=date,
                author=author,
                subject=subject,
                refs=refs,
            )
        )
    return commits


def collect_branch_tips(root: Path, since_dt: datetime) -> list[BranchTip]:
    lines = git_lines(
        root,
        "for-each-ref",
        "--format=%(refname:short)|%(committerdate:iso-strict)|%(subject)",
        "refs/heads",
        "refs/remotes",
    )
    tips: list[BranchTip] = []
    for line in lines:
        name, date, subject = (line.split("|", 2) + ["", ""])[:3]
        try:
            tip_dt = datetime.fromisoformat(date)
        except ValueError:
            continue
        if tip_dt.tzinfo is None:
            tip_dt = tip_dt.replace(tzinfo=timezone.utc)
        if tip_dt >= since_dt:
            tips.append(BranchTip(name=name, date=date, subject=subject))
    tips.sort(key=lambda t: t.date, reverse=True)
    return tips


def count_commits_on_ref(root: Path, ref: str, since: str, until: str) -> int:
    lines = git_lines(
        root,
        "rev-list",
        "--count",
        f"--since={since}",
        f"--until={until}",
        ref,
    )
    if not lines:
        return 0
    try:
        return int(lines[0].strip())
    except ValueError:
        return 0


def infer_pushes(
    root: Path,
    branch_tips: list[BranchTip],
    since: str,
    until: str,
) -> list[dict[str, str]]:
    """Infer push activity from remote-tracking branch tips that moved this week."""
    remote_tips = [b for b in branch_tips if b.name.startswith("origin/")]
    pushed: list[dict[str, str]] = []
    for tip in remote_tips:
        count = count_commits_on_ref(root, tip.name, since, until)
        pushed.append(
            {
                "remote_branch": tip.name,
                "tip_date": tip.date,
                "tip_subject": tip.subject,
                "related_commits_this_week": str(count),
            }
        )
    return pushed


def collect_prs(since: str) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    if not shutil.which("gh"):
        notes.append("GitHub CLI (gh) not available; skipped PR listing.")
        return [], notes

    proc = run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            "50",
            "--json",
            "number,title,state,isDraft,url,createdAt,updatedAt,headRefName,additions,deletions,changedFiles",
        ]
    )
    if proc.returncode != 0:
        notes.append(f"gh pr list failed: {proc.stderr.strip() or 'unknown error'}")
        return [], notes

    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        notes.append("Could not parse gh pr list JSON.")
        return [], notes

    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    active: list[dict[str, Any]] = []
    for pr in items:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if created >= since_dt or updated >= since_dt:
            active.append(pr)
    return active, notes


def render_markdown(report: WeeklyReport) -> str:
    lines = [
        f"# Laporan Aktivitas Mingguan",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Window: `{report.since}` → `{report.until}`",
        f"- Git root: `{report.git_root}`",
        f"- Remote: `{report.remote or '(none)'}`",
        f"- Commits: **{report.commit_count}**",
        "",
        "## Commits",
        "",
    ]
    if not report.commits:
        lines.append("_Tidak ada commit dalam jendela waktu ini._")
    else:
        lines.append("| SHA | Waktu | Author | Subject |")
        lines.append("|---|---|---|---|")
        for c in report.commits:
            subj = c.subject.replace("|", "\\|")
            lines.append(f"| `{c.sha}` | {c.date} | {c.author} | {subj} |")

    lines.extend(["", "## Remote branch tips (indikasi push)", ""])
    if not report.pushes_inferred:
        lines.append("_Tidak ada remote branch tip yang bergerak minggu ini._")
    else:
        for p in report.pushes_inferred:
            lines.append(
                f"- `{p['remote_branch']}` @ {p['tip_date']} — {p['tip_subject']} "
                f"(~{p['related_commits_this_week']} commit terkait)"
            )

    lines.extend(["", "## Pull requests aktif", ""])
    if not report.pull_requests:
        lines.append("_Tidak ada PR aktif dalam jendela waktu ini._")
    else:
        for pr in report.pull_requests:
            draft = " draft" if pr.get("isDraft") else ""
            lines.append(
                f"- #{pr['number']} [{pr['title']}]({pr['url']}) "
                f"— `{pr['state']}{draft}` on `{pr['headRefName']}` "
                f"(+{pr.get('additions', '?')}/-{pr.get('deletions', '?')}, "
                f"{pr.get('changedFiles', '?')} files)"
            )

    if report.notes:
        lines.extend(["", "## Notes", ""])
        for n in report.notes:
            lines.append(f"- {n}")

    lines.append("")
    return "\n".join(lines)


def build_report(days: int, git_root_arg: str | None) -> WeeklyReport:
    root = find_git_root(git_root_arg)
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)
    since = since_dt.isoformat().replace("+00:00", "Z")
    until = now.isoformat().replace("+00:00", "Z")

    remote_proc = run(["git", "remote", "get-url", "origin"], cwd=root)
    remote = remote_proc.stdout.strip() if remote_proc.returncode == 0 else ""
    # Redact tokens in remote URL for safe reports
    if "@" in remote and "://" in remote:
        scheme, rest = remote.split("://", 1)
        if "@" in rest:
            remote = f"{scheme}://***@{rest.split('@', 1)[1]}"

    commits = collect_commits(root, since, until)
    tips = collect_branch_tips(root, since_dt)
    pushes = infer_pushes(root, tips, since, until)
    prs, notes = collect_prs(since)

    if not Path("/git").exists():
        notes.append(
            "Path /git tidak ada di environment ini; memakai git root terdeteksi "
            f"({root}). Folder .git diperiksa di root tersebut."
        )

    return WeeklyReport(
        generated_at=until,
        since=since,
        until=until,
        git_root=str(root),
        remote=remote,
        commit_count=len(commits),
        commits=commits,
        branch_tips=tips,
        pushes_inferred=pushes,
        pull_requests=prs,
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument(
        "--git-root",
        default=os.environ.get("GIT_ROOT"),
        help="Explicit git worktree root (or set GIT_ROOT). Default: /git then /workspace",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write report to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = build_report(args.days, args.git_root)
    if args.format == "json":
        payload = asdict(report)
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    else:
        text = render_markdown(report)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
