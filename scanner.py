"""
scanner.py - Scans Codex Desktop local state and rollout files into a
dashboard-owned SQLite database.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from codex_safety import assert_dashboard_write_path, connect_sqlite_readonly


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = assert_dashboard_write_path(PROJECT_ROOT / ".codex_usage.db")
DEFAULT_CODEX_HOME = Path.home() / ".codex"
STATE_DB_NAME = "state_5.sqlite"
SESSIONS_DIR_NAME = "sessions"
ARCHIVED_SESSIONS_DIR_NAME = "archived_sessions"


@dataclass
class ScanPaths:
    codex_home: Path
    state_db_path: Path
    sessions_dir: Path
    archived_sessions_dir: Path


def get_scan_paths(codex_home: Optional[Path] = None) -> ScanPaths:
    base = Path(codex_home or DEFAULT_CODEX_HOME).expanduser().resolve(strict=False)
    return ScanPaths(
        codex_home=base,
        state_db_path=base / STATE_DB_NAME,
        sessions_dir=base / SESSIONS_DIR_NAME,
        archived_sessions_dir=base / ARCHIVED_SESSIONS_DIR_NAME,
    )


def get_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    resolved = assert_dashboard_write_path(db_path)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads (
            thread_id            TEXT PRIMARY KEY,
            title                TEXT,
            project_name         TEXT,
            cwd                  TEXT,
            model                TEXT,
            model_provider       TEXT,
            reasoning_effort     TEXT,
            created_at           TEXT,
            updated_at           TEXT,
            created_at_unix      INTEGER,
            updated_at_unix      INTEGER,
            archived             INTEGER NOT NULL DEFAULT 0,
            tokens_used          INTEGER NOT NULL DEFAULT 0,
            cli_version          TEXT,
            source               TEXT,
            rollout_path         TEXT,
            session_timestamp    TEXT
        );

        CREATE TABLE IF NOT EXISTS usage_events (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path                TEXT NOT NULL,
            line_no                    INTEGER NOT NULL,
            thread_id                  TEXT NOT NULL,
            turn_id                    TEXT,
            timestamp                  TEXT NOT NULL,
            day                        TEXT NOT NULL,
            project_name               TEXT,
            cwd                        TEXT,
            model                      TEXT,
            input_tokens               INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens        INTEGER NOT NULL DEFAULT 0,
            output_tokens              INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens    INTEGER NOT NULL DEFAULT 0,
            total_tokens               INTEGER NOT NULL DEFAULT 0,
            total_input_tokens         INTEGER NOT NULL DEFAULT 0,
            total_cached_input_tokens  INTEGER NOT NULL DEFAULT 0,
            total_output_tokens        INTEGER NOT NULL DEFAULT 0,
            total_reasoning_tokens     INTEGER NOT NULL DEFAULT 0,
            total_all_tokens           INTEGER NOT NULL DEFAULT 0,
            model_context_window       INTEGER,
            UNIQUE(source_path, line_no)
        );

        CREATE TABLE IF NOT EXISTS rate_limit_snapshots (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path                TEXT NOT NULL,
            line_no                    INTEGER NOT NULL,
            thread_id                  TEXT,
            turn_id                    TEXT,
            timestamp                  TEXT NOT NULL,
            plan_type                  TEXT,
            primary_used_percent       REAL,
            primary_window_minutes     INTEGER,
            primary_resets_at          INTEGER,
            secondary_used_percent     REAL,
            secondary_window_minutes   INTEGER,
            secondary_resets_at        INTEGER,
            UNIQUE(source_path, line_no)
        );

        CREATE TABLE IF NOT EXISTS processed_files (
            path                       TEXT PRIMARY KEY,
            mtime                      REAL NOT NULL,
            lines                      INTEGER NOT NULL DEFAULT 0,
            last_input_tokens          INTEGER NOT NULL DEFAULT 0,
            last_cached_input_tokens   INTEGER NOT NULL DEFAULT 0,
            last_output_tokens         INTEGER NOT NULL DEFAULT 0,
            last_reasoning_tokens      INTEGER NOT NULL DEFAULT 0,
            last_total_tokens          INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_threads_updated_at_unix ON threads(updated_at_unix);
        CREATE INDEX IF NOT EXISTS idx_threads_project_name ON threads(project_name);
        CREATE INDEX IF NOT EXISTS idx_usage_events_day ON usage_events(day);
        CREATE INDEX IF NOT EXISTS idx_usage_events_thread_id ON usage_events(thread_id);
        CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
        CREATE INDEX IF NOT EXISTS idx_rate_limit_snapshots_thread_id ON rate_limit_snapshots(thread_id);
        """
    )
    conn.commit()


