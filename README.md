# Codex Local Usage Dashboard

Local usage dashboard for Codex Desktop.

This project now reads Codex's local state from `~/.codex`, builds a separate dashboard-owned SQLite database in this repo, and serves a local dashboard with thread, model, project, token, and rate-limit views.

## Safety

The dashboard is designed to be non-interfering:

- It treats `~/.codex` as read-only input.
- It never writes into `~/.codex`.
- It opens Codex SQLite databases in read-only mode.
- It stores its own database in this repo as `.codex_usage.db`.

## What It Tracks

From Codex local state it currently indexes:

- threads and titles
- project/cwd
- model
- archived vs active threads
- per-turn token deltas from rollout `token_count` events
- input tokens
- cached input tokens
- output tokens
- reasoning output tokens
- total tokens
- latest rate-limit snapshots
- plan type

## Data Sources

- `~/.codex/state_5.sqlite`
- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/archived_sessions/**/*.jsonl`

`logs_2.sqlite` is not required for the current implementation.

## Quick Start

```bash
python cli.py scan
python cli.py stats
python cli.py dashboard
```

The dashboard runs locally on `http://localhost:8080` by default.

## CLI

```bash
python cli.py scan [--codex-home PATH]
python cli.py today
python cli.py stats
python cli.py dashboard [--codex-home PATH]
```

## Notes

- This is not a 1:1 Claude dashboard port.
- Cost estimation is intentionally out of scope.
- Metrics come from Codex local data and are optimized for usefulness, not billing parity.

## Tests

```bash
python -m unittest
```
