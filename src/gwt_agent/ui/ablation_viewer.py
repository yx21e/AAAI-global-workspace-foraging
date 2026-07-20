from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from gwt_agent.ui.qiyuan_viewer import default_run_paths, load_jsonl, relative_path


def build_ablation_viewer(
    *,
    manifest_path: str,
    output_path: Optional[str] = None,
) -> Path:
    manifest = Path(manifest_path).expanduser().resolve()
    if output_path:
        viewer_path = Path(output_path).expanduser().resolve()
    else:
        viewer_path = manifest.with_name(f"{manifest.stem}_viewer.html")
    payload = build_ablation_payload(
        manifest_path=str(manifest),
        viewer_dir=str(viewer_path.parent),
    )
    viewer_path.parent.mkdir(parents=True, exist_ok=True)
    viewer_path.write_text(render_html(payload), encoding="utf-8")
    return viewer_path


def build_ablation_payload(
    *,
    manifest_path: str,
    viewer_dir: Optional[str] = None,
) -> dict:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    base_dir = manifest_file.parent
    viewer_base = Path(viewer_dir).expanduser().resolve() if viewer_dir else base_dir
    levels = []
    for level in normalize_levels(manifest):
        conditions = []
        for condition in level["conditions"]:
            run_metrics = [
                run_metric(
                    run_ref=run_ref,
                    default_run_dir=condition.get("run_dir") or level.get("run_dir") or manifest.get("run_dir"),
                    base_dir=base_dir,
                    viewer_base=viewer_base,
                )
                for run_ref in normalize_run_refs(condition)
            ]
            conditions.append(
                {
                    "id": str(condition.get("id") or slug(condition.get("label") or "condition")),
                    "label": str(condition.get("label") or condition.get("id") or "Condition"),
                    "description": str(condition.get("description") or ""),
                    "expected_effect": str(condition.get("expected_effect") or ""),
                    "manipulation": str(condition.get("manipulation") or ""),
                    "metrics": aggregate_metrics(run_metrics),
                    "runs": run_metrics,
                }
            )
        levels.append(
            {
                "id": str(level.get("id") or slug(level.get("label") or "level")),
                "label": str(level.get("label") or level.get("id") or "Ablation Level"),
                "description": str(level.get("description") or ""),
                "conditions": conditions,
            }
        )
    return {
        "title": str(manifest.get("title") or "GWT Ablation Dashboard"),
        "description": str(manifest.get("description") or ""),
        "generated_from": relative_path(manifest_file, viewer_base),
        "levels": levels,
        "total_conditions": sum(len(level["conditions"]) for level in levels),
        "total_runs": sum(
            len(condition["runs"])
            for level in levels
            for condition in level["conditions"]
        ),
    }


def normalize_levels(manifest: dict) -> List[dict]:
    levels = manifest.get("levels")
    if isinstance(levels, list):
        normalized = []
        for level in levels:
            if not isinstance(level, dict):
                continue
            conditions = level.get("conditions")
            if not isinstance(conditions, list):
                continue
            normalized.append({**level, "conditions": [item for item in conditions if isinstance(item, dict)]})
        return normalized

    conditions = [item for item in manifest.get("conditions", []) if isinstance(item, dict)]
    grouped: Dict[str, dict] = {}
    for condition in conditions:
        level_label = str(condition.get("level") or "Ablation")
        level_id = slug(level_label)
        grouped.setdefault(
            level_id,
            {
                "id": level_id,
                "label": level_label,
                "description": "",
                "run_dir": manifest.get("run_dir"),
                "conditions": [],
            },
        )["conditions"].append(condition)
    return list(grouped.values())


def normalize_run_refs(condition: dict) -> List[Any]:
    if isinstance(condition.get("runs"), list):
        return condition["runs"]
    if isinstance(condition.get("run_ids"), list):
        return [{"run_id": item} for item in condition["run_ids"]]
    if condition.get("run_id"):
        return [{"run_id": condition["run_id"]}]
    return []


