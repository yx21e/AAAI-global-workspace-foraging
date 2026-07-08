# Module Selection for Qiyuan Foraging Environment

Date: 2026-06-25

## 1. What Qiyuan's Current Code Actually Provides

Checked repo:

<https://github.com/llll0630/Foraging-Environment-Design>

Current `foraging_env.py` returns this state dict from `reset()` / `step()`:

```python
{
    "agent_pos": (x, y),
    "resource_pos": (x, y) or None,
    "base_pos": (1, 1),
    "carrying": bool,
    "action_success": bool,
    "step_count": int,
    "resources_collected": int,
}
```

Current actions accepted by `step(action)`:

```text
UP, DOWN, LEFT, RIGHT, PICKUP
```

Current code also exposes useful internal attributes through the env object:

```python
env.grid          # 15x15 floor/wall grid
env.grid_size
env.base_pos
env.agent_pos
env.resource_pos
env.carrying
```

Current `render(filename)` can save a full screenshot.

## 2. Important Mismatch Between Docs and Current Code

The interface spec mentions:

- `facing`
- `local_view_radius`
- `state["local_view"]`

But the current GitHub `foraging_env.py` does **not** implement these in
`reset()` / `step()` yet.

Our adapter therefore supports future `local_view`, but for the current code it
derives `wall_positions` and optional local view from `env.grid`.

## 3. Module Candidates

| Candidate module | Keep now? | Directly supported by Qiyuan env? | Why |
|---|---:|---|
| `LLMPerceptionModule` | Yes | Yes | It receives previous broadcast plus global bird's-eye map screenshot and symbolic state such as agent/resource/base coordinates and walls. It is not limited to local view. |
| `LLMMotorModule` | Yes | Yes | It receives previous broadcast plus nearby obstacle state and produces simulator actions: `UP/DOWN/LEFT/RIGHT/PICKUP`. It can act via workspace broadcast or the separate motor threshold route. |
| `LLMLanguageModule` | Yes | No | It receives previous broadcast plus the current experimenter report/query signal, while the persistent experimenter instruction is available as `task_goal`. It acts as the system's outward-facing spokesperson to the experimenter, not to the 2D simulator. |
| `OutcomeMonitorModule` | Optional for feedback/intervention experiments | Yes | Uses `action_success`, `carrying`, `resources_collected`, `step_count`. Not part of the default module set; useful if we explicitly study feedback monitoring, agency, or delayed/mismatched outcome interventions. |
| `EmotionModule` | No | No | Not supported by the current environment fields and not necessary for first-wave GWT pipeline. If needed later, implement as `Value/SalienceEvaluation`, not "emotion". |
| `MemoryModule` | Later | Partly | Useful for map memory or history when local view is limited, but less necessary if full coordinates/grid are available. |
| `VisualScreenshotModule` | No separate module | Partly | Rendered screenshots are now routed into `LLMPerceptionModule`, so a standalone screenshot module would duplicate perception. |

## 4. First-Version Module Set

Recommended first-version module list:

```python
[
    LLMPerceptionModule(),    # multimodal global map screenshot + symbolic perception
    LLMMotorModule(),         # action proposal
    LLMLanguageModule(),      # outward report to the experimenter
]
```

Minimal control-only baseline:

```python
[
    LLMPerceptionModule(),
    LLMMotorModule(),
]
```

Optional feedback/intervention extension:

```python
[
    LLMPerceptionModule(),
    LLMMotorModule(),
    LLMLanguageModule(),
    OutcomeMonitorModule(),   # explicit feedback/agency monitor
]
```

## 5. Information Routing

Modules should not receive identical full information.

Current routing:

- `PerceptionModule` receives:
  - global bird's-eye map/screenshot if available through render/adapter
  - `agent_position`
  - `resource_position`
  - `base_position`
  - `wall_positions`
  - `action_success`
- `MotorModule` receives:
  - `agent_position`
  - `resource_position`
  - `base_position`
  - `carrying_resource`
  - nearby obstacles / blocked directions
  - `action_success`
  - its own short private history of recent positions to avoid immediate
    oscillation around obstacles
- `OutcomeMonitorModule` receives:
  - `action_success`
  - `resources_collected`
  - `carrying_resource`
  - `step_count`
- `LLMLanguageModule` receives:
  - last global broadcast from our own workspace through `global_broadcast`
  - experimenter instruction through `module_input.task_goal`
  - optional report query if we inject one through `env_state.info`
  - a low-pressure idle/report candidate so default cycles do not simply repeat
    the task prompt every timestep

Important: the current Qiyuan environment does not provide language/report/query
fields. `LLMLanguageModule` is still part of our cognitive/report pipeline
because it is the system's spokesperson to the experimenter, not a simulator
control component.

The previous broadcast is a shared input, not part of any module's private
observation. This keeps the information boundary auditable in the JSON trace.

The full state is logged in `TraceEnvelope`, but modules only consume their own
`ModuleInput`.

## 6. Meeting Summary

The module choice should be driven by what the foraging environment actually
exposes and by the experimenter's need to query/report the system. With the
current Qiyuan code, the defensible first set is multimodal/global-map
perception, motor/action, and language report to the experimenter. For a pure
navigation/control baseline, perception + motor is enough. `OutcomeMonitorModule`
is optional feedback/intervention infrastructure, not a required default module.
A literal emotion module is not justified at this stage.
