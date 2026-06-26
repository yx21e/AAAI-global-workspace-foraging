from __future__ import annotations

from typing import Iterable, List

from gwt_agent.core.types import ModuleProposal, WorkspaceBroadcast, WorkspaceState


class CentralWorkspace:
    """Winner-take-all workspace competition."""

    def __init__(self, capacity: int = 1, ignition_threshold: float = 0.0) -> None:
        self.state = WorkspaceState(capacity=capacity)
        self.ignition_threshold = ignition_threshold

    def select_winner(self, proposals: Iterable[ModuleProposal]) -> ModuleProposal:
        proposal_list: List[ModuleProposal] = list(proposals)
        if not proposal_list:
            raise ValueError("CentralWorkspace requires at least one proposal.")
        return max(
            proposal_list,
            key=lambda proposal: (
                proposal.uptake_score
                if proposal.uptake_score is not None
                else proposal.importance_score,
                proposal.confidence if proposal.confidence is not None else -1.0,
                proposal.module_name,
            ),
        )

    def broadcast(self, timestamp: int, winner: ModuleProposal) -> WorkspaceBroadcast:
        score = winner.uptake_score if winner.uptake_score is not None else winner.importance_score
        broadcast = WorkspaceBroadcast(
            timestamp=timestamp,
            winner_module=winner.module_name,
            content=winner.content,
            importance_score=score,
            confidence=winner.confidence,
            action_hint=winner.action_hint,
            metadata=winner.metadata,
        )
        self.state.cycle_t = timestamp
        self.state.update(broadcast)
        return broadcast
