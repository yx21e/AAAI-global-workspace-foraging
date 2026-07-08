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
                route="forced_action",
            )
        if broadcast.action_hint:
            return self._from_command(
                command=broadcast.action_hint,
                broadcast=broadcast,
                source_module=broadcast.winner_module,
                confidence=broadcast.confidence,
                route="workspace_broadcast",
            )

        if self.config.allow_non_workspace_motor_action:
            motor_proposals = [
                proposal
                for proposal in proposal_list
                if proposal.action_hint and proposal.module_name.lower().startswith("motor")
            ]
            if motor_proposals:
                best_motor = max(motor_proposals, key=lambda proposal: proposal.importance_score)
                motor_score = best_motor.uptake_score
                if motor_score is None:
                    motor_score = best_motor.importance_score
                if motor_score >= self.config.motor_execution_threshold:
                    return self._from_command(
                        command=best_motor.action_hint or self.config.no_op_action,
                        broadcast=broadcast,
                        source_module=best_motor.module_name,
                        confidence=best_motor.confidence,
                        route="non_workspace_motor_threshold",
                        route_metadata={
                            "motor_importance": motor_score,
                            "motor_execution_threshold": self.config.motor_execution_threshold,
                            "allow_non_workspace_motor_action": True,
                        },
                    )

            return self._from_command(
                command=self.config.no_op_action,
                broadcast=broadcast,
                source_module=broadcast.winner_module,
                confidence=broadcast.confidence,
                route="no_action_threshold_not_met",
                route_metadata={"allow_non_workspace_motor_action": True},
            )

        return self._from_command(
            command=self.config.no_op_action,
            broadcast=broadcast,
            source_module=broadcast.winner_module,
            confidence=broadcast.confidence,
            route="no_workspace_action",
            route_metadata={"allow_non_workspace_motor_action": False},
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
        route: str,
        route_metadata: Optional[dict] = None,
    ) -> EnvAction:
        normalized = (command or self.config.no_op_action).upper()
        metadata = {
            "action_route": route,
            **(route_metadata or {}),
        }
        if normalized in {"UP", "DOWN", "LEFT", "RIGHT"}:
            return EnvAction(
                action_type="MOVE",
                command=normalized,
                should_step=True,
                direction=normalized,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={**metadata, "qiyuan_env_action": normalized},
            )
        if normalized == "PICKUP":
            return EnvAction(
                action_type="PICKUP",
                command="PICKUP",
                should_step=True,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={**metadata, "qiyuan_env_action": "PICKUP"},
            )
        if normalized in {"NOOP", "WAIT", "STAY", "NONE"}:
            return EnvAction(
                action_type="NOOP",
                command=None,
                should_step=False,
                confidence=confidence,
                source_module=source_module,
                source_timestamp=broadcast.timestamp,
                metadata={**metadata, "qiyuan_env_action": None},
            )
        return EnvAction(
            action_type="INVALID",
            command=normalized,
            should_step=False,
            confidence=confidence,
            source_module=source_module,
            source_timestamp=broadcast.timestamp,
            metadata={
                **metadata,
                "qiyuan_env_action": None,
                "reason": "unsupported_action_for_foraging_env",
            },
        )
