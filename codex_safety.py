"""
codex_safety.py - Guardrails for reading Codex Desktop data without
interfering with Codex-managed state.
"""

import sqlite3
from pathlib import Path
from urllib.request import pathname2url


DEFAULT_CODEX_HOME = Path.home() / ".codex"


def _resolve_path(path):
    """Resolve a path without requiring it to exist."""
    return Path(path).expanduser().resolve(strict=False)


def is_codex_managed_path(path, codex_home=DEFAULT_CODEX_HOME):
    """Return True when path points at Codex-managed state."""
    resolved_path = _resolve_path(path)
    resolved_codex_home = _resolve_path(codex_home)
    return resolved_path == resolved_codex_home or resolved_codex_home in resolved_path.parents


def assert_dashboard_write_path(path, codex_home=DEFAULT_CODEX_HOME):
    """Reject dashboard-owned write paths that would land under ~/.codex."""
    resolved_path = _resolve_path(path)
    if is_codex_managed_path(resolved_path, codex_home=codex_home):
        raise ValueError(f"Dashboard writes must not target Codex-managed path: {resolved_path}")
    return resolved_path


def build_sqlite_readonly_uri(db_path):
    """Build a SQLite URI that opens an existing database in read-only mode."""
    resolved_path = _resolve_path(db_path)
    return f"file:{pathname2url(str(resolved_path))}?mode=ro"


def connect_sqlite_readonly(db_path, **kwargs):
    """Open a SQLite database in read-only mode."""
    uri = build_sqlite_readonly_uri(db_path)
    return sqlite3.connect(uri, uri=True, **kwargs)
