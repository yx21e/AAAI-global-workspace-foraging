from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Optional


def load_jsonl(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def default_run_paths(run_dir: Path, run_id: str) -> dict:
    return {
        "summary": run_dir / f"{run_id}_summary.json",
        "envelopes": run_dir / f"{run_id}_envelopes.jsonl",
        "actions": run_dir / f"{run_id}_actions.jsonl",
        "frames": run_dir / f"{run_id}_frames",
        "viewer": run_dir / f"{run_id}_viewer.html",
    }


def build_viewer(
    *,
    run_dir: str,
    run_id: str,
    output_path: Optional[str] = None,
    frames_dir: Optional[str] = None,
) -> Path:
    run_path = Path(run_dir).expanduser().resolve()
    paths = default_run_paths(run_path, run_id)
    summary_path = paths["summary"]
    envelope_path = paths["envelopes"]
    action_path = paths["actions"]
    frame_path = Path(frames_dir).expanduser().resolve() if frames_dir else paths["frames"]
    viewer_path = Path(output_path).expanduser().resolve() if output_path else paths["viewer"]

    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary file: {summary_path}")
    if not envelope_path.exists():
        raise FileNotFoundError(f"Missing envelope file: {envelope_path}")
    if not action_path.exists():
        raise FileNotFoundError(f"Missing action stream file: {action_path}")
    if not frame_path.exists():
        raise FileNotFoundError(f"Missing frame directory: {frame_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    envelopes = load_jsonl(envelope_path)
    actions = load_jsonl(action_path)
    frames = sorted(frame_path.glob("*.png"), key=frame_sort_key)
    if not frames:
        raise ValueError(f"No PNG frames found under {frame_path}")

    payload = {
        "summary": summary,
        "frames": [
            {
                "index": index,
                "src": relative_path(frame, viewer_path.parent),
                "name": frame.name,
            }
            for index, frame in enumerate(frames)
        ],
        "steps": build_step_payload(envelopes, actions),
    }

    viewer_path.parent.mkdir(parents=True, exist_ok=True)
    viewer_path.write_text(render_html(payload), encoding="utf-8")
    return viewer_path


def frame_sort_key(path: Path):
    numbers = [int(value) for value in re.findall(r"\d+", path.name)]
    return numbers or [0]


def relative_path(path: Path, base: Path) -> str:
    return os.path.relpath(Path(path).resolve(), base.resolve()).replace(os.sep, "/")


def build_step_payload(envelopes: List[dict], actions: List[dict]) -> List[dict]:
    steps = [
        {
            "frame_index": 0,
            "label": "Initial",
            "cycle_t": None,
            "env_t": envelopes[0].get("env_t") if envelopes else None,
            "action": None,
            "action_type": "INITIAL",
            "route": "initial_state",
            "workspace_winner": None,
            "workspace_ignited": None,
            "workspace_maintained": None,
            "agent_position": get_symbolic(envelopes[0], before=True).get("agent_position")
            if envelopes
            else None,
            "resource_position": get_symbolic(envelopes[0], before=True).get("resource_position")
            if envelopes
            else None,
            "resources_collected": get_symbolic(envelopes[0], before=True).get("resources_collected")
            if envelopes
            else None,
            "carrying_resource": get_symbolic(envelopes[0], before=True).get("carrying_resource")
            if envelopes
            else None,
            "modules": [],
            "language_report": None,
        }
    ]

    for index, envelope in enumerate(envelopes, start=1):
        action = envelope.get("env_action", {})
        action_metadata = action.get("metadata", {})
        broadcast = envelope.get("workspace_broadcast", {})
        workspace = broadcast.get("metadata", {}).get("workspace", {})
        symbolic = get_symbolic(envelope, before=False)
        modules = []
        language_report = None
        for state in envelope.get("module_states", []):
            proposal = state.get("proposal") or {}
            module_name = state.get("module_name")
            if module_name == "language_report":
                content = proposal.get("content") or {}
                language_report = content.get("verbal_report")
            modules.append(
                {
                    "module": module_name,
                    "status": state.get("status"),
                    "importance": proposal.get("importance_score"),
                    "salience": proposal.get("salience_score"),
                    "relevance": proposal.get("goal_relevance_score"),
                    "action_hint": proposal.get("action_hint"),
                }
            )
        steps.append(
            {
                "frame_index": index,
                "label": f"Cycle {envelope.get('cycle_t')}",
                "cycle_t": envelope.get("cycle_t"),
                "env_t": envelope.get("env_t"),
                "action": action.get("command"),
                "action_type": action.get("action_type"),
                "route": action_metadata.get("action_route"),
                "workspace_winner": broadcast.get("winner_module"),
                "workspace_ignited": workspace.get("ignited"),
                "workspace_maintained": workspace.get("maintained"),
                "agent_position": symbolic.get("agent_position"),
                "resource_position": symbolic.get("resource_position"),
                "resources_collected": symbolic.get("resources_collected"),
                "carrying_resource": symbolic.get("carrying_resource"),
                "modules": modules,
                "language_report": language_report,
                "action_record": actions[index - 1] if index - 1 < len(actions) else None,
            }
        )
    return steps


def get_symbolic(envelope: dict, *, before: bool) -> dict:
    state_key = "env_state" if before else "next_env_state"
    state = envelope.get(state_key) or envelope.get("env_state") or {}
    return state.get("symbolic_state") or {}


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
  <title>Qiyuan GWT Demo Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f5;
      --panel: #ffffff;
      --ink: #17212b;
      --muted: #64717f;
      --line: #d9dfdd;
      --blue: #2563eb;
      --green: #159957;
      --gold: #b7791f;
      --red: #c24137;
      --shadow: 0 10px 28px rgba(25, 32, 40, 0.10);
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
      min-height: 70px;
      padding: 16px 24px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfb;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 750;
    }
    .summary {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .pill {
      min-height: 28px;
      padding: 5px 9px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .ok { color: var(--green); }
    .bad { color: var(--red); }
    main {
      height: calc(100vh - 70px);
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 0;
    }
    .stage {
      min-width: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
    }
    .frame-wrap {
      min-height: 0;
      padding: 18px;
      display: grid;
      place-items: center;
    }
    #frameImage {
      width: min(78vh, 92%);
      max-width: 760px;
      height: auto;
      aspect-ratio: 1 / 1;
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      background: #fff;
    }
    .timeline {
      border-top: 1px solid var(--line);
      background: #fbfcfb;
      padding: 12px 18px 14px;
      display: grid;
      gap: 10px;
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--ink);
      min-width: 38px;
      height: 36px;
      border-radius: 6px;
      font-size: 14px;
      cursor: pointer;
    }
    button:hover { border-color: var(--blue); color: var(--blue); }
    button:focus-visible {
      outline: 3px solid rgba(37, 99, 235, 0.22);
      outline-offset: 2px;
    }
    .wide {
      min-width: 72px;
      padding-inline: 10px;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--blue);
    }
    aside {
      min-width: 0;
      overflow: auto;
      border-left: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 15px;
      line-height: 1.25;
    }
    .section {
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
    }
    .kv {
      display: grid;
      grid-template-columns: 130px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
      line-height: 1.45;
    }
    .k { color: var(--muted); }
    .v {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .route {
      color: var(--blue);
      font-weight: 700;
    }
    .module-list {
      display: grid;
      gap: 8px;
    }
    .module-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px;
      display: grid;
      gap: 6px;
      font-size: 12px;
    }
    .module-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-weight: 700;
    }
    .bar {
      height: 7px;
      border-radius: 999px;
      background: #e7ebe9;
      overflow: hidden;
    }
    .bar > span {
      display: block;
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }
    .report {
      margin: 0;
      color: #27313c;
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    @media (max-width: 920px) {
      header {
        align-items: flex-start;
        flex-direction: column;
      }
      .summary { justify-content: flex-start; }
      main {
        height: auto;
        min-height: calc(100vh - 70px);
        grid-template-columns: 1fr;
      }
      aside {
        border-left: 0;
        border-top: 1px solid var(--line);
      }
      #frameImage {
        width: min(92vw, 640px);
      }
    }
  </style>
