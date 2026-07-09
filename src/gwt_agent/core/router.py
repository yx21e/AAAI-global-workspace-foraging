from __future__ import annotations

from copy import deepcopy
from typing import Dict, Iterable, Optional

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.types import (
    EnvironmentState,
    ModuleInput,
    WorkspaceBroadcast,
    WorkspaceState,
)
from gwt_agent.modules.base import BaseModule


class InputRouter:
    """Build module-specific inputs instead of sharing one full context."""

    def __init__(self, task_goal: str = "collect_resource_and_return") -> None:
        self.task_goal = task_goal

    def build_inputs(
        self,
        modules: Iterable[BaseModule],
        env_state: EnvironmentState,
        cycle_t: int,
        workspace_state: WorkspaceState,
        last_broadcast: Optional[WorkspaceBroadcast],
        experiment: ExperimentConfig,
    ) -> Dict[str, ModuleInput]:
        return {
            module.name: self._build_for_module(
                module_name=module.name,
                env_state=env_state,
                cycle_t=cycle_t,
                workspace_state=workspace_state,
                last_broadcast=last_broadcast,
                experiment=experiment,
            )
            for module in modules
        }

    def _build_for_module(
        self,
        module_name: str,
        env_state: EnvironmentState,
        cycle_t: int,
        workspace_state: WorkspaceState,
        last_broadcast: Optional[WorkspaceBroadcast],
        experiment: ExperimentConfig,
    ) -> ModuleInput:
        private_observation = self._private_observation(
            module_name,
            env_state,
            last_broadcast,
        )
        return ModuleInput(
            module_name=module_name,
            env_t=env_state.timestamp,
            cycle_t=cycle_t,
            private_observation=private_observation,
            global_broadcast=last_broadcast,
            workspace_state=deepcopy(workspace_state),
            task_goal=self._task_goal(env_state),
            available_actions=env_state.available_actions,
            experiment=experiment.to_dict(),
            metadata={
                "env_timestamp": env_state.timestamp,
                "routing_policy": self._routing_policy_name(module_name),
            },
        )

    def _task_goal(self, env_state: EnvironmentState) -> str:
        return env_state.info.get("experimenter_instruction", self.task_goal)

    def _private_observation(
        self,
        module_name: str,
        env_state: EnvironmentState,
        last_broadcast: Optional[WorkspaceBroadcast],
    ):
        state = env_state.symbolic_state
        lower_name = module_name.lower()
        if lower_name.startswith("perception"):
            return {
                "global_visual_observation": state.get("global_visual_observation"),
                "global_map": state.get("global_map"),
                "global_screenshot": state.get("global_screenshot"),
                "agent_position": state.get("agent_position"),
                "resource_position": state.get("resource_position"),
                "base_position": state.get("base_position"),
                "wall_positions": state.get("wall_positions", state.get("hazard_positions")),
                "action_success": state.get("action_success"),
                "grid_size": state.get("grid_size"),
            }
        if lower_name.startswith("motor"):
            return {
                "agent_position": state.get("agent_position"),
                "resource_position": state.get("resource_position"),
                "base_position": state.get("base_position"),
                "carrying_resource": state.get("carrying_resource"),
                "nearby_obstacles": state.get("nearby_obstacles", state.get("hazards_nearby")),
                "blocked_directions": state.get("blocked_directions", {}),
                "action_success": state.get("action_success"),
            }
        if "outcome" in lower_name or "monitor" in lower_name:
            return {
                "action_success": state.get("action_success"),
                "resources_collected": state.get("resources_collected"),
                "carrying_resource": state.get("carrying_resource"),
                "step_count": state.get("step_count"),
            }
        if "language" in lower_name or "report" in lower_name:
            pause_requested = bool(env_state.info.get("language_pause_requested"))
            user_prompt = env_state.info.get("language_user_prompt")
            report_query = env_state.info.get("report_query")
            return {
                "interaction_mode": (
                    "user_pause"
                    if pause_requested
                    else "report_query"
                    if report_query
                    else "broadcast_listening"
                ),
                "pause_requested": pause_requested,
                "user_prompt": user_prompt,
                "report_query": report_query,
                "report_query_active": bool(report_query),
            }
        return {
            "task_goal": self.task_goal,
            "broadcast_available": env_state.info.get("broadcast_available", True),
        }

    def _routing_policy_name(self, module_name: str) -> str:
        lower_name = module_name.lower()
        if lower_name.startswith("perception"):
            return "global_visual_private_input"
        if lower_name.startswith("motor"):
            return "nearby_obstacle_private_input"
        if "outcome" in lower_name or "monitor" in lower_name:
            return "outcome_feedback_input"
        if "language" in lower_name or "report" in lower_name:
            return "broadcast_plus_language_event_input"
        return "broadcast_plus_private_state"


def last_broadcast_to_dict(value):
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value
