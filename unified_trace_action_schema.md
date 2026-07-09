# Unified Trace / Action Schema for Foraging Environment

Date: 2026-06-25

This schema is designed for two consumers:

1. **Our side** reads the full standardized trace for module analysis, replay,
   ablation, and dissociation markers.
2. **Qiyuan's simulation side** can read only the `env_action` / action stream
   and attach it to the foraging environment.

The target simulator is:

<https://github.com/llll0630/Foraging-Environment-Design>

## 1. Simulator Constraints From Qiyuan's Environment

From `foraging_env.py` and the interface spec:

- `env.step(action)` accepts only these strings:
  - `"UP"`
  - `"DOWN"`
  - `"LEFT"`
  - `"RIGHT"`
  - `"PICKUP"`
- Each movement action moves exactly one grid cell.
- Picking up resource requires a separate `"PICKUP"` call after reaching the resource.
- There is no `STAY`, `WAIT`, or `NOOP` command.
- If we do not want to move at one cognitive timestep, Qiyuan's side should **not call** `env.step()`.

## 2. Full Standardized Envelope

Each cognitive timestep can be exported as one JSON object:

```json
{
  "schema_version": "gwt_trace_v1",
  "run_id": "mock-export",
  "timestamp": 0,
  "env_t": 0,
  "cycle_t": 0,
  "env_state": {
    "timestamp": 0,
    "observation": {},
    "symbolic_state": {},
    "available_actions": ["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"],
    "reward": 0.0,
    "done": false,
    "info": {}
  },
  "module_states": [
    {
      "module_name": "perception",
      "status": "proposed",
      "module_input": {
        "module_name": "perception",
        "env_t": 0,
        "cycle_t": 0,
        "private_observation": {},
        "global_broadcast": null,
        "task_goal": "collect_resource_and_return"
      },
      "proposal": {
        "module_name": "perception",
        "content": {},
        "importance_score": 0.45,
        "confidence": 0.75,
        "action_hint": null,
        "rationale": "...",
        "metadata": {}
      },
      "private_state": {},
      "error": null
    }
  ],
  "workspace_state": {
    "cycle_t": 0,
    "active_content": {},
    "history": [],
    "capacity": 1
  },
  "workspace_broadcast": {
    "timestamp": 0,
    "winner_module": "motor",
    "content": {},
    "importance_score": 0.65,
    "confidence": 0.7,
    "action_hint": "RIGHT",
    "metadata": {}
  },
  "env_action": {
    "action_type": "MOVE",
    "command": "RIGHT",
    "should_step": true,
    "direction": "RIGHT",
    "target": null,
    "confidence": 0.7,
    "source_module": "motor",
    "source_timestamp": 0,
    "metadata": {
      "qiyuan_env_action": "RIGHT"
    }
  },
  "next_env_state": {},
  "intervention_config": {},
  "metadata": {}
}
```

## 3. Minimal Action Stream for Qiyuan

Qiyuan does not need to parse the full trace. We can also export one JSONL file
where each line is only the simulator action payload:

```json
{
  "schema_version": "gwt_trace_v1",
  "run_id": "mock-export",
  "timestamp": 0,
  "should_step": true,
  "action": "RIGHT",
  "action_type": "MOVE",
  "direction": "RIGHT",
  "confidence": 0.7,
  "source_module": "motor",
  "source_timestamp": 0
}
```

For no-movement cognitive timesteps:

```json
{
  "schema_version": "gwt_trace_v1",
  "run_id": "mock-export",
  "timestamp": 3,
  "should_step": false,
  "action": null,
  "action_type": "NOOP",
  "direction": null,
  "confidence": 0.6,
  "source_module": "language",
  "source_timestamp": 3
}
```

Qiyuan-side rule:

```python
if record["should_step"]:
    state = env.step(record["action"])
else:
    # no STAY/NOOP exists in the simulator
    # skip env.step(), keep current simulator state
    state = current_state
```

For exact visualization replay, use the full envelope file because it contains
the recorded symbolic map/state at every cognitive cycle. For simulator
execution replay, use the minimal action stream and call Qiyuan `env.step()`.

Default action policy: if the workspace broadcast has no `action_hint`,
`should_step=false`; Qiyuan does not receive an action for that cognitive cycle.
The motor-threshold bypass is optional and should be explicitly enabled for
reflex/ablation runs.

## 4. Action Mapping

