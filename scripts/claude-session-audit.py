#!/usr/bin/env python3
"""
Claude Code Session Audit Tool (Max Plan Edition)

Designed for Claude Max subscribers who care about limit windows, not API dollars.
Analyzes all local session transcripts to show:
- Which sessions are eating your quota fastest (weighted token burn)
- Waste factor: how bloated each session's context has become
- When you should have rotated to a fresh session
- Relative quota share: what % of your window each session consumed

Usage:
    python3 claude-session-audit.py                # Summary of all sessions
    python3 claude-session-audit.py --detail UUID   # Deep dive into one session
    python3 claude-session-audit.py --recent 7      # Only last N days
    python3 claude-session-audit.py --csv            # CSV output for spreadsheets
    python3 claude-session-audit.py --window 5h      # Group by 5-hour limit windows
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ── Quota weight factors (for Max plan burn rate) ────────────────────────────
# Anthropic doesn't publish exact weights. These are informed guesses based on:
# - Cache reads are explicitly cheaper (Anthropic docs say "reduced cost")
# - Output tokens are most expensive across all Claude pricing tiers
# - Cache creation has overhead vs plain input
# The absolute numbers don't matter — only the ratios between them.
QUOTA_WEIGHTS = {
    "input": 1.0,
    "cache_create": 1.25,
    "cache_read": 0.1,
    "output": 5.0,
}


def parse_session(filepath: Path) -> dict | None:
    """Parse a JSONL session file and extract per-turn token usage."""
    turns = []
    model = None
    version = None
    cwd = None
    git_branch = None
    first_ts = None
    last_ts = None
    first_user_msg = None

    try:
        with open(filepath, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp")
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

                if not cwd and obj.get("cwd"):
                    cwd = obj["cwd"]
                if not version and obj.get("version"):
                    version = obj["version"]
                if not git_branch and obj.get("gitBranch"):
                    git_branch = obj["gitBranch"]

                # Capture first meaningful user message as topic
                if first_user_msg is None and obj.get("type") == "user":
                    msg = obj.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        content = " ".join(texts)
                    content = content.strip()
                    content = re.sub(r"<system-reminder>.*?</system-reminder>", "", content, flags=re.DOTALL).strip()
                    content = re.sub(r"<[^>]+>", "", content).strip()  # strip XML-ish tags
                    content = content.replace("\n", " ").strip()
                    if len(content) >= 10:
                        first_user_msg = content[:120]

                if obj.get("type") != "assistant":
                    continue

                msg = obj.get("message", {})
                usage = msg.get("usage")
                if not usage:
                    continue

                if not model and msg.get("model"):
                    model = msg["model"]

                input_tokens = usage.get("input_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_context = input_tokens + cache_create + cache_read

                if total_context < 100 and output_tokens < 50:
                    continue

                turns.append({
                    "input": input_tokens,
                    "cache_create": cache_create,
                    "cache_read": cache_read,
                    "output": output_tokens,
                    "total_context": total_context,
                    "timestamp": ts,
                })
    except (PermissionError, OSError):
        return None

    if not turns:
        return None

    session_id = filepath.stem
    n = len(turns)
    window = min(5, n)

    first_avg = sum(t["total_context"] for t in turns[:window]) / window
    last_avg = sum(t["total_context"] for t in turns[-window:]) / window
    waste_factor = last_avg / first_avg if first_avg > 0 else 1.0

    total_input = sum(t["input"] for t in turns)
    total_cache_create = sum(t["cache_create"] for t in turns)
    total_cache_read = sum(t["cache_read"] for t in turns)
    total_output = sum(t["output"] for t in turns)
    total_all_input = total_input + total_cache_create + total_cache_read

    cache_ratio = total_cache_read / total_all_input if total_all_input > 0 else 0.0

    # Weighted quota burn — the best proxy we have for actual quota consumption
    weighted_burn = (
        total_input * QUOTA_WEIGHTS["input"]
        + total_cache_create * QUOTA_WEIGHTS["cache_create"]
        + total_cache_read * QUOTA_WEIGHTS["cache_read"]
        + total_output * QUOTA_WEIGHTS["output"]
    )

    # What burn WOULD have been if session stayed at baseline context size
    # (i.e., if you had rotated perfectly)
    baseline_context = turns[0]["total_context"]
    ideal_burn = sum(
        baseline_context * QUOTA_WEIGHTS["cache_read"]  # assume all cache reads at baseline
        + t["output"] * QUOTA_WEIGHTS["output"]
        for t in turns
    )
    excess_burn = max(0, weighted_burn - ideal_burn)

    # Duration
    duration_minutes = None
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration_minutes = (t1 - t0).total_seconds() / 60
        except (ValueError, TypeError):
            pass

    # Cache health trend
    mid = n // 2
    if mid > 0:
        second_half_reads = sum(t["cache_read"] for t in turns[mid:])
        second_half_total = sum(t["total_context"] for t in turns[mid:])
        second_ratio = second_half_reads / second_half_total if second_half_total > 0 else 0

        if second_ratio > 0.8:
            cache_health = "healthy"
        elif second_ratio > 0.5:
            cache_health = "degraded"
        else:
            cache_health = "broken"
    else:
        cache_health = "unknown"

    # Find the turn where waste crossed 5x and 10x
    rotation_point_5x = None
    rotation_point_10x = None
    for i, t in enumerate(turns):
        ratio = t["total_context"] / baseline_context if baseline_context > 0 else 1
        if ratio >= 5 and rotation_point_5x is None:
            rotation_point_5x = i + 1
        if ratio >= 10 and rotation_point_10x is None:
            rotation_point_10x = i + 1

    return {
        "session_id": session_id,
        "filepath": str(filepath),
        "project": filepath.parent.name,
        "cwd": cwd,
        "model": model or "unknown",
        "version": version,
        "git_branch": git_branch,
        "turns": n,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "duration_minutes": duration_minutes,
        "waste_factor": waste_factor,
        "cache_ratio": cache_ratio,
        "cache_health": cache_health,
        "total_input": total_input,
        "total_cache_create": total_cache_create,
        "total_cache_read": total_cache_read,
        "total_output": total_output,
        "weighted_burn": weighted_burn,
        "ideal_burn": ideal_burn,
        "excess_burn": excess_burn,
        "first_context": turns[0]["total_context"],
        "last_context": turns[-1]["total_context"],
        "peak_context": max(t["total_context"] for t in turns),
        "topic": first_user_msg or "",
        "rotation_5x": rotation_point_5x,
        "rotation_10x": rotation_point_10x,
        "turns_data": turns,
    }


def find_sessions(claude_dir: Path, recent_days: int | None = None) -> list[Path]:
    """Find all top-level JSONL session files (skip subagent files)."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        print(f"No projects directory found at {projects_dir}", file=sys.stderr)
        sys.exit(1)

    cutoff = None
    if recent_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)

    sessions = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            if "subagent" in str(jsonl):
                continue
            if cutoff:
                mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    continue
            sessions.append(jsonl)
    return sessions


