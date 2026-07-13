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
            recurrence_bonus = self._recurrence_bonus(proposal, workspace_state, experiment)
            workspace_adjustment = self._workspace_adjustment(
                proposal=proposal,
                module_input=module_input,
                last_broadcast=last_broadcast,
            )
            uptake = (importance.importance + recurrence_bonus) * workspace_adjustment
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
                            "workspace_adjustment": workspace_adjustment,
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
        experiment: ExperimentConfig,
    ) -> float:
        active = workspace_state.active_content
        if active is None:
            return 0.0
        if active.winner_module == proposal.module_name:
            return experiment.workspace_recurrence_bonus
        return 0.0

    def _workspace_adjustment(
        self,
        *,
        proposal: ModuleProposal,
        module_input: ModuleInput,
        last_broadcast: Optional[WorkspaceBroadcast],
    ) -> float:
        policy = str(module_input.experiment.get("workspace_adjustment_policy", "none")).lower()
        if policy in {"", "none", "off", "false"}:
            return 1.0
        if policy != "anti_echo":
            return 1.0
        lower_name = proposal.module_name.lower()
        action_hint = (proposal.action_hint or "").upper()
        if lower_name.startswith("motor") and action_hint in {"NOOP", "WAIT", "STAY", "NONE"}:
            return 0.35
        if (
            lower_name.startswith("motor")
            and last_broadcast is not None
            and str(last_broadcast.winner_module).lower().startswith("motor")
        ):
            return 0.55
        if "language" in lower_name or "report" in lower_name:
            private = module_input.private_observation
            if isinstance(private, dict) and not private.get("pause_requested") and not private.get("report_query"):
                return 0.55
        return 1.0