def run_metric(
    *,
    run_ref: Any,
    default_run_dir: Optional[str],
    base_dir: Path,
    viewer_base: Path,
) -> dict:
    if isinstance(run_ref, str):
        run_ref = {"run_id": run_ref}
    if not isinstance(run_ref, dict):
        return {"run_id": str(run_ref), "error": "Run reference must be a string or object."}

    run_id = str(run_ref.get("run_id") or "")
    run_dir_value = run_ref.get("run_dir") or default_run_dir or "."
    run_dir = resolve_path(str(run_dir_value), base_dir)
    paths = default_run_paths(run_dir, run_id)
    metric = {
        "run_id": run_id,
        "label": str(run_ref.get("label") or run_id),
        "run_dir": str(run_dir),
        "summary_link": None,
        "viewer_link": None,
        "done": False,
        "success": False,
        "cycle_count": None,
        "env_step_count": None,
        "resources_collected": None,
        "map_label": "-",
        "agent_position": None,
        "winner_counts": {},
        "route_counts": {},
        "motor_target_sources": {},
        "action_failures": 0,
        "longest_same_position": 0,
        "max_period2_repeat": 0,
        "error": None,
    }
    if paths["summary"].exists():
        metric["summary_link"] = relative_path(paths["summary"], viewer_base)
    if paths["viewer"].exists():
        metric["viewer_link"] = relative_path(paths["viewer"], viewer_base)
    try:
        summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
        metric.update(summary_metrics(summary))
        if paths["envelopes"].exists():
            metric.update(trace_metrics(load_jsonl(paths["envelopes"])))
    except Exception as exc:
        metric["error"] = str(exc)
    return metric


def summary_metrics(summary: dict) -> dict:
    resolved_preset = summary.get("resolved_map_preset") or summary.get("map_preset") or "qiyuan-default"
    resolved_variant = summary.get("resolved_map_variant")
    map_label = (
        str(resolved_preset)
        if resolved_variant is None
        else f"{resolved_preset} v{resolved_variant}"
    )
    resources = summary.get("resources_collected")
    done = bool(summary.get("done"))
    target_resources = summary.get("target_resources") or 1
    try:
        success = done and int(resources or 0) >= int(target_resources)
    except (TypeError, ValueError):
        success = done
    return {
        "done": done,
        "success": success,
        "cycle_count": summary.get("cycle_count"),
        "env_step_count": summary.get("env_step_count"),
        "resources_collected": resources,
        "map_label": map_label,
        "agent_position": summary.get("agent_position"),
        "difficulty": summary.get("difficulty"),
        "seed": summary.get("seed"),
        "target_resources": target_resources,
        "ablation_config": {
            "disabled_modules": summary.get("disabled_modules"),
            "score_modifiers": summary.get("score_modifiers"),
            "ignition_threshold": summary.get("ignition_threshold"),
            "salience_weight": summary.get("salience_weight"),
            "relevance_weight": summary.get("relevance_weight"),
            "workspace_recurrence_bonus": summary.get("workspace_recurrence_bonus"),
            "workspace_adjustment_policy": summary.get("workspace_adjustment_policy"),
            "allow_non_workspace_motor_action": summary.get("allow_non_workspace_motor_action"),
            "motor_execution_threshold": summary.get("motor_execution_threshold"),
        },
    }


def trace_metrics(envelopes: List[dict]) -> dict:
    winners = Counter()
    routes = Counter()
    motor_sources = Counter()
    positions = []
    action_failures = 0
    for envelope in envelopes:
        broadcast = envelope.get("workspace_broadcast") or {}
        winners[broadcast.get("winner_module") or "none"] += 1
        action = envelope.get("env_action") or {}
        routes[(action.get("metadata") or {}).get("action_route") or "unknown"] += 1
        symbolic = ((envelope.get("next_env_state") or {}).get("symbolic_state") or {})
        position = symbolic.get("agent_position")
        if isinstance(position, list) and len(position) == 2:
            positions.append(tuple(position))
        if action.get("should_step") and symbolic.get("action_success") is False:
            action_failures += 1
        for state in envelope.get("module_states") or []:
            if state.get("module_name") != "motor":
                continue
            proposal = state.get("proposal") or {}
            observations = (proposal.get("content") or {}).get("observations") or []
            source = first_observation_value(observations, "target_source") or "none"
            motor_sources[source] += 1
    return {
        "winner_counts": dict(winners),
        "route_counts": dict(routes),
        "motor_target_sources": dict(motor_sources),
        "action_failures": action_failures,
        "longest_same_position": longest_same_position(positions),
        "max_period2_repeat": max_period2_repeat(positions),
    }


