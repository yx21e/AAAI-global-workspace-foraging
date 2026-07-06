from __future__ import annotations

from typing import List, Optional, Tuple

from gwt_agent.core.types import ModuleInput, ModuleProposal
from gwt_agent.modules.base import BaseModule


Position = Tuple[int, int]


class MotorModule(BaseModule):
    """Reference motor module for simple grid movement."""

    def __init__(self) -> None:
        super().__init__("motor")
        self.recent_positions: List[Position] = []
        self.last_goal: Optional[str] = None

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        state = module_input.private_observation or {}
        agent_pos = tuple(state.get("agent_position", (0, 0)))
        carrying = bool(state.get("carrying_resource", False))
        goal = "return_to_base" if carrying else "collect_resource"
        if goal != self.last_goal:
            self.recent_positions = []
            self.last_goal = goal
        target = tuple(state.get("base_position" if carrying else "resource_position", agent_pos))
        nearby_obstacles = {tuple(item) for item in state.get("nearby_obstacles", [])}
        blocked_directions = state.get("blocked_directions", {})
        if not carrying and state.get("resource_position") is not None and agent_pos == target:
            action = "PICKUP"
        else:
            action = self._choose_action(
                agent_pos,
                target,
                nearby_obstacles,
                blocked_directions,
                set(self.recent_positions),
            )
        self._remember_position(agent_pos)

        return ModuleProposal(
            module_name=self.name,
            content={
                "goal": goal,
                "target_position": target,
                "planned_action": action,
                "blocked_directions": blocked_directions,
                "recent_positions": self.recent_positions,
            },
            importance_score=0.65,
            confidence=0.7,
            action_hint=action,
            salience_score=0.55,
            goal_relevance_score=0.85,
            rationale="Move one step toward the current task target while avoiding known hazards.",
        )

    def _choose_action(
        self,
        agent_pos: Position,
        target: Position,
        hazards: set,
        blocked_directions,
        avoid_positions: set,
    ) -> str:
        x, y = agent_pos
        tx, ty = target
        candidates = []
        if tx > x:
            candidates.append(("RIGHT", (x + 1, y)))
        if tx < x:
            candidates.append(("LEFT", (x - 1, y)))
        if ty > y:
            candidates.append(("DOWN", (x, y + 1)))
        if ty < y:
            candidates.append(("UP", (x, y - 1)))
        candidates.extend(
            [
                ("RIGHT", (x + 1, y)),
                ("DOWN", (x, y + 1)),
                ("LEFT", (x - 1, y)),
                ("UP", (x, y - 1)),
            ]
        )

        action = self._first_safe_action(
            candidates,
            hazards,
            blocked_directions,
            avoid_positions,
        )
        return action or "NOOP"

    def _first_safe_action(
        self,
        candidates,
        hazards: set,
        blocked_directions,
        avoid_positions: set,
    ) -> Optional[str]:
        safe_actions = []
        for action, pos in candidates:
            if not blocked_directions.get(action, False) and pos not in hazards:
                safe_actions.append((action, pos))
        for action, pos in safe_actions:
            if pos not in avoid_positions:
                return action
        if safe_actions:
            return safe_actions[0][0]
        return None

    def _remember_position(self, position: Position) -> None:
        self.recent_positions.append(position)
        self.recent_positions = self.recent_positions[-6:]
