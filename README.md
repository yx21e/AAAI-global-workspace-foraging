# AAAI Global Workspace Foraging

This repository contains the current runnable side of our Global Workspace
foraging demo. It connects our multi-module workspace loop to Qiyuan's 2D
foraging environment:

<https://github.com/llll0630/Foraging-Environment-Design>

The project should be described as a **GWT/GWS-inspired engineering scaffold**,
not as a biologically faithful Global Neuronal Workspace implementation. It
implements the practical selection-broadcast loop we need for demos, replay,
ablation, and handoff to the simulator side.

## Current Pipeline

```text
Qiyuan ForagingEnv
  -> ForagingEnvAdapter
     builds EnvironmentState and saves Qiyuan episode grid
  -> InputRouter
     perception: previous broadcast + global map/screenshot + symbolic visual state
     motor: previous broadcast + local obstacle/blocked-direction state only
     language: previous broadcast + experimenter pause/query + language history
  -> specialized modules produce ModuleProposal objects
     perception may use a multimodal model
     motor/language may use text-only models
     each proposal includes output language, action_hint, confidence, rationale, and reflection
  -> deterministic AttentionGate
     bottom-up salience = private-input change
     top-down relevance = proposal similarity to task goal + previous broadcast
  -> CentralWorkspace
     highest proposal above ignition threshold wins
     otherwise maintained content decays
  -> WorkspaceBroadcast
     winning content is broadcast back to all modules on the next cycle
  -> ActionResolver
     executes workspace action only if a fresh ignited broadcast has an action_hint
     optionally executes high-importance motor action through non-workspace route
  -> Qiyuan env.step(action) only when EnvAction.should_step=true
  -> trace/action/viewer/replay artifacts
```

Important implementation boundaries:

- Modules do **not** receive identical full environment information.
- The motor module does **not** receive `resource_position` or `base_position`
  through its private channel. It can only use target information after that
  information appears in a workspace broadcast.
- Only perception may globally broadcast resource/base/target coordinates.
  Raw motor proposals are still logged for debugging, but motor broadcasts are
  sanitized before they become the next cycle's shared workspace input.
- A maintained workspace broadcast can be heard by modules as context, but its
  old `action_hint` is not resent to Qiyuan as a new simulator action.
- The language module is the experimenter-facing spokesperson. It never sends
  actions to Qiyuan. If an experimenter pause prompt contains an explicit
  temporary navigation instruction, language may broadcast structured
  `instruction_*` fields only by winning workspace; motor can then use that
  broadcast as a top-down cue on later cycles.
- The non-workspace motor route is off by default. When enabled, it represents
  an automatic/local action route and is logged separately from workspace actions.
- The viewer's reasoning display is a concise decision-basis audit plus
  reportable module reflections. It is not a hidden chain-of-thought trace.
- By default there is no winner-balancing rule: no perception/motor alternation,
  no winner quota, and no viewer-driven broadcast schedule.

## Mechanism Integrity

The default run follows the discussed pipeline directly. At each cognitive
cycle, modules submit proposals, the deterministic scorer computes importance
from bottom-up salience and top-down relevance, and `CentralWorkspace` selects
the highest-scoring proposal only if it crosses the ignition threshold.
Perception, motor, and language proposals all participate in this competition
on every cycle. A language winner broadcasts language content but does not send
a simulator action. A motor `NOOP` winner is valid workspace content but also
does not advance Qiyuan's environment state.

The code does **not** force perception and motor to alternate, does **not**
require each module to win a minimum number of times, and does **not** choose
winners for visualization. If one module has the highest score for several
consecutive cycles, it can win several consecutive cycles.

Optional switches such as `--score-modifier`, `--workspace-recurrence-bonus`,
and `--workspace-adjustment-policy anti_echo` are explicit diagnostic/ablation
settings. They are not enabled in the default mechanism.

## Strict Broadcast Isolation

The current version enforces the information boundary that motivated the latest
pipeline revision:

- perception receives the full global map/screenshot and may broadcast spatial
  target coordinates
- motor receives only local obstacle/blocked-direction state plus the previous
  broadcast
- language receives the previous broadcast plus experimenter pause/query events
  and language history
