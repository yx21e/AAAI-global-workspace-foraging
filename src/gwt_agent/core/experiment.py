from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from gwt_agent.core.types import JsonDict, ModuleProposal, to_jsonable


@dataclass
class ExperimentConfig:
    """Runtime switches for ablation and intervention experiments."""

    disabled_modules: List[str] = field(default_factory=list)
    score_modifiers: Dict[str, float] = field(default_factory=dict)
    forced_action: Optional[str] = None
    no_op_action: str = "NOOP"
    salience_weight: float = 0.55
    relevance_weight: float = 0.45
    ignition_threshold: float = 0.25
    workspace_decay: float = 0.85
    workspace_maintenance_steps: int = 4
    motor_execution_threshold: float = 0.02
    allow_non_workspace_motor_action: bool = False
    metadata: JsonDict = field(default_factory=dict)

    def is_disabled(self, module_name: str) -> bool:
        return module_name in set(self.disabled_modules)

    def apply_to_proposal(self, proposal: ModuleProposal) -> ModuleProposal:
        factor = self.score_modifiers.get(proposal.module_name, 1.0)
        if factor == 1.0:
            return proposal
        return ModuleProposal(
            module_name=proposal.module_name,
            content=proposal.content,
            importance_score=proposal.importance_score * factor,
            confidence=proposal.confidence,
            action_hint=proposal.action_hint,
            rationale=proposal.rationale,
            salience_score=proposal.salience_score,
            goal_relevance_score=proposal.goal_relevance_score,
            uptake_score=proposal.uptake_score * factor
            if proposal.uptake_score is not None
            else None,
            metadata={**proposal.metadata, "score_modifier": factor},
        )

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)