</head>
<body>
  <header>
    <h1 id="title">Qiyuan GWT Demo</h1>
    <div class="summary">
      <span class="pill" id="donePill"></span>
      <span class="pill" id="cyclePill"></span>
      <span class="pill" id="resourcePill"></span>
      <span class="pill" id="difficultyPill"></span>
    </div>
  </header>
  <main>
    <section class="stage">
      <div class="frame-wrap">
        <img id="frameImage" alt="Qiyuan foraging frame">
      </div>
      <div class="timeline">
        <input id="scrubber" type="range" min="0" value="0" step="1">
        <div class="controls">
          <button id="firstBtn" title="First frame">|&lt;</button>
          <button id="prevBtn" title="Previous frame">&lt;</button>
          <button id="playBtn" class="wide" title="Play or pause">Play</button>
          <button id="nextBtn" title="Next frame">&gt;</button>
          <button id="lastBtn" title="Last frame">&gt;|</button>
          <button id="pickupBtn" class="wide" title="Jump to pickup">PICKUP</button>
        </div>
      </div>
    </section>
    <aside>
      <div class="section">
        <h2>Step</h2>
        <div class="kv" id="stepPanel"></div>
      </div>
      <div class="section">
        <h2>Workspace</h2>
        <div class="kv" id="workspacePanel"></div>
      </div>
      <div class="section">
        <h2>Modules</h2>
        <div class="module-list" id="modulePanel"></div>
      </div>
      <div class="section">
        <h2>Language</h2>
        <p class="report" id="reportPanel"></p>
      </div>
    </aside>
  </main>
  <script>
    const data = __PAYLOAD__;
    const image = document.getElementById('frameImage');
    const scrubber = document.getElementById('scrubber');
    const playBtn = document.getElementById('playBtn');
    const pickupBtn = document.getElementById('pickupBtn');
    let index = 0;
    let timer = null;

    function text(value) {
      if (value === null || value === undefined || value === '') return '-';
      if (Array.isArray(value)) return '[' + value.join(', ') + ']';
      return String(value);
    }

    function kv(container, rows) {
      container.innerHTML = rows.map(([k, v, cls]) => (
        `<div class="k">${k}</div><div class="v ${cls || ''}">${text(v)}</div>`
      )).join('');
    }

    function pct(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return 0;
      return Math.max(0, Math.min(100, n * 100));
    }

    function renderModules(step) {
      const panel = document.getElementById('modulePanel');
      const rows = step.modules || [];
      if (!rows.length) {
        panel.innerHTML = '<div class="k">No proposals yet.</div>';
        return;
      }
      panel.innerHTML = rows.map(row => {
        const importance = Number(row.importance || 0);
        return `<div class="module-row">
          <div class="module-top">
            <span>${text(row.module)}</span>
            <span>${importance.toFixed(3)}</span>
          </div>
          <div class="bar"><span style="width:${pct(importance)}%"></span></div>
          <div class="kv">
            <div class="k">importance</div><div class="v">${importance.toFixed(3)}</div>
            <div class="k">salience</div><div class="v">${Number(row.salience || 0).toFixed(3)}</div>
            <div class="k">relevance</div><div class="v">${Number(row.relevance || 0).toFixed(3)}</div>
            <div class="k">hint</div><div class="v">${text(row.action_hint)}</div>
          </div>
        </div>`;
      }).join('');
    }

    function render() {
      const frame = data.frames[index];
      const step = data.steps[Math.min(index, data.steps.length - 1)] || {};
      image.src = frame.src;
      scrubber.value = index;

      kv(document.getElementById('stepPanel'), [
        ['frame', `${index + 1} / ${data.frames.length}`],
        ['cycle_t', step.cycle_t],
        ['env_t', step.env_t],
        ['action', step.action || step.action_type],
        ['route', step.route, 'route'],
        ['agent', step.agent_position],
        ['resource', step.resource_position],
        ['collected', step.resources_collected],
        ['carrying', step.carrying_resource],
      ]);
      kv(document.getElementById('workspacePanel'), [
        ['winner', step.workspace_winner],
        ['ignited', step.workspace_ignited],
        ['maintained', step.workspace_maintained],
      ]);
      renderModules(step);
      document.getElementById('reportPanel').textContent = step.language_report || '-';
    }

    function setIndex(next) {
      index = Math.max(0, Math.min(data.frames.length - 1, next));
      render();
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = null;
      playBtn.textContent = 'Play';
    }

    function play() {
      if (timer) {
        stop();
        return;
      }
      playBtn.textContent = 'Pause';
      timer = window.setInterval(() => {
        if (index >= data.frames.length - 1) {
          stop();
          return;
        }
        setIndex(index + 1);
      }, 420);
    }

    function pickupIndex() {
      const found = data.steps.findIndex(step => step.action === 'PICKUP');
      return found >= 0 ? found : data.frames.length - 1;
    }

    document.getElementById('title').textContent = data.summary.run_id || 'Qiyuan GWT Demo';
    document.getElementById('donePill').innerHTML = data.summary.done ? '<span class="ok">done</span>' : '<span class="bad">not done</span>';
    document.getElementById('cyclePill').textContent = `cycles ${data.summary.cycle_count}`;
    document.getElementById('resourcePill').textContent = `resources ${data.summary.resources_collected}`;
    document.getElementById('difficultyPill').textContent = `difficulty ${data.summary.difficulty}`;
    scrubber.max = Math.max(0, data.frames.length - 1);
    scrubber.addEventListener('input', event => setIndex(Number(event.target.value)));
    document.getElementById('firstBtn').addEventListener('click', () => setIndex(0));
    document.getElementById('prevBtn').addEventListener('click', () => setIndex(index - 1));
    document.getElementById('playBtn').addEventListener('click', play);
    document.getElementById('nextBtn').addEventListener('click', () => setIndex(index + 1));
    document.getElementById('lastBtn').addEventListener('click', () => setIndex(data.frames.length - 1));
    pickupBtn.addEventListener('click', () => setIndex(pickupIndex()));
    window.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft') setIndex(index - 1);
      if (event.key === 'ArrowRight') setIndex(index + 1);
      if (event.key === ' ') {
        event.preventDefault();
        play();
      }
    });
    render();
  </script>
</body>
</html>
"""