- perception, motor, and language all enter workspace competition after scoring;
  there is no idle-language or motor-`NOOP` eligibility filter

This means motor cannot preserve a resource/base target by winning and
rebroadcasting its own target-bearing content. If motor wins, the broadcast sent
back to modules removes `resource_position`, `base_position`, and
`target_position`. On the next cycle, motor must either hear a fresh perception
target broadcast, hear an explicit language `instruction_*` broadcast, or return
`NOOP`.

## Repository Layout

```text
configs/                  default config examples
examples/                 minimal action-stream example
scripts/                  runnable demos, replay, viewer server, HF downloads
src/gwt_agent/core/       workspace loop, attention, action resolver, trace types
src/gwt_agent/envs/       Qiyuan adapter and replay helpers
src/gwt_agent/llm/        mock/OpenAI/HuggingFace JSON clients
src/gwt_agent/modules/    perception, motor, language modules
src/gwt_agent/ui/         clickable HTML viewer generator
tests/                    unit tests for the final scaffold
```

Old meeting slides, PPT files, and early research notes have been removed from
the repo. This README is the source of truth for the current version.

## Install

Core code uses only the Python standard library.

```bash
cd /home/yx21e.fsu/AAAI_project/begining_stage
python3 -m pip install -e .
```

For Qiyuan's simulator integration:

```bash
python3 -m pip install -r requirements-foraging.txt
```

For OpenAI-backed agents:

```bash
python3 -m pip install -r requirements-llm.txt
export OPENAI_API_KEY=...
```

For local HuggingFace agents:

```bash
python3 -m pip install -r requirements-hf.txt
```

On the FSU machine, the HuggingFace environment and models are intentionally
stored under orange, not home/blue:

```text
/orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/hf_env
/orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/hf_home
/orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/pip-cache
```

Default local model choices:

```text
perception: Qwen/Qwen3-VL-8B-Instruct
motor:      Qwen/Qwen3-4B-Instruct-2507
language:   Qwen/Qwen3-4B-Instruct-2507
```

## Run Tests

```bash
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
```

Expected current result:

```text
42 tests OK
```

## Run the Integrated Qiyuan Demo

Qiyuan's repo is expected at:

```text
/home/yx21e.fsu/AAAI_project/qiyuan_foraging_env
```

Run the current mock-LLM demo:

```bash
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path /home/yx21e.fsu/AAAI_project/qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --map-preset auto \
  --map-variant auto \
  --target-resources 1 \
  --max-cycles 400 \
  --run-id current-demo \
  --agent-backend mock-llm \
  --allow-non-workspace-motor
```

This writes:

```text
runs/qiyuan_integrated/current-demo_summary.json
runs/qiyuan_integrated/current-demo_trace.jsonl
runs/qiyuan_integrated/current-demo_envelopes.jsonl
runs/qiyuan_integrated/current-demo_actions.jsonl
runs/qiyuan_integrated/current-demo_episode_grid.json
runs/qiyuan_integrated/current-demo_frames/
runs/qiyuan_integrated/current-demo_perception_inputs/
runs/qiyuan_integrated/current-demo_viewer.html
```

For difficulty 2, `--map-preset auto` uses a five-map preset instead of a
single fixed layout. `--map-variant auto` selects `seed % 5`; set
`--map-variant 0`, `1`, `2`, `3`, or `4` to force a particular map. Each
variant changes the base position, resource position, and a small number of
interior obstacles. The resolved map variant is written to the summary, and the
episode grid is still saved for exact replay.

The episode grid is saved once using Qiyuan's `get_grid()` API and also embedded
in each trace state's `info.qiyuan_episode_grid`. Replay uses Qiyuan's
`load_state(state, grid)` API when available.

## Run With HuggingFace Models

Use the orange venv and cache:

```bash
cd /home/yx21e.fsu/AAAI_project/begining_stage
export HF_HOME=/orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/hf_home

PYTHONPATH=src /orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/hf_env/bin/python \
  scripts/run_qiyuan_integrated.py \
  --qiyuan-path /home/yx21e.fsu/AAAI_project/qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --target-resources 1 \
  --agent-backend huggingface \
  --hf-vision-model Qwen/Qwen3-VL-8B-Instruct \
  --hf-model Qwen/Qwen3-4B-Instruct-2507
```

