"""Reference and LLM-backed modules for the global workspace scaffold."""

from gwt_agent.modules.llm_agents import (
    LLMLanguageModule,
    LLMMotorModule,
    LLMModule,
    LLMPerceptionModule,
)
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.perception import PerceptionModule

__all__ = [
    "LLMModule",
    "LLMPerceptionModule",
    "LLMMotorModule",
    "LLMLanguageModule",
    "PerceptionModule",
    "MotorModule",
    "LanguageReportModule",
]
