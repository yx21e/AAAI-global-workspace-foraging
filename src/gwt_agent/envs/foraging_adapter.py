from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from gwt_agent.core.types import EnvironmentState
from gwt_agent.envs.adapter import EnvironmentAdapter


FORAGING_ACTIONS = ["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"]


class ForagingEnvAdapter(EnvironmentAdapter):
    """Adapter for Qiyuan's ForagingEnv.

    The simulator accepts only UP/DOWN/LEFT/RIGHT/PICKUP strings. Waiting is
    represented on our side by EnvAction.should_step=false, so this adapter's
    step method assumes it receives only valid simulator actions.
    """

    def __init__(
        self,
        env: Any,
        difficulty: int = 1,
        local_view_radius: Optional[int] = None,
        experimenter_instruction: str = "collect_resource_and_return",
    ) -> None:
        self.env = env
        self.difficulty = difficulty
        self.local_view_radius = local_view_radius
        self.experimenter_instruction = experimenter_instruction
        self._last_state: Optional[Dict[str, Any]] = None

    def reset(self) -> EnvironmentState:
        kwargs = {"difficulty": self.difficulty}
        if self.local_view_radius is not None:
            kwargs["local_view_radius"] = self.local_view_radius
        try:
            state = self.env.reset(**kwargs)
        except TypeError:
            state = self.env.reset(difficulty=self.difficulty)
        self._last_state = state
        return self._convert_state(state)

    def step(self, action: str) -> EnvironmentState:
        if action not in FORAGING_ACTIONS:
            raise ValueError(
                f"ForagingEnvAdapter received unsupported action {action!r}. "
                f"Allowed actions: {FORAGING_ACTIONS}"
            )
        state = self.env.step(action)
        self._last_state = state
        return self._convert_state(state)

    def _convert_state(self, state: Dict[str, Any]) -> EnvironmentState:
        wall_positions = self._wall_positions()
        local_view = state.get("local_view")
        if local_view is None and self.local_view_radius is not None:
            local_view = self._local_view(
                center=state.get("agent_pos"),
                radius=self.local_view_radius,
            )
        symbolic = {
            "global_visual_observation": "qiyuan_global_grid_map",
            "global_map": self._global_map(),
            "global_screenshot": state.get("global_screenshot"),
            "agent_position": state.get("agent_pos"),
            "resource_position": state.get("resource_pos"),
            "base_position": state.get("base_pos"),
            "carrying_resource": state.get("carrying"),
            "facing": state.get("facing"),
            "action_success": state.get("action_success"),
            "resources_collected": state.get("resources_collected"),
            "step_count": state.get("step_count"),
            "wall_positions": wall_positions,
            "nearby_obstacles": self._nearby_obstacles(state.get("agent_pos")),
            "blocked_directions": self._blocked_directions(state.get("agent_pos")),
            "grid_size": getattr(self.env, "grid_size", None),
        }
        if local_view is not None:
            symbolic["local_view"] = local_view
        return EnvironmentState(
            timestamp=int(state.get("step_count", 0)),
            observation=state,
            symbolic_state=symbolic,
            available_actions=FORAGING_ACTIONS,
            reward=float(state.get("resources_collected", 0)),
            done=False,
            info={
                "env_name": "qiyuan_foraging",
                "difficulty": self.difficulty,
                "action_success": state.get("action_success"),
                "experimenter_instruction": state.get(
                    "experimenter_instruction",
                    self.experimenter_instruction,
                ),
                "report_query": state.get("report_query"),
            },
        )

    def _wall_positions(self) -> List[Tuple[int, int]]:
        grid = getattr(self.env, "grid", None)
        if grid is None:
            return []
        walls = []
        for y, row in enumerate(grid):
            for x, value in enumerate(row):
                if value == 1:
                    walls.append((x, y))
        return walls

    def _global_map(self):
        grid = getattr(self.env, "grid", None)
        if grid is None:
            return None
        resource = state_tuple(getattr(self.env, "resource_pos", None))
        base = state_tuple(getattr(self.env, "base_pos", None))
        agent = state_tuple(getattr(self.env, "agent_pos", None))
        rendered = []
        for y, row in enumerate(grid):
            rendered_row = []
            for x, value in enumerate(row):
                pos = (x, y)
                if agent is not None and pos == agent:
                    rendered_row.append("AGENT")
                elif resource is not None and pos == resource:
                    rendered_row.append("RESOURCE")
                elif base is not None and pos == base:
                    rendered_row.append("BASE")
                elif value == 1:
                    rendered_row.append("WALL")
                else:
                    rendered_row.append("FLOOR")
            rendered.append(rendered_row)
        return rendered

    def _nearby_obstacles(self, center) -> List[Tuple[int, int]]:
        blocked = self._blocked_positions(center)
        return [position for _, position in blocked]

    def _blocked_directions(self, center) -> Dict[str, bool]:
        blocked = {direction: True for direction, _ in self._blocked_positions(center)}
        return {
            "UP": blocked.get("UP", False),
            "DOWN": blocked.get("DOWN", False),
            "LEFT": blocked.get("LEFT", False),
            "RIGHT": blocked.get("RIGHT", False),
        }

    def _blocked_positions(self, center):
        grid = getattr(self.env, "grid", None)
        if grid is None or center is None:
            return []
        x, y = center
        candidates = {
            "UP": (x, y - 1),
            "DOWN": (x, y + 1),
            "LEFT": (x - 1, y),
            "RIGHT": (x + 1, y),
        }
        blocked = []
        for direction, (nx, ny) in candidates.items():
            if ny < 0 or nx < 0 or ny >= len(grid) or nx >= len(grid[ny]):
                blocked.append((direction, (nx, ny)))
            elif grid[ny][nx] == 1:
                blocked.append((direction, (nx, ny)))
        return blocked

    def _local_view(self, center, radius: int):
        grid = getattr(self.env, "grid", None)
        if grid is None or center is None:
            return None
        ax, ay = center
        resource = state_tuple(getattr(self.env, "resource_pos", None))
        base = state_tuple(getattr(self.env, "base_pos", None))
        view = []
        for y in range(ay - radius, ay + radius + 1):
            row = []
            for x in range(ax - radius, ax + radius + 1):
                if y < 0 or x < 0 or y >= len(grid) or x >= len(grid[y]):
                    row.append("OUT_OF_BOUNDS")
                elif (x, y) == tuple(center):
                    row.append("AGENT")
                elif resource is not None and (x, y) == resource:
                    row.append("RESOURCE")
                elif base is not None and (x, y) == base:
                    row.append("BASE")
                elif grid[y][x] == 1:
                    row.append("WALL")
                else:
                    row.append("FLOOR")
            view.append(row)
        return view


def state_tuple(value):
    if value is None:
        return None
    return tuple(value)
