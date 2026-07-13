from __future__ import annotations

from typing import Iterable, List, Optional

from gwt_agent.core.types import ModuleProposal, WorkspaceBroadcast, WorkspaceState


class CentralWorkspace:
    """All-or-none global workspace with decaying maintained content."""

    def __init__(
        self,
        capacity: int = 1,
        ignition_threshold: float = 0.25,
        decay_rate: float = 0.85,
        maintenance_steps: int = 4,
    ) -> None:
        self.state = WorkspaceState(
            capacity=capacity,
            decay_rate=decay_rate,
            maintenance_steps=maintenance_steps,
        )
        self.ignition_threshold = ignition_threshold

    def select_winner(self, proposals: Iterable[ModuleProposal]) -> Optional[ModuleProposal]:
        proposal_list: List[ModuleProposal] = list(proposals)
        if not proposal_list:
            raise ValueError("CentralWorkspace requires at least one proposal.")
        winner = max(
            proposal_list,
            key=lambda proposal: (
                proposal.uptake_score
                if proposal.uptake_score is not None
                else proposal.importance_score,
                proposal.confidence if proposal.confidence is not None else -1.0,
                proposal.module_name,
            ),
        )
        score = winner.uptake_score if winner.uptake_score is not None else winner.importance_score
        if score < self.ignition_threshold:
            return None
        return winner

    def broadcast(
        self,
        timestamp: int,
        winner: Optional[ModuleProposal],
    ) -> WorkspaceBroadcast:
        self.state.cycle_t = timestamp
        if winner is None:
            return self._maintain_or_idle(timestamp)

        score = winner.uptake_score if winner.uptake_score is not None else winner.importance_score
        broadcast = WorkspaceBroadcast(
            timestamp=timestamp,
            winner_module=winner.module_name,
            content=winner.content,
            importance_score=score,
            confidence=winner.confidence,
            action_hint=winner.action_hint,
            metadata={
                **winner.metadata,
                "winner_rationale": winner.rationale,
                "winner_reflection": winner.reflection,
                "workspace": {
                    "ignited": True,
                    "ignition_threshold": self.ignition_threshold,
                    "maintained": False,
                    "strength": 1.0,
                },
            },
        )
        self.state.update(broadcast, strength=1.0)
        return broadcast

    def _maintain_or_idle(self, timestamp: int) -> WorkspaceBroadcast:
        maintained = self.state.decay()
        if maintained is None:
            return WorkspaceBroadcast(
                timestamp=timestamp,
                winner_module="workspace",
                content={"status": "no_ignition", "active_content": None},
                importance_score=0.0,
                confidence=None,
                action_hint=None,
                metadata={
                    "workspace": {
                        "ignited": False,
                        "maintained": False,
                        "ignition_threshold": self.ignition_threshold,
                        "strength": 0.0,
                    }
                },
            )
        return WorkspaceBroadcast(
            timestamp=timestamp,
            winner_module=maintained.winner_module,
            content=maintained.content,
            importance_score=self.state.active_strength,
            confidence=maintained.confidence,
            action_hint=maintained.action_hint,
            metadata={
                **maintained.metadata,
                "workspace": {
                    "ignited": False,
                    "maintained": True,
                    "ignition_threshold": self.ignition_threshold,
                    "strength": self.state.active_strength,
                    "age": self.state.active_age,
                },
            },
        )
