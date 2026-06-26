# Multi-Agent Global Workspace Scaffold

This folder contains the non-2D-environment side of the project: a small Python
framework for running specialized modules through a central global workspace,
selecting a winning broadcast, resolving an action, and logging every timestamp.

The 2D character environment is intentionally behind an adapter interface. When
the real environment code arrives, add a concrete adapter that implements:

```python
class EnvironmentAdapter:
    def reset(self) -> EnvironmentState: ...
    def step(self, action: str) -> EnvironmentState: ...
```

## Current Flow

```text
EnvironmentAdapter
  -> InputRouter builds module-specific ModuleInput
  -> specialized modules produce ModuleProposal from private input + broadcast
  -> AttentionGate computes uptake scores
  -> CentralWorkspace selects winner and updates WorkspaceState
  -> WorkspaceBroadcast
  -> ActionResolver
  -> EnvironmentAdapter.step(action)
  -> TraceLogger writes JSONL
```

## Key Files

- `src/gwt_agent/core/types.py`: shared data structures.
- `src/gwt_agent/core/router.py`: routes different private inputs to modules.
- `src/gwt_agent/core/attention.py`: attention / uptake scoring before workspace.
- `src/gwt_agent/envs/adapter.py`: environment interface for the future 2D code.
- `src/gwt_agent/core/workspace.py`: winner-take-all central workspace with persistent state.
- `src/gwt_agent/core/runner.py`: one-step and multi-step execution loop.
- `src/gwt_agent/core/logger.py`: timestamp-level JSONL logger.
- `src/gwt_agent/core/export.py`: full trace and simulator action export helpers.
- `src/gwt_agent/core/experiment.py`: ablation/intervention config.
- `src/gwt_agent/modules/`: reference perception, motor, outcome-monitor, and language/report modules.
- `src/gwt_agent/envs/mock_env.py`: minimal mock grid only for interface testing.
- `src/gwt_agent/envs/foraging_adapter.py`: adapter for Qiyuan's foraging env.
- `unified_trace_action_schema.md`: shared schema for full traces and action replay.
- `module_selection_for_foraging.md`: module choices grounded in Qiyuan's env fields.

## Run the Mock Demo

```bash
cd /home/yx21e.fsu/AAAI_project/begining_stage
PYTHONPATH=src python3 scripts/run_mock.py
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
PYTHONPATH=src python3 scripts/export_mock_actions.py
```

This writes:

```text
runs/mock_trace_envelopes.jsonl
runs/mock_action_stream.jsonl
```

## Expected Adapter Contract for the Real 2D Environment

The real adapter should convert whatever the 2D code returns into:

```python
EnvironmentState(
    timestamp=int,
    observation=raw_or_structured_observation,
    symbolic_state={
        "agent_position": ...,
        "base_position": ...,
        "resource_position": ...,
        "hazard_positions": ...,
        "carrying_resource": ...,
    },
    available_actions=["UP", "DOWN", "LEFT", "RIGHT", "NOOP"],
    reward=float,
    done=bool,
    info={...},
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
- The first attention policy combines salience, goal relevance, confidence, and a small recurrence bonus.
- The first workspace policy is winner-take-all by uptake score.
- If the winning broadcast has no `action_hint`, the resolver falls back to the
  best motor proposal, then `NOOP`.
- Ablations are centralized in `ExperimentConfig`, not scattered inside modules.

## First-Version Module Set

Grounded in Qiyuan's current environment fields, the recommended first-version
modules are:

```python
[
    PerceptionModule(),       # symbolic spatial state / optional local view
    MotorModule(),            # UP/DOWN/LEFT/RIGHT/PICKUP proposal
    OutcomeMonitorModule(),   # action_success / progress feedback
    LanguageReportModule(),   # optional report / explanation channel
]
```

For a minimal control-only run, `LanguageReportModule` can be removed. We do not
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