def project_name_from_cwd(cwd: Optional[str]) -> str:
    """Derive a stable project label from the cwd."""
    if not cwd:
        return "unknown"
    parts = cwd.replace("\\", "/").rstrip("/").split("/")
    if parts and parts[0] == "":
        parts = parts[1:]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else "unknown"


def iso_from_unix(ts: Optional[int]) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def discover_rollout_files(paths: ScanPaths) -> List[Path]:
    files: List[Path] = []
    for root in (paths.sessions_dir, paths.archived_sessions_dir):
        if not root.exists():
            continue
        files.extend(Path(p) for p in glob.glob(str(root / "**" / "*.jsonl"), recursive=True))
    return sorted(files)


def load_threads_from_state_db(state_db_path: Path) -> List[Dict[str, object]]:
    if not state_db_path.exists():
        return []

    conn = connect_sqlite_readonly(state_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                title,
                cwd,
                model,
                model_provider,
                reasoning_effort,
                created_at,
                updated_at,
                archived,
                tokens_used,
                cli_version,
                source,
                rollout_path
            FROM threads
            """
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        result.append(
            {
                "thread_id": row["id"],
                "title": row["title"],
                "cwd": row["cwd"],
                "project_name": project_name_from_cwd(row["cwd"]),
                "model": row["model"] or "unknown",
                "model_provider": row["model_provider"] or "unknown",
                "reasoning_effort": row["reasoning_effort"] or "",
                "created_at": iso_from_unix(row["created_at"]),
                "updated_at": iso_from_unix(row["updated_at"]),
                "created_at_unix": row["created_at"],
                "updated_at_unix": row["updated_at"],
                "archived": int(row["archived"] or 0),
                "tokens_used": int(row["tokens_used"] or 0),
                "cli_version": row["cli_version"] or "",
                "source": row["source"] or "",
                "rollout_path": row["rollout_path"] or "",
                "session_timestamp": "",
            }
        )
    return result


def upsert_threads(conn: sqlite3.Connection, threads: Iterable[Dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO threads (
            thread_id, title, project_name, cwd, model, model_provider,
            reasoning_effort, created_at, updated_at, created_at_unix,
            updated_at_unix, archived, tokens_used, cli_version, source,
            rollout_path, session_timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            title = COALESCE(excluded.title, threads.title),
            project_name = COALESCE(excluded.project_name, threads.project_name),
            cwd = COALESCE(excluded.cwd, threads.cwd),
            model = COALESCE(excluded.model, threads.model),
            model_provider = COALESCE(excluded.model_provider, threads.model_provider),
            reasoning_effort = COALESCE(NULLIF(excluded.reasoning_effort, ''), threads.reasoning_effort),
            created_at = COALESCE(NULLIF(excluded.created_at, ''), threads.created_at),
            updated_at = COALESCE(NULLIF(excluded.updated_at, ''), threads.updated_at),
            created_at_unix = COALESCE(excluded.created_at_unix, threads.created_at_unix),
            updated_at_unix = COALESCE(excluded.updated_at_unix, threads.updated_at_unix),
            archived = COALESCE(excluded.archived, threads.archived),
            tokens_used = MAX(threads.tokens_used, COALESCE(excluded.tokens_used, 0)),
            cli_version = COALESCE(NULLIF(excluded.cli_version, ''), threads.cli_version),
            source = COALESCE(NULLIF(excluded.source, ''), threads.source),
            rollout_path = COALESCE(NULLIF(excluded.rollout_path, ''), threads.rollout_path),
            session_timestamp = COALESCE(NULLIF(excluded.session_timestamp, ''), threads.session_timestamp)
        """,
        [
            (
                thread["thread_id"],
                thread.get("title", ""),
                thread.get("project_name", "unknown"),
                thread.get("cwd", ""),
                thread.get("model", "unknown"),
                thread.get("model_provider", "unknown"),
                thread.get("reasoning_effort", ""),
                thread.get("created_at", ""),
                thread.get("updated_at", ""),
                thread.get("created_at_unix"),
                thread.get("updated_at_unix"),
                int(thread.get("archived", 0) or 0),
                int(thread.get("tokens_used", 0) or 0),
                thread.get("cli_version", ""),
                thread.get("source", ""),
                thread.get("rollout_path", ""),
                thread.get("session_timestamp", ""),
            )
            for thread in threads
        ],
    )
    conn.commit()