The current login node reports no CUDA device, so full local inference may be
slow unless run on a GPU node.

## Clickable Viewer and Experimenter Prompt

Build a static viewer for an existing run:

```bash
PYTHONPATH=src python3 scripts/build_qiyuan_viewer.py \
  --run-id current-demo
```

Start the local interactive viewer server:

```bash
PYTHONPATH=src:. python3 scripts/serve_qiyuan_viewer.py \
  --run-id current-demo \
  --port 8765 \
  --max-cycles 400
```

Or double-click the launcher in the project root:

```text
Open_GWT_Viewer.desktop
```

The launcher starts `all-compete-v3` with `GWT_MAX_CYCLES=400` by default. To
launch a different existing run from a terminal, set `GWT_RUN_ID` before running
`launch_interactive_viewer.sh`.

Open:

```text
http://127.0.0.1:8765/
```

The viewer supports:

- frame-by-frame replay
- play/pause and timeline scrubber
- workspace winner and winning output
- reasoning panel with winner rationale/reflection, score basis, ignition basis, and action route
- every module's score, action hint, summary, and observations
- every module's concise rationale and reflection
- map panel for loading Qiyuan's default map or one of the five difficulty-2
  preset maps
- experimenter prompt panel for pausing at the selected cycle and sending a
  language input to the language module

Open the viewer through `scripts/serve_qiyuan_viewer.py` for clickable reruns.
Opening the HTML file directly is static playback only.

When an experimenter prompt is submitted, the server reruns the integrated demo
with:

```text
--pause-language-at CYCLE=PROMPT
```

The current browser page is then updated in place with the new prompt-conditioned
run payload. The frames after the selected cycle are recomputed; the old viewer
is no longer just a retrospective recording once the server is active. This does
not add a special score bonus to language. The prompt enters only through the
language module's private input, and the same deterministic salience/relevance
importance function decides whether the language reply wins workspace.

If the prompt says something like `move to (2,2) for next 5 moves` or `move up
for 5 steps`, language converts it into structured `instruction_*` fields. Those
fields affect movement only if the language proposal wins workspace and is
broadcast. Motor hears that broadcast on the following cycle and may use the
temporary top-down instruction while still respecting blocked-direction input.

When a map is loaded from the Map panel, the server creates a clean new episode
for that map variant and updates the current browser page with the new run
payload. Map switching does not inherit previous experimenter language pauses.

## Reasoning and Reflection Display

Each `ModuleProposal` records two explanation fields:

- `rationale`: a short reason why this module produced its proposal
- `reflection`: a reportable self-explanation of how the module currently
  understands the situation, what it is inclined to do, and which constraints or
  uncertainties matter

The viewer surfaces both fields. Each module card shows the module's rationale
and reflection. The right-side Reasoning panel summarizes the workspace winner's
rationale/reflection, the deterministic importance-score breakdown, the
ignition/maintenance decision, and the action route used by `ActionResolver`.

This is useful for debugging odd transitions. For example, if a frame appears
to move left into a wall, inspect:

- `action route` and `source_module` to see which module actually caused the
  simulator action
- the motor module's `reflection` for its target source, blocked directions,
  and why it considered the action safe
- the perception module's `reflection` to confirm that perception reported
  global spatial context but did not emit a simulator action

This should be described as **reportable decision basis and module
self-report**, not full internal reasoning. The deterministic scoring terms
remain external to the modules: modules do not set their own importance scores.

## Ablation Dashboard

Use `configs/ablation_manifest_template.json` as the starting point for an
ablation suite. Group conditions by level, fill in the relevant `run_ids`, then
build a static comparison dashboard:

```bash
PYTHONPATH=src python3 scripts/build_ablation_viewer.py \
  --manifest configs/ablation_manifest_template.json \
  --open
```

The dashboard gives you a level dropdown and a condition dropdown, then shows
success rate, cycles, action routes, fresh ignition winners, maintained
broadcast sources, and links to the underlying run artifacts for each condition.

