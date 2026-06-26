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

| Candidate module | Keep now? | Why |
|---|---:|---|
| `PerceptionModule` | Yes, but redefine | It should parse spatial state: agent/resource/base coordinates, wall grid, optional local view. It is not a true image vision module yet unless screenshots are explicitly used. |
| `MotorModule` | Yes | It is the only module that produces simulator actions: `UP/DOWN/LEFT/RIGHT/PICKUP`. Qiyuan's env needs this output. |
| `OutcomeMonitorModule` | Yes | Uses `action_success`, `carrying`, `resources_collected`, `step_count`. Needed for feedback, self-monitoring, replay, and later confabulation/agency tests. |
| `LanguageReportModule` | Optional / experimental | Not needed for basic navigation, but needed if we want reportability, blindsight-like behavior, confabulation, or explanation traces. |
| `EmotionModule` | No | Not supported by the current environment fields and not necessary for first-wave GWT pipeline. If needed later, implement as `Value/SalienceEvaluation`, not "emotion". |
| `MemoryModule` | Later | Useful for map memory or history when local view is limited, but less necessary if full coordinates/grid are available. |
| `VisualScreenshotModule` | Later | Only useful if we decide to feed rendered screenshots to a vision model. Current state dict is already symbolic. |

## 4. First-Version Module Set

Recommended first-version module list:

```python
[
    PerceptionModule(),       # spatial/symbolic perception
    MotorModule(),            # action proposal
    OutcomeMonitorModule(),   # feedback/self-monitoring
    LanguageReportModule(),   # optional report/explanation channel
]
```

If the meeting wants the minimal control-only set:

```python
[
    PerceptionModule(),
    MotorModule(),
    OutcomeMonitorModule(),
]
```

## 5. Information Routing

Modules should not receive identical full information.

Current routing:

- `PerceptionModule` receives:
  - `agent_position`
  - `resource_position`
  - `base_position`
  - `wall_positions`
  - optional `local_view`
  - `action_success`
- `MotorModule` receives:
  - `agent_position`
  - `resource_position`
  - `base_position`
  - `carrying_resource`
  - `wall_positions`
  - `action_success`
- `OutcomeMonitorModule` receives:
  - `action_success`
  - `resources_collected`
  - `carrying_resource`
  - `step_count`
- `LanguageReportModule` receives:
  - last global broadcast
  - optional report query
  - action success

The full state is logged in `TraceEnvelope`, but modules only consume their own
`ModuleInput`.

## 6. Meeting Summary

The module choice should be driven by what the foraging environment actually
exposes. With the current Qiyuan code, the defensible first set is spatial
perception, motor/action, outcome monitoring, and optional language/report. A
literal emotion module is not justified at this stage.