def aggregate_metrics(runs: List[dict]) -> dict:
    valid_runs = [run for run in runs if not run.get("error")]
    run_count = len(runs)
    success_count = sum(1 for run in valid_runs if run.get("success"))
    cycles = [run.get("cycle_count") for run in valid_runs if is_number(run.get("cycle_count"))]
    env_steps = [run.get("env_step_count") for run in valid_runs if is_number(run.get("env_step_count"))]
    winners = Counter()
    routes = Counter()
    motor_sources = Counter()
    for run in valid_runs:
        winners.update(run.get("winner_counts") or {})
        routes.update(run.get("route_counts") or {})
        motor_sources.update(run.get("motor_target_sources") or {})
    return {
        "run_count": run_count,
        "valid_run_count": len(valid_runs),
        "success_count": success_count,
        "success_rate": success_count / len(valid_runs) if valid_runs else 0.0,
        "avg_cycles": mean(cycles) if cycles else None,
        "avg_env_steps": mean(env_steps) if env_steps else None,
        "avg_longest_same_position": mean(
            run.get("longest_same_position", 0) for run in valid_runs
        )
        if valid_runs
        else None,
        "action_failures": sum(int(run.get("action_failures") or 0) for run in valid_runs),
        "winner_counts": dict(winners),
        "route_counts": dict(routes),
        "motor_target_sources": dict(motor_sources),
    }


def first_observation_value(observations: Iterable[Any], key: str) -> Optional[str]:
    prefix = f"{key}="
    for item in observations:
        if isinstance(item, str) and item.startswith(prefix):
            return item.split("=", 1)[1]
    return None


def longest_same_position(positions: List[tuple]) -> int:
    longest = 0
    current = 0
    previous = object()
    for position in positions:
        current = current + 1 if position == previous else 1
        longest = max(longest, current)
        previous = position
    return longest


def max_period2_repeat(positions: List[tuple]) -> int:
    longest = 0
    current = 0
    for index in range(2, len(positions)):
        if positions[index] == positions[index - 2] and positions[index] != positions[index - 1]:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "item"


