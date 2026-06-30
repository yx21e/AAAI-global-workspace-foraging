# GWT Pipeline Refinement Notes

Date: 2026-06-25

## 1. Representative Papers to Anchor the Pipeline

| Paper / source | Why it matters for us | Pipeline implication |
|---|---|---|
| Baars, 1988 / 2005, Global Workspace Theory | Foundational GWT: many specialized processors compete for limited conscious access; winning content is globally broadcast. | We need specialized modules + limited-capacity workspace + broadcast, not a generic multi-agent vote. |
| Dehaene, Kerszberg & Changeux, 1998, *A neuronal model of a global workspace in effortful cognitive tasks* | Formal GNW model: distinguishes a global workspace from specialized perceptual, motor, memory, evaluative, attentional processors. | Our module list should follow functional processors: perception, memory, evaluative/affective, attention, motor, report. |
| Mashour, Roelfsema, Changeux & Dehaene, 2020, *Conscious Processing and the Global Neuronal Workspace Hypothesis* | Modern GNW review: conscious access is nonlinear ignition plus recurrent processing that amplifies/sustains a representation for global access. | Workspace should have recurrent state / working memory, not just a one-shot winner object. |
| Butlin et al., 2023, *Consciousness in Artificial Intelligence* | Gives four AI-friendly GWT indicators: parallel modules, limited workspace + attention bottleneck, global broadcast, state-dependent attention. | These should be our compliance checklist. |
| VanRullen & Kanai, 2021, *Deep Learning and the Global Workspace Theory* | AI implementation roadmap: independent specialized latent spaces + shared amodal global latent workspace + attention + broadcast. | We need a shared representation / message format between heterogeneous modules. |
| Goyal et al., 2021/2022, *Coordination Among Neural Modules Through a Shared Global Workspace* | Engineering implementation: bandwidth-limited shared workspace makes specialists compete and supports synchronization. | Competition should be over workspace bandwidth, not merely over action choice. |
| Dossa et al., 2024, *Design and evaluation of a global workspace agent embodied in a realistic multimodal environment* | Embodied GWT agent: working memory is the workspace; previous workspace state is broadcast back into modality encoders. | Broadcast should feed back into module processing at the next cycle. |
| Baars & Franklin / LIDA, 2009-2011 | Computational GWT cognitive cycle: understanding -> consciousness/attention -> action selection. | Our loop should separate cognitive cycle from environment step and action execution. |
| Dehaene / GNW controlled-vs-automatic distinction | Effortful, reportable, or non-routine tasks require workspace-level coordination; routine specialized mappings can remain automatic. | We can add a narrow automatic motor route for reflex-like actions, but should not present it as the main workspace path. |
| Nakanishi et al., 2025, *GWT and dealing with a real-time world* | Recent robotics-oriented GWT: selection-broadcast cycle for dynamic real-time adaptation; modules can operate in parallel/asynchronously. | We should support async/event-driven env input, with a synchronous wrapper only as a first implementation. |

## 2. What Is Wrong With Our Current Pipeline

Current scaffold:

```text
env_state
  -> same ModuleContext to all modules
  -> every module proposes content + score + action_hint
  -> workspace picks max score
  -> action resolver immediately maps winner/proposals to env action
  -> env.step(action)
```

This is runnable, but it is not yet a good GWT pipeline.

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

6. **Language is mixed with control.**
   - Language/report should be one module or output channel.
   - The shared representation layer can be language-like, but it should not become a cognitive "language center" that controls everything.

## 3. Refined Pipeline

Recommended pipeline:

```text
External Environment
  -> EnvironmentAdapter
  -> Sensory/Input Buffers
  -> Specialized Modules process in parallel
       multimodal perception module
       motor/action module
       language/report module
       optional memory module
       optional feedback/outcome monitor
       optional attention/priority module
       self-monitor/metacognition module
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

Not as a cognitive center.

We should separate two things:

1. **Language/report module**
   - A normal specialized module.
   - It receives broadcasts and produces verbal reports to the experimenter.
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
still use symbolic fields for reliability, but the conceptual perception module
should not be limited to a local neighborhood view.

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

This is still future design work in our scaffold. It should be logged clearly so
the trace distinguishes `automatic_route=true` from `workspace_selected=true`.

### Q4. Does the timestep output to simulation need standardization?

Yes. Strongly.

The environment should never receive raw module text or raw workspace content.

It should receive a standardized action command:

```python
EnvAction = {
    "action_type": "MOVE" | "PICKUP" | "DROP" | "WAIT" | "NOOP",
    "direction": "UP" | "DOWN" | "LEFT" | "RIGHT" | None,
    "target": optional,
    "duration": 1,
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
