from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


class PerceptionModule(BaseModule):
    """Reference perception module that summarizes local symbolic state."""

    def __init__(self) -> None:
        super().__init__("perception")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        walls = state.get("wall_positions") or []
        local_view = state.get("local_view")
        resource_pos = state.get("resource_position")
        agent_pos = state.get("agent_position")

        if local_view:
            return ModuleProposal(
                module_name=self.name,
                content={
                    "salient_event": "local_view_available",
                    "agent_position": agent_pos,
                    "local_view": local_view,
                },
                importance_score=0.7,
                confidence=0.8,
                salience_score=0.75,
                goal_relevance_score=0.75,
                rationale="Local visual field is available for spatial navigation.",
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
            rationale="Use coordinate-level state for task-relevant spatial tracking.",
        )
