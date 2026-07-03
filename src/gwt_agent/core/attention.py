from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.importance import DeterministicImportanceScorer, ImportanceWeights
from gwt_agent.core.types import ModuleInput, ModuleProposal, WorkspaceBroadcast, WorkspaceState


class AttentionGate:
    """Compute fixed importance scores before workspace competition."""

    def __init__(self, scorer: Optional[DeterministicImportanceScorer] = None) -> None:
        self.scorer = scorer or DeterministicImportanceScorer()

    def score(
        self,
        proposals: Iterable[ModuleProposal],
        module_inputs: Dict[str, ModuleInput],
        previous_private_inputs: Dict[str, object],
        last_broadcast: Optional[WorkspaceBroadcast],
        workspace_state: WorkspaceState,
        experiment: ExperimentConfig,
    ) -> List[ModuleProposal]:
        self.scorer.weights = ImportanceWeights(
            salience=experiment.salience_weight,
            relevance=experiment.relevance_weight,
        )
        scored = []
        for proposal in proposals:
            module_input = module_inputs[proposal.module_name]
            importance = self.scorer.score(
                proposal=proposal,
                module_input=module_input,
                previous_private_input=previous_private_inputs.get(proposal.module_name),
                last_broadcast=last_broadcast,
            )
            recurrence_bonus = self._recurrence_bonus(proposal, workspace_state)
            uptake = importance.importance + recurrence_bonus
            scored.append(
                ModuleProposal(
                    module_name=proposal.module_name,
                    content=proposal.content,
                    importance_score=uptake,
                    confidence=proposal.confidence,
                    action_hint=proposal.action_hint,
                    rationale=proposal.rationale,
                    salience_score=importance.salience,
                    goal_relevance_score=importance.relevance,
                    uptake_score=uptake,
                    metadata={
                        **proposal.metadata,
                        "importance_function": {
                            "bottom_up_salience": importance.salience,
                            "top_down_relevance": importance.relevance,
                            "salience_weight": experiment.salience_weight,
                            "relevance_weight": experiment.relevance_weight,
                            "recurrence_bonus": recurrence_bonus,
                            "encoder": self.scorer.encoder.__class__.__name__,
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
