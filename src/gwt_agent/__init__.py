"""Multi-agent global workspace scaffold for dissociation experiments."""

from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.core.types import (
    EnvironmentState,
    ModuleContext,
    ModuleProposal,
    TraceStep,
    WorkspaceBroadcast,
)

__all__ = [
    "EnvironmentState",
    "ModuleContext",
    "ModuleProposal",
    "TraceStep",
    "WorkspaceBroadcast",
    "WorkspaceRunner",
]
