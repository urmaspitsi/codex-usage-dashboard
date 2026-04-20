"""Tests for Codex non-interference guardrails."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from codex_safety import (
    DEFAULT_CODEX_HOME,
    assert_dashboard_write_path,
    build_sqlite_readonly_uri,
    connect_sqlite_readonly,
    is_codex_managed_path,
)


class TestCodexPathSafety(unittest.TestCase):
    def test_detects_codex_home(self):
        self.assertTrue(is_codex_managed_path(DEFAULT_CODEX_HOME))

    def test_detects_codex_descendant(self):
        path = DEFAULT_CODEX_HOME / "state_5.sqlite"
        self.assertTrue(is_codex_managed_path(path))

    def test_non_codex_path_is_allowed(self):
        path = Path.home() / "Documents" / "codex-usage-dashboard" / "usage.db"
        self.assertFalse(is_codex_managed_path(path))
        self.assertEqual(assert_dashboard_write_path(path), path.resolve(strict=False))

    def test_dashboard_write_path_rejects_codex_managed_target(self):
        with self.assertRaises(ValueError):
            assert_dashboard_write_path(DEFAULT_CODEX_HOME / "usage.db")


class TestReadonlySqliteAccess(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "sample.sqlite"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO items (name) VALUES ('alpha')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_readonly_uri_uses_mode_ro(self):
        uri = build_sqlite_readonly_uri(self.db_path)
        self.assertTrue(uri.startswith("file:"))
        self.assertIn("?mode=ro", uri)

    def test_readonly_connection_can_read(self):
        conn = connect_sqlite_readonly(self.db_path)
        try:
            row = conn.execute("SELECT name FROM items").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "alpha")

    def test_readonly_connection_rejects_writes(self):
        conn = connect_sqlite_readonly(self.db_path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO items (name) VALUES ('beta')")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
