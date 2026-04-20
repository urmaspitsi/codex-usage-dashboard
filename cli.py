"""
cli.py - Command-line interface for the Codex local usage dashboard.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from datetime import date
from pathlib import Path

from scanner import DB_PATH, scan


def fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def hr(char: str = "-", width: int = 68) -> None:
    print(char * width)


def require_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"Database not found. Run: python cli.py scan")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_scan(codex_home: str | None = None) -> None:
    scan(codex_home=Path(codex_home) if codex_home else None)


def cmd_today() -> None:
    conn = require_db()
    today = date.today().isoformat()

    rows = conn.execute(
        """
        SELECT
            COALESCE(model, 'unknown') AS model,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            COUNT(*) AS turns,
            COUNT(DISTINCT thread_id) AS threads
        FROM usage_events
        WHERE day = ?
        GROUP BY model
        ORDER BY total_tokens DESC, model ASC
        """,
        (today,),
    ).fetchall()

    latest_rate = conn.execute(
        """
        SELECT plan_type, primary_used_percent, primary_window_minutes, primary_resets_at,
               secondary_used_percent, secondary_window_minutes, secondary_resets_at
        FROM rate_limit_snapshots
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    print()
    hr("=")
    print(f"  Codex Usage Today ({today})")
    hr("=")

    if not rows:
        print("  No Codex usage events recorded today.")
        print()
        conn.close()
        return

    total_input = total_cached = total_output = total_reasoning = total_tokens = 0
    total_turns = total_threads = 0
    for row in rows:
        total_input += row["input_tokens"] or 0
        total_cached += row["cached_input_tokens"] or 0
        total_output += row["output_tokens"] or 0
        total_reasoning += row["reasoning_output_tokens"] or 0
        total_tokens += row["total_tokens"] or 0
        total_turns += row["turns"] or 0
        total_threads += row["threads"] or 0
        print(
            f"  {row['model']:<18} "
            f"threads={row['threads']:<3} "
            f"turns={row['turns']:<4} "
            f"total={fmt(row['total_tokens'] or 0):<8} "
            f"in={fmt(row['input_tokens'] or 0):<8} "
            f"out={fmt(row['output_tokens'] or 0):<8}"
        )

    hr()
    print(f"  Total threads:    {total_threads}")
    print(f"  Total turns:      {fmt(total_turns)}")
    print(f"  Input tokens:     {fmt(total_input)}")
    print(f"  Cached input:     {fmt(total_cached)}")
    print(f"  Output tokens:    {fmt(total_output)}")
    print(f"  Reasoning tokens: {fmt(total_reasoning)}")
    print(f"  Total tokens:     {fmt(total_tokens)}")

    if latest_rate:
        print()
        print(f"  Plan type:        {latest_rate['plan_type'] or 'unknown'}")
        print(
            f"  Primary window:   {latest_rate['primary_used_percent'] or 0:.1f}% "
            f"of {latest_rate['primary_window_minutes'] or 0}m"
        )
        print(
            f"  Secondary window: {latest_rate['secondary_used_percent'] or 0:.1f}% "
            f"of {latest_rate['secondary_window_minutes'] or 0}m"
        )

    hr("=")
    print()
    conn.close()