Relative `run_dir` values are resolved from the manifest file location, so the
template points `../runs/qiyuan_integrated` back to the repo's run folder.

## Replay Historical Records

Exact trace replay, using Qiyuan `load_state(state, grid)`:

```bash
PYTHONPATH=src python3 scripts/replay_qiyuan_record.py \
  --qiyuan-path /home/yx21e.fsu/AAAI_project/qiyuan_foraging_env \
  --mode trace \
  --trace runs/qiyuan_integrated/current-demo_envelopes.jsonl \
  --grid runs/qiyuan_integrated/current-demo_episode_grid.json \
  --render-dir runs/qiyuan_integrated/current-demo_trace_replay
```

Action-stream replay, using Qiyuan `env.step(action)`:

```bash
PYTHONPATH=src python3 scripts/replay_qiyuan_record.py \
  --qiyuan-path /home/yx21e.fsu/AAAI_project/qiyuan_foraging_env \
  --mode action \
  --trace runs/qiyuan_integrated/current-demo_envelopes.jsonl \
  --actions runs/qiyuan_integrated/current-demo_actions.jsonl \
  --grid runs/qiyuan_integrated/current-demo_episode_grid.json \
  --render-dir runs/qiyuan_integrated/current-demo_action_replay
```

Trace replay is best for slides/debugging because it restores every recorded
state exactly. Action replay is best for proving that Qiyuan can consume our
minimal action stream.

## Standardized Action Stream

Each line of `<run_id>_actions.jsonl` is the minimal Qiyuan-readable action:

```json
{
  "schema_version": "gwt_trace_v1",
  "run_id": "current-demo",
  "timestamp": 1,
  "should_step": true,
  "action": "DOWN",
  "action_type": "MOVE",
  "direction": "DOWN",
  "confidence": 0.76,
  "source_module": "motor",
  "source_timestamp": 1
}
```

Qiyuan-side replay rule:

```python
if record["should_step"]:
    state = env.step(record["action"])
else:
    # Qiyuan has no NOOP/WAIT action; keep current simulator state.
    state = current_state
```

For exact visual replay:

```python
grid = json.load(open("<run_id>_episode_grid.json"))
env.load_state(step_record["env_state"]["observation"], grid)
env.render(...)
```

## Current Expected Behavior

With the current mock demo command above:

```text
done: true
resources_collected: 1
cycle_count: 51
env_step_count: 25
fresh ignition winners: perception=25, motor=15, language=11
action routes: workspace_broadcast=15, non_workspace_motor_threshold=10, no_action_threshold_not_met=26
non-workspace motor moves: 10
non-perception broadcast target leaks: 0
motor next-cycle old-action leaks: 0
motor next-cycle target leaks: 0
maintained old-action replays: 0
```

The motor module no longer receives target coordinates privately. Perception
must broadcast global target information before motor can use it. Movement may
execute through the non-workspace motor threshold only when that route is
explicitly enabled and the current motor proposal is a real action above the
threshold; in the all-compete smoke run above, language wins are allowed and
some movement occurs through that separate motor-threshold route.

## What to Avoid Claiming

- Do not claim a biologically faithful GNW implementation.
- Do not claim true parallel module execution; modules are evaluated
  sequentially but treated as same-cycle proposals.
- Do not claim learned latent workspace representations; the workspace message
  format is structured JSON/natural language for debugging and replay.
- Do not claim access to full hidden model reasoning or chain-of-thought; only
  concise module rationales, reportable reflections, and deterministic score
  metadata are logged.
- Do not claim the automatic motor route is the workspace. It is logged as a
  separate route for automatic/non-workspace action experiments.

## Useful Commands

```bash
# Unit tests
PYTHONPATH=src:. python3 -m unittest discover -s tests -v

# Mock interface demo
PYTHONPATH=src python3 scripts/run_mock.py

# Export mock action stream
PYTHONPATH=src python3 scripts/export_mock_actions.py

# Download default HF models into orange cache
PYTHONPATH=src python3 scripts/download_hf_models.py \
  --cache-dir /orange/fsu-compsci-dept/yx21e.fsu/AAAI_project/hf_home
```

## License

MIT. See `LICENSE`.
