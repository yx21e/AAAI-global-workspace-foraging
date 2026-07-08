from __future__ import annotations

import base64
import importlib.util
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol


JsonDict = Dict[str, Any]


class LLMClientError(RuntimeError):
    """Raised when an LLM backend cannot produce a usable JSON response."""


class LLMClient(Protocol):
    provider_name: str

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: JsonDict,
        response_schema: JsonDict,
        image_path: Optional[str] = None,
        model: Optional[str] = None,
    ) -> JsonDict:
        ...


@dataclass
class MockLLMClient:
    """Deterministic local stand-in that exercises the same LLM module path."""

    provider_name: str = "mock-llm"

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: JsonDict,
        response_schema: JsonDict,
        image_path: Optional[str] = None,
        model: Optional[str] = None,
    ) -> JsonDict:
        agent_name = str(user_payload.get("agent_name", "")).lower()
        if agent_name == "perception":
            return self._perception_response(user_payload, image_path)
        if agent_name == "motor":
            return self._motor_response(user_payload)
        if agent_name == "language":
            return self._language_response(user_payload)
        return {
            "summary": "No specialized mock response is configured.",
            "observations": [],
            "confidence": 0.2,
            "action_hint": None,
            "rationale": "Unknown mock agent.",
        }

    def _perception_response(
        self,
        user_payload: JsonDict,
        image_path: Optional[str],
    ) -> JsonDict:
        state = private_observation(user_payload)
        broadcast = user_payload.get("last_broadcast")
        if isinstance(broadcast, dict) and broadcast.get("winner_module") == "perception":
            return {
                "summary": "No new visual update; the prior map broadcast remains usable.",
                "observations": [
                    f"agent_position={state.get('agent_position')}",
                    f"resource_position={state.get('resource_position')}",
                ],
                "confidence": 0.55,
                "action_hint": None,
                "rationale": "Avoid re-igniting unchanged perceptual content when the prior broadcast already carried it.",
            }
        walls = state.get("wall_positions") or []
        screenshot = image_path or state.get("global_screenshot")
        observations = [
            f"agent_position={state.get('agent_position')}",
            f"resource_position={state.get('resource_position')}",
            f"base_position={state.get('base_position')}",
            f"known_wall_count={len(walls)}",
        ]
        if screenshot:
            observations.append(f"map_screenshot={screenshot}")
        return {
            "summary": (
                "Global map and screenshot are available; the visual center "
                "identifies agent, base, resource, and wall layout."
            ),
            "observations": observations,
            "confidence": 0.72,
            "action_hint": None,
            "rationale": "Perception reports salient visual-spatial state but does not command the simulator.",
        }

    def _motor_response(self, user_payload: JsonDict) -> JsonDict:
        state = private_observation(user_payload)
        broadcast_summary = summarize_broadcast(user_payload.get("last_broadcast"))
        agent_pos = tuple_or_none(state.get("agent_position")) or (0, 0)
        carrying = bool(state.get("carrying_resource", False))
        target_key = "base_position" if carrying else "resource_position"
        target = tuple_or_none(state.get(target_key)) or agent_pos
        blocked = state.get("blocked_directions") or {}
        nearby = {tuple(item) for item in state.get("nearby_obstacles") or []}
        private_state = user_payload.get("module_private_state") or {}
        recent_positions = {
            tuple(item)
            for item in private_state.get("recent_positions", [])
        }

        if not carrying and state.get("resource_position") is not None and agent_pos == target:
            action = "PICKUP"
        else:
            action = choose_greedy_safe_action(
                agent_pos,
                target,
                nearby,
                blocked,
                recent_positions,
            )

        goal = "return_to_base" if carrying else "collect_resource"
        return {
            "summary": (
                f"Using the current workspace broadcast ({broadcast_summary}), "
                f"motor center proposes {action} for {goal}."
            ),
            "observations": [
                f"agent_position={agent_pos}",
                f"target_position={target}",
                f"blocked_directions={blocked}",
            ],
            "confidence": 0.76 if action != "NOOP" else 0.45,
            "action_hint": action,
            "rationale": "Choose the next allowed simulator action using nearby obstacle constraints.",
        }

    def _language_response(self, user_payload: JsonDict) -> JsonDict:
        state = private_observation(user_payload)
        query = state.get("report_query")
        broadcast = user_payload.get("last_broadcast")
        broadcast_summary = summarize_broadcast(broadcast)
        winner = None
        if isinstance(broadcast, dict):
            winner = broadcast.get("winner_module")
        cycle_t = int(user_payload.get("cycle_t") or 0)
        idle_corpus = [
            "No experimenter report is requested in this cycle.",
            "The report channel is standing by while workspace activity continues.",
            "No outward verbal answer is needed right now.",
            "The language center is monitoring the latest broadcast for possible reporting.",
        ]
        if query:
            summary = (
                f"Experimenter query: {query}. Active workspace broadcast is "
                f"{broadcast_summary}. Task goal is {user_payload.get('task_goal')}."
            )
            confidence = 0.82
        elif winner == "language":
            summary = "Idle."
            confidence = 0.25
        else:
            summary = idle_corpus[cycle_t % len(idle_corpus)]
            confidence = 0.45
        observations = [] if summary == "Idle." else [
            f"last_workspace_winner={winner or 'none'}",
            f"broadcast_summary={broadcast_summary}",
        ]
        return {
            "summary": summary,
            "observations": observations,
            "confidence": confidence,
            "action_hint": None,
            "rationale": "Language reports to the experimenter, not to the 2D simulator.",
        }


