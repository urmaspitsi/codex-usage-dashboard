"""Tests for Codex scanner ingestion and aggregation."""

from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from scanner import (
    discover_rollout_files,
    get_db,
    get_scan_paths,
    init_db,
    load_threads_from_state_db,
    parse_rollout_file,
    project_name_from_cwd,
    scan,
)
from tests.helpers import create_sample_codex_home


class TestProjectNameFromCwd(unittest.TestCase):
    def test_windows_path(self):
        self.assertEqual(project_name_from_cwd("C:\\Users\\me\\project"), "me/project")

    def test_trailing_slash(self):
        self.assertEqual(project_name_from_cwd("/home/user/project/"), "user/project")

    def test_empty_or_none(self):
        self.assertEqual(project_name_from_cwd(""), "unknown")
        self.assertEqual(project_name_from_cwd(None), "unknown")


class TestStateDbLoading(unittest.TestCase):
    def test_load_threads_from_state_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = create_sample_codex_home(Path(tmp))
            threads = load_threads_from_state_db(paths["state_db_path"])
            self.assertEqual(len(threads), 2)
            self.assertEqual(threads[0]["model_provider"], "openai")
            self.assertGreaterEqual(threads[0]["tokens_used"], 180)


class TestRolloutParsing(unittest.TestCase):
    def test_parse_rollout_file_dedups_duplicate_total_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = create_sample_codex_home(Path(tmp))
            thread_updates, usage_events, rate_snapshots, line_count, end_totals = parse_rollout_file(
                paths["rollout_one"]
            )
            self.assertEqual(len(thread_updates), 1)
            self.assertEqual(len(usage_events), 2)
            self.assertGreaterEqual(len(rate_snapshots), 3)
            self.assertEqual(line_count, 10)
            self.assertEqual(end_totals[-1], 180)
            self.assertEqual(sum(event["total_tokens"] for event in usage_events), 180)
            self.assertEqual(usage_events[0]["model"], "gpt-5.4")
            self.assertEqual(usage_events[1]["model"], "gpt-5.4-mini")

    def test_discover_rollout_files_finds_active_and_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = get_scan_paths(Path(tmp))
            create_sample_codex_home(paths.codex_home)
            files = discover_rollout_files(paths)
            self.assertEqual(len(files), 2)
            self.assertTrue(any("archived_sessions" in str(path) for path in files))


class TestScanIntegration(unittest.TestCase):
    def test_scan_builds_dashboard_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            db_path = Path(tmp) / "usage.sqlite"
            create_sample_codex_home(codex_home)

            result = scan(codex_home=codex_home, db_path=db_path, verbose=False)
            self.assertEqual(result["new"], 2)
            self.assertEqual(result["usage_events"], 4)
            self.assertEqual(result["threads"], 2)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            usage_count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            rate_count = conn.execute("SELECT COUNT(*) FROM rate_limit_snapshots").fetchone()[0]
            thread_row = conn.execute(
                "SELECT title, archived, tokens_used FROM threads WHERE thread_id = 'thread-002'"
            ).fetchone()
            conn.close()

            self.assertEqual(usage_count, 4)
            self.assertGreaterEqual(rate_count, 6)
            self.assertEqual(thread_row["title"], "Beta archive")
            self.assertEqual(thread_row["archived"], 1)
            self.assertEqual(thread_row["tokens_used"], 180)

    def test_scan_is_incremental(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            db_path = Path(tmp) / "usage.sqlite"
            paths = create_sample_codex_home(codex_home)

            first = scan(codex_home=codex_home, db_path=db_path, verbose=False)
            second = scan(codex_home=codex_home, db_path=db_path, verbose=False)
            self.assertEqual(first["usage_events"], 4)
            self.assertEqual(second["usage_events"], 0)
            self.assertEqual(second["skipped"], 2)

            time.sleep(0.05)
            with open(paths["rollout_one"], "a", encoding="utf-8") as handle:
                handle.write(
                    '{"timestamp":"2026-04-20T10:00:10Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":200,"cached_input_tokens":60,"output_tokens":30,"reasoning_output_tokens":5,"total_tokens":235},"last_token_usage":{"input_tokens":50,"cached_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0,"total_tokens":55},"model_context_window":258400},"rate_limits":{"limit_id":"codex","primary":{"used_percent":18.0,"window_minutes":300,"resets_at":1776708201},"secondary":{"used_percent":4.0,"window_minutes":10080,"resets_at":1777016830},"plan_type":"prolite"}}}\n'
                )

            third = scan(codex_home=codex_home, db_path=db_path, verbose=False)
            self.assertEqual(third["updated"], 1)
            self.assertEqual(third["usage_events"], 1)

            conn = sqlite3.connect(db_path)
            total = conn.execute("SELECT SUM(total_tokens) FROM usage_events WHERE thread_id = 'thread-001'").fetchone()[0]
            conn.close()
            self.assertEqual(total, 235)

    def test_init_db_creates_expected_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "usage.sqlite"
            conn = get_db(db_path)
            init_db(conn)
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            conn.close()
            self.assertIn("threads", tables)
            self.assertIn("usage_events", tables)
            self.assertIn("rate_limit_snapshots", tables)
            self.assertIn("processed_files", tables)


if __name__ == "__main__":
    unittest.main()
