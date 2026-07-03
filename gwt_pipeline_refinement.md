# GWT Pipeline Refinement Notes

Date: 2026-07-03

## 0. Current Boss-Aligned Pipeline

The current implementation follows the latest meeting prompt:

```text
Qiyuan simulator output
  -> EnvironmentAdapter
  -> InputRouter
       visual center: previous broadcast + global visual map/screenshot
       motor center: previous broadcast + nearby obstacle state
       language center: previous broadcast + experimenter instruction
  -> three module replies
  -> fixed deterministic importance scoring
       salience = embedding-space change in private input vs previous step
       relevance = cosine(reply, task goal + previous broadcast)
       importance = w_salience * salience + w_relevance * relevance
  -> all-or-none workspace ignition
       highest proposal wins only if above ignition_threshold
       otherwise previous content is maintained and decays
  -> global broadcast to visual, motor, and language centers
  -> action execution
       route 1: active broadcast requests action
       route 2: motor importance exceeds separate motor_execution_threshold
  -> standardized EnvAction + trace logging
```

If no proposal crosses the ignition threshold and there is no maintained old
content, the trace records a `no_ignition` placeholder for analysis, but the
placeholder is not rebroadcast as a real input to modules.

The thresholds and weights are experimental hyperparameters:

```text
salience_weight
relevance_weight
ignition_threshold
workspace_decay
workspace_maintenance_steps
motor_execution_threshold
```

The default code uses a deterministic hashing sentence encoder so the scaffold
runs without third-party dependencies. A sentence-transformers encoder can be
plugged into the same interface.

## 1. Representative Papers to Anchor the Pipeline

