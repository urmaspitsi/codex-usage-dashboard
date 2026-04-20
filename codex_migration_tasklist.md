# Codex Migration Task List

## Goal

Port this local usage dashboard from Claude-specific data sources to Codex Desktop data sources on this machine.

The target is **not** a 1:1 Claude clone. The target is a useful local Codex usage dashboard based on data Codex already writes locally.

## Hard Constraint

The dashboard app/service **must not interfere with Codex Desktop**. It must not interrupt, corrupt, lock, modify, or slow down Codex's own local state in a meaningful way.

## Non-Interference Rules

- [x] Treat `C:\Users\Urmas\.codex` as a read-only source of truth.
- [x] Do not write anything into `~/.codex`.
- [x] Do not delete, vacuum, migrate, or alter Codex SQLite files.
- [x] Open Codex SQLite databases in read-only mode only.
- [ ] Prefer short-lived reads over long-lived open handles.
- [ ] Avoid relying on unstable internal files when a safer source exists.
- [x] Parse session rollout files as append-only inputs; never rewrite them.
- [x] Store all dashboard-owned state in this project or another dashboard-owned path only.
- [ ] Fail closed: if a Codex source cannot be read safely, skip it and keep the dashboard working.
- [ ] Document rollback: stopping the dashboard leaves Codex data untouched.

## Phase 1: Source Mapping

- [x] Confirm exact Codex data sources to support:
- [x] `state_5.sqlite` for thread metadata.
- [x] `sessions/**/*.jsonl` for rollout events.
- [x] `archived_sessions/**/*.jsonl` for archived thread history.
- [x] Evaluate `logs_2.sqlite` as optional enrichment only, not primary dependency.
- [ ] Document field mapping from Codex sources to dashboard schema.
- [x] Identify duplicate or cumulative event patterns that require deduplication.

## Phase 2: Dashboard Data Model

- [x] Design a Codex-specific local `usage.db` schema.
- [x] Separate `threads`, `usage_events`, `rate_limit_snapshots`, and `processed_files`.
- [ ] Track source file path, mtime, and last processed position for incremental scans.
- [x] Add a clear dedup key strategy for cumulative token events.
- [ ] Decide which metrics are primary and which are optional.

## Phase 3: MVP Metrics

- [x] Implement thread/session inventory:
- [x] title
- [x] cwd/project
- [x] model
- [x] created/updated timestamps
- [x] archived status
- [x] total `tokens_used`
- [x] Implement daily usage totals.
- [x] Implement per-project totals.
- [x] Implement per-model totals.
- [x] Implement recent threads view.

## Phase 4: Useful Codex-Native Metrics

- [x] Add `input_tokens`.
- [x] Add `cached_input_tokens`.
- [x] Add `output_tokens`.
- [x] Add `reasoning_output_tokens`.
- [x] Add `total_tokens`.
- [x] Add rate-limit usage snapshots from rollout events.
- [ ] Add rate-limit reset times.
- [x] Add plan type when present.
- [x] Add context-window visibility when present.

## Phase 5: Scanner Rewrite

- [x] Replace Claude JSONL parsing logic in `scanner.py` with Codex-specific parsing.
- [x] Preserve incremental scanning behavior.
- [x] Make scanner resilient to malformed or partial lines.
- [x] Make scanner resilient to live-growing rollout files.
- [x] Ensure repeated scans do not inflate totals.
- [ ] Keep scanner output deterministic.

## Phase 6: Dashboard/UI Adaptation

- [x] Rename product language from Claude to Codex.
- [x] Remove cost-first language from CLI and dashboard.
- [x] Replace cost cards/tables with Codex-native metrics.
- [x] Keep range filtering and model/project/session filtering.
- [x] Keep local-only serving model.
- [x] Add a visible note that the dashboard is read-only over Codex data.

## Phase 7: Safety Implementation

- [x] Use read-only SQLite connection strings for Codex DB access.
- [ ] Decide whether to read live DBs directly or copy snapshots first.
- [ ] If direct-read is used, keep reads brief and retry safely on lock/busy states.
- [ ] If snapshot-copy is used, copy into a dashboard-owned temp/work path only.
- [ ] Never block dashboard startup on optional enrichment sources.
- [x] Add explicit guards that prevent accidental writes to Codex paths.

## Phase 8: Testing

- [ ] Keep non-interference tests as a blocking release gate.
- [x] Add fixture-based tests for Codex rollout parsing.
- [x] Add tests for deduplication of cumulative token events.
- [x] Add tests for archived-session ingestion.
- [x] Add tests for live-file incremental scanning.
- [ ] Add tests proving scanner works when optional sources are missing.
- [ ] Add tests proving dashboard still works with partial data.
- [x] Add tests that verify no write paths target `~/.codex`.
- [x] Add tests that verify Codex SQLite access uses read-only connections.
- [x] Add tests that verify attempted writes through Codex read handles fail.

## Phase 9: CLI and Docs

- [x] Update `README.md` for Codex setup and usage.
- [x] Update `cli.py` help text and command descriptions.
- [ ] Document supported local Codex sources.
- [ ] Document known gaps versus Claude dashboard.
- [ ] Document privacy and non-interference guarantees.

## Optional Enhancements

- [ ] Add OTEL/log enrichment from `logs_2.sqlite` behind a feature flag.
- [ ] Add per-turn or per-response views if dedup is reliable enough.
- [ ] Add thread drill-down page.
- [ ] Add export for CSV/JSON reports.
- [ ] Add archived vs active thread filters.

## Known Gaps

- [ ] No need to match Claude pricing or cost estimation.
- [ ] No need to match Claude transcript structure exactly.
- [ ] Cross-device/account-wide aggregation is out of scope.
- [ ] Internal Codex telemetry formats may change between app versions.

## Acceptance Criteria

- [x] Dashboard reads Codex data without writing to `~/.codex`.
- [ ] Non-interference tests pass and remain required for future changes.
- [x] Repeated scans do not corrupt or inflate metrics.
- [ ] Stopping the dashboard leaves Codex fully unaffected.
- [x] Dashboard provides useful usage views even without OTEL enrichment.
- [x] All tests pass.
