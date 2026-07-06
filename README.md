# Multi-Agent Global Workspace Scaffold

This repository contains the non-2D-environment side of the project: a small
Python framework for running specialized modules through a central global
workspace, selecting a winning broadcast, resolving a standardized simulator
action, and logging every cognitive timestep.

The code is designed to connect to Qiyuan's foraging simulator:

<https://github.com/llll0630/Foraging-Environment-Design>

The 2D character environment is intentionally behind an adapter interface. When
the real environment code arrives, add a concrete adapter that implements:

```python
class EnvironmentAdapter:
    def reset(self) -> EnvironmentState: ...
    def step(self, action: str) -> EnvironmentState: ...
```

## Current Flow

```text
Qiyuan simulator output
  -> EnvironmentAdapter builds EnvironmentState
  -> InputRouter builds module-specific ModuleInput
       perception: previous broadcast + global visual map/screenshot
       motor: previous broadcast + nearby obstacle state
       language: previous broadcast + experimenter instruction
  -> specialized modules produce one reply / ModuleProposal each
  -> fixed deterministic ImportanceScorer
       bottom-up salience = private-input change from previous step
       top-down relevance = similarity(reply, task goal + previous broadcast)
  -> CentralWorkspace all-or-none ignition
       winner must be highest score and exceed ignition_threshold
       otherwise old workspace content is maintained and decays
  -> WorkspaceBroadcast to all three modules
  -> ActionResolver
       workspace action route if active broadcast asks for action
       non-workspace motor route if motor importance exceeds motor threshold
  -> standardized EnvAction for Qiyuan
  -> TraceLogger writes JSONL
```

The motor route threshold is independent from the workspace ignition threshold,
so threshold-level / non-workspace actions can be studied separately.
If no proposal crosses the ignition threshold and no old content is still
maintained, the trace records a `no_ignition` placeholder, but that placeholder
is not fed back as a real broadcast on the next cycle.

## Quick Start

```bash
git clone https://github.com/yx21e/AAAI-global-workspace-foraging.git
cd AAAI-global-workspace-foraging
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/run_mock.py
python scripts/export_mock_actions.py
python -m unittest discover -s tests -v
```

The core scaffold has no third-party runtime dependencies.

To run against Qiyuan's actual simulator, install the simulator-side dependency:

```bash
python -m pip install -r requirements-foraging.txt
```

To use a sentence-transformers model instead of the built-in deterministic
hashing encoder, install the optional encoder dependency:

```bash
python -m pip install -r requirements-encoder.txt
```

## Qiyuan Handoff

For simulator integration, Qiyuan can start from:

- `unified_trace_action_schema.md`: full trace schema and replay contract.
- `qiyuan_end_to_end_demo.md`: complete run/replay/demo plan.
- `examples/action_stream_example.jsonl`: minimal action stream example.
- `src/gwt_agent/envs/foraging_adapter.py`: adapter for the current
  `ForagingEnv` state fields.
- `scripts/run_qiyuan_integrated.py`: run Qiyuan's env with our GWT loop.
- `scripts/replay_qiyuan_record.py`: replay a historical full trace or action stream.

The action stream fields the simulator needs are:

```json
{
  "timestamp": 0,
  "should_step": true,
  "action": "RIGHT",
  "action_type": "MOVE"
}
```

Replay rule:

```python
if record["should_step"]:
    state = env.step(record["action"])
else:
    state = current_state
```

## Key Files

- `src/gwt_agent/core/types.py`: shared data structures.
- `src/gwt_agent/core/router.py`: routes different private inputs to modules.
- `src/gwt_agent/core/importance.py`: fixed sentence-encoder importance function.
- `src/gwt_agent/core/attention.py`: applies deterministic importance scoring before workspace.
- `src/gwt_agent/envs/adapter.py`: environment interface for the future 2D code.
- `src/gwt_agent/core/workspace.py`: winner-take-all central workspace with persistent state.
- `src/gwt_agent/core/runner.py`: one-step and multi-step execution loop.
- `src/gwt_agent/core/logger.py`: timestamp-level JSONL logger.
- `src/gwt_agent/core/export.py`: full trace and simulator action export helpers.
- `src/gwt_agent/core/experiment.py`: ablation/intervention config.
- `src/gwt_agent/modules/`: perception, motor, language/report modules plus optional outcome-monitor diagnostics.
- `src/gwt_agent/envs/mock_env.py`: minimal mock grid only for interface testing.
- `src/gwt_agent/envs/foraging_adapter.py`: adapter for Qiyuan's foraging env.
- `unified_trace_action_schema.md`: shared schema for full traces and action replay.
- `module_selection_for_foraging.md`: module choices grounded in Qiyuan's env fields.
- `pipeline_paper_alignment.md`: what is paper-derived vs. project-specific adaptation.

## Run the Mock Demo

```bash
python scripts/run_mock.py
```

The demo writes:

```text
runs/mock_trace.jsonl
```

Each line is one timestamp containing environment state, all module proposals,
the workspace winner, broadcast content, selected action, next environment state,
and intervention config.

The trace now distinguishes:

```text
env_t   = external simulator time
cycle_t = internal cognitive selection-broadcast cycle
```

The current default is semi-synchronous: one cognitive cycle normally produces
one simulator action. The runner is structured so this can be relaxed later.