def render_html(payload: dict) -> str:
    return HTML_TEMPLATE.replace(
        "__PAYLOAD__",
        json.dumps(payload, ensure_ascii=True),
    )


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GWT Ablation Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f3;
      --panel: #ffffff;
      --ink: #17212b;
      --muted: #64717f;
      --line: #d9dfdd;
      --blue: #2563eb;
      --green: #159957;
      --gold: #a46612;
      --red: #c24137;
      --soft: #f9faf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      padding: 16px 22px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfb;
      display: flex;
      gap: 16px;
      justify-content: space-between;
      align-items: flex-start;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
    }
    .subtitle {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
      max-width: 860px;
    }
    .pills {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
    }
    .pill {
      min-height: 28px;
      padding: 5px 9px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      white-space: nowrap;
    }
    main {
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      min-height: calc(100vh - 72px);
    }
    aside {
      border-right: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
      display: grid;
      align-content: start;
      gap: 16px;
    }
    .content {
      min-width: 0;
      padding: 18px 22px 28px;
      display: grid;
      gap: 18px;
      align-content: start;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 15px;
      line-height: 1.25;
    }
    h3 {
      margin: 0 0 8px;
      font-size: 13px;
      line-height: 1.25;
      color: #27313c;
    }
    .section {
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }
    .controls {
      display: grid;
      gap: 8px;
    }
    label {
      color: var(--muted);
      font-size: 12px;
    }
    select {
      width: 100%;
      height: 36px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 13px;
    }
    .text {
      color: #27313c;
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
      min-height: 74px;
      display: grid;
      align-content: start;
      gap: 4px;
    }
    .metric .k {
      color: var(--muted);
      font-size: 12px;
    }
    .metric .v {
      font-size: 20px;
      font-weight: 760;
      line-height: 1.1;
    }
    .ok { color: var(--green); }
    .bad { color: var(--red); }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      line-height: 1.35;
    }
    th, td {
      padding: 8px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    th {
      background: var(--soft);
      color: var(--muted);
      font-weight: 700;
    }
    tr:last-child td { border-bottom: 0; }
    .wrap {
      white-space: normal;
      min-width: 160px;
      overflow-wrap: anywhere;
    }
    a {
      color: var(--blue);
      text-decoration: none;
      font-weight: 700;
    }
    a:hover { text-decoration: underline; }
    .bar-list {
      display: grid;
      gap: 8px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 135px minmax(0, 1fr) 54px;
      gap: 8px;
      align-items: center;
      font-size: 12px;
    }
    .bar {
      height: 8px;
      border-radius: 999px;
      background: #e7ebe9;
      overflow: hidden;
    }
    .bar span {
      display: block;
      height: 100%;
      width: 0;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }
    .two-col {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }
    .kv {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 12px;
      line-height: 1.4;
    }
    .k { color: var(--muted); }
    .v {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    @media (max-width: 980px) {
      header { flex-direction: column; }
      .pills { justify-content: flex-start; }
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .metric-grid { grid-template-columns: repeat(2, minmax(130px, 1fr)); }
      .two-col { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1 id="title">GWT Ablation Dashboard</h1>
      <p class="subtitle" id="description"></p>
    </div>
    <div class="pills">
      <span class="pill" id="conditionPill"></span>
      <span class="pill" id="runPill"></span>
      <span class="pill" id="sourcePill"></span>
    </div>
  </header>
  <main>
    <aside>
      <div class="section">
        <h2>Ablation</h2>
        <div class="controls">
          <label for="levelSelect">Level</label>
          <select id="levelSelect"></select>
          <label for="conditionSelect">Condition</label>
          <select id="conditionSelect"></select>
        </div>
      </div>
      <div class="section">
        <h2>Level Notes</h2>
        <div class="text" id="levelDescription"></div>
      </div>
      <div class="section">
        <h2>Manipulation</h2>
        <div class="text" id="manipulationText"></div>
      </div>
      <div class="section">
        <h2>Expected Effect</h2>
        <div class="text" id="expectedText"></div>
      </div>
    </aside>
    <section class="content">
      <div>
        <h2>Selected Condition</h2>
        <div class="metric-grid" id="metricsGrid"></div>
      </div>
      <div class="two-col">
        <div class="panel">
          <h2>Workspace Winners</h2>
          <div class="bar-list" id="winnerBars"></div>
        </div>
        <div class="panel">
          <h2>Action Routes</h2>
          <div class="bar-list" id="routeBars"></div>
        </div>
      </div>
      <div class="panel">
        <h2>Level Overview</h2>
        <div class="table-wrap">
          <table id="levelTable"></table>
        </div>
      </div>
      <div class="panel">
        <h2>Runs</h2>
        <div class="table-wrap">
          <table id="runTable"></table>
        </div>
      </div>
      <div class="panel">
        <h2>Configuration</h2>
        <div class="kv" id="configPanel"></div>
      </div>
    </section>
  </main>
  <script>
    const data = __PAYLOAD__;
    const levelSelect = document.getElementById('levelSelect');
    const conditionSelect = document.getElementById('conditionSelect');

    function text(value) {
      if (value === null || value === undefined || value === '') return '-';
      if (Array.isArray(value)) return '[' + value.join(', ') + ']';
      if (typeof value === 'object') return JSON.stringify(value);
      return String(value);
    }

    function html(value) {
      return text(value).replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[ch]);
    }

    function pct(value) {
      const number = Number(value || 0);
      return Math.max(0, Math.min(100, number * 100));
    }

    function fmt(value, digits = 1) {
      const number = Number(value);
      if (!Number.isFinite(number)) return '-';
      return number.toFixed(digits);
    }

    function percent(value) {
      return `${fmt(Number(value || 0) * 100, 0)}%`;
    }

    function currentLevel() {
      return data.levels[Number(levelSelect.value || 0)] || data.levels[0] || {conditions: []};
    }

    function currentCondition() {
      const level = currentLevel();
      return level.conditions[Number(conditionSelect.value || 0)] || level.conditions[0] || {metrics: {}, runs: []};
    }

    function renderSelects() {
      levelSelect.innerHTML = data.levels.map((level, index) => (
        `<option value="${index}">${html(level.label)}</option>`
      )).join('');
      renderConditionSelect();
    }

    function renderConditionSelect() {
      const level = currentLevel();
      conditionSelect.innerHTML = (level.conditions || []).map((condition, index) => (
        `<option value="${index}">${html(condition.label)}</option>`
      )).join('');
      conditionSelect.disabled = (level.conditions || []).length <= 1;
    }

    function metric(label, value, cls) {
      return `<div class="metric"><div class="k">${html(label)}</div><div class="v ${cls || ''}">${html(value)}</div></div>`;
    }

    function renderMetrics(condition) {
      const metrics = condition.metrics || {};
      document.getElementById('metricsGrid').innerHTML = [
        metric('success rate', percent(metrics.success_rate), Number(metrics.success_rate || 0) >= 0.8 ? 'ok' : 'bad'),
        metric('successful runs', `${metrics.success_count || 0} / ${metrics.valid_run_count || 0}`),
        metric('avg cycles', fmt(metrics.avg_cycles, 1)),
        metric('avg env steps', fmt(metrics.avg_env_steps, 1)),
        metric('action failures', metrics.action_failures || 0),
        metric('avg longest same pos', fmt(metrics.avg_longest_same_position, 1)),
        metric('valid runs', metrics.valid_run_count || 0),
        metric('total runs', metrics.run_count || 0),
      ].join('');
    }

    function renderBars(containerId, counts) {
      const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
      const total = entries.reduce((sum, item) => sum + Number(item[1] || 0), 0);
      const container = document.getElementById(containerId);
      if (!entries.length) {
        container.innerHTML = '<div class="k">No trace counts available.</div>';
        return;
      }
      container.innerHTML = entries.map(([name, count]) => {
        const fraction = total ? Number(count) / total : 0;
        return `<div class="bar-row">
          <div class="v">${html(name)}</div>
          <div class="bar"><span style="width:${pct(fraction)}%"></span></div>
          <div class="k">${html(count)}</div>
        </div>`;
      }).join('');
    }

    function renderLevelTable(level) {
      const rows = (level.conditions || []).map(condition => {
        const metrics = condition.metrics || {};
        return `<tr>
          <td class="wrap">${html(condition.label)}</td>
          <td>${percent(metrics.success_rate)}</td>
          <td>${html(`${metrics.success_count || 0}/${metrics.valid_run_count || 0}`)}</td>
          <td>${fmt(metrics.avg_cycles, 1)}</td>
          <td>${fmt(metrics.avg_env_steps, 1)}</td>
          <td>${html(metrics.action_failures || 0)}</td>
        </tr>`;
      }).join('');
      document.getElementById('levelTable').innerHTML = `
        <thead><tr>
          <th>condition</th><th>success</th><th>runs</th><th>avg cycles</th><th>avg env steps</th><th>failures</th>
        </tr></thead><tbody>${rows}</tbody>`;
    }

    function renderRunTable(condition) {
      const rows = (condition.runs || []).map(run => {
        const link = run.viewer_link
          ? `<a href="${html(run.viewer_link)}" target="_blank" rel="noopener">viewer</a>`
          : run.summary_link
          ? `<a href="${html(run.summary_link)}" target="_blank" rel="noopener">summary</a>`
          : '-';
        const status = run.error ? `<span class="bad">error</span>` : run.success ? `<span class="ok">success</span>` : `<span class="bad">not done</span>`;
        return `<tr>
          <td class="wrap">${html(run.label || run.run_id)}</td>
          <td>${status}</td>
          <td>${html(run.map_label)}</td>
          <td>${html(run.cycle_count)}</td>
          <td>${html(run.env_step_count)}</td>
          <td>${html(run.longest_same_position)}</td>
          <td>${html(run.max_period2_repeat)}</td>
          <td>${link}</td>
          <td class="wrap">${html(run.error || '')}</td>
        </tr>`;
      }).join('');
      document.getElementById('runTable').innerHTML = `
        <thead><tr>
          <th>run</th><th>status</th><th>map</th><th>cycles</th><th>env steps</th><th>same pos</th><th>period-2</th><th>open</th><th>error</th>
        </tr></thead><tbody>${rows}</tbody>`;
    }

    function renderConfig(condition) {
      const first = (condition.runs || []).find(run => !run.error) || {};
      const config = first.ablation_config || {};
      document.getElementById('configPanel').innerHTML = [
        ['disabled modules', config.disabled_modules],
        ['score modifiers', config.score_modifiers],
        ['ignition threshold', config.ignition_threshold],
        ['salience weight', config.salience_weight],
        ['relevance weight', config.relevance_weight],
        ['workspace recurrence bonus', config.workspace_recurrence_bonus],
        ['workspace adjustment policy', config.workspace_adjustment_policy],
        ['allow non-workspace motor', config.allow_non_workspace_motor_action],
        ['motor execution threshold', config.motor_execution_threshold],
      ].map(([key, value]) => `<div class="k">${html(key)}</div><div class="v">${html(value)}</div>`).join('');
    }

    function render() {
      const level = currentLevel();
      const condition = currentCondition();
      document.getElementById('title').textContent = data.title || 'GWT Ablation Dashboard';
      document.getElementById('description').textContent = data.description || '';
      document.getElementById('conditionPill').textContent = `${data.total_conditions || 0} conditions`;
      document.getElementById('runPill').textContent = `${data.total_runs || 0} runs`;
      document.getElementById('sourcePill').textContent = `source ${data.generated_from || '-'}`;
      document.getElementById('levelDescription').textContent = level.description || '-';
      document.getElementById('manipulationText').textContent = condition.manipulation || condition.description || '-';
      document.getElementById('expectedText').textContent = condition.expected_effect || '-';
      renderMetrics(condition);
      renderBars('winnerBars', (condition.metrics || {}).winner_counts);
      renderBars('routeBars', (condition.metrics || {}).route_counts);
      renderLevelTable(level);
      renderRunTable(condition);
      renderConfig(condition);
    }

    levelSelect.addEventListener('change', () => {
      renderConditionSelect();
      conditionSelect.value = '0';
      render();
    });
    conditionSelect.addEventListener('change', render);
    renderSelects();
    render();
  </script>
</body>
</html>
"""