def insert_usage_events(conn: sqlite3.Connection, usage_events: Iterable[Dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO usage_events (
            source_path, line_no, thread_id, turn_id, timestamp, day,
            project_name, cwd, model, input_tokens, cached_input_tokens,
            output_tokens, reasoning_output_tokens, total_tokens,
            total_input_tokens, total_cached_input_tokens,
            total_output_tokens, total_reasoning_tokens, total_all_tokens,
            model_context_window
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                event["source_path"],
                event["line_no"],
                event["thread_id"],
                event.get("turn_id"),
                event["timestamp"],
                event["day"],
                event["project_name"],
                event["cwd"],
                event["model"],
                event["input_tokens"],
                event["cached_input_tokens"],
                event["output_tokens"],
                event["reasoning_output_tokens"],
                event["total_tokens"],
                event["total_input_tokens"],
                event["total_cached_input_tokens"],
                event["total_output_tokens"],
                event["total_reasoning_tokens"],
                event["total_all_tokens"],
                event.get("model_context_window"),
            )
            for event in usage_events
        ],
    )


def insert_rate_limit_snapshots(conn: sqlite3.Connection, snapshots: Iterable[Dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO rate_limit_snapshots (
            source_path, line_no, thread_id, turn_id, timestamp, plan_type,
            primary_used_percent, primary_window_minutes, primary_resets_at,
            secondary_used_percent, secondary_window_minutes, secondary_resets_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                snap["source_path"],
                snap["line_no"],
                snap.get("thread_id"),
                snap.get("turn_id"),
                snap["timestamp"],
                snap.get("plan_type"),
                snap.get("primary_used_percent"),
                snap.get("primary_window_minutes"),
                snap.get("primary_resets_at"),
                snap.get("secondary_used_percent"),
                snap.get("secondary_window_minutes"),
                snap.get("secondary_resets_at"),
            )
            for snap in snapshots
        ],
    )


