from __future__ import annotations

from abc import ABC, abstractmethod

from gwt_agent.core.types import EnvironmentState


class EnvironmentAdapter(ABC):
    """Interface between the workspace system and any external environment."""

    @abstractmethod
    def reset(self) -> EnvironmentState:
        """Reset the environment and return a unified state."""

    @abstractmethod
    def step(self, action: str) -> EnvironmentState:
        """Apply an action to the environment and return the next state."""