# ── Formatting helpers ───────────────────────────────────────────────────────

def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)

def fmt_burn(n: float) -> str:
    """Format weighted burn as compact number."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return f"{n:.0f}"

def fmt_duration(minutes: float | None) -> str:
    if minutes is None:
        return "?"
    if minutes < 60:
        return f"{minutes:.0f}m"
    return f"{minutes / 60:.1f}h"

def fmt_pct(ratio: float) -> str:
    return f"{ratio:.0%}" if ratio >= 0.01 else "<1%"

def waste_label(wf: float) -> str:
    if wf < 3:    return "ok"
    if wf < 6:    return "MED"
    if wf < 10:   return "HIGH"
    return "CRIT"

def friendly_project(project_name: str) -> str:
    parts = project_name.split("-")
    try:
        idx = parts.index("projects")
        return "/".join(parts[idx + 1:]) or project_name
    except ValueError:
        return project_name


# ── Summary view ─────────────────────────────────────────────────────────────

def print_summary(sessions: list[dict], sort_by: str = "burn"):
    if not sessions:
        print("No sessions found.")
        return

    sort_keys = {
        "burn":  lambda s: -s["weighted_burn"],
        "waste": lambda s: -s["waste_factor"],
        "date":  lambda s: s["first_ts"] or "",
        "turns": lambda s: -s["turns"],
        "excess": lambda s: -s["excess_burn"],
    }
    sessions.sort(key=sort_keys.get(sort_by, sort_keys["burn"]))

    total_burn = sum(s["weighted_burn"] for s in sessions)
    total_excess = sum(s["excess_burn"] for s in sessions)
    avg_waste = sum(s["waste_factor"] for s in sessions) / len(sessions)
    sessions_over_10x = sum(1 for s in sessions if s["waste_factor"] > 10)

    print("=" * 120)
    print("CLAUDE CODE SESSION AUDIT — Max Plan Quota Analysis")
    print("=" * 120)
    print()
    print(f"  Sessions:           {len(sessions)}")
    print(f"  Avg waste factor:   {avg_waste:.1f}x")
    print(f"  Sessions > 10x:     {sessions_over_10x} (should have been rotated)")
    print(f"  Excess burn:        {fmt_pct(total_excess / total_burn if total_burn else 0)} of total quota went to context bloat")
    print()

    hdr = (
        f"{'ID':<10} {'Date':<12} {'Turns':>5} {'Duration':>8} "
        f"{'Ctx Now':>8} {'Waste':>6} {'Quota%':>6} {'Excess%':>7} {'Rotate@':>8}  "
        f"{'Topic'}"
    )
    print(hdr)
    print("-" * 130)

    for s in sessions:
        date_str = s["first_ts"][:10] if s["first_ts"] else "?"
        quota_pct = s["weighted_burn"] / total_burn * 100 if total_burn else 0
        excess_pct = s["excess_burn"] / s["weighted_burn"] * 100 if s["weighted_burn"] else 0

        # Rotation recommendation
        if s["rotation_10x"]:
            rotate_at = f"turn {s['rotation_10x']}"
        elif s["rotation_5x"]:
            rotate_at = f"~turn {s['rotation_5x']}"
        else:
            rotate_at = "-"

        topic = s.get("topic", "")
        if len(topic) > 48:
            topic = topic[:45] + "..."

        wf = s["waste_factor"]
        waste_str = f"{wf:>4.1f}x" if wf < 100 else f"{wf:>4.0f}x"

        print(
            f"{s['session_id'][:8]:<10} "
            f"{date_str:<12} "
            f"{s['turns']:>5} "
            f"{fmt_duration(s['duration_minutes']):>8} "
            f"{fmt_tokens(s['last_context']):>8} "
            f"{waste_str:>6} "
            f"{quota_pct:>5.1f}% "
            f"{excess_pct:>5.1f}%  "
            f"{rotate_at:>8}  "
            f"{topic}"
        )

    print()

    # ── Actionable insights ──────────────────────────────────────────────
    print("INSIGHTS:")

    # Top 3 quota hogs
    top3 = sorted(sessions, key=lambda s: -s["weighted_burn"])[:3]
    total_top3_pct = sum(s["weighted_burn"] for s in top3) / total_burn * 100 if total_burn else 0
    print(f"  Top 3 sessions consumed {total_top3_pct:.0f}% of your quota:")
    for s in top3:
        pct = s["weighted_burn"] / total_burn * 100 if total_burn else 0
        topic = s.get("topic", "")[:50] or friendly_project(s["project"])
        print(f"    {s['session_id'][:8]}  {pct:>4.1f}%  {s['waste_factor']:.0f}x waste  {s['turns']} turns  {topic}")

    # Rotation savings
    if sessions_over_10x:
        excess_ratio = total_excess / total_burn if total_burn else 0
        print(f"\n  {excess_ratio:.0%} of your total quota burn was excess context bloat.")
        print(f"  Rotating sessions at 10x waste would reclaim most of this.")
        print(f"  Rule of thumb: /clear or new terminal after ~{_estimate_rotation_turns(sessions)} turns.")

    print()
    print(f"TIP: --detail <id>  Deep dive  |  --sort=burn|waste|excess|date|turns  |  --window 5h  Group by limit windows")


def _estimate_rotation_turns(sessions: list[dict]) -> int:
    """Estimate the ideal rotation point based on session data."""
    rotation_points = [s["rotation_5x"] for s in sessions if s["rotation_5x"]]
    if not rotation_points:
        return 200
    return int(sum(rotation_points) / len(rotation_points))


# ── Window view ──────────────────────────────────────────────────────────────

def print_windows(sessions: list[dict], window_hours: float):
    """Group sessions into limit windows and show quota distribution."""
    if not sessions:
        print("No sessions found.")
        return

    # Collect all turns with timestamps across all sessions
    all_events = []
    for s in sessions:
        for t in s["turns_data"]:
            if t.get("timestamp"):
                try:
                    ts = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
                    burn = (
                        t["input"] * QUOTA_WEIGHTS["input"]
                        + t["cache_create"] * QUOTA_WEIGHTS["cache_create"]
                        + t["cache_read"] * QUOTA_WEIGHTS["cache_read"]
                        + t["output"] * QUOTA_WEIGHTS["output"]
                    )
                    all_events.append((ts, burn, s["session_id"]))
                except (ValueError, TypeError):
                    continue

    if not all_events:
        print("No timestamped events found.")
        return

    all_events.sort(key=lambda x: x[0])

    # Bucket into windows
    window_delta = timedelta(hours=window_hours)
    window_start = all_events[0][0]
    windows = []
    current_window = {"start": window_start, "burn": 0, "turns": 0, "sessions": set()}

    for ts, burn, sid in all_events:
        while ts >= current_window["start"] + window_delta:
            windows.append(current_window)
            current_window = {
                "start": current_window["start"] + window_delta,
                "burn": 0, "turns": 0, "sessions": set()
            }
        current_window["burn"] += burn
        current_window["turns"] += 1
        current_window["sessions"].add(sid[:8])

    windows.append(current_window)

    # Filter out empty windows
    windows = [w for w in windows if w["turns"] > 0]

    if not windows:
        print("No windows with activity found.")
        return

    max_burn = max(w["burn"] for w in windows)

    print("=" * 100)
    print(f"LIMIT WINDOW VIEW — {window_hours}h windows")
    print("=" * 100)
    print()
    print(f"{'Window Start':<22} {'Turns':>6} {'Sessions':>8} {'Weighted Burn':>14}  {'Relative Load'}")
    print("-" * 100)

    for w in windows:
        bar_len = int((w["burn"] / max_burn) * 40) if max_burn > 0 else 0
        load_pct = w["burn"] / max_burn * 100 if max_burn else 0

        # Intensity marker
        if load_pct > 80:
            marker = "!"
        elif load_pct > 50:
            marker = "#"
        else:
            marker = "."

        print(
            f"{w['start'].strftime('%Y-%m-%d %H:%M'):>22} "
            f"{w['turns']:>6} "
            f"{len(w['sessions']):>8} "
            f"{fmt_burn(w['burn']):>14}  "
            f"|{marker * bar_len} {load_pct:.0f}%"
        )

    print()
    heaviest = max(windows, key=lambda w: w["burn"])
    print(f"  Heaviest window: {heaviest['start'].strftime('%Y-%m-%d %H:%M')} — "
          f"{heaviest['turns']} turns across {len(heaviest['sessions'])} session(s)")
    print(f"  Sessions in that window: {', '.join(sorted(heaviest['sessions']))}")


# ── Detail view ──────────────────────────────────────────────────────────────

def print_detail(sessions: list[dict], session_prefix: str):
    matches = [s for s in sessions if s["session_id"].startswith(session_prefix)]
    if not matches:
        print(f"No session found matching '{session_prefix}'")
        print("Recent sessions:")
        for s in sorted(sessions, key=lambda s: s["first_ts"] or "")[-10:]:
            topic = s.get("topic", "")[:50] or friendly_project(s["project"])
            print(f"  {s['session_id'][:12]}  {s['first_ts'][:10] if s['first_ts'] else '?':<12}  {topic}")
        return

    s = matches[0]
    turns = s["turns_data"]
    total_burn_all = sum(ss["weighted_burn"] for ss in sessions)
    quota_pct = s["weighted_burn"] / total_burn_all * 100 if total_burn_all else 0

    print("=" * 90)
    print(f"SESSION: {s['session_id']}")
    print("=" * 90)
    if s.get("topic"):
        print(f"  Topic:         {s['topic']}")
    print(f"  Project:       {friendly_project(s['project'])}")
    print(f"  Model:         {s['model']}")
    print(f"  Version:       {s['version']}")
    print(f"  Branch:        {s['git_branch']}")
    print(f"  Duration:      {fmt_duration(s['duration_minutes'])}")
    print(f"  Turns:         {s['turns']}")
    print(f"  Period:        {s['first_ts'][:19] if s['first_ts'] else '?'} -> {s['last_ts'][:19] if s['last_ts'] else '?'}")
    print()
    print(f"  Waste factor:  {s['waste_factor']:.1f}x ({waste_label(s['waste_factor'])})")
    print(f"  Cache ratio:   {s['cache_ratio']:.1%} ({s['cache_health']})")
    print(f"  Context:       {fmt_tokens(s['first_context'])} -> {fmt_tokens(s['last_context'])} (peak: {fmt_tokens(s['peak_context'])})")
    print(f"  Quota share:   {quota_pct:.1f}% of analyzed period")
    excess_pct = s["excess_burn"] / s["weighted_burn"] * 100 if s["weighted_burn"] else 0
    print(f"  Excess burn:   {excess_pct:.0f}% of this session's quota went to bloated context")
    if s["rotation_10x"]:
        print(f"  Should rotate: at turn {s['rotation_10x']} (context hit 10x baseline)")
    elif s["rotation_5x"]:
        print(f"  Consider rotating: at turn {s['rotation_5x']} (context hit 5x baseline)")
    print()

    # Turn-by-turn chart
    max_display = 60
    step = max(1, len(turns) // max_display)
    sampled = turns[::step]
    max_ctx = max(t["total_context"] for t in turns)
    bar_width = 50
    baseline = turns[0]["total_context"]

    print(f"{'Turn':>5}  {'Context':>8}  {'Output':>7}  {'Cache%':>6}  {'Ratio':>6}  {'Bar'}")
    print("-" * 90)

    for i, t in enumerate(sampled):
        turn_num = i * step + 1
        ctx = t["total_context"]
        bar_len = int((ctx / max_ctx) * bar_width) if max_ctx > 0 else 0
        cache_pct = t["cache_read"] / ctx * 100 if ctx > 0 else 0
        ratio = ctx / baseline if baseline > 0 else 1

        if ratio < 3:     marker = "."
        elif ratio < 6:   marker = "+"
        elif ratio < 10:  marker = "#"
        else:             marker = "!"

        ratio_str = f"{ratio:.0f}x" if ratio >= 2 else ""

        print(
            f"{turn_num:>5}  "
            f"{fmt_tokens(ctx):>8}  "
            f"{fmt_tokens(t['output']):>7}  "
            f"{cache_pct:>5.0f}%  "
            f"{ratio_str:>6}  "
            f"|{marker * bar_len}"
        )

    print()
    print("  . = <3x baseline   + = 3-6x   # = 6-10x   ! = >10x (rotate!)")

    # Anomalies
    print()
    print("ANOMALIES:")
    anomalies = []
    avg_ctx = sum(t["total_context"] for t in turns) / len(turns)

    for i in range(1, len(turns)):
        prev_ratio = turns[i-1]["cache_read"] / turns[i-1]["total_context"] if turns[i-1]["total_context"] > 0 else 0
        curr_ratio = turns[i]["cache_read"] / turns[i]["total_context"] if turns[i]["total_context"] > 0 else 0
        if prev_ratio > 0.5 and curr_ratio < prev_ratio * 0.5:
            anomalies.append(f"  Turn {i+1}: cache invalidation (ratio {prev_ratio:.0%} -> {curr_ratio:.0%})")

    for i, t in enumerate(turns):
        if t["total_context"] > avg_ctx * 5:
            anomalies.append(f"  Turn {i+1}: context spike {fmt_tokens(t['total_context'])} (avg: {fmt_tokens(int(avg_ctx))})")

    if anomalies:
        for a in anomalies[:10]:
            print(a)
        if len(anomalies) > 10:
            print(f"  ... and {len(anomalies) - 10} more")
    else:
        print("  None detected.")


# ── CSV export ───────────────────────────────────────────────────────────────

def print_csv(sessions: list[dict]):
    total_burn = sum(s["weighted_burn"] for s in sessions)
    fields = [
        "session_id", "topic", "project", "model", "date", "duration_min",
        "turns", "waste_factor", "cache_ratio", "cache_health",
        "first_context", "last_context", "peak_context",
        "weighted_burn", "excess_burn", "quota_pct",
        "rotation_5x_turn", "rotation_10x_turn",
    ]
    print(",".join(fields))
    for s in sorted(sessions, key=lambda s: s["first_ts"] or ""):
        topic_csv = s.get("topic", "").replace('"', '""')
        quota_pct = s["weighted_burn"] / total_burn * 100 if total_burn else 0
        row = [
            s["session_id"],
            f'"{topic_csv}"',
            friendly_project(s["project"]),
            s["model"],
            s["first_ts"][:10] if s["first_ts"] else "",
            f"{s['duration_minutes']:.0f}" if s["duration_minutes"] else "",
            str(s["turns"]),
            f"{s['waste_factor']:.2f}",
            f"{s['cache_ratio']:.4f}",
            s["cache_health"],
            str(s["first_context"]),
            str(s["last_context"]),
            str(s["peak_context"]),
            f"{s['weighted_burn']:.0f}",
            f"{s['excess_burn']:.0f}",
            f"{quota_pct:.2f}",
            str(s["rotation_5x"] or ""),
            str(s["rotation_10x"] or ""),
        ]
        print(",".join(row))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code Session Audit — Max Plan Quota Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--detail", metavar="ID", help="Deep-dive into a specific session (prefix match)")
    parser.add_argument("--recent", type=int, metavar="DAYS", help="Only analyze sessions from the last N days")
    parser.add_argument("--sort", default="burn", choices=["burn", "waste", "excess", "date", "turns"],
                        help="Sort order (default: burn)")
    parser.add_argument("--window", metavar="HOURS", help="Group by limit windows (e.g., 5h, 168h for weekly)")
    parser.add_argument("--csv", action="store_true", help="CSV output for spreadsheets")
    parser.add_argument("--claude-dir", default=os.path.expanduser("~/.claude"), help="Claude config directory")
    parser.add_argument("--min-turns", type=int, default=5, help="Min turns to include (default: 5)")
    args = parser.parse_args()

    claude_dir = Path(args.claude_dir)
    session_files = find_sessions(claude_dir, recent_days=args.recent)

    if not session_files:
        print("No session files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(session_files)} session files...", file=sys.stderr)

    sessions = []
    for sf in session_files:
        result = parse_session(sf)
        if result and result["turns"] >= args.min_turns:
            sessions.append(result)

    print(f"Parsed {len(sessions)} sessions with >= {args.min_turns} turns.", file=sys.stderr)

    if args.csv:
        print_csv(sessions)
    elif args.detail:
        print_detail(sessions, args.detail)
    elif args.window:
        hours = float(args.window.rstrip("h"))
        print_windows(sessions, hours)
    else:
        print_summary(sessions, sort_by=args.sort)


if __name__ == "__main__":
    main()
