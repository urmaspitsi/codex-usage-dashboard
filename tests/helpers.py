"""Shared helpers for Codex dashboard tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def create_state_db(path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            cwd TEXT NOT NULL,
            model TEXT,
            model_provider TEXT NOT NULL,
            reasoning_effort TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            cli_version TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL,
            rollout_path TEXT NOT NULL
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO threads (
            id, title, cwd, model, model_provider, reasoning_effort,
            created_at, updated_at, archived, tokens_used, cli_version,
            source, rollout_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["title"],
                row["cwd"],
                row.get("model"),
                row.get("model_provider", "openai"),
                row.get("reasoning_effort", "high"),
                row["created_at"],
                row["updated_at"],
                row.get("archived", 0),
                row.get("tokens_used", 0),
                row.get("cli_version", "0.122.0-alpha.1"),
                row.get("source", "vscode"),
                row.get("rollout_path", ""),
            )
            for row in rows
        ],
    )
    conn.commit()
    conn.close()


def write_rollout(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def build_sample_rollout(thread_id: str, cwd: str, title: str, archived: bool = False) -> list[dict]:
    session_timestamp = "2026-04-20T10:00:00Z"
    rollout = [
        {
            "timestamp": session_timestamp,
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "timestamp": session_timestamp,
                "cwd": cwd,
                "originator": "Codex Desktop",
                "cli_version": "0.122.0-alpha.1",
                "source": "vscode",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2026-04-20T10:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "thread_name_updated",
                "thread_id": thread_id,
                "thread_name": title,
            },
        },
        {
            "timestamp": "2026-04-20T10:00:02Z",
            "type": "turn_context",
            "payload": {
                "turn_id": f"{thread_id}-turn-1",
                "cwd": cwd,
                "current_date": "2026-04-20",
                "timezone": "Europe/Tallinn",
                "model": "gpt-5.4",
                "effort": "high",
            },
        },
        {
            "timestamp": "2026-04-20T10:00:03Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": f"{thread_id}-turn-1",
                "started_at": 1776688803,
                "model_context_window": 258400,
            },
        },
        {
            "timestamp": "2026-04-20T10:00:04Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": None,
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 15.0, "window_minutes": 300, "resets_at": 1776708201},
                    "secondary": {"used_percent": 4.0, "window_minutes": 10080, "resets_at": 1777016830},
                    "plan_type": "prolite",
                },
            },
        },
        {
            "timestamp": "2026-04-20T10:00:05Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 40,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 125,
                    },
                    "last_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 40,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 125,
                    },
                    "model_context_window": 258400,
                },
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 15.0, "window_minutes": 300, "resets_at": 1776708201},
                    "secondary": {"used_percent": 4.0, "window_minutes": 10080, "resets_at": 1777016830},
                    "plan_type": "prolite",
                },
            },
        },
        {
            "timestamp": "2026-04-20T10:00:06Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 40,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 125,
                    },
                    "last_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 40,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 125,
                    },
                    "model_context_window": 258400,
                },
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 15.0, "window_minutes": 300, "resets_at": 1776708201},
                    "secondary": {"used_percent": 4.0, "window_minutes": 10080, "resets_at": 1777016830},
                    "plan_type": "prolite",
                },
            },
        },
        {
            "timestamp": "2026-04-20T10:00:07Z",
            "type": "turn_context",
            "payload": {
                "turn_id": f"{thread_id}-turn-2",
                "cwd": cwd,
                "current_date": "2026-04-20",
                "timezone": "Europe/Tallinn",
                "model": "gpt-5.4-mini",
                "effort": "medium",
            },
        },
        {
            "timestamp": "2026-04-20T10:00:08Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": f"{thread_id}-turn-2",
                "started_at": 1776688808,
                "model_context_window": 258400,
            },
        },
        {
            "timestamp": "2026-04-20T10:00:09Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 150,
                        "cached_input_tokens": 60,
                        "output_tokens": 25,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 180,
                    },
                    "last_token_usage": {
                        "input_tokens": 50,
                        "cached_input_tokens": 20,
                        "output_tokens": 5,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 55,
                    },
                    "model_context_window": 258400,
                },
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 17.0, "window_minutes": 300, "resets_at": 1776708201},
                    "secondary": {"used_percent": 4.0, "window_minutes": 10080, "resets_at": 1777016830},
                    "plan_type": "prolite",
                },
            },
        },
    ]
    if archived:
        rollout.append(
            {
                "timestamp": "2026-04-20T10:00:10Z",
                "type": "event_msg",
                "payload": {"type": "thread_archived", "thread_id": thread_id},
            }
        )
    return rollout


def create_sample_codex_home(codex_home: Path) -> dict[str, Path]:
    sessions_dir = codex_home / "sessions" / "2026" / "04" / "20"
    archived_dir = codex_home / "archived_sessions"
    state_db_path = codex_home / "state_5.sqlite"

    thread_one_id = "thread-001"
    thread_two_id = "thread-002"

    rollout_one = sessions_dir / "rollout-2026-04-20T10-00-00-thread-001.jsonl"
    rollout_two = archived_dir / "rollout-2026-04-20T10-30-00-thread-002.jsonl"

    write_rollout(
        rollout_one,
        build_sample_rollout(thread_one_id, "C:\\Work\\alpha", "Alpha thread"),
    )
    write_rollout(
        rollout_two,
        build_sample_rollout(thread_two_id, "C:\\Work\\beta", "Beta archive", archived=True),
    )

    create_state_db(
        state_db_path,
        [
            {
                "id": thread_one_id,
                "title": "Alpha thread",
                "cwd": "C:\\Work\\alpha",
                "model": "gpt-5.4",
                "created_at": 1776688800,
                "updated_at": 1776688850,
                "archived": 0,
                "tokens_used": 180,
                "rollout_path": str(rollout_one),
            },
            {
                "id": thread_two_id,
                "title": "Beta archive",
                "cwd": "C:\\Work\\beta",
                "model": "gpt-5.4-mini",
                "created_at": 1776689800,
                "updated_at": 1776689850,
                "archived": 1,
                "tokens_used": 180,
                "rollout_path": str(rollout_two),
            },
        ],
    )

    return {
        "state_db_path": state_db_path,
        "rollout_one": rollout_one,
        "rollout_two": rollout_two,
    }
