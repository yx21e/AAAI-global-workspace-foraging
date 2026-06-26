from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.types import ModuleProposal, WorkspaceState


@dataclass
class AttentionWeights:
    salience: float = 0.55
    goal_relevance: float = 0.35
    confidence: float = 0.10


class AttentionGate:
    """Compute uptake scores before workspace competition."""

    def __init__(self, weights: Optional[AttentionWeights] = None) -> None:
        self.weights = weights or AttentionWeights()

    def score(
        self,
        proposals: Iterable[ModuleProposal],
        workspace_state: WorkspaceState,
        experiment: ExperimentConfig,
    ) -> List[ModuleProposal]:
        scored = []
        for proposal in proposals:
            salience = proposal.salience_score
            if salience is None:
                salience = proposal.importance_score
            relevance = proposal.goal_relevance_score
            if relevance is None:
                relevance = proposal.importance_score
            confidence = proposal.confidence if proposal.confidence is not None else 0.0
            recurrence_bonus = self._recurrence_bonus(proposal, workspace_state)
            uptake = (
                self.weights.salience * salience
                + self.weights.goal_relevance * relevance
                + self.weights.confidence * confidence
                + recurrence_bonus
            )
            scored.append(
                ModuleProposal(
                    module_name=proposal.module_name,
                    content=proposal.content,
                    importance_score=uptake,
                    confidence=proposal.confidence,
                    action_hint=proposal.action_hint,
                    rationale=proposal.rationale,
                    salience_score=salience,
                    goal_relevance_score=relevance,
                    uptake_score=uptake,
                    metadata={
                        **proposal.metadata,
                        "attention_gate": {
                            "salience": salience,
                            "goal_relevance": relevance,
                            "confidence": confidence,
                            "recurrence_bonus": recurrence_bonus,
                        },
                    },
                )
            )
        return [experiment.apply_to_proposal(item) for item in scored]

    def _recurrence_bonus(
        self,
        proposal: ModuleProposal,
        workspace_state: WorkspaceState,
    ) -> float:
        active = workspace_state.active_content
        if active is None:
            return 0.0
        if active.winner_module == proposal.module_name:
            return 0.03
        return 0.0
