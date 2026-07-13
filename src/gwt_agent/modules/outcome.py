from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


class OutcomeMonitorModule(BaseModule):
    """Monitor action feedback and task progress from the environment."""

    def __init__(self) -> None:
        super().__init__("outcome_monitor")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        action_success = state.get("action_success")
        collected = state.get("resources_collected")
        carrying = state.get("carrying_resource")

        if action_success is False:
            return ModuleProposal(
                module_name=self.name,
                content={
                    "outcome": "last_action_failed",
                    "action_success": action_success,
                    "resources_collected": collected,
                },
                importance_score=0.8,
                confidence=0.9,
                salience_score=0.85,
                goal_relevance_score=0.75,
                rationale="Failed action should be globally available for replanning and self-monitoring.",
                reflection=(
                    "The last environment action failed. This likely matters for replanning, "
                    "so I should broadcast failure feedback rather than propose a movement."
                ),
            )

        return ModuleProposal(
            module_name=self.name,
            content={
                "outcome": "task_progress",
                "action_success": action_success,
                "resources_collected": collected,
                "carrying_resource": carrying,
            },
            importance_score=0.35,
            confidence=0.8,
            salience_score=0.3,
            goal_relevance_score=0.55,
            rationale="Track progress feedback without forcing an action.",
            reflection=(
                f"Task progress is resources_collected={collected}, carrying_resource={carrying}, "
                f"last_action_success={action_success}. I should monitor outcome changes, not command the simulator."
            ),
        )
