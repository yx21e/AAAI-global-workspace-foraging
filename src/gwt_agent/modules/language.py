from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


class LanguageReportModule(BaseModule):
    """Reference language/report module for system-level verbal reports."""

    def __init__(self) -> None:
        super().__init__("language_report")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        last = module_input.global_broadcast
        if last is None:
            content = "No prior broadcast is available. I am initializing the task context."
            score = 0.25
        else:
            content = (
                f"Last winning module was {last.winner_module}; "
                f"broadcast content was {last.content}."
            )
            score = 0.35

        return ModuleProposal(
            module_name=self.name,
            content={"verbal_report": content},
            importance_score=score,
            confidence=0.6,
            salience_score=0.2,
            goal_relevance_score=0.35,
            rationale="Generate a report from the previous workspace broadcast.",
            metadata={"report_type": "workspace_summary"},
        )