| Our `EnvAction` | Qiyuan simulator call |
|---|---|
| `{"action_type": "MOVE", "command": "UP", "should_step": true}` | `env.step("UP")` |
| `{"action_type": "MOVE", "command": "DOWN", "should_step": true}` | `env.step("DOWN")` |
| `{"action_type": "MOVE", "command": "LEFT", "should_step": true}` | `env.step("LEFT")` |
| `{"action_type": "MOVE", "command": "RIGHT", "should_step": true}` | `env.step("RIGHT")` |
| `{"action_type": "PICKUP", "command": "PICKUP", "should_step": true}` | `env.step("PICKUP")` |
| `{"action_type": "NOOP", "command": null, "should_step": false}` | Do not call `env.step()` |

## 4.1 Information-Sharing Boundary

Modules are **not** assumed to share the full same input. The standardized trace
records module-specific inputs so we can audit what each module actually had
access to.

```text
Private information:
  module_input.private_observation
  module_input.private_state

Shared cognitive information:
  module_input.global_broadcast
  module_input.workspace_state
  module_input.task_goal

Experiment-only observability:
  full TraceEnvelope / TraceLogger
```

The logger may be omniscient for analysis, but modules should only consume their
own `ModuleInput`.

Boss-aligned default routing:

```text
perception private_observation = global map / screenshot + symbolic global state
motor private_observation      = nearby obstacles / blocked directions + task state
language private_observation   = current report query or user-pause prompt
language private_state/history = recent language input/output history
module_input.task_goal         = persistent experimenter task instruction
global_broadcast               = previous ignited or maintained workspace content
```

If no proposal ignites and no old content is maintained, the trace may contain a
`no_ignition` placeholder for bookkeeping. That placeholder is not treated as a
real `global_broadcast` for the next cognitive cycle.

## 4.2 Fixed Importance, Ignition, and Action Routes

Each module reply is rescored by a fixed deterministic function. The module does
not get to freely report its own importance:

```json
{
  "importance_function": {
    "bottom_up_salience": 0.32,
    "top_down_relevance": 0.71,
    "salience_weight": 0.55,
    "relevance_weight": 0.45,
    "encoder": "HashingSentenceEncoder"
  }
}
```

Workspace metadata records whether the all-or-none ignition threshold was
crossed:

```json
{
  "workspace": {
    "ignited": true,
    "maintained": false,
    "ignition_threshold": 0.25,
    "strength": 1.0
  }
}
```

If no proposal crosses the threshold, the previous content can be maintained and
decayed:

```json
{
  "workspace": {
    "ignited": false,
    "maintained": true,
    "strength": 0.85,
    "age": 1
  }
}
```

Actions record whether they came from the workspace broadcast or the independent
non-workspace motor threshold:

```json
{
  "env_action": {
    "command": "RIGHT",
    "should_step": true,
    "metadata": {
      "action_route": "non_workspace_motor_threshold",
      "motor_importance": 0.038,
      "motor_execution_threshold": 0.02
    }
  }
}
```

Route meanings:

| `action_route` | Meaning |
|---|---|
| `workspace_broadcast` | The active workspace broadcast carried an explicit simulator action. |
| `non_workspace_motor_threshold` | Optional route: motor exceeded `motor_execution_threshold` even though it did not win workspace ignition. |
| `no_workspace_action` | Default no-action route: the workspace winner had no simulator action hint, so Qiyuan `env.step()` is skipped. |
| `no_action_threshold_not_met` | Optional bypass was enabled, but motor did not cross its execution threshold. |
| `forced_action` | Experiment config overrode normal resolution for intervention/debugging. |

## 5. Code Utilities Already Implemented

- `gwt_agent.core.types.EnvAction`
- `gwt_agent.core.types.ModuleStateSnapshot`
- `gwt_agent.core.types.TraceEnvelope`
- `gwt_agent.core.export.write_action_stream(...)`
- `gwt_agent.core.export.write_envelopes_jsonl(...)`
- `gwt_agent.core.export.replay_actions(...)`
- `gwt_agent.envs.foraging_adapter.ForagingEnvAdapter`
- `scripts/run_qiyuan_integrated.py`
- `scripts/replay_qiyuan_record.py`

## 6. Generate Example Files

```bash
cd /home/yx21e.fsu/AAAI_project/begining_stage
PYTHONPATH=src python3 scripts/export_mock_actions.py
```

This writes:

```text
runs/mock_trace_envelopes.jsonl
runs/mock_action_stream.jsonl
```

`mock_trace_envelopes.jsonl` is the full standardized record.

`mock_action_stream.jsonl` is the minimal file Qiyuan can replay.
