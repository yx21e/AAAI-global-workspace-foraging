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
            "workspace_output_language": None,
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
            "reasoning": {
                "winner_rationale": "",
                "winner_reflection": "",
                "score_basis": "Initial frame before module proposals.",
                "ignition_basis": "",
                "action_basis": "No simulator action has been selected yet.",
            },
        }
    ]

    for index, envelope in enumerate(envelopes, start=1):
        action = envelope.get("env_action", {})
        action_metadata = action.get("metadata", {})
        broadcast = envelope.get("workspace_broadcast", {})
        workspace = broadcast.get("metadata", {}).get("workspace", {})
        workspace_output_language = proposal_language({"content": broadcast.get("content")})
        symbolic = get_symbolic(envelope, before=False)
        modules = []
        language_report = None
        for state in envelope.get("module_states", []):
            proposal = state.get("proposal") or {}
            module_name = state.get("module_name")
            output_language = proposal_language(proposal)
            if module_name in {"language_report", "language"}:
                language_report = output_language
            modules.append(
                {
                    "module": module_name,
                    "status": state.get("status"),
                    "importance": proposal.get("importance_score"),
                    "salience": proposal.get("salience_score"),
                    "relevance": proposal.get("goal_relevance_score"),
                    "action_hint": proposal.get("action_hint"),
                    "output_language": output_language,
                    "rationale": proposal.get("rationale") or "",
                    "reflection": proposal.get("reflection") or "",
                    "importance_function": (proposal.get("metadata") or {}).get("importance_function") or {},
                }
            )
        reasoning = reasoning_payload(
            broadcast=broadcast,
            workspace=workspace,
            action=action,
            action_metadata=action_metadata,
            modules=modules,
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
                "workspace_output_language": workspace_output_language,
                "workspace_ignited": workspace.get("ignited"),
                "workspace_maintained": workspace.get("maintained"),
                "agent_position": symbolic.get("agent_position"),
                "resource_position": symbolic.get("resource_position"),
                "resources_collected": symbolic.get("resources_collected"),
                "carrying_resource": symbolic.get("carrying_resource"),
                "modules": modules,
                "language_report": language_report,
                "reasoning": reasoning,
                "action_record": actions[index - 1] if index - 1 < len(actions) else None,
            }
        )
    return steps


def get_symbolic(envelope: dict, *, before: bool) -> dict:
    state_key = "env_state" if before else "next_env_state"
    state = envelope.get(state_key) or envelope.get("env_state") or {}
    return state.get("symbolic_state") or {}


def proposal_language(proposal: dict) -> str:
    content = proposal.get("content")
    if isinstance(content, dict):
        summary = content.get("summary") or content.get("verbal_report")
        observations = content.get("observations")
        if summary and isinstance(observations, list) and observations:
            shown = "; ".join(str(item) for item in observations[:5])
            if len(observations) > 5:
                shown += "; ..."
            return f"{summary}\nobservations: {shown}"
        if summary:
            return str(summary)
        for key in ("verbal_report", "summary", "salient_event", "planned_action", "goal"):
            value = content.get(key)
            if value:
                return str(value)
        if content:
            return json.dumps(content, ensure_ascii=True, sort_keys=True)
    if content is None:
        return ""
    return str(content)


def reasoning_payload(
    *,
    broadcast: dict,
    workspace: dict,
    action: dict,
    action_metadata: dict,
    modules: List[dict],
) -> dict:
    winner = broadcast.get("winner_module")
    winner_row = next((row for row in modules if row.get("module") == winner), None)
    broadcast_metadata = broadcast.get("metadata") or {}
    importance_function = (
        (winner_row or {}).get("importance_function")
        or broadcast_metadata.get("importance_function")
        or {}
    )
    rationale = (
        (winner_row or {}).get("rationale")
        or broadcast_metadata.get("winner_rationale")
        or fallback_rationale(workspace)
    )
    reflection = (
        (winner_row or {}).get("reflection")
        or broadcast_metadata.get("winner_reflection")
        or fallback_reflection(workspace)
    )
    score_value = (
        (winner_row or {}).get("importance")
        if winner_row is not None
        else broadcast.get("importance_score")
    )
    return {
        "winner_rationale": rationale,
        "winner_reflection": reflection,
        "score_basis": score_basis_text(score_value, importance_function),
        "ignition_basis": ignition_basis_text(workspace),
        "action_basis": action_basis_text(action, action_metadata, winner),
    }


