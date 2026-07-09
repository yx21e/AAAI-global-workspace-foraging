# Qiyuan End-to-End Demo Plan

Date: 2026-07-06

This is the full demo path:

```text
Qiyuan ForagingEnv
  -> ForagingEnvAdapter
  -> GWT LLM modules: multimodal perception / motor / language
  -> fixed importance scoring
  -> workspace ignition or maintained broadcast
  -> ActionResolver
       default: only active workspace action is executed
       optional: motor threshold bypass for reflex/ablation runs
  -> Qiyuan env.step(action) only when EnvAction.should_step=true
  -> full trace + action stream + rendered frames
  -> replay from historical records
```

## 1. Setup

Qiyuan's repo is kept outside our repo:

```bash
git clone https://github.com/llll0630/Foraging-Environment-Design.git ../qiyuan_foraging_env
python3 -m pip install -r requirements-foraging.txt
```

For real OpenAI-backed LLM agents:

```bash
python3 -m pip install -r requirements-llm.txt
export OPENAI_API_KEY=...
```

If this dependency/key is absent, `--agent-backend auto` uses `mock-llm` through
the same module interface so the clickable demo still runs locally.

For downloaded open HuggingFace models:

```bash
python3 -m pip install -r requirements-hf.txt
PYTHONPATH=src python3 scripts/download_hf_models.py --cache-dir /tmp/hf_home
export HF_HOME=/tmp/hf_home
```

Default HF model assignment:

```text
perception: Qwen/Qwen3-VL-8B-Instruct
motor:      Qwen/Qwen3-4B-Instruct-2507
language:   Qwen/Qwen3-4B-Instruct-2507
```

## 2. Run The Integrated System

Use difficulty 1 to explain the minimum closed loop. Use difficulty 2 with the
same seed to show obstacle avoidance in a map with internal walls. Difficulty 3
should still be treated as a stress test for future planner improvements.

```bash
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 1 \
  --seed 7 \
  --target-resources 1 \
  --agent-backend auto
```

Obstacle demo:

```bash
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --target-resources 1 \
  --run-id qiyuan-d2-seed7 \
  --agent-backend auto
```

To force real OpenAI calls instead of the local mock backend:

```bash
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --target-resources 1 \
  --agent-backend openai \
  --openai-model gpt-5.5 \
  --openai-vision-model gpt-5.5
```

To run local HuggingFace models instead:

```bash
export HF_HOME=/tmp/hf_home
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --target-resources 1 \
  --agent-backend huggingface \
  --hf-vision-model Qwen/Qwen3-VL-8B-Instruct \
  --hf-model Qwen/Qwen3-4B-Instruct-2507
```

Outputs:

```text
runs/qiyuan_integrated/<run_id>_trace.jsonl       full per-cycle trace
runs/qiyuan_integrated/<run_id>_envelopes.jsonl   full standardized replay file
runs/qiyuan_integrated/<run_id>_actions.jsonl     minimal Qiyuan action stream
runs/qiyuan_integrated/<run_id>_frames/           rendered PNG frames
runs/qiyuan_integrated/<run_id>_perception_inputs/ current map screenshots for perception
runs/qiyuan_integrated/<run_id>_viewer.html       clickable browser viewer
runs/qiyuan_integrated/<run_id>_summary.json      short demo summary
```

For an existing run:

```bash
PYTHONPATH=src python3 scripts/build_qiyuan_viewer.py \
  --run-id qiyuan-d2-seed7
```

Open the generated `*_viewer.html` in a browser. The viewer has frame stepping,
play/pause, a timeline slider, a PICKUP jump, action route, workspace state, and
module scores. The right sidebar also prints each module's output language at
the bottom of its module card, and the Workspace panel prints the winning
module's output language.

## 3. Replay From Historical Records

Exact trace replay:

