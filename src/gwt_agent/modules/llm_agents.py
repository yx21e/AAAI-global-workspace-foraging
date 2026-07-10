from __future__ import annotations

from typing import Optional

from gwt_agent.core.types import ModuleInput, ModuleProposal, to_jsonable
from gwt_agent.llm.client import LLMClient, MockLLMClient, summarize_broadcast
from gwt_agent.modules.base import BaseModule


ALLOWED_ACTIONS = {"UP", "DOWN", "LEFT", "RIGHT", "PICKUP", "NOOP", "WAIT", "STAY", "NONE"}


class LLMModule(BaseModule):
    """Base class for LLM-backed specialized modules."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        client: Optional[LLMClient] = None,
        model: Optional[str] = None,
        supports_images: bool = False,
        allow_action_hint: bool = False,
    ) -> None:
        super().__init__(name)
        self.system_prompt = system_prompt
        self.client = client or MockLLMClient()
        self.model = model
        self.supports_images = supports_images
        self.allow_action_hint = allow_action_hint

    def propose(self, module_input: ModuleInput) -> ModuleProposal:
        image_path = self._image_path(module_input) if self.supports_images else None
        response = self.client.complete_json(
            system_prompt=self.system_prompt,
            user_payload=self._payload(module_input),
            response_schema=proposal_response_schema(),
            image_path=image_path,
            model=self.model,
        )
        content = self._content_from_response(response)
        action_hint = self._action_hint(response, module_input)
        proposal = ModuleProposal(
            module_name=self.name,
            content=content,
            importance_score=0.0,
            confidence=clamp_float(response.get("confidence"), default=0.5),
            action_hint=action_hint,
            rationale=str(response.get("rationale") or ""),
            metadata={
                "llm_agent": {
                    "backend": getattr(self.client, "provider_name", self.client.__class__.__name__),
                    "model": self.model,
                    "supports_images": self.supports_images,
                    "image_path": image_path,
                    "importance_self_report_used": False,
                }
            },
        )
        self._after_propose(module_input, proposal)
        return proposal

    def _payload(self, module_input: ModuleInput) -> dict:
        return {
            "agent_name": self.name,
            "env_t": module_input.env_t,
            "cycle_t": module_input.cycle_t,
            "task_goal": module_input.task_goal,
            "available_actions": module_input.available_actions,
            "private_observation": to_jsonable(module_input.private_observation),
            "last_broadcast": to_jsonable(module_input.global_broadcast),
            "workspace_state": to_jsonable(module_input.workspace_state),
            "output_contract": {
                "importance_score": "Do not provide it; fixed deterministic scorer computes it after your reply.",
                "action_hint": (
                    "Only motor may use UP, DOWN, LEFT, RIGHT, PICKUP, or NOOP. "
                    "Perception and language must return null."
                ),
            },
        }

    def _image_path(self, module_input: ModuleInput) -> Optional[str]:
        private = module_input.private_observation
        if isinstance(private, dict):
            return private.get("global_screenshot")
        return None

    def _content_from_response(self, response: dict) -> dict:
        observations = response.get("observations")
        if not isinstance(observations, list):
            observations = []
        return {
            "summary": str(response.get("summary") or ""),
            "observations": [str(item) for item in observations],
        }

    def _action_hint(self, response: dict, module_input: ModuleInput) -> Optional[str]:
        if not self.allow_action_hint:
            return None
        raw_action = response.get("action_hint")
        if raw_action is None:
            return None
        action = str(raw_action).upper()
        if action not in ALLOWED_ACTIONS:
            return None
        allowed = {item.upper() for item in module_input.available_actions}
        if action in {"WAIT", "STAY", "NONE"}:
            action = "NOOP"
        if allowed and action not in allowed and action != "NOOP":
            return None
        return action

    def _after_propose(
        self,
        module_input: ModuleInput,
        proposal: ModuleProposal,
    ) -> None:
        return None


class LLMPerceptionModule(LLMModule):
    """Multimodal visual center: full map screenshot + global symbolic map."""

    def __init__(
        self,
        *,
        client: Optional[LLMClient] = None,
        model: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="perception",
            client=client,
            model=model,
            supports_images=True,
            allow_action_hint=False,
            system_prompt=(
                "You are the visual/perception center in a global workspace foraging system. "
                "You receive the current full-map screenshot plus symbolic map fields. "
                "Describe salient visual-spatial facts: agent, base, resource, walls, blocked "
                "regions, and any change from the previous broadcast. If the previous broadcast "
                "already came from perception and the map has no meaningful new change, say that "
                "there is no new visual update instead of repeating the same map summary. You must "
                "not issue a simulator action. Return only JSON matching the schema."
            ),
        )


class LLMMotorModule(LLMModule):
    """Motor center: nearby obstacles + previous broadcast -> candidate action."""

    def __init__(
        self,
        *,
        client: Optional[LLMClient] = None,
        model: Optional[str] = None,
    ) -> None:
        self.recent_positions = []
        self.last_goal = None
        super().__init__(
            name="motor",
            client=client,
            model=model,
            supports_images=False,
            allow_action_hint=True,
            system_prompt=(
                "You are the motor center in a global workspace foraging system. "
                "Your private channel is limited to nearby obstacle/blocked-direction "
                "information, current agent position, carry state, and action feedback. "
                "Target locations or desired directions must come from the previous workspace "
                "broadcast, not from private input. Propose one immediate simulator action "
                "from UP, DOWN, LEFT, RIGHT, PICKUP, or NOOP. Never move into a blocked "
                "direction. Use PICKUP only when the broadcast target is the resource and "
                "the current agent position is at that target. If no target/action cue is "
                "available in the broadcast, return NOOP unless a local safety reflex is "
                "needed. Use your recent position history to avoid short oscillations when "
                "another safe step is available. Return only JSON matching the schema."
            ),
        )

    def _payload(self, module_input: ModuleInput) -> dict:
        payload = super()._payload(module_input)
        state = module_input.private_observation or {}
        carrying = bool(state.get("carrying_resource", False)) if isinstance(state, dict) else False
        goal = "return_to_base" if carrying else "collect_resource"
        if goal != self.last_goal:
            self.recent_positions = []
            self.last_goal = goal
        payload["module_private_state"] = {
            "recent_positions": list(self.recent_positions),
            "last_goal": self.last_goal,
        }
        return payload

    def _after_propose(
        self,
        module_input: ModuleInput,
        proposal: ModuleProposal,
    ) -> None:
        state = module_input.private_observation or {}
        if not isinstance(state, dict):
            return
        position = state.get("agent_position")
        if position is None:
            return
        self.recent_positions.append(tuple(position))
        self.recent_positions = self.recent_positions[-8:]


class LLMLanguageModule(LLMModule):
    """Language center: spokesperson to the experimenter, not to the simulator."""

    def __init__(
        self,
        *,
        client: Optional[LLMClient] = None,
        model: Optional[str] = None,
    ) -> None:
        self.input_history = []
        super().__init__(
            name="language",
            client=client,
            model=model,
            supports_images=False,
            allow_action_hint=False,
            system_prompt=(
                "You are the language center in a global workspace foraging system. "
                "By default, you listen to the previous workspace broadcast and your own "
                "recent input history. When pause_requested is true, the experimenter has "
                "paused the run and is speaking directly to you through user_prompt; answer "
                "that prompt using the previous broadcast and history. When report_query is "
                "present, answer outward to the experimenter. Do not send actions to the 2D "
                "simulator. Return only JSON matching the schema."
            ),
        )

    def _payload(self, module_input: ModuleInput) -> dict:
        payload = super()._payload(module_input)
        payload["module_private_state"] = {
            "input_history": list(self.input_history),
        }
        return payload

    def _after_propose(
        self,
        module_input: ModuleInput,
        proposal: ModuleProposal,
    ) -> None:
        private = module_input.private_observation or {}
        if not isinstance(private, dict):
            private = {}
        self.input_history.append(
            {
                "cycle_t": module_input.cycle_t,
                "env_t": module_input.env_t,
                "mode": private.get("interaction_mode"),
                "user_prompt": private.get("user_prompt"),
                "report_query": private.get("report_query"),
                "heard_broadcast": summarize_broadcast(to_jsonable(module_input.global_broadcast)),
                "output_language": proposal.content.get("summary")
                if isinstance(proposal.content, dict)
                else str(proposal.content),
            }
        )
        self.input_history = self.input_history[-8:]


def proposal_response_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "observations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "number"},
            "action_hint": {
                "anyOf": [
                    {
                        "type": "string",
                        "enum": ["UP", "DOWN", "LEFT", "RIGHT", "PICKUP", "NOOP"],
                    },
                    {"type": "null"},
                ]
            },
            "rationale": {"type": "string"},
        },
        "required": [
            "summary",
            "observations",
            "confidence",
            "action_hint",
            "rationale",
        ],
    }


def clamp_float(value, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
