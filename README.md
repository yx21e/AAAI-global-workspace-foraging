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
  -> deterministic AttentionGate
     bottom-up salience = private-input change
     top-down relevance = proposal similarity to task goal + previous broadcast
     fixed workspace adjustments prevent idle language/NOOP motor/motor echo dominance
  -> CentralWorkspace
     highest proposal above ignition threshold wins
     otherwise maintained content decays
  -> WorkspaceBroadcast
     winning content is broadcast back to all modules on the next cycle
  -> ActionResolver
     executes workspace action if the winning broadcast has an action_hint
     optionally executes high-importance motor action through non-workspace route
  -> Qiyuan env.step(action) only when EnvAction.should_step=true
  -> trace/action/viewer/replay artifacts
```

Important implementation boundaries:

- Modules do **not** receive identical full environment information.
- The motor module does **not** receive `resource_position` or `base_position`
  through its private channel. It can only use target information after that
  information appears in a workspace broadcast.
- The language module is the experimenter-facing spokesperson. It never sends
  actions to Qiyuan.
- The non-workspace motor route is off by default. When enabled, it represents
  an automatic/local action route and is logged separately from workspace actions.

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
20 tests OK
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
  --target-resources 1 \
  --max-cycles 90 \
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
  --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The viewer supports:

- frame-by-frame replay
- play/pause and timeline scrubber
- workspace winner and winning output
- every module's score, action hint, summary, and observations
- experimenter prompt panel for pausing at a selected cycle

When an experimenter prompt is submitted, the server reruns the integrated demo
with:

```text
--pause-language-at CYCLE=PROMPT
```

and opens a new prompt-conditioned viewer.

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
workspace winners: perception and motor both appear
motor private resource/base leaks: 0
```

The motor module no longer receives target coordinates privately. Perception
must broadcast global target information before motor can use it. Some movement
may still execute through the non-workspace motor threshold when that route is
explicitly enabled.

## What to Avoid Claiming

- Do not claim a biologically faithful GNW implementation.
- Do not claim true parallel module execution; modules are evaluated
  sequentially but treated as same-cycle proposals.
- Do not claim learned latent workspace representations; the workspace message
  format is structured JSON/natural language for debugging and replay.
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