```bash
PYTHONPATH=src python3 scripts/replay_qiyuan_record.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --mode trace \
  --trace runs/qiyuan_integrated/<run_id>_envelopes.jsonl \
  --render-dir runs/qiyuan_integrated/<run_id>_trace_replay
```

Action-stream replay:

```bash
PYTHONPATH=src python3 scripts/replay_qiyuan_record.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --mode action \
  --trace runs/qiyuan_integrated/<run_id>_envelopes.jsonl \
  --actions runs/qiyuan_integrated/<run_id>_actions.jsonl \
  --render-dir runs/qiyuan_integrated/<run_id>_action_replay
```

Use `trace` replay for slides and debugging because it restores recorded states
frame by frame. Use `action` replay to prove Qiyuan can consume our minimal
action stream and call `env.step(action)`.

## 4. Experimenter Prompt Design

The experimenter prompt is a task-level top-down goal, not a per-step control
command. It should contain:

```text
Goal: collect exactly one resource and return it to base.
Constraints: avoid walls; use PICKUP only when standing on the resource.
Stopping rule: stop once the resource has been delivered to base.
Reporting role: language should summarize the current workspace content
for the experimenter, not send actions to the simulator.
```

The default script prompt is:

```text
Collect exactly one resource, avoid walls, use PICKUP only when standing on the
resource, return to base, and stop after the resource is delivered.
```

Implementation detail: this instruction is routed to all modules as
`module_input.task_goal`, so the fixed importance scorer's top-down relevance
term is aligned to the experimenter's current task. The language private channel
is reserved for the current `report_query` event so salience reflects new
experimenter-facing language input instead of the static task instruction.

The language module does not send actions to the simulator. In normal navigation
cycles it produces a low-pressure status/report candidate; when an explicit
`report_query` is injected, it switches to an outward experimenter-facing answer.
For demoing language ignition, use `--report-query-every N`.

For a user-controlled pause, pass a cycle-indexed prompt:

```bash
PYTHONPATH=src python3 scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 2 \
  --seed 7 \
  --target-resources 1 \
  --pause-language-at "8=What did you just hear from the workspace?"
```

At that cycle, the language module receives the previous broadcast, the user
prompt, and its own recent language input/output history. It still does not
send an action to the simulator.

## 5. Timestep Definition

Use three indices in the demo:

| Name | Meaning | When it changes |
|---|---|---|
| `cycle_t` | One internal GWT cognitive cycle: modules propose, scores are computed, workspace may ignite, action may be resolved. | Every line of our trace/action stream. |
| `env_t` | Qiyuan simulator step count. | Only when `EnvAction.should_step=true` and Qiyuan `env.step(action)` is called. |
| `frame_i` | Rendered visualization frame. | `frame_0000` is initial state; `frame_i` is the environment after cognitive cycle `i`. |

If no action is executed, `cycle_t` still advances but `env_t` and the rendered
agent position can stay unchanged. This is expected: it represents an internal
cognitive timestep without movement.

Default demo rule:

```text
workspace winner has action_hint -> send action to Qiyuan env.step()
workspace winner has no action_hint -> log the cycle, do not update Qiyuan env
```

The optional `--allow-non-workspace-motor` flag restores the earlier motor
threshold bypass. That route should be shown as an ablation/reflex condition,
not as the default GWT action path.

## 6. Demo Storyboard

For a short group-meeting demo:

1. Show `frame_0000_initial.png`: Qiyuan map, base, resource, agent.
2. Show 3-5 middle frames: action stream moves the agent toward resource and,
   for difficulty 2, avoids walls using nearby obstacle input plus motor
   private history.
3. Show the frame where `PICKUP` happens.
4. Show the final frame: agent returns to base, `resources_collected = 1`.
5. Open one trace line to show:
   - module-specific inputs;
   - fixed importance scores;
   - workspace broadcast;
   - action route (`workspace_broadcast` by default);
   - Qiyuan-readable `env_action`.
6. Run replay and show that historical records regenerate the same visual path.