def get_processed_file(conn: sqlite3.Connection, path: Path) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT path, mtime, lines, last_input_tokens, last_cached_input_tokens,
               last_output_tokens, last_reasoning_tokens, last_total_tokens
        FROM processed_files
        WHERE path = ?
        """,
        (str(path),),
    ).fetchone()


def update_processed_file(
    conn: sqlite3.Connection,
    path: Path,
    mtime: float,
    lines: int,
    last_totals: Tuple[int, int, int, int, int],
) -> None:
    conn.execute(
        """
        INSERT INTO processed_files (
            path, mtime, lines, last_input_tokens, last_cached_input_tokens,
            last_output_tokens, last_reasoning_tokens, last_total_tokens
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime = excluded.mtime,
            lines = excluded.lines,
            last_input_tokens = excluded.last_input_tokens,
            last_cached_input_tokens = excluded.last_cached_input_tokens,
            last_output_tokens = excluded.last_output_tokens,
            last_reasoning_tokens = excluded.last_reasoning_tokens,
            last_total_tokens = excluded.last_total_tokens
        """,
        (str(path), mtime, lines, *last_totals),
    )


def normalize_totals(total_usage: Optional[Dict[str, object]]) -> Tuple[int, int, int, int, int]:
    total_usage = total_usage or {}
    return (
        int(total_usage.get("input_tokens", 0) or 0),
        int(total_usage.get("cached_input_tokens", 0) or 0),
        int(total_usage.get("output_tokens", 0) or 0),
        int(total_usage.get("reasoning_output_tokens", 0) or 0),
        int(total_usage.get("total_tokens", 0) or 0),
    )


def parse_rollout_file(
    filepath: Path,
    start_line: int = 0,
    last_totals: Optional[Tuple[int, int, int, int, int]] = None,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], List[Dict[str, object]], int, Tuple[int, int, int, int, int]]:
    thread_updates: Dict[str, Dict[str, object]] = {}
    usage_events: List[Dict[str, object]] = []
    rate_snapshots: List[Dict[str, object]] = []
    line_count = 0

    current_thread_id: Optional[str] = None
    current_turn_id: Optional[str] = None
    turn_contexts: Dict[str, Dict[str, object]] = {}
    running_totals = last_totals or (0, 0, 0, 0, 0)

    with open(filepath, encoding="utf-8", errors="replace") as handle:
        for line_count, line in enumerate(handle, 1):
            if line_count <= start_line:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            record_type = record.get("type")
            payload = record.get("payload") or {}
            timestamp = record.get("timestamp", "")

            if record_type == "session_meta":
                current_thread_id = payload.get("id") or current_thread_id
                if not current_thread_id:
                    continue
                thread_updates[current_thread_id] = {
                    "thread_id": current_thread_id,
                    "title": thread_updates.get(current_thread_id, {}).get("title", ""),
                    "project_name": project_name_from_cwd(payload.get("cwd")),
                    "cwd": payload.get("cwd", ""),
                    "model": thread_updates.get(current_thread_id, {}).get("model", "unknown"),
                    "model_provider": payload.get("model_provider", "unknown"),
                    "reasoning_effort": thread_updates.get(current_thread_id, {}).get("reasoning_effort", ""),
                    "created_at": payload.get("timestamp", ""),
                    "updated_at": timestamp or payload.get("timestamp", ""),
                    "created_at_unix": None,
                    "updated_at_unix": None,
                    "archived": int(ARCHIVED_SESSIONS_DIR_NAME in filepath.parts),
                    "tokens_used": 0,
                    "cli_version": payload.get("cli_version", ""),
                    "source": payload.get("source", ""),
                    "rollout_path": str(filepath),
                    "session_timestamp": payload.get("timestamp", ""),
                }
                continue

            if record_type == "turn_context":
                turn_id = payload.get("turn_id")
                if not turn_id:
                    continue
                current_turn_id = turn_id
                turn_contexts[turn_id] = payload
                if current_thread_id:
                    thread = thread_updates.setdefault(
                        current_thread_id,
                        {
                            "thread_id": current_thread_id,
                            "title": "",
                            "project_name": project_name_from_cwd(payload.get("cwd")),
                            "cwd": payload.get("cwd", ""),
                            "model": payload.get("model", "unknown"),
                            "model_provider": "unknown",
                            "reasoning_effort": payload.get("effort", ""),
                            "created_at": "",
                            "updated_at": timestamp,
                            "created_at_unix": None,
                            "updated_at_unix": None,
                            "archived": int(ARCHIVED_SESSIONS_DIR_NAME in filepath.parts),
                            "tokens_used": 0,
                            "cli_version": "",
                            "source": "",
                            "rollout_path": str(filepath),
                            "session_timestamp": "",
                        },
                    )
                    thread["cwd"] = payload.get("cwd", thread.get("cwd", ""))
                    thread["project_name"] = project_name_from_cwd(thread["cwd"])
                    thread["model"] = payload.get("model", thread.get("model", "unknown"))
                    thread["reasoning_effort"] = payload.get("effort", thread.get("reasoning_effort", ""))
                    thread["updated_at"] = timestamp or thread.get("updated_at", "")
                continue

            if record_type != "event_msg":
                continue

            event_type = payload.get("type")
            if event_type == "task_started" and payload.get("turn_id"):
                current_turn_id = payload["turn_id"]
                continue

            if event_type == "thread_name_updated":
                thread_id = payload.get("thread_id") or current_thread_id
                if not thread_id:
                    continue
                current_thread_id = thread_id
                thread = thread_updates.setdefault(
                    thread_id,
                    {
                        "thread_id": thread_id,
                        "title": "",
                        "project_name": "unknown",
                        "cwd": "",
                        "model": "unknown",
                        "model_provider": "unknown",
                        "reasoning_effort": "",
                        "created_at": "",
                        "updated_at": timestamp,
                        "created_at_unix": None,
                        "updated_at_unix": None,
                        "archived": int(ARCHIVED_SESSIONS_DIR_NAME in filepath.parts),
                        "tokens_used": 0,
                        "cli_version": "",
                        "source": "",
                        "rollout_path": str(filepath),
                        "session_timestamp": "",
                    },
                )
                thread["title"] = payload.get("thread_name", thread.get("title", ""))
                thread["updated_at"] = timestamp or thread.get("updated_at", "")
                continue

            if event_type != "token_count":
                continue

            rate_limits = payload.get("rate_limits") or {}
            if rate_limits:
                rate_snapshots.append(
                    {
                        "source_path": str(filepath),
                        "line_no": line_count,
                        "thread_id": current_thread_id,
                        "turn_id": current_turn_id,
                        "timestamp": timestamp,
                        "plan_type": rate_limits.get("plan_type"),
                        "primary_used_percent": (rate_limits.get("primary") or {}).get("used_percent"),
                        "primary_window_minutes": (rate_limits.get("primary") or {}).get("window_minutes"),
                        "primary_resets_at": (rate_limits.get("primary") or {}).get("resets_at"),
                        "secondary_used_percent": (rate_limits.get("secondary") or {}).get("used_percent"),
                        "secondary_window_minutes": (rate_limits.get("secondary") or {}).get("window_minutes"),
                        "secondary_resets_at": (rate_limits.get("secondary") or {}).get("resets_at"),
                    }
                )

            info = payload.get("info")
            if not info:
                continue

            totals = normalize_totals(info.get("total_token_usage"))
            if totals == running_totals:
                continue

            last_usage = normalize_totals(info.get("last_token_usage"))
            if sum(last_usage) == 0:
                continue

            context = turn_contexts.get(current_turn_id or "", {})
            cwd = context.get("cwd") or thread_updates.get(current_thread_id or "", {}).get("cwd", "")
            model = context.get("model") or thread_updates.get(current_thread_id or "", {}).get("model", "unknown")
            thread_id = current_thread_id or "unknown"

            usage_events.append(
                {
                    "source_path": str(filepath),
                    "line_no": line_count,
                    "thread_id": thread_id,
                    "turn_id": current_turn_id,
                    "timestamp": timestamp,
                    "day": (timestamp or "")[:10],
                    "project_name": project_name_from_cwd(cwd),
                    "cwd": cwd,
                    "model": model or "unknown",
                    "input_tokens": last_usage[0],
                    "cached_input_tokens": last_usage[1],
                    "output_tokens": last_usage[2],
                    "reasoning_output_tokens": last_usage[3],
                    "total_tokens": last_usage[4],
                    "total_input_tokens": totals[0],
                    "total_cached_input_tokens": totals[1],
                    "total_output_tokens": totals[2],
                    "total_reasoning_tokens": totals[3],
                    "total_all_tokens": totals[4],
                    "model_context_window": info.get("model_context_window"),
                }
            )

            running_totals = totals
            if thread_id in thread_updates:
                thread_updates[thread_id]["tokens_used"] = max(
                    int(thread_updates[thread_id].get("tokens_used", 0) or 0),
                    totals[4],
                )
                thread_updates[thread_id]["updated_at"] = timestamp or thread_updates[thread_id].get("updated_at", "")

    return list(thread_updates.values()), usage_events, rate_snapshots, line_count, running_totals


def scan(codex_home: Optional[Path] = None, db_path: Path = DB_PATH, verbose: bool = True) -> Dict[str, int]:
    paths = get_scan_paths(codex_home=codex_home)
    conn = get_db(db_path)
    init_db(conn)

    upsert_threads(conn, load_threads_from_state_db(paths.state_db_path))

    new_files = 0
    updated_files = 0
    skipped_files = 0
    usage_events_added = 0
    rate_snapshots_added = 0

    for filepath in discover_rollout_files(paths):
        try:
            mtime = os.path.getmtime(filepath)
        except OSError:
            continue

        processed = get_processed_file(conn, filepath)
        if processed and abs(processed["mtime"] - mtime) < 0.01:
            skipped_files += 1
            continue

        thread_updates, usage_events, rate_snapshots, line_count, end_totals = parse_rollout_file(
            filepath,
            start_line=0,
            last_totals=None,
        )

        before_usage = conn.execute(
            "SELECT COUNT(*) FROM usage_events WHERE source_path = ?",
            (str(filepath),),
        ).fetchone()[0]
        before_rates = conn.execute(
            "SELECT COUNT(*) FROM rate_limit_snapshots WHERE source_path = ?",
            (str(filepath),),
        ).fetchone()[0]

        upsert_threads(conn, thread_updates)
        insert_usage_events(conn, usage_events)
        insert_rate_limit_snapshots(conn, rate_snapshots)
        update_processed_file(conn, filepath, mtime, line_count, end_totals)
        conn.commit()

        after_usage = conn.execute(
            "SELECT COUNT(*) FROM usage_events WHERE source_path = ?",
            (str(filepath),),
        ).fetchone()[0]
        after_rates = conn.execute(
            "SELECT COUNT(*) FROM rate_limit_snapshots WHERE source_path = ?",
            (str(filepath),),
        ).fetchone()[0]

        inserted_usage = max(after_usage - before_usage, 0)
        inserted_rates = max(after_rates - before_rates, 0)

        usage_events_added += inserted_usage
        rate_snapshots_added += inserted_rates

        if processed and line_count <= processed["lines"] and inserted_usage == 0 and inserted_rates == 0:
            skipped_files += 1
            continue

        if processed:
            updated_files += 1
        else:
            new_files += 1

        if verbose:
            status = "NEW" if not processed else "UPD"
            print(f"[{status}] {filepath}")

    result = {
        "new": new_files,
        "updated": updated_files,
        "skipped": skipped_files,
        "usage_events": usage_events_added,
        "rate_snapshots": rate_snapshots_added,
        "threads": conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0],
    }

    if verbose:
        print("\nScan complete:")
        print(f"  New files:        {new_files}")
        print(f"  Updated files:    {updated_files}")
        print(f"  Skipped files:    {skipped_files}")
        print(f"  Usage events:     {usage_events_added}")
        print(f"  Rate snapshots:   {rate_snapshots_added}")
        print(f"  Threads indexed:  {result['threads']}")

    conn.close()
    return result


if __name__ == "__main__":
    import sys

    codex_home = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--codex-home" and i + 1 < len(sys.argv[1:]):
            codex_home = Path(sys.argv[i + 2])
            break

    scan(codex_home=codex_home)
