"""Tests for the Codex dashboard data and HTTP endpoints."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import dashboard
from scanner import scan
from tests.helpers import create_sample_codex_home


class TestGetDashboardData(unittest.TestCase):
    def test_returns_codex_data_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            db_path = Path(tmp) / "usage.sqlite"
            create_sample_codex_home(codex_home)
            scan(codex_home=codex_home, db_path=db_path, verbose=False)

            data = dashboard.get_dashboard_data(db_path=db_path)
            self.assertIn("all_models", data)
            self.assertIn("daily_by_model", data)
            self.assertIn("models_all", data)
            self.assertIn("threads_all", data)
            self.assertIn("summary", data)
            self.assertIn("latest_rate", data)
            self.assertEqual(data["summary"]["threads"], 2)
            self.assertEqual(len(data["threads_all"]), 2)

    def test_missing_db_returns_error(self):
        data = dashboard.get_dashboard_data(db_path=Path("C:/does/not/exist/usage.sqlite"))
        self.assertIn("error", data)


class TestDashboardHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.codex_home = Path(cls.tmpdir.name) / "codex-home"
        cls.db_path = Path(cls.tmpdir.name) / "usage.sqlite"
        create_sample_codex_home(cls.codex_home)
        scan(codex_home=cls.codex_home, db_path=cls.db_path, verbose=False)

        cls.original_db_path = dashboard.DB_PATH
        cls.original_scan = dashboard.scan
        dashboard.DB_PATH = cls.db_path
        dashboard.scan = lambda verbose=False: scan(codex_home=cls.codex_home, db_path=cls.db_path, verbose=verbose)

        cls.server = dashboard.HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        dashboard.DB_PATH = cls.original_db_path
        dashboard.scan = cls.original_scan
        cls.tmpdir.cleanup()

    def test_index_returns_html(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("Codex Local Usage Dashboard", body)
            self.assertIn("Read-only over Codex local state", body)

    def test_api_data_returns_json(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/data") as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("summary", payload)
            self.assertEqual(payload["summary"]["threads"], 2)

    def test_api_rescan_returns_json(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/rescan", method="POST")
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("threads", payload)

    def test_404_for_unknown_path(self):
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/nope")
        self.assertEqual(exc.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
