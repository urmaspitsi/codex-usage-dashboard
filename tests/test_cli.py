"""Tests for the Codex usage CLI."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cli
from scanner import scan
from tests.helpers import create_sample_codex_home


class TestCliHelpers(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(cli.fmt(999), "999")
        self.assertEqual(cli.fmt(1_200), "1.2K")
        self.assertEqual(cli.fmt(1_500_000), "1.50M")

    def test_parse_codex_home(self):
        args = ["--codex-home", "C:\\Temp\\.codex"]
        self.assertEqual(cli.parse_codex_home(args), "C:\\Temp\\.codex")
        self.assertIsNone(cli.parse_codex_home([]))


class TestCliCommands(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.tmpdir.name) / "codex-home"
        self.db_path = Path(self.tmpdir.name) / "usage.sqlite"
        create_sample_codex_home(self.codex_home)
        scan(codex_home=self.codex_home, db_path=self.db_path, verbose=False)
        self.original_db_path = cli.DB_PATH
        cli.DB_PATH = self.db_path

    def tearDown(self):
        cli.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_cmd_today_prints_codex_metrics(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.cmd_today()
        output = buf.getvalue()
        self.assertIn("Codex Usage Today", output)
        self.assertIn("Input tokens", output)
        self.assertIn("Plan type", output)

    def test_cmd_stats_prints_summary(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.cmd_stats()
        output = buf.getvalue()
        self.assertIn("Codex Local Usage Statistics", output)
        self.assertIn("Top Models", output)
        self.assertIn("Top Projects", output)


if __name__ == "__main__":
    unittest.main()