def cmd_stats() -> None:
    conn = require_db()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS usage_events,
            COUNT(DISTINCT thread_id) AS active_threads,
            MIN(day) AS first_day,
            MAX(day) AS last_day,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens
        FROM usage_events
        """
    ).fetchone()

    thread_summary = conn.execute(
        """
        SELECT
            COUNT(*) AS threads,
            SUM(archived) AS archived_threads,
            SUM(tokens_used) AS tokens_used
        FROM threads
        """
    ).fetchone()

    top_models = conn.execute(
        """
        SELECT
            COALESCE(model, 'unknown') AS model,
            COUNT(*) AS turns,
            COUNT(DISTINCT thread_id) AS threads,
            SUM(total_tokens) AS total_tokens
        FROM usage_events
        GROUP BY model
        ORDER BY total_tokens DESC, model ASC
        LIMIT 10
        """
    ).fetchall()

    top_projects = conn.execute(
        """
        SELECT
            COALESCE(project_name, 'unknown') AS project_name,
            COUNT(*) AS turns,
            COUNT(DISTINCT thread_id) AS threads,
            SUM(total_tokens) AS total_tokens
        FROM usage_events
        GROUP BY project_name
        ORDER BY total_tokens DESC, project_name ASC
        LIMIT 10
        """
    ).fetchall()

    latest_rate = conn.execute(
        """
        SELECT plan_type, primary_used_percent, primary_window_minutes, primary_resets_at,
               secondary_used_percent, secondary_window_minutes, secondary_resets_at
        FROM rate_limit_snapshots
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    print()
    hr("=")
    print("  Codex Local Usage Statistics")
    hr("=")
    print(f"  Period:           {(summary['first_day'] or 'n/a')} to {(summary['last_day'] or 'n/a')}")
    print(f"  Indexed threads:  {thread_summary['threads'] or 0}")
    print(f"  Archived threads: {thread_summary['archived_threads'] or 0}")
    print(f"  Usage events:     {summary['usage_events'] or 0}")
    print(f"  Thread tokens:    {fmt(thread_summary['tokens_used'] or 0)}")
    print()
    print(f"  Input tokens:     {fmt(summary['input_tokens'] or 0)}")
    print(f"  Cached input:     {fmt(summary['cached_input_tokens'] or 0)}")
    print(f"  Output tokens:    {fmt(summary['output_tokens'] or 0)}")
    print(f"  Reasoning tokens: {fmt(summary['reasoning_output_tokens'] or 0)}")
    print(f"  Total tokens:     {fmt(summary['total_tokens'] or 0)}")

    if latest_rate:
        print()
        print(f"  Latest plan:      {latest_rate['plan_type'] or 'unknown'}")
        print(
            f"  Primary window:   {latest_rate['primary_used_percent'] or 0:.1f}% "
            f"of {latest_rate['primary_window_minutes'] or 0}m"
        )
        print(
            f"  Secondary window: {latest_rate['secondary_used_percent'] or 0:.1f}% "
            f"of {latest_rate['secondary_window_minutes'] or 0}m"
        )

    hr()
    print("  Top Models:")
    for row in top_models:
        print(
            f"    {row['model']:<18} threads={row['threads']:<3} "
            f"turns={row['turns']:<4} total={fmt(row['total_tokens'] or 0)}"
        )

    hr()
    print("  Top Projects:")
    for row in top_projects:
        print(
            f"    {row['project_name']:<28} threads={row['threads']:<3} "
            f"turns={row['turns']:<4} total={fmt(row['total_tokens'] or 0)}"
        )
    hr("=")
    print()
    conn.close()


def cmd_dashboard(codex_home: str | None = None) -> None:
    import webbrowser
    from dashboard import serve

    print("Running scan first...")
    cmd_scan(codex_home=codex_home)

    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", "8080"))

    def open_browser() -> None:
        time.sleep(1.0)
        webbrowser.open(f"http://{host}:{port}")

    thread = threading.Thread(target=open_browser, daemon=True)
    thread.start()
    serve(host=host, port=port)


USAGE = """
Codex Local Usage Dashboard

Usage:
  python cli.py scan [--codex-home PATH]
  python cli.py today
  python cli.py stats
  python cli.py dashboard [--codex-home PATH]
"""


COMMANDS = {
    "scan": cmd_scan,
    "today": cmd_today,
    "stats": cmd_stats,
    "dashboard": cmd_dashboard,
}


def parse_codex_home(args: list[str]) -> str | None:
    for i, arg in enumerate(args):
        if arg == "--codex-home" and i + 1 < len(args):
            return args[i + 1]
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        sys.exit(0)

    command = sys.argv[1]
    codex_home = parse_codex_home(sys.argv[2:])
    if command in ("scan", "dashboard"):
        COMMANDS[command](codex_home=codex_home)
    else:
        COMMANDS[command]()
