# Pipeline Paper Alignment Audit

Date: 2026-06-28

## Bottom Line

The current scaffold is mostly aligned with existing Global Workspace /
Global Neuronal Workspace pipelines. It should be presented as an
implementation scaffold that integrates established mechanisms, not as a new
cognitive architecture.

Our intended novelty should stay narrow:

1. adapting an existing selection-broadcast workspace pipeline to Qiyuan's
   2D foraging environment;
2. making the trace/action/report schema explicit enough for replay, ablation, and
   dissociation-style analysis;
3. using lightweight module agents as readable specialist processors.

Everything else should be described as inherited from prior work.

## Alignment Matrix

| Pipeline element | Existing-paper basis | Current implementation status | How we should describe it |
|---|---|---|---|
| Specialized processors/modules | Baars GWT; Dehaene GNW; LIDA | Implemented as `BaseModule` subclasses: multimodal perception, motor, language report, optional outcome monitor | Standard GWT/GNW assumption, not our innovation |
| Limited central workspace | Baars GWT; GNW; Goyal shared workspace | Implemented as `CentralWorkspace(capacity=1)` | Standard bottleneck / workspace access mechanism |
| Competition for access | Baars GWT; LIDA coalitions; Goyal bandwidth-limited specialist competition | Implemented as `AttentionGate` scoring plus `select_winner` | Paper-derived, but our scoring formula is a simple engineering approximation |
| Global broadcast | Baars GWT; GNW; LIDA; Goyal; Dossa | Implemented as `WorkspaceBroadcast`, fed into next-cycle module inputs | Core paper mechanism |
| Recurrent / working-memory workspace state | GNW recurrent ignition; Dossa embodied GWT agent; LIDA cognitive cycle | Implemented as persistent `WorkspaceState.history` / `active_content` | Paper-derived, but current memory is minimal |
| Action selection after broadcast | LIDA cognitive cycle; GWT action selection phase | Implemented as downstream `ActionResolver` after broadcast | Paper-derived separation: workspace content is not automatically an action |
| Automatic / direct action route | GWT/GNW distinction between controlled conscious access and automatic specialized processing | Future design option for reflex-like or overlearned simulator actions such as immediate `PICKUP` when already at the resource | Paper-consistent only if described as automatic local processing, not as a replacement for workspace competition |
| Module-specific information access | GWT/GNW specialized processors; VanRullen & Kanai heterogeneous specialist modules | Implemented in `InputRouter`; modules do not all receive the same raw state | Paper-consistent; exact routing is environment-specific |
| Shared representation / message format | VanRullen & Kanai global latent workspace; Goyal shared workspace | Implemented as structured Python dataclasses / JSON trace | Our engineering adaptation: structured messages instead of learned latent vectors |
| Decoupled env time and cognitive cycle time | LIDA cognitive cycle; real-time selection-broadcast discussions | Implemented as `env_t` and `cycle_t`; runner supports multiple cycles per env step | Paper-consistent design; current runner is still semi-synchronous |
| Embodied environment interface | Dossa embodied GWT agent; robotics / real-time GWT work | Implemented as `EnvironmentAdapter` and `ForagingEnvAdapter` | Paper-consistent embodied-agent wrapper |
| Ablation / intervention hooks | Experimental consciousness-marker work; general causal intervention practice | Implemented as `ExperimentConfig` | Experimental infrastructure, not a new GWT mechanism |
| Replayable trace/action schema | Needed for our collaboration with Qiyuan and dissociation analysis | Implemented as `TraceEnvelope`, `EnvAction`, action JSONL | Project-specific engineering contribution |

## What Is Already Safe To Say In Slides

- "We instantiate an existing Global Workspace style selection-broadcast loop."
- "Specialized modules generate candidate contents; an attention/bottleneck
  stage selects one content for workspace access."
- "The selected content is globally broadcast back to modules."
- "Action is resolved downstream of the broadcast, so the workspace winner need
  not be a motor command."
- "Some routine/reflex-like actions may be handled by an automatic route, but
  conflict, reporting, or deliberation should still use the workspace route."
- "The first simulator implementation is semi-synchronous but records separate
  `env_t` and `cycle_t`."
- "Our main contribution at this stage is the interface/trace scaffold for
  running ablation and replay experiments in the foraging environment."

## What We Should Not Claim Yet

- Do not claim a new theory of consciousness.
- Do not claim biologically faithful neural ignition; the current
  `AttentionGate` is only a lightweight proxy.
- Do not claim full asynchronous real-time GWT; the runner is prepared for
  multiple cognitive cycles, but not yet a fully concurrent runtime.
- Do not claim the module set is universal. It is chosen from Qiyuan's current
  environment fields.
- Do not claim "emotion center" unless we add an evidence-backed
  value/salience module. The current first version does not need it.
- Do not claim the automatic route is a new GWT mechanism. It is our engineering
  realization of the standard controlled-vs-automatic distinction.

## Places Where The Current Scaffold Is Still Simplified

1. `AttentionGate` uses fixed salience / goal relevance / confidence weights.
   This is a minimal proxy for attention and workspace uptake, not a learned or
   biologically detailed attention model.
2. `CentralWorkspace` has an `ignition_threshold` parameter, but true nonlinear
   ignition is not implemented yet.
3. Parallelism is conceptual in the first scaffold. Modules are called
   sequentially in Python, while representing parallel specialist proposals.
4. `WorkspaceState` stores a short active history, not a rich working-memory or
   latent workspace.
5. The structured JSON message layer is our practical substitute for the latent
   spaces used in deep-learning GWT papers.

## Source Anchors

- Baars, Global Workspace Theory: specialized processors, limited workspace,
  competition, global broadcast.
- Dehaene, Kerszberg & Changeux, 1998, GNW model: two computational spaces and
  global access through long-distance workspace connectivity; automatic
  specialized processors can handle routine mappings without workspace-level
  coordination, while effortful tasks require global coordination.
- Mashour, Roelfsema, Changeux & Dehaene, 2020: nonlinear ignition, recurrence,
  sustained globally accessible representation.
- VanRullen & Kanai, 2021: deep-learning route with specialized modules and a
  shared amodal global latent workspace.
- Goyal et al., 2021: shared, bandwidth-limited workspace for neural specialist
  coordination.
- Baars & Franklin / LIDA: cognitive cycle of understanding, consciousness /
  attention, and action selection.
- Dossa et al., 2024: embodied GWT agent using working memory and broadcast
  back into modality encoders.
- Nakanishi et al., 2025: selection-broadcast cycle in dynamic real-time
  settings.

## Current Answer To "Are We Mostly Paper-Based?"

Yes, for the architecture skeleton:

```text
specialized modules
  -> attention / bottleneck competition
  -> limited workspace
  -> global broadcast
  -> downstream action selection
  -> environment interaction
```

But the implementation should be described as a minimal engineering scaffold.
The most project-specific parts are the JSON schema, Qiyuan action/report
contract, module routing from available simulator fields, automatic-route
heuristics, and replay/ablation logging.
