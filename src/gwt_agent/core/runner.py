from __future__ import annotations

from copy import deepcopy
from typing import Iterable, List, Optional
from uuid import uuid4

from gwt_agent.core.action import ActionResolver
from gwt_agent.core.attention import AttentionGate
from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.router import InputRouter
from gwt_agent.core.types import ModuleStateSnapshot, TraceEnvelope, TraceStep, WorkspaceBroadcast
from gwt_agent.core.workspace import CentralWorkspace
from gwt_agent.envs.adapter import EnvironmentAdapter
from gwt_agent.modules.base import BaseModule


class WorkspaceRunner:
    """Run environment states through modules, workspace competition, and actions."""

    def __init__(
        self,
        env_adapter: EnvironmentAdapter,
        modules: Iterable[BaseModule],
        workspace: Optional[CentralWorkspace] = None,
        experiment: Optional[ExperimentConfig] = None,
        logger: Optional[TraceLogger] = None,
        run_id: Optional[str] = None,
        input_router: Optional[InputRouter] = None,
        attention_gate: Optional[AttentionGate] = None,
        max_cycles_per_env_step: int = 1,
    ) -> None:
        self.env_adapter = env_adapter
        self.modules: List[BaseModule] = list(modules)
        self.experiment = experiment or ExperimentConfig()
        self.workspace = workspace or CentralWorkspace(
            ignition_threshold=self.experiment.ignition_threshold,
            decay_rate=self.experiment.workspace_decay,
            maintenance_steps=self.experiment.workspace_maintenance_steps,
        )
        self.logger = logger or TraceLogger()
        self.action_resolver = ActionResolver(self.experiment)
        self.run_id = run_id or f"run-{uuid4().hex[:8]}"
        self.input_router = input_router or InputRouter()
        self.attention_gate = attention_gate or AttentionGate()
        self.max_cycles_per_env_step = max_cycles_per_env_step
        self.last_broadcast: Optional[WorkspaceBroadcast] = None
        self.previous_private_inputs = {}
        self.shared_memory = {}
        self.cycle_t = 0

    def step(self):
        env_state = getattr(self, "_current_state", None)
        if env_state is None:
            env_state = self.env_adapter.reset()
            self._current_state = env_state

        trace = None
        for _ in range(self.max_cycles_per_env_step):
            trace = self._cognitive_cycle(env_state)
            if trace.env_action and trace.env_action.should_step:
                break
        if trace is None:
            raise RuntimeError("WorkspaceRunner failed to produce a trace.")
        return trace

    def _cognitive_cycle(self, env_state):
        module_inputs = self.input_router.build_inputs(
            modules=self.modules,
            env_state=env_state,
            cycle_t=self.cycle_t,
            workspace_state=self.workspace.state,
            last_broadcast=self.last_broadcast,
            experiment=self.experiment,
        )

        raw_proposals = []
        module_states = []
        for module in self.modules:
            module_input = module_inputs[module.name]
            if self.experiment.is_disabled(module.name):
                module_states.append(
                    ModuleStateSnapshot(
                        module_name=module.name,
                        status="disabled",
                        module_input=module_input,
                    )
                )
                continue
            proposal = module.propose(module_input)
            raw_proposals.append(proposal)
            module_states.append(
                ModuleStateSnapshot(
                    module_name=module.name,
                    status="proposed",
                    proposal=proposal,
                    module_input=module_input,
                )
            )

        proposals = self.attention_gate.score(
            raw_proposals,
            module_inputs=module_inputs,
            previous_private_inputs=self.previous_private_inputs,
            last_broadcast=self.last_broadcast,
            workspace_state=self.workspace.state,
            experiment=self.experiment,
        )
        proposal_by_module = {proposal.module_name: proposal for proposal in proposals}
        for state in module_states:
            if state.module_name in proposal_by_module:
                state.proposal = proposal_by_module[state.module_name]

        winner = self.workspace.select_winner(proposals)
        broadcast = self.workspace.broadcast(self.cycle_t, winner)
        env_action = self.action_resolver.resolve(broadcast, proposals)
        next_state = self.env_adapter.step(env_action.command) if env_action.should_step else env_state

        trace = TraceStep(
            timestamp=self.cycle_t,
            env_t=env_state.timestamp,
            cycle_t=self.cycle_t,
            env_state=env_state,
            proposals=proposals,
            broadcast=broadcast,
            selected_action=env_action.command,
            env_action=env_action,
            module_states=module_states,
            workspace_state=deepcopy(self.workspace.state),
            next_env_state=next_state,
            intervention_config=self.experiment.to_dict(),
        )
        self.logger.log(trace)

        self.last_broadcast = self._broadcast_signal_for_next_cycle(broadcast)
        self.previous_private_inputs = {
            name: deepcopy(module_input.private_observation)
            for name, module_input in module_inputs.items()
        }
        self._current_state = next_state
        self.cycle_t += 1
        return trace

    def _broadcast_signal_for_next_cycle(
        self,
        broadcast: WorkspaceBroadcast,
    ) -> Optional[WorkspaceBroadcast]:
        workspace_metadata = broadcast.metadata.get("workspace", {})
        if workspace_metadata.get("ignited") or workspace_metadata.get("maintained"):
            return broadcast
        return None

    def step_envelope(self) -> TraceEnvelope:
        trace = self.step()
        if trace.env_action is None:
            raise ValueError("TraceStep did not include env_action.")
        return TraceEnvelope(
            schema_version="gwt_trace_v1",
            run_id=self.run_id,
            timestamp=trace.timestamp,
            env_t=trace.env_t,
            cycle_t=trace.cycle_t,
            env_state=trace.env_state,
            module_states=trace.module_states,
            workspace_state=trace.workspace_state,
            workspace_broadcast=trace.broadcast,
            env_action=trace.env_action,
            next_env_state=trace.next_env_state,
            intervention_config=trace.intervention_config,
            metadata={"selected_action": trace.selected_action},
        )

    def run(self, num_steps: int) -> List[TraceStep]:
        traces = []
        for _ in range(num_steps):
            trace = self.step()
            traces.append(trace)
            if trace.next_env_state and trace.next_env_state.done:
                break
        return traces