To export the full standardized trace plus the minimal Qiyuan-readable action
stream:

```bash
python scripts/export_mock_actions.py
```

This writes:

```text
runs/mock_trace_envelopes.jsonl
runs/mock_action_stream.jsonl
```

## Run With Qiyuan's Actual Environment

Clone Qiyuan's repo next to this repo and install the simulator dependency:

```bash
git clone https://github.com/llll0630/Foraging-Environment-Design.git ../qiyuan_foraging_env
python -m pip install -r requirements-foraging.txt
```

Then run the integrated demo:

```bash
PYTHONPATH=src python scripts/run_qiyuan_integrated.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --difficulty 1 \
  --seed 7 \
  --target-resources 1
```

This writes full traces, a minimal action stream, rendered frames, and a short
summary under:

```text
runs/qiyuan_integrated/
```

It also writes a clickable browser viewer:

```text
runs/qiyuan_integrated/<run_id>_viewer.html
```

For an existing run, rebuild the viewer with:

```bash
PYTHONPATH=src python scripts/build_qiyuan_viewer.py \
  --run-id <run_id>
```

Replay the historical record exactly:

```bash
PYTHONPATH=src python scripts/replay_qiyuan_record.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --mode trace \
  --trace runs/qiyuan_integrated/<run_id>_envelopes.jsonl \
  --render-dir runs/qiyuan_integrated/<run_id>_trace_replay
```

Replay only the minimal action stream through Qiyuan `env.step(action)`:

```bash
PYTHONPATH=src python scripts/replay_qiyuan_record.py \
  --qiyuan-path ../qiyuan_foraging_env \
  --mode action \
  --trace runs/qiyuan_integrated/<run_id>_envelopes.jsonl \
  --actions runs/qiyuan_integrated/<run_id>_actions.jsonl \
  --render-dir runs/qiyuan_integrated/<run_id>_action_replay
```

## Expected Adapter Contract for the Real 2D Environment

The real adapter should convert whatever the 2D code returns into:

```python
EnvironmentState(
    timestamp=int,
    observation=raw_or_structured_observation,
    symbolic_state={
        "global_visual_observation": ...,
        "global_map": ...,
        "global_screenshot": ...,
        "agent_position": ...,
        "base_position": ...,
        "resource_position": ...,
        "wall_positions": ...,
        "nearby_obstacles": ...,
        "blocked_directions": ...,
        "carrying_resource": ...,
        "action_success": ...,
        "resources_collected": ...,
    },
    available_actions=["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"],
    reward=float,
    done=bool,
    info={
        "experimenter_instruction": ...,
        "report_query": optional,
    },
)
```

The symbolic fields can change once the real environment arrives, but the goal is
to keep them explicit enough that modules and trace analysis can read them.

## Design Defaults

- Modules do not receive identical full information.
- Each module receives a module-specific `ModuleInput`:
  - private observation / private state
  - last global broadcast
  - persistent workspace state
  - task goal and experiment config
- Module proposals are structured; natural language is just one possible field.
- The perception module is conceptually multimodal: global bird's-eye map /
  screenshot plus symbolic state. It is not routed a local neighborhood view in
  the default boss-aligned pipeline.
- Importance is not self-reported by modules. A fixed scorer computes bottom-up
  salience and top-down relevance with a sentence-encoder style interface.
- The first workspace policy is all-or-none ignition with a configurable threshold.
- If no proposal crosses the ignition threshold, the previous workspace content
  is maintained for several steps and decays over time.
- If the broadcast asks for an action, the resolver executes it. Separately, a
  high-importance motor proposal can execute through the non-workspace motor route.
- Ablations are centralized in `ExperimentConfig`, not scattered inside modules.

## First-Version Module Set

Grounded in Qiyuan's current environment fields and our need for an outward
report channel, the recommended first-version modules are:

```python
[
    PerceptionModule(),       # multimodal global map + symbolic state
    MotorModule(),            # UP/DOWN/LEFT/RIGHT/PICKUP proposal
    LanguageReportModule(),   # report to the experimenter, not the simulator
]
```

For a pure navigation/control baseline, `PerceptionModule` + `MotorModule` is
enough. `LanguageReportModule` reads our internal workspace broadcast and acts
as the system's spokesperson to the experimenter; Qiyuan's current environment
does not provide language/report/query fields. `OutcomeMonitorModule` is
optional for explicit feedback/agency/intervention experiments. We do not
include a literal emotion module in the first version; if we later need that
role, it should be a `Value` or `SalienceEvaluation` module.

## Qiyuan Foraging Environment Action Contract

Qiyuan's simulator accepts only:

```text
UP, DOWN, LEFT, RIGHT, PICKUP
```

There is no simulator-side `NOOP` or `WAIT`. Our standardized `EnvAction`
therefore includes:

```python
{
    "command": "RIGHT",
    "should_step": True
}
```

or, for no movement:

```python
{
    "command": None,
    "should_step": False
}
```

Qiyuan-side replay should use:

```python
if record["should_step"]:
    state = env.step(record["action"])
else:
    state = current_state
```

## Dependency Notes

- Core package: Python standard library only.
- Test runner: Python standard library `unittest`.
- Qiyuan simulator integration: requires `pygame`, declared in
  `requirements-foraging.txt` and the optional package extra `.[foraging]`.

## License

MIT. See `LICENSE`.
