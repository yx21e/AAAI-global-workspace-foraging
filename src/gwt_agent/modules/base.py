from __future__ import annotations

from abc import ABC, abstractmethod

from gwt_agent.core.types import ModuleInput, ModuleProposal


class BaseModule(ABC):
    """Base class for specialized modules competing for the workspace."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        """Return this module's candidate content for the current timestamp."""