def fallback_rationale(workspace: dict) -> str:
    if workspace.get("maintained"):
        return "No new proposal crossed threshold; the previous broadcast is maintained with decay."
    if workspace.get("ignited") is False:
        return "No proposal crossed the ignition threshold in this cycle."
    return ""


def fallback_reflection(workspace: dict) -> str:
    if workspace.get("maintained"):
        return "The active workspace content is being carried forward because no new proposal ignited."
    if workspace.get("ignited") is False:
        return "No module proposal became globally broadcast in this cycle."
    return ""


def score_basis_text(score_value, importance_function: dict) -> str:
    if not importance_function:
        if score_value is None:
            return "No scored proposal is available for this frame."
        return f"workspace score={format_score(score_value)}"
    salience = importance_function.get("bottom_up_salience")
    relevance = importance_function.get("top_down_relevance")
    salience_weight = importance_function.get("salience_weight")
    relevance_weight = importance_function.get("relevance_weight")
    recurrence_bonus = importance_function.get("recurrence_bonus")
    adjustment = importance_function.get("workspace_adjustment")
    encoder = importance_function.get("encoder")
    return (
        f"importance={format_score(score_value)}; "
        f"salience={format_score(salience)}*{format_score(salience_weight)} + "
        f"relevance={format_score(relevance)}*{format_score(relevance_weight)}; "
        f"recurrence_bonus={format_score(recurrence_bonus)}; "
        f"workspace_adjustment={format_score(adjustment)}; "
        f"encoder={encoder or '-'}"
    )


def ignition_basis_text(workspace: dict) -> str:
    threshold = format_score(workspace.get("ignition_threshold"))
    strength = format_score(workspace.get("strength"))
    if workspace.get("ignited"):
        return f"Winner crossed ignition threshold={threshold}; new broadcast strength={strength}."
    if workspace.get("maintained"):
        age = workspace.get("age")
        return f"No new ignition; maintained previous broadcast with strength={strength}, age={age}."
    return f"No proposal crossed ignition threshold={threshold}; workspace did not ignite."


def action_basis_text(action: dict, action_metadata: dict, winner: Optional[str]) -> str:
    route = action_metadata.get("action_route")
    command = action.get("command") or action.get("action_type")
    if route == "workspace_broadcast":
        return f"Executed {command} from winner={winner} because the broadcast carried an action_hint."
    if route == "non_workspace_motor_threshold":
        return (
            f"Executed {command} through the non-workspace motor threshold route "
            f"(motor_importance={format_score(action_metadata.get('motor_importance'))}, "
            f"threshold={format_score(action_metadata.get('motor_execution_threshold'))})."
        )
    if route == "forced_action":
        return f"Executed forced action {command} from experiment config."
    if route == "no_action_threshold_not_met":
        return "No simulator action executed because the non-workspace motor threshold was not met."
    if route == "no_workspace_action":
        return "No simulator action executed because the winning broadcast had no action_hint."
    return f"action_route={route or '-'}; command={command or '-'}"