| Paper / source | Why it matters for us | Pipeline implication |
|---|---|---|
| [Dossa et al., 2024, embodied global workspace agent](https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2024.1352685/full) | Implements and evaluates a GWT-style embodied multimodal agent. | Use modality-specific processors, a workspace/working-memory bottleneck, and broadcast feedback into the next cycle. |
| [Butlin et al., 2025, indicators of consciousness in AI systems](https://www.cell.com/trends/cognitive-sciences/fulltext/S1364-6613%2825%2900286-4) | Gives AI-friendly indicators including parallel modules, limited workspace, global broadcast, and state-dependent attention. | Use this as our compliance checklist for GWT-style implementation. |
| [Nakanishi et al., 2025, GWT and real-time world](https://arxiv.org/abs/2505.13969) | Focuses on the selection-broadcast cycle in dynamic real-time settings. | Keep `env_t` and `cycle_t` separable, even if the first demo is semi-synchronous. |
| [Goyal et al., 2021, shared global workspace](https://arxiv.org/abs/2103.01197) | Engineering version of specialist modules competing for a bandwidth-limited shared workspace. | Competition should be for workspace access, not merely action voting. |
| [VanRullen & Kanai, 2021, deep learning and GWT](https://arxiv.org/abs/2012.10390) | Describes specialized latent spaces connected through an amodal global workspace. | Our JSON/message layer is a practical first substitute for a shared latent representation. |
| [Goldstein & Kirk-Giannini, 2024, language agents and GWT](https://arxiv.org/abs/2410.11407) | Discusses how language-agent architectures can be assessed through GWT conditions. | The language module can be an outward report specialist, but it should not replace the workspace. |

## 2. What Was Wrong With The Old Pipeline

Old scaffold:

```text
env_state
  -> same ModuleContext to all modules
  -> every module proposes content + score + action_hint
  -> workspace picks max score
  -> action resolver immediately maps winner/proposals to env action
  -> env.step(action)
```

This was runnable, but it was not yet a good GWT pipeline.

Main mismatches:

1. **All modules directly receive the raw environment state.**
   - In GWT/GNW, sensory/perceptual processors receive external input first.
   - Other modules mainly receive global broadcast plus their private state.

2. **Competition currently looks like action voting.**
   - In GWT, modules compete for access to a limited-capacity workspace.
   - The winner is a conscious/access-level content, not necessarily an action.

3. **Workspace has no persistent working-memory state.**
   - GNW/Dossa-style implementations treat workspace/working memory as recurrent.
   - Our `WorkspaceBroadcast` is currently only a one-step message.

4. **Attention is collapsed into `importance_score`.**
   - We need bottom-up salience plus top-down/task-dependent attention.
   - This can still be simple, but the abstraction should exist.

5. **Environment step is forced to synchronize with workspace tick.**
   - That is convenient for a grid-world demo, but too rigid theoretically.
   - We should decouple environment time from cognitive-cycle time.

6. **Language was mixed with control.**
   - Language/report should be one module or output channel.
   - The shared representation layer can be language-like, but it should not become a cognitive "language center" that controls everything.

## 3. Refined Pipeline

Current recommended pipeline:

```text
External Environment
  -> EnvironmentAdapter
  -> Sensory/Input Buffers
  -> Specialized Modules process in parallel
       multimodal perception module
       motor/action module
       language/report module
  -> Candidate Coalitions / ModuleProposals
  -> Attention + Uptake Gate
       bottom-up salience
       top-down goal relevance
       current workspace state
       intervention/ablation config
  -> Global Workspace / Working Memory
       limited capacity
       coherent content
       recurrent state
       optional ignition threshold
  -> Global Broadcast
       sent back to all modules
       stored in trace
  -> Action Selection / Effector Layer
       may output action or NOOP
  -> Standardized EnvAction
  -> EnvironmentAdapter.step(action)

Optional automatic route:

```text
Specialized motor/action processor
  -> AutomaticActionGuard
  -> ActionResolver
  -> EnvironmentAdapter.step(action)
```

This route is only for routine, low-conflict, locally decidable actions. It
should not replace workspace competition when the system needs deliberation,
conflict resolution, reporting, or experimenter-visible explanation.
```

Key change:

```text
The workspace does not directly "decide movement."
It selects globally available content.
Action selection is a downstream effect of broadcast.
```

## 4. Answer to the Four Current Questions

### Q1. Should we push over the old pipeline?

Yes, conceptually.

We can keep some code names, but the theoretical pipeline should be rewritten. The key is to integrate existing GWT papers rather than invent our own architecture:

- Baars / GNW gives the core: specialized processors, limited workspace, broadcast.
- Butlin gives AI indicator checklist.
- VanRullen & Kanai gives shared representation / latent-space translation.
- Goyal gives bandwidth-limited specialist coordination.
- Dossa gives embodied recurrent workspace / working memory.
- LIDA gives cognitive cycle with action selection after consciousness/broadcast.

Minimal innovation:

- use LLM-style modules as readable specialist processors;
- use structured messages instead of latent vectors;
- log everything for dissociation/ablation experiments.

This should be treated as the novelty boundary. The selection-broadcast
architecture itself should be presented as inherited from GWT/GNW/LIDA and
recent global-workspace agent papers. See `pipeline_paper_alignment.md` for the
paper-derived vs. project-specific split.

### Q2. Must environment timestep and workspace timestep be synchronous?

No. They should be decoupled in the design.

Recommended distinction:

- `env_t`: external simulation time, changed by `env.step(action)`.
- `cycle_t`: internal cognitive selection-broadcast cycle.

Default implementation for the 2D grid:

```text
For one environment observation:
  run 1..K cognitive cycles
  stop when an action command is committed
  then call env.step(action)
```

This is "semi-synchronous":

- synchronous enough to be easy to debug;
- flexible enough to allow internal cycles without movement;
- ready for async interrupts later.

Why this is better:

- GWT/LIDA treats cognition as repeated sense-attend-act cycles.
- Real-time GWT work argues that external input can intervene at any stage of selection-broadcast, because modules operate in parallel/asynchronously.
- Our system should therefore support async/event-driven input, even if the first 2D demo uses a synchronous wrapper.

### Q3. Do we need an extra language center above Context and below multi-agent?

Not above the modules. In the current boss-aligned version, language is one of
the three specialized modules.

We should separate two things:

1. **Language/report module**
   - A normal specialized module.
   - It receives the previous global broadcast plus experimenter instruction.
   - It produces verbal reports to the experimenter.
   - It is not an action channel to the 2D simulator.
   - It is useful for reportability, confabulation, and self-explanation experiments.

2. **Language/serialization interface**
   - Engineering middleware.
   - It formats `WorkspaceState`, `Broadcast`, and module-private inputs into prompts or structured messages.
   - It is not a GWT module and should not control the system.

Recommended rule:

```text
Language can be a module and a message format,
but it should not be the central workspace itself.
```

So the hierarchy should be:

```text
EnvironmentAdapter
  -> Input/Sensory Buffers
  -> ContextBuilder / MessageCodec  (engineering layer)
  -> Specialized Modules
  -> Attention/Uptake
  -> Global Workspace
  -> Broadcast
  -> Report module speaks to experimenter
  -> Action module / resolver sends EnvAction to simulator
```

### Q3.1 Should perception be local spatial view or global map?

For Qiyuan's current environment, perception should be multimodal and global:

- global bird's-eye map or rendered screenshot, if available through the adapter;
- symbolic state: agent/resource/base coordinates, walls, carrying state;
- optional local view later if Qiyuan implements `local_view_radius`.

This is consistent with embodied/multimodal GWT agents, where modality-specific
encoders feed information into a shared workspace. The first implementation can
still use symbolic fields for reliability, but the default boss-aligned
perception module is not routed a local neighborhood view.

### Q3.2 Can a motor action bypass full workspace competition?

Yes, but only under a narrow "automatic route" interpretation.

GWT/GNW distinguishes effortful/reportable tasks that need global workspace
coordination from automatic specialized processing that can proceed locally. For
our foraging environment, possible automatic-route candidates are:

- agent is already on the resource cell and not carrying -> `PICKUP`;
- agent is carrying and already at base -> no explicit simulator action is
  needed if Qiyuan auto-delivers on arrival;
- a reflex-like invalid-action correction after a simple failed movement.

We should not phrase this as "motor wins without competing." A safer phrasing:

```text
Routine motor schemas may emit an automatic EnvAction when the action is
locally decidable and low-conflict; otherwise candidate contents enter the
attention/workspace route.
```

This is implemented as a separate `motor_execution_threshold`, and it is logged
as `action_route = "non_workspace_motor_threshold"`. It should be treated as a
non-workspace / automatic motor channel, not as a second workspace winner.

### Q4. Does the timestep output to simulation need standardization?

Yes. Strongly.

The environment should never receive raw module text or raw workspace content.

It should receive a standardized action command:

```python
EnvAction = {
    "action_type": "MOVE" | "PICKUP" | "NOOP",
    "direction": "UP" | "DOWN" | "LEFT" | "RIGHT" | None,
    "target": optional,
    "confidence": float,
    "source_cycle_id": int,
    "source_broadcast_id": str,
    "metadata": {...}
}
```

The trace can store rich explanations, but the simulator receives only a valid `EnvAction`.

This also handles the case where the workspace winner is not motor-related:

```text
emotion/report/memory wins -> broadcast occurs -> no motor command -> EnvAction = WAIT or NOOP
```

## 5. Proposed New Types / Interfaces

We should revise the scaffold around these objects:

```python
EnvironmentFrame
  env_t
  raw_observation
  sensory_channels
  available_actions
  reward
  done

CognitiveCycle
  cycle_t
  env_t
  workspace_state_before
  module_private_inputs
  candidate_coalitions
  attention_scores
  selected_content
  workspace_state_after
  broadcast
  action_command

ModuleProposal
  module_name
  content
  salience_score
  goal_relevance_score
  confidence
  requested_workspace_write
  suggested_action
  rationale

WorkspaceState
  contents
  capacity
  active_content_id
  recurrence_memory
  coherence_score

EnvAction
  action_type
  direction
  target
  confidence
  source_broadcast_id
```

## 6. Implementation Consequences

The existing code is a useful scaffold, but should be refactored before building experiments.

Priority changes:

1. Rename/reshape `EnvironmentState` into `EnvironmentFrame`.
2. Add `CognitiveCycle` separate from environment timestep.
3. Replace one shared `ModuleContext` with:
   - `private_input`
   - `last_broadcast`
   - `workspace_state`
   - `task_goal`
   - `experiment_config`
4. Add an `AttentionGate` before `CentralWorkspace`.
5. Make `CentralWorkspace` persistent/recurrent.
6. Replace raw string action with standardized `EnvAction`.
7. Keep `LanguageReportModule`, but add `MessageCodec` as non-cognitive middleware if modules are LLM-based.

Current scaffold status:

- Implemented: module-specific `ModuleInput`.
- Implemented: `InputRouter`.
- Implemented: `AttentionGate`.
- Implemented: persistent `WorkspaceState`.
- Implemented: `env_t` / `cycle_t` fields in trace.
- Implemented: standardized `EnvAction`.
- Still future work: richer async event handling and LLM-specific `MessageCodec`.

## 7. One-Sentence Meeting Version

The new pipeline should treat GWT as a selection-broadcast cognitive cycle: specialized processors operate in parallel, candidate contents compete through attention for a limited recurrent workspace, the selected content is globally broadcast, and only a downstream action-selection layer emits a standardized action to the 2D simulator.
