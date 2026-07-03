from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


class PerceptionModule(BaseModule):
    """Reference multimodal perception module for global map + symbolic state."""

    def __init__(self) -> None:
        super().__init__("perception")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        walls = state.get("wall_positions") or []
        global_visual = state.get("global_visual_observation")
        global_map = state.get("global_map")
        global_screenshot = state.get("global_screenshot")
        resource_pos = state.get("resource_position")
        agent_pos = state.get("agent_position")

        if global_map or global_screenshot or global_visual:
            return ModuleProposal(
                module_name=self.name,
                content={
                    "salient_event": "global_visual_state_available",
                    "agent_position": agent_pos,
                    "resource_position": resource_pos,
                    "global_visual_observation": global_visual,
                    "global_map": global_map,
                    "global_screenshot": global_screenshot,
                    "known_wall_count": len(walls),
                },
                importance_score=0.7,
                confidence=0.8,
                salience_score=0.75,
                goal_relevance_score=0.75,
                rationale="Global visual map and symbolic state are available for multimodal perception.",
            )

        return ModuleProposal(
            module_name=self.name,
            content={
                "salient_event": "global_coordinate_tracking",
                "agent_position": agent_pos,
                "resource_position": resource_pos,
                "known_wall_count": len(walls),
            },
            importance_score=0.45,
            confidence=0.75,
            salience_score=0.45,
            goal_relevance_score=0.6,
            rationale="Use symbolic state when no global visual input is available.",
        )
