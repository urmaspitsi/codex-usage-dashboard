"""
dashboard.py - Local Codex usage dashboard served on localhost.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from scanner import DB_PATH, scan


def _duration_minutes(start: str, end: str) -> float:
    if not start or not end:
        return 0.0
    try:
        t1 = datetime.fromisoformat(start.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return round(max((t2 - t1).total_seconds(), 0) / 60, 1)


def get_dashboard_data(db_path: Path | None = None) -> dict:
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return {"error": "Database not found. Run: python cli.py scan"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS usage_events,
            COUNT(DISTINCT thread_id) AS threads_with_usage,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens
        FROM usage_events
        """
    ).fetchone()

    thread_totals = conn.execute(
        """
        SELECT
            COUNT(*) AS threads,
            SUM(CASE WHEN archived = 0 THEN 1 ELSE 0 END) AS active_threads,
            SUM(CASE WHEN archived = 1 THEN 1 ELSE 0 END) AS archived_threads,
            SUM(tokens_used) AS tokens_used
        FROM threads
        """
    ).fetchone()

    latest_rate = conn.execute(
        """
        SELECT
            plan_type,
            primary_used_percent,
            primary_window_minutes,
            primary_resets_at,
            secondary_used_percent,
            secondary_window_minutes,
            secondary_resets_at
        FROM rate_limit_snapshots
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    daily_rows = conn.execute(
        """
        SELECT
            day,
            COALESCE(model, 'unknown') AS model,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            COUNT(*) AS turns
        FROM usage_events
        GROUP BY day, model
        ORDER BY day, model
        """
    ).fetchall()

    model_rows = conn.execute(
        """
        SELECT
            COALESCE(model, 'unknown') AS model,
            COUNT(*) AS turns,
            COUNT(DISTINCT thread_id) AS threads,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens
        FROM usage_events
        GROUP BY model
        ORDER BY total_tokens DESC, model ASC
        """
    ).fetchall()

    thread_rows = conn.execute(
        """
        SELECT
            t.thread_id,
            t.title,
            t.project_name,
            t.cwd,
            t.model,
            t.created_at,
            t.updated_at,
            t.archived,
            t.tokens_used,
            COUNT(u.id) AS turns,
            COALESCE(SUM(u.input_tokens), 0) AS input_tokens,
            COALESCE(SUM(u.cached_input_tokens), 0) AS cached_input_tokens,
            COALESCE(SUM(u.output_tokens), 0) AS output_tokens,
            COALESCE(SUM(u.reasoning_output_tokens), 0) AS reasoning_output_tokens,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens
        FROM threads t
        LEFT JOIN usage_events u ON u.thread_id = t.thread_id
        GROUP BY t.thread_id
        ORDER BY COALESCE(t.updated_at_unix, 0) DESC, t.updated_at DESC, t.thread_id DESC
        """
    ).fetchall()

    conn.close()

    all_models = [row["model"] for row in model_rows]
    daily_by_model = [
        {
            "day": row["day"],
            "model": row["model"],
            "input": row["input_tokens"] or 0,
            "cached": row["cached_input_tokens"] or 0,
            "output": row["output_tokens"] or 0,
            "reasoning": row["reasoning_output_tokens"] or 0,
            "total": row["total_tokens"] or 0,
            "turns": row["turns"] or 0,
        }
        for row in daily_rows
    ]

    models_all = [
        {
            "model": row["model"],
            "turns": row["turns"] or 0,
            "threads": row["threads"] or 0,
            "input": row["input_tokens"] or 0,
            "cached": row["cached_input_tokens"] or 0,
            "output": row["output_tokens"] or 0,
            "reasoning": row["reasoning_output_tokens"] or 0,
            "total": row["total_tokens"] or 0,
        }
        for row in model_rows
    ]

    threads_all = []
    for row in thread_rows:
        threads_all.append(
            {
                "thread_id": row["thread_id"],
                "short_id": (row["thread_id"] or "")[:8],
                "title": row["title"] or "Untitled thread",
                "project": row["project_name"] or "unknown",
                "cwd": row["cwd"] or "",
                "model": row["model"] or "unknown",
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
                "updated_day": (row["updated_at"] or "")[:10],
                "duration_min": _duration_minutes(row["created_at"], row["updated_at"]),
                "archived": int(row["archived"] or 0),
                "turns": row["turns"] or 0,
                "input": row["input_tokens"] or 0,
                "cached": row["cached_input_tokens"] or 0,
                "output": row["output_tokens"] or 0,
                "reasoning": row["reasoning_output_tokens"] or 0,
                "event_total": row["total_tokens"] or 0,
                "tokens_used": row["tokens_used"] or 0,
            }
        )

    return {
        "all_models": all_models,
        "daily_by_model": daily_by_model,
        "models_all": models_all,
        "threads_all": threads_all,
        "summary": {
            "usage_events": summary["usage_events"] or 0,
            "threads_with_usage": summary["threads_with_usage"] or 0,
            "threads": thread_totals["threads"] or 0,
            "active_threads": thread_totals["active_threads"] or 0,
            "archived_threads": thread_totals["archived_threads"] or 0,
            "thread_tokens_used": thread_totals["tokens_used"] or 0,
            "input_tokens": summary["input_tokens"] or 0,
            "cached_input_tokens": summary["cached_input_tokens"] or 0,
            "output_tokens": summary["output_tokens"] or 0,
            "reasoning_output_tokens": summary["reasoning_output_tokens"] or 0,
            "total_tokens": summary["total_tokens"] or 0,
        },
        "latest_rate": dict(latest_rate) if latest_rate else None,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Codex Local Usage Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0b1220;
    --panel: #121b2f;
    --panel-2: #16213a;
    --border: #233252;
    --text: #eef4ff;
    --muted: #9aa8c7;
    --accent: #64d2ff;
    --accent-2: #78f0c4;
    --warn: #ffb86b;
    --danger: #ff8d8d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background:
      radial-gradient(circle at top left, rgba(100,210,255,0.10), transparent 30%),
      radial-gradient(circle at top right, rgba(120,240,196,0.08), transparent 30%),
      linear-gradient(180deg, #0a1020 0%, #0b1220 100%);
    color: var(--text);
    font-family: "Segoe UI", system-ui, sans-serif;
  }
  header {
    padding: 22px 24px 18px;
    border-bottom: 1px solid var(--border);
    background: rgba(10,16,32,0.75);
    backdrop-filter: blur(8px);
    position: sticky;
    top: 0;
    z-index: 5;
  }
  h1 { margin: 0; font-size: 24px; }
  .meta { color: var(--muted); font-size: 13px; margin-top: 4px; }
  .notice {
    margin-top: 10px;
    color: var(--accent-2);
    font-size: 12px;
  }
  .toolbar {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }
  .toolbar .group {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .toolbar-label {
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  button, .chip {
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    border-radius: 999px;
    padding: 7px 12px;
    cursor: pointer;
    font-size: 12px;
  }
  button:hover { border-color: var(--accent); }
  button.active {
    background: rgba(100,210,255,0.12);
    border-color: var(--accent);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
  }
  .chip input { display: none; }
  .chip.checked {
    background: rgba(120,240,196,0.10);
    border-color: var(--accent-2);
  }
  .container {
    max-width: 1440px;
    margin: 0 auto;
    padding: 24px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 14px;
    margin-bottom: 20px;
  }
  .card {
    background: linear-gradient(180deg, rgba(18,27,47,0.98), rgba(18,27,47,0.92));
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 12px 28px rgba(0,0,0,0.20);
  }
  .stat-label {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }
  .stat-value {
    font-size: 26px;
    font-weight: 700;
  }
  .stat-sub {
    color: var(--muted);
    font-size: 12px;
    margin-top: 6px;
  }
  .grid {
    display: grid;
    grid-template-columns: 1.3fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }
  .panel-title {
    margin: 0 0 12px;
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .chart-wrap { position: relative; height: 320px; }
  .table-card { margin-top: 16px; overflow-x: auto; }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    text-align: left;
    font-size: 13px;
    vertical-align: top;
  }
  th {
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  tr:last-child td { border-bottom: none; }
  .muted { color: var(--muted); }
  .num { font-family: Consolas, monospace; }
  .tag {
    display: inline-block;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 4px 8px;
    font-size: 11px;
    color: var(--accent);
    background: rgba(100,210,255,0.08);
  }
  .tag.archived {
    color: var(--warn);
    background: rgba(255,184,107,0.08);
  }
  .rate-line {
    font-size: 13px;
    color: var(--muted);
    margin-top: 8px;
  }
  .bar {
    margin-top: 8px;
    height: 10px;
    width: 100%;
    background: rgba(255,255,255,0.05);
    border-radius: 999px;
    overflow: hidden;
  }
  .bar > span {
    display: block;
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
  }
  @media (max-width: 960px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <h1>Codex Local Usage Dashboard</h1>
  <div class="meta" id="meta">Loading…</div>
  <div class="notice">Read-only over Codex local state. Dashboard data is stored separately and never written into <code>~/.codex</code>.</div>
  <div class="toolbar">
    <div class="group">
      <span class="toolbar-label">Range</span>
      <button class="range-btn" data-range="7d" onclick="setRange('7d')">7d</button>
      <button class="range-btn" data-range="30d" onclick="setRange('30d')">30d</button>
      <button class="range-btn" data-range="90d" onclick="setRange('90d')">90d</button>
      <button class="range-btn" data-range="all" onclick="setRange('all')">All</button>
    </div>
    <div class="group">
      <span class="toolbar-label">Models</span>
      <div id="model-filter"></div>
      <button onclick="selectAllModels()">All</button>
      <button onclick="clearModels()">None</button>
    </div>
    <div class="group">
      <button id="rescan-btn" onclick="triggerRescan()">Rescan</button>
    </div>
  </div>
</header>

<div class="container">
  <div class="stats" id="stats"></div>
  <div class="grid">
    <div class="card">
      <h2 class="panel-title">Daily Token Flow</h2>
      <div class="chart-wrap"><canvas id="daily-chart"></canvas></div>
    </div>
    <div class="card">
      <h2 class="panel-title">Latest Rate Limits</h2>
      <div id="rate-card"></div>
    </div>
  </div>
  <div class="grid">
    <div class="card">
      <h2 class="panel-title">Tokens By Model</h2>
      <div class="chart-wrap"><canvas id="model-chart"></canvas></div>
    </div>
    <div class="card">
      <h2 class="panel-title">Top Projects</h2>
      <div class="chart-wrap"><canvas id="project-chart"></canvas></div>
    </div>
  </div>
  <div class="card table-card">
    <h2 class="panel-title">Models</h2>
    <table>
      <thead>
        <tr>
          <th>Model</th>
          <th>Threads</th>
          <th>Turns</th>
          <th>Total</th>
          <th>Input</th>
          <th>Cached</th>
          <th>Output</th>
          <th>Reasoning</th>
        </tr>
      </thead>
      <tbody id="models-body"></tbody>
    </table>
  </div>
  <div class="card table-card">
    <h2 class="panel-title">Recent Threads</h2>
    <table>
      <thead>
        <tr>
          <th>Thread</th>
          <th>Project</th>
          <th>Updated</th>
          <th>Status</th>
          <th>Model</th>
          <th>Turns</th>
          <th>Event Total</th>
          <th>Thread Tokens</th>
        </tr>
      </thead>
      <tbody id="threads-body"></tbody>
    </table>
  </div>
</div>

<script>
const RANGE_LABELS = { '7d': 'Last 7 days', '30d': 'Last 30 days', '90d': 'Last 90 days', 'all': 'All time' };
const COLORS = ['#64d2ff','#78f0c4','#ffb86b','#c59bff','#8bd3ff','#f98fb7','#ffe082','#a7f3d0','#fda4af','#93c5fd'];

let rawData = null;
let selectedModels = new Set();
let selectedRange = '30d';
let charts = {};

function esc(value) {
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

function fmt(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n || 0);
}

function pct(value) {
  return ((value || 0)).toFixed(1) + '%';
}

function cutoffFor(range) {
  if (range === 'all') return null;
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  const date = new Date();
  date.setDate(date.getDate() - (days - 1));
  return date.toISOString().slice(0, 10);
}

function buildModelFilter(models) {
  const host = document.getElementById('model-filter');
  host.innerHTML = models.map(model => `
    <label class="chip checked" data-model="${esc(model)}">
      <input type="checkbox" checked onchange="toggleModel('${esc(model)}')">
      <span>${esc(model)}</span>
    </label>
  `).join('');
}

function toggleModel(model) {
  if (selectedModels.has(model)) selectedModels.delete(model);
  else selectedModels.add(model);
  syncModelFilter();
  applyFilter();
}

function syncModelFilter() {
  document.querySelectorAll('#model-filter .chip').forEach(label => {
    const model = label.getAttribute('data-model');
    const checked = selectedModels.has(model);
    label.classList.toggle('checked', checked);
    label.querySelector('input').checked = checked;
  });
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.range === selectedRange);
  });
}

function selectAllModels() {
  rawData.all_models.forEach(model => selectedModels.add(model));
  syncModelFilter();
  applyFilter();
}

function clearModels() {
  selectedModels.clear();
  syncModelFilter();
  applyFilter();
}

function setRange(range) {
  selectedRange = range;
  syncModelFilter();
  applyFilter();
}

function aggregateProjects(threads) {
  const map = {};
  for (const t of threads) {
    const key = t.project || 'unknown';
    if (!map[key]) {
      map[key] = { project: key, threads: 0, turns: 0, total: 0, input: 0, cached: 0, output: 0, reasoning: 0 };
    }
    map[key].threads += 1;
    map[key].turns += t.turns;
    map[key].total += t.event_total;
    map[key].input += t.input;
    map[key].cached += t.cached;
    map[key].output += t.output;
    map[key].reasoning += t.reasoning;
  }
  return Object.values(map).sort((a, b) => b.total - a.total);
}

function applyFilter() {
  if (!rawData) return;
  const cutoff = cutoffFor(selectedRange);

  const daily = rawData.daily_by_model.filter(row =>
    selectedModels.has(row.model) && (!cutoff || row.day >= cutoff)
  );

  const models = rawData.models_all.filter(row => selectedModels.has(row.model));

  const threads = rawData.threads_all.filter(row =>
    selectedModels.has(row.model) && (!cutoff || !row.updated_day || row.updated_day >= cutoff)
  );

  const totals = {
    threads: threads.length,
    activeThreads: threads.filter(t => !t.archived).length,
    archivedThreads: threads.filter(t => t.archived).length,
    turns: threads.reduce((sum, row) => sum + row.turns, 0),
    input: models.reduce((sum, row) => sum + row.input, 0),
    cached: models.reduce((sum, row) => sum + row.cached, 0),
    output: models.reduce((sum, row) => sum + row.output, 0),
    reasoning: models.reduce((sum, row) => sum + row.reasoning, 0),
    total: models.reduce((sum, row) => sum + row.total, 0),
  };

  renderStats(totals);
  renderRateCard(rawData.latest_rate);
  renderDailyChart(daily);
  renderModelChart(models);
  renderProjectChart(aggregateProjects(threads));
  renderModelsTable(models);
  renderThreadsTable(threads.slice(0, 30));
}

function renderStats(totals) {
  const stats = [
    ['Threads', totals.threads, RANGE_LABELS[selectedRange]],
    ['Active', totals.activeThreads, 'non-archived'],
    ['Archived', totals.archivedThreads, 'archived'],
    ['Turns', fmt(totals.turns), RANGE_LABELS[selectedRange]],
    ['Input', fmt(totals.input), 'input tokens'],
    ['Cached', fmt(totals.cached), 'cached input'],
    ['Output', fmt(totals.output), 'output tokens'],
    ['Reasoning', fmt(totals.reasoning), 'reasoning tokens'],
    ['Total', fmt(totals.total), 'summed last-token deltas'],
  ];
  document.getElementById('stats').innerHTML = stats.map(([label, value, sub]) => `
    <div class="card">
      <div class="stat-label">${esc(label)}</div>
      <div class="stat-value">${esc(value)}</div>
      <div class="stat-sub">${esc(sub)}</div>
    </div>
  `).join('');
}

function renderRateCard(rate) {
  const host = document.getElementById('rate-card');
  if (!rate) {
    host.innerHTML = '<div class="muted">No rate limit snapshots recorded yet.</div>';
    return;
  }
  const primary = Math.max(0, Math.min(rate.primary_used_percent || 0, 100));
  const secondary = Math.max(0, Math.min(rate.secondary_used_percent || 0, 100));
  host.innerHTML = `
    <div class="stat-value">${esc(rate.plan_type || 'unknown')}</div>
    <div class="stat-sub">Latest recorded Codex plan type</div>
    <div class="rate-line">Primary: ${pct(primary)} of ${esc(rate.primary_window_minutes || 0)} minutes</div>
    <div class="bar"><span style="width:${primary}%"></span></div>
    <div class="rate-line">Secondary: ${pct(secondary)} of ${esc(rate.secondary_window_minutes || 0)} minutes</div>
    <div class="bar"><span style="width:${secondary}%"></span></div>
  `;
}

function destroyChart(name) {
  if (charts[name]) charts[name].destroy();
}

function renderDailyChart(rows) {
  destroyChart('daily');
  const dailyMap = {};
  for (const row of rows) {
    if (!dailyMap[row.day]) dailyMap[row.day] = { day: row.day, input: 0, cached: 0, output: 0, reasoning: 0 };
    dailyMap[row.day].input += row.input;
    dailyMap[row.day].cached += row.cached;
    dailyMap[row.day].output += row.output;
    dailyMap[row.day].reasoning += row.reasoning;
  }
  const daily = Object.values(dailyMap).sort((a, b) => a.day.localeCompare(b.day));
  charts.daily = new Chart(document.getElementById('daily-chart'), {
    type: 'bar',
    data: {
      labels: daily.map(row => row.day),
      datasets: [
        { label: 'Input', data: daily.map(row => row.input), backgroundColor: '#64d2ff', stack: 'tokens' },
        { label: 'Cached', data: daily.map(row => row.cached), backgroundColor: '#78f0c4', stack: 'tokens' },
        { label: 'Output', data: daily.map(row => row.output), backgroundColor: '#ffb86b', stack: 'tokens' },
        { label: 'Reasoning', data: daily.map(row => row.reasoning), backgroundColor: '#c59bff', stack: 'tokens' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#9aa8c7' } } },
      scales: {
        x: { ticks: { color: '#9aa8c7' }, grid: { color: '#233252' } },
        y: { ticks: { color: '#9aa8c7', callback: value => fmt(value) }, grid: { color: '#233252' } }
      }
    }
  });
}

function renderModelChart(rows) {
  destroyChart('model');
  charts.model = new Chart(document.getElementById('model-chart'), {
    type: 'doughnut',
    data: {
      labels: rows.map(row => row.model),
      datasets: [{ data: rows.map(row => row.total), backgroundColor: COLORS, borderColor: '#121b2f', borderWidth: 2 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#9aa8c7' } } }
    }
  });
}

function renderProjectChart(rows) {
  destroyChart('project');
  const top = rows.slice(0, 10);
  charts.project = new Chart(document.getElementById('project-chart'), {
    type: 'bar',
    data: {
      labels: top.map(row => row.project.length > 24 ? '…' + row.project.slice(-22) : row.project),
      datasets: [{ label: 'Total Tokens', data: top.map(row => row.total), backgroundColor: '#64d2ff' }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#9aa8c7' } } },
      scales: {
        x: { ticks: { color: '#9aa8c7', callback: value => fmt(value) }, grid: { color: '#233252' } },
        y: { ticks: { color: '#9aa8c7' }, grid: { color: '#233252' } }
      }
    }
  });
}

function renderModelsTable(rows) {
  document.getElementById('models-body').innerHTML = rows.map(row => `
    <tr>
      <td><span class="tag">${esc(row.model)}</span></td>
      <td class="num">${esc(row.threads)}</td>
      <td class="num">${esc(row.turns)}</td>
      <td class="num">${esc(fmt(row.total))}</td>
      <td class="num">${esc(fmt(row.input))}</td>
      <td class="num">${esc(fmt(row.cached))}</td>
      <td class="num">${esc(fmt(row.output))}</td>
      <td class="num">${esc(fmt(row.reasoning))}</td>
    </tr>
  `).join('');
}

function renderThreadsTable(rows) {
  document.getElementById('threads-body').innerHTML = rows.map(row => `
    <tr>
      <td>
        <div>${esc(row.title)}</div>
        <div class="muted">${esc(row.short_id)}…</div>
      </td>
      <td>${esc(row.project)}</td>
      <td class="muted">${esc((row.updated_at || '').slice(0, 16).replace('T', ' '))}</td>
      <td>${row.archived ? '<span class="tag archived">Archived</span>' : '<span class="tag">Active</span>'}</td>
      <td><span class="tag">${esc(row.model)}</span></td>
      <td class="num">${esc(row.turns)}</td>
      <td class="num">${esc(fmt(row.event_total))}</td>
      <td class="num">${esc(fmt(row.tokens_used))}</td>
    </tr>
  `).join('');
}

async function triggerRescan() {
  const btn = document.getElementById('rescan-btn');
  btn.disabled = true;
  btn.textContent = 'Scanning…';
  try {
    await fetch('/api/rescan', { method: 'POST' });
    await loadData();
    btn.textContent = 'Rescan';
  } finally {
    btn.disabled = false;
  }
}

async function loadData() {
  const response = await fetch('/api/data');
  const data = await response.json();
  if (data.error) {
    document.body.innerHTML = '<div style="padding:32px;color:#ff8d8d">' + esc(data.error) + '</div>';
    return;
  }
  rawData = data;
  document.getElementById('meta').textContent = 'Updated: ' + data.generated_at + ' · Auto-refresh every 30 seconds';
  if (selectedModels.size === 0) {
    data.all_models.forEach(model => selectedModels.add(model));
    buildModelFilter(data.all_models);
  }
  syncModelFilter();
  applyFilter();
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        pass

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = HTML_TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/data":
            body = json.dumps(get_dashboard_data()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path == "/api/rescan":
            if DB_PATH.exists():
                DB_PATH.unlink()
            result = scan(verbose=False)
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or os.environ.get("HOST", "localhost")
    port = port or int(os.environ.get("PORT", "8080"))
    server = HTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    serve()