class OpenAIResponsesClient:
    """OpenAI Responses API backend with optional image input."""

    provider_name = "openai-responses"

    def __init__(
        self,
        *,
        default_model: str = "gpt-5.5",
        max_output_tokens: int = 700,
    ) -> None:
        if importlib.util.find_spec("openai") is None:
            raise LLMClientError(
                "The openai package is not installed. Install requirements-llm.txt "
                "or run with --agent-backend mock-llm."
            )
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMClientError(
                "OPENAI_API_KEY is not set. Set it or run with --agent-backend mock-llm."
            )
        from openai import OpenAI

        self.client = OpenAI()
        self.default_model = default_model
        self.max_output_tokens = max_output_tokens

    @staticmethod
    def available() -> bool:
        return bool(os.getenv("OPENAI_API_KEY")) and importlib.util.find_spec("openai") is not None

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: JsonDict,
        response_schema: JsonDict,
        image_path: Optional[str] = None,
        model: Optional[str] = None,
    ) -> JsonDict:
        content = [
            {
                "type": "input_text",
                "text": json.dumps(user_payload, ensure_ascii=True, sort_keys=True),
            }
        ]
        if image_path:
            content.append(
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(image_path),
                }
            )

        try:
            response = self.client.responses.create(
                model=model or self.default_model,
                input=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "module_proposal",
                        "schema": response_schema,
                        "strict": True,
                    }
                },
                max_output_tokens=self.max_output_tokens,
            )
        except Exception as exc:  # pragma: no cover - requires live OpenAI API.
            raise LLMClientError(f"OpenAI request failed: {exc}") from exc

        text = getattr(response, "output_text", None)
        if not text:
            text = extract_response_text(response)
        try:
            parsed = json.loads(text)
        except Exception as exc:  # pragma: no cover - requires live OpenAI API.
            raise LLMClientError(f"OpenAI response was not valid JSON: {text!r}") from exc
        if not isinstance(parsed, dict):
            raise LLMClientError(f"OpenAI response JSON must be an object, got {type(parsed).__name__}.")
        return parsed


def build_llm_client(
    backend: str,
    *,
    default_model: str = "gpt-5.5",
) -> LLMClient:
    normalized = backend.lower()
    if normalized == "mock-llm":
        return MockLLMClient()
    if normalized == "openai":
        return OpenAIResponsesClient(default_model=default_model)
    if normalized == "auto":
        if OpenAIResponsesClient.available():
            return OpenAIResponsesClient(default_model=default_model)
        return MockLLMClient(provider_name="mock-llm-auto")
    raise ValueError(f"Unsupported LLM backend {backend!r}. Use auto, openai, or mock-llm.")


def private_observation(user_payload: JsonDict) -> JsonDict:
    value = user_payload.get("private_observation") or {}
    return value if isinstance(value, dict) else {}


def tuple_or_none(value) -> Optional[tuple]:
    if value is None:
        return None
    return tuple(value)


def summarize_broadcast(value) -> str:
    if not isinstance(value, dict):
        return "no prior broadcast"
    module = value.get("winner_module") or "unknown"
    content = value.get("content")
    summary = ""
    if isinstance(content, dict):
        summary = str(content.get("summary") or "")
    elif content is not None:
        summary = str(content)
    if len(summary) > 120:
        summary = summary[:117] + "..."
    return f"{module}: {summary}" if summary else str(module)


def choose_greedy_safe_action(
    agent_pos: tuple,
    target: tuple,
    nearby_obstacles: set,
    blocked_directions: JsonDict,
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
    safe = []
    for action, position in candidates:
        if not blocked_directions.get(action, False) and position not in nearby_obstacles:
            safe.append((action, position))
    for action, position in safe:
        if position not in avoid_positions:
            return action
    if safe:
        return safe[0][0]
    return "NOOP"


def image_to_data_url(path: str) -> str:
    image_path = Path(path).expanduser().resolve()
    if not image_path.exists():
        raise LLMClientError(f"Image path does not exist: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_response_text(response) -> str:
    output = getattr(response, "output", None) or []
    chunks = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)
