from __future__ import annotations

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


IDLE_REPORT_CORPUS = [
    "Report channel idle; no external query is pending.",
    "No verbal report requested at this cycle.",
    "Workspace activity is being logged for later inspection.",
    "Standing by for an experimenter-facing report request.",
]

QUERY_REPORT_CORPUS = [
    "Experimenter query received; latest broadcast came from {winner}.",
    "Answering the report query using the current workspace content from {winner}.",
    "The system can report that the active broadcast source is {winner}.",
]


class LanguageReportModule(BaseModule):
    """Reference language/report module for system-level verbal reports."""

    def __init__(self) -> None:
        super().__init__("language_report")

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        instruction = state.get("experimenter_instruction") or module_input.task_goal
        report_query = state.get("report_query")
        last = module_input.global_broadcast
        if report_query:
            template = self._choose_template(QUERY_REPORT_CORPUS, module_input.cycle_t)
            winner = last.winner_module if last else "none"
            content = (
                f"{template.format(winner=winner)} "
                f"Query: {report_query}. "
                f"Broadcast summary: {summarize_content(last.content) if last else 'none'}."
            )
            score = 0.35
        else:
            template = self._choose_template(IDLE_REPORT_CORPUS, module_input.cycle_t)
            content = template
            score = 0.12

        return ModuleProposal(
            module_name=self.name,
            content={
                "verbal_report": content,
                "report_requested": bool(report_query),
                "corpus_item": template,
            },
            importance_score=score,
            confidence=0.6,
            salience_score=0.1 if report_query else 0.02,
            goal_relevance_score=0.35 if report_query else 0.05,
            rationale=(
                "Report workspace broadcast content to the experimenter."
                if report_query
                else "Keep the report channel available without restating the task goal."
            ),
            reflection=(
                f"I am tracking the latest broadcast for the experimenter. "
                f"report_requested={bool(report_query)}; instruction={instruction}; "
                "I should speak outward only when queried or paused, and I should not emit simulator actions."
            ),
            metadata={
                "report_type": "experimenter_spokesperson",
                "experimenter_instruction": instruction,
                "report_query": report_query,
            },
        )

    def _choose_template(self, corpus, cycle_t: int) -> str:
        return corpus[cycle_t % len(corpus)]


def summarize_content(content) -> str:
    if isinstance(content, dict):
        keys = ", ".join(sorted(str(key) for key in content.keys())[:5])
        return f"dict keys: {keys}"
    text = str(content)
    if len(text) > 160:
        return text[:157] + "..."
    return text
