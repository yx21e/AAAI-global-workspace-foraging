from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from gwt_agent.core.types import EnvironmentState
from gwt_agent.envs.adapter import EnvironmentAdapter


Position = Tuple[int, int]


@dataclass
class MockGridConfig:
    width: int = 5
    height: int = 5
    base_position: Position = (0, 0)
    resource_position: Position = (4, 4)
    hazard_positions: Tuple[Position, ...] = ((2, 2),)
    max_steps: int = 30


class MockGridAdapter(EnvironmentAdapter):
    """Small deterministic grid used only to validate the workspace interface."""

    def __init__(self, config: MockGridConfig = MockGridConfig()) -> None:
        self.config = config
        self.timestamp = 0
        self.agent_position = config.base_position
        self.carrying_resource = False
        self.done = False
        self.resources_collected = 0

    def reset(self) -> EnvironmentState:
        self.timestamp = 0
        self.agent_position = self.config.base_position
        self.carrying_resource = False
        self.done = False
        self.resources_collected = 0
        return self._state(reward=0.0)

    def step(self, action: str) -> EnvironmentState:
        if self.done:
            return self._state(reward=0.0)

        self.timestamp += 1
        next_pos = self._move(self.agent_position, action)
        reward = -0.01

        if next_pos in self.config.hazard_positions:
            reward -= 0.2
        else:
            self.agent_position = next_pos

        if self.agent_position == self.config.resource_position and not self.carrying_resource:
            self.carrying_resource = True
            reward += 0.5

        if self.agent_position == self.config.base_position and self.carrying_resource:
            self.done = True
            self.resources_collected += 1
            reward += 1.0

        if self.timestamp >= self.config.max_steps:
            self.done = True

        return self._state(reward=reward)

    def _move(self, position: Position, action: str) -> Position:
        x, y = position
        deltas: Dict[str, Position] = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0),
            "NOOP": (0, 0),
        }
        dx, dy = deltas.get(action, (0, 0))
        nx = min(max(x + dx, 0), self.config.width - 1)
        ny = min(max(y + dy, 0), self.config.height - 1)
        return (nx, ny)

    def _state(self, reward: float) -> EnvironmentState:
        symbolic = {
            "agent_position": self.agent_position,
            "base_position": self.config.base_position,
            "resource_position": self.config.resource_position,
            "hazard_positions": list(self.config.hazard_positions),
            "hazards_nearby": self._nearby_hazards(),
            "carrying_resource": self.carrying_resource,
            "action_success": reward >= -0.01,
            "step_count": self.timestamp,
            "resources_collected": self.resources_collected,
            "wall_positions": list(self.config.hazard_positions),
            "nearby_obstacles": self._nearby_hazards(),
            "blocked_directions": self._blocked_directions(),
            "grid_size": self.config.width,
            "global_map": self._global_map(),
            "global_visual_observation": "mock_global_grid_map",
        }
        return EnvironmentState(
            timestamp=self.timestamp,
            observation=symbolic,
            symbolic_state=symbolic,
            available_actions=["UP", "DOWN", "LEFT", "RIGHT", "PICKUP", "NOOP"],
            reward=reward,
            done=self.done,
            info={
                "env_name": "mock_grid",
                "experimenter_instruction": "collect_resource_and_return",
            },
        )

    def _nearby_hazards(self) -> List[Position]:
        x, y = self.agent_position
        hazards = []
        for hx, hy in self.config.hazard_positions:
            if abs(hx - x) + abs(hy - y) <= 1:
                hazards.append((hx, hy))
        return hazards

    def _blocked_directions(self) -> Dict[str, bool]:
        x, y = self.agent_position
        checks = {
            "UP": (x, y - 1),
            "DOWN": (x, y + 1),
            "LEFT": (x - 1, y),
            "RIGHT": (x + 1, y),
        }
        return {
            action: (
                pos in self.config.hazard_positions
                or pos[0] < 0
                or pos[1] < 0
                or pos[0] >= self.config.width
                or pos[1] >= self.config.height
            )
            for action, pos in checks.items()
        }

    def _global_map(self) -> List[List[str]]:
        grid = [["FLOOR" for _ in range(self.config.width)] for _ in range(self.config.height)]
        for x, y in self.config.hazard_positions:
            grid[y][x] = "WALL"
        bx, by = self.config.base_position
        rx, ry = self.config.resource_position
        ax, ay = self.agent_position
        grid[by][bx] = "BASE"
        grid[ry][rx] = "RESOURCE"
        grid[ay][ax] = "AGENT"
        return grid
