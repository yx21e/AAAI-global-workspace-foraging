from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


class LanguageReportModule(BaseModule):
    """Reference language/report module for system-level verbal reports."""

    def __init__(self) -> None:
        super().__init__("language_report")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        instruction = state.get("experimenter_instruction") or module_input.task_goal
        last = module_input.global_broadcast
        if last is None:
            content = (
                f"Experimenter instruction: {instruction}. "
                "No prior broadcast is available yet."
            )
            score = 0.25
        else:
            content = (
                f"Experimenter instruction: {instruction}. "
                f"Last broadcast came from {last.winner_module}; "
                f"action hint was {last.action_hint}; "
                f"content summary was {summarize_content(last.content)}."
            )
            score = 0.35

        return ModuleProposal(
            module_name=self.name,
            content={"verbal_report": content},
            importance_score=score,
            confidence=0.6,
            salience_score=0.2,
            goal_relevance_score=0.35,
            rationale="Report workspace broadcast content to the experimenter.",
            metadata={
                "report_type": "experimenter_spokesperson",
                "experimenter_instruction": instruction,
            },
        )


def summarize_content(content) -> str:
    if isinstance(content, dict):
        keys = ", ".join(sorted(str(key) for key in content.keys())[:5])
        return f"dict keys: {keys}"
    text = str(content)
    if len(text) > 160:
        return text[:157] + "..."
    return text
