from __future__ import annotations

from typing import Iterable, Optional

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.types import EnvAction, ModuleProposal, WorkspaceBroadcast


class ActionResolver:
    """Map workspace content into an environment action."""

    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config

    def resolve(
        self,
        broadcast: WorkspaceBroadcast,
        proposals: Iterable[ModuleProposal],
    ) -> EnvAction:
        proposal_list = list(proposals)
        if self.config.forced_action:
            return self._from_command(
                command=self.config.forced_action,
                broadcast=broadcast,
                source_module="experiment_config",
                confidence=broadcast.confidence,
            )
        if broadcast.action_hint:
            return self._from_command(
                command=broadcast.action_hint,
                broadcast=broadcast,
                source_module=broadcast.winner_module,
                confidence=broadcast.confidence,
            )

        motor_proposals = [
            proposal
            for proposal in proposal_list
            if proposal.action_hint and proposal.module_name.lower().startswith("motor")
        ]
        if motor_proposals:
            best_motor = max(motor_proposals, key=lambda proposal: proposal.importance_score)
            return self._from_command(
                command=best_motor.action_hint or self.config.no_op_action,
                broadcast=broadcast,
                source_module=best_motor.module_name,
                confidence=best_motor.confidence,
            )

        fallback = self._fallback_from_any_action_hint(proposal_list)
        return self._from_command(
            command=fallback or self.config.no_op_action,
            broadcast=broadcast,
            source_module=broadcast.winner_module,
            confidence=broadcast.confidence,
        )

    def _fallback_from_any_action_hint(
        self,
        proposals: Iterable[ModuleProposal],
    ) -> Optional[str]:
        action_proposals = [proposal for proposal in proposals if proposal.action_hint]
        if not action_proposals:
            return None
        best = max(action_proposals, key=lambda proposal: proposal.importance_score)
        return best.action_hint

    def _from_command(
        self,
        command: Optional[str],
        broadcast: WorkspaceBroadcast,
        source_module: Optional[str],
        confidence: Optional[float],
    ) -> EnvAction:
        normalized = (command or self.config.no_op_action).upper()
        if normalized in {"UP", "DOWN", "LEFT", "RIGHT"}:
            return EnvAction(
                action_type="MOVE",
                command=normalized,
                should_step=True,
                direction=normalized,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={"qiyuan_env_action": normalized},
            )
        if normalized == "PICKUP":
            return EnvAction(
                action_type="PICKUP",
                command="PICKUP",
                should_step=True,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={"qiyuan_env_action": "PICKUP"},
            )
        if normalized in {"NOOP", "WAIT", "STAY", "NONE"}:
            return EnvAction(
                action_type="NOOP",
                command=None,
                should_step=False,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={"qiyuan_env_action": None},
            )
        return EnvAction(
            action_type="INVALID",
            command=normalized,
            should_step=False,
            confidence=confidence,
            source_module=source_module,
            source_timestamp=broadcast.timestamp,
            metadata={
                "qiyuan_env_action": None,
                "reason": "unsupported_action_for_foraging_env",
            },
        )