def format_score(value) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


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
    .reasoning .v {
      white-space: pre-wrap;
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
    .prompt-grid {
      display: grid;
      gap: 8px;
    }
    label {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
    }
    input[type="number"],
    textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 13px;
    }
    input[type="number"] {
      height: 34px;
      padding: 6px 8px;
    }
    textarea {
      min-height: 82px;
      resize: vertical;
      padding: 8px;
      line-height: 1.35;
    }
    .prompt-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .command {
      margin: 0;
      max-height: 110px;
      overflow: auto;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f7f8f6;
      color: #27313c;
      font-size: 11px;
      line-height: 1.35;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .status {
      min-height: 18px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      white-space: pre-wrap;
    }
    .module-output {
      margin-top: 2px;
      padding-top: 6px;
      border-top: 1px solid var(--line);
      color: #27313c;
      line-height: 1.4;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .module-rationale,
    .module-reflection {
      display: grid;
      grid-template-columns: 72px minmax(0, 1fr);
      gap: 8px;
      padding-top: 4px;
      color: #27313c;
      line-height: 1.35;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .module-reflection {
      padding-top: 2px;
    }
    .module-rationale span,
    .module-reflection span {
      color: var(--muted);
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
        <h2>Reasoning</h2>
        <div class="kv reasoning" id="reasoningPanel"></div>
      </div>
      <div class="section">
        <h2>Modules</h2>
        <div class="module-list" id="modulePanel"></div>
      </div>
      <div class="section">
        <h2>Language</h2>
        <p class="report" id="reportPanel"></p>
      </div>
      <div class="section">
        <h2>Experimenter</h2>
        <div class="prompt-grid">
          <label for="promptCycle">Cycle</label>
          <input id="promptCycle" type="number" min="0" step="1" value="0">
          <label for="experimenterPrompt">Prompt</label>
          <textarea id="experimenterPrompt"></textarea>
          <div class="prompt-actions">
            <button id="sendPromptBtn" class="wide" title="Rerun with this language prompt">Run</button>
            <button id="copyCommandBtn" class="wide" title="Copy rerun command">Copy</button>
          </div>
          <pre class="command" id="rerunCommand"></pre>
          <div class="status" id="promptStatus"></div>
        </div>
      </div>
    </aside>
  </main>
  <script>
    const data = __PAYLOAD__;
    const image = document.getElementById('frameImage');
    const scrubber = document.getElementById('scrubber');
    const playBtn = document.getElementById('playBtn');
    const pickupBtn = document.getElementById('pickupBtn');
    const promptCycle = document.getElementById('promptCycle');
    const experimenterPrompt = document.getElementById('experimenterPrompt');
    const sendPromptBtn = document.getElementById('sendPromptBtn');
    const copyCommandBtn = document.getElementById('copyCommandBtn');
    const rerunCommand = document.getElementById('rerunCommand');
    const promptStatus = document.getElementById('promptStatus');
    let index = 0;
    let timer = null;

    function text(value) {
      if (value === null || value === undefined || value === '') return '-';
      if (Array.isArray(value)) return '[' + value.join(', ') + ']';
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

    function kv(container, rows) {
      container.innerHTML = rows.map(([k, v, cls]) => (
        `<div class="k">${html(k)}</div><div class="v ${cls || ''}">${html(v)}</div>`
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
            <span>${html(row.module)}</span>
            <span>${importance.toFixed(3)}</span>
          </div>
          <div class="bar"><span style="width:${pct(importance)}%"></span></div>
          <div class="kv">
            <div class="k">importance</div><div class="v">${importance.toFixed(3)}</div>
            <div class="k">salience</div><div class="v">${Number(row.salience || 0).toFixed(3)}</div>
            <div class="k">relevance</div><div class="v">${Number(row.relevance || 0).toFixed(3)}</div>
            <div class="k">hint</div><div class="v">${html(row.action_hint)}</div>
          </div>
          <div class="module-output">${html(row.output_language)}</div>
          <div class="module-rationale"><span>rationale</span>${html(row.rationale)}</div>
          <div class="module-reflection"><span>reflection</span>${html(row.reflection)}</div>
        </div>`;
      }).join('');
    }

    function renderReasoning(step) {
      const reasoning = step.reasoning || {};
      kv(document.getElementById('reasoningPanel'), [
        ['winner rationale', reasoning.winner_rationale],
        ['winner reflection', reasoning.winner_reflection],
        ['score basis', reasoning.score_basis],
        ['ignition', reasoning.ignition_basis],
        ['action route', reasoning.action_basis],
      ]);
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
        ['winner output', step.workspace_output_language],
        ['ignited', step.workspace_ignited],
        ['maintained', step.workspace_maintained],
      ]);
      renderReasoning(step);
      renderModules(step);
      document.getElementById('reportPanel').textContent = step.language_report || '-';
      if (document.activeElement !== promptCycle) {
        promptCycle.value = step.cycle_t === null || step.cycle_t === undefined ? 0 : step.cycle_t;
      }
      refreshRerunCommand();
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

    function shellQuote(value) {
      const textValue = text(value);
      return "'" + textValue.replace(/'/g, "'\\''") + "'";
    }

    function argPair(args, flag, value) {
      if (value === null || value === undefined || value === '') return;
      args.push(flag, shellQuote(value));
    }

    function buildRerunCommand() {
      const summary = data.summary || {};
      const cycle = Number(promptCycle.value || 0);
      const prompt = experimenterPrompt.value || '';
      const root = summary.project_root || '.';
      const args = ['python3', 'scripts/run_qiyuan_integrated.py'];
      argPair(args, '--qiyuan-path', summary.qiyuan_path);
      argPair(args, '--difficulty', summary.difficulty);
      argPair(args, '--seed', summary.seed);
      argPair(args, '--target-resources', summary.target_resources);
      argPair(args, '--max-cycles', summary.max_cycles || Math.max(summary.cycle_count || 0, 1));
      argPair(args, '--run-id', `${summary.run_id || 'run'}-prompt-c${cycle}`);
      argPair(args, '--out-dir', summary.out_dir);
      argPair(args, '--instruction', summary.experimenter_instruction);
      argPair(args, '--agent-backend', summary.agent_backend || summary.resolved_agent_backend || 'mock-llm');
      argPair(args, '--openai-model', summary.openai_model);
      argPair(args, '--openai-vision-model', summary.openai_vision_model);
      argPair(args, '--hf-model', summary.hf_model);
      argPair(args, '--hf-vision-model', summary.hf_vision_model);
      argPair(args, '--ignition-threshold', summary.ignition_threshold);
      argPair(args, '--salience-weight', summary.salience_weight);
      argPair(args, '--relevance-weight', summary.relevance_weight);
      argPair(args, '--workspace-recurrence-bonus', summary.workspace_recurrence_bonus);
      argPair(args, '--workspace-adjustment-policy', summary.workspace_adjustment_policy);
      argPair(args, '--report-query-every', summary.report_query_every || 0);
      argPair(args, '--report-query', summary.report_query);
      const modifiers = summary.score_modifiers || {};
      Object.keys(modifiers).sort().forEach(key => {
        argPair(args, '--score-modifier', `${key}=${modifiers[key]}`);
      });
      const pauses = Object.assign({}, summary.language_pause_cycles || {});
      if (prompt.trim()) {
        pauses[String(cycle)] = prompt;
      }
      Object.keys(pauses).sort((a, b) => Number(a) - Number(b)).forEach(key => {
        argPair(args, '--pause-language-at', `${key}=${pauses[key]}`);
      });
      if (summary.allow_non_workspace_motor_action) {
        args.push('--allow-non-workspace-motor');
      }
      return `cd ${shellQuote(root)} && PYTHONPATH=src ${args.join(' ')}`;
    }

    function refreshRerunCommand() {
      rerunCommand.textContent = buildRerunCommand();
    }

    function canUsePromptServer() {
      return window.location.protocol === 'http:' || window.location.protocol === 'https:';
    }

    async function submitPrompt() {
      const prompt = experimenterPrompt.value.trim();
      if (!prompt) {
        promptStatus.textContent = 'Prompt is empty.';
        return;
      }
      refreshRerunCommand();
      if (!canUsePromptServer()) {
        promptStatus.textContent = 'Open this viewer through scripts/serve_qiyuan_viewer.py to run from the button.';
        return;
      }
      sendPromptBtn.disabled = true;
      promptStatus.textContent = 'Running...';
      try {
        const response = await fetch('/api/rerun', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            run_id: data.summary.run_id,
            cycle: Number(promptCycle.value || 0),
            prompt,
          }),
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
          throw new Error(result.error || `HTTP ${response.status}`);
        }
        promptStatus.textContent = `Created ${result.run_id}`;
        window.location.href = result.viewer_url;
      } catch (error) {
        promptStatus.textContent = String(error.message || error);
        sendPromptBtn.disabled = false;
      }
    }

    async function copyCommand() {
      refreshRerunCommand();
      const command = rerunCommand.textContent;
      try {
        await navigator.clipboard.writeText(command);
        promptStatus.textContent = 'Command copied.';
      } catch (error) {
        promptStatus.textContent = command;
      }
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
    promptCycle.addEventListener('input', refreshRerunCommand);
    experimenterPrompt.addEventListener('input', refreshRerunCommand);
    sendPromptBtn.addEventListener('click', submitPrompt);
    copyCommandBtn.addEventListener('click', copyCommand);
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
