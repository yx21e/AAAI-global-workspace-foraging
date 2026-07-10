from __future__ import annotations

import base64
import importlib.util
import json
import mimetypes
import os
import re
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
        agent = state.get("agent_position")
        resource = state.get("resource_position")
        base = state.get("base_position")
        return {
            "summary": (
                f"Visual map update: agent at {agent}, resource at {resource}, "
                f"base at {base}, with {len(walls)} known walls."
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
        broadcast_positions = extract_positions_from_broadcast(user_payload.get("last_broadcast"))
        target_key = "base_position" if carrying else "resource_position"
        target = tuple_or_none(broadcast_positions.get(target_key))
        blocked = state.get("blocked_directions") or {}
        nearby = {tuple(item) for item in state.get("nearby_obstacles") or []}
        private_state = user_payload.get("module_private_state") or {}
        recent_positions = {
            tuple(item)
            for item in private_state.get("recent_positions", [])
        }

        target_text = str(target) if target is not None else "no broadcast target"
        if target is None:
            action = "NOOP"
        elif not carrying and agent_pos == target:
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
        if target is None:
            return {
                "summary": "No workspace target or action cue is available; motor holds position.",
                "observations": [
                    f"agent_position={agent_pos}",
                    "target_source=unavailable",
                    f"blocked_directions={blocked}",
                ],
                "confidence": 0.35,
                "action_hint": "NOOP",
                "rationale": (
                    "The motor center only has local obstacle information and has not "
                    "received a global target through the workspace broadcast."
                ),
            }
        return {
            "summary": (
                f"Motor proposes {action}; goal={goal}; target={target_text}; "
                "cue_source=workspace_broadcast."
            ),
            "observations": [
                f"agent_position={agent_pos}",
                f"resource_position={broadcast_positions.get('resource_position')}",
                f"base_position={broadcast_positions.get('base_position')}",
                f"target_position={target}",
                "target_source=workspace_broadcast" if target is not None else "target_source=unavailable",
                f"heard_broadcast={broadcast_summary}",
                f"blocked_directions={blocked}",
            ],
            "confidence": 0.76 if action != "NOOP" else 0.45,
            "action_hint": action,
            "rationale": (
                "Choose the next simulator action using nearby obstacle constraints "
                "and target information available from the workspace broadcast."
            ),
        }

    def _language_response(self, user_payload: JsonDict) -> JsonDict:
        state = private_observation(user_payload)
        user_prompt = state.get("user_prompt")
        pause_requested = bool(state.get("pause_requested"))
        query = state.get("report_query")
        broadcast = user_payload.get("last_broadcast")
        broadcast_summary = summarize_broadcast(broadcast)
        private_state = user_payload.get("module_private_state") or {}
        history = private_state.get("input_history") or []
        history_summary = summarize_history(history)
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
        if pause_requested and user_prompt:
            summary = (
                f"User pause prompt: {user_prompt}. I heard the active workspace broadcast as "
                f"{broadcast_summary}. Recent language history: {history_summary}."
            )
            confidence = 0.88
        elif query:
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
            f"history_summary={history_summary}",
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


class HuggingFaceTransformersClient:
    """Local HuggingFace Transformers backend for downloaded open models."""

    provider_name = "huggingface-transformers"

    def __init__(
        self,
        *,
        default_model: str = "Qwen/Qwen3-4B-Instruct-2507",
        cache_dir: Optional[str] = None,
        max_new_tokens: int = 700,
    ) -> None:
        if importlib.util.find_spec("torch") is None:
            raise LLMClientError(
                "torch is not installed. Install requirements-hf.txt or use "
                "--agent-backend mock-llm."
            )
        if importlib.util.find_spec("transformers") is None:
            raise LLMClientError(
                "transformers is not installed. Install requirements-hf.txt or use "
                "--agent-backend mock-llm."
            )
        self.default_model = default_model
        self.cache_dir = cache_dir or os.getenv("HF_HOME") or os.getenv("TRANSFORMERS_CACHE")
        self.max_new_tokens = max_new_tokens
        self._loaded = {}

    @staticmethod
    def available() -> bool:
        return (
            importlib.util.find_spec("torch") is not None
            and importlib.util.find_spec("transformers") is not None
        )

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: JsonDict,
        response_schema: JsonDict,
        image_path: Optional[str] = None,
        model: Optional[str] = None,
    ) -> JsonDict:
        model_id = model or self.default_model
        prompt = json.dumps(
            {
                "payload": user_payload,
                "response_schema": response_schema,
                "instruction": "Return one JSON object only. Do not include markdown.",
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        if image_path:
            output = self._generate_vision(
                model_id=model_id,
                system_prompt=system_prompt,
                prompt=prompt,
                image_path=image_path,
            )
        else:
            output = self._generate_text(
                model_id=model_id,
                system_prompt=system_prompt,
                prompt=prompt,
            )
        return parse_json_object(output)

    def _generate_text(
        self,
        *,
        model_id: str,
        system_prompt: str,
        prompt: str,
    ) -> str:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        key = ("text", model_id)
        if key not in self._loaded:
            tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                cache_dir=self.cache_dir,
                trust_remote_code=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                cache_dir=self.cache_dir,
                device_map="auto",
                torch_dtype="auto",
                trust_remote_code=True,
            )
            self._loaded[key] = (model, tokenizer)
        model, tokenizer = self._loaded[key]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer([text], return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {name: value.to(device) for name, value in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        output_ids = generated[0][inputs["input_ids"].shape[-1] :]
        return tokenizer.decode(output_ids, skip_special_tokens=True)

    def _generate_vision(
        self,
        *,
        model_id: str,
        system_prompt: str,
        prompt: str,
        image_path: str,
    ) -> str:
        import torch
        from PIL import Image
        from transformers import AutoProcessor

        key = ("vision", model_id)
        if key not in self._loaded:
            model_cls = image_text_model_class()
            processor = AutoProcessor.from_pretrained(
                model_id,
                cache_dir=self.cache_dir,
                trust_remote_code=True,
            )
            model = model_cls.from_pretrained(
                model_id,
                cache_dir=self.cache_dir,
                device_map="auto",
                torch_dtype="auto",
                trust_remote_code=True,
            )
            self._loaded[key] = (model, processor)
        model, processor = self._loaded[key]
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image = Image.open(image_path).convert("RGB")
        inputs = processor(
            text=[text],
            images=[image],
            return_tensors="pt",
        )
        device = next(model.parameters()).device
        inputs = {name: value.to(device) for name, value in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        output_ids = generated[0][inputs["input_ids"].shape[-1] :]
        return processor.decode(output_ids, skip_special_tokens=True)


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
    if normalized in {"hf", "huggingface"}:
        return HuggingFaceTransformersClient(default_model=default_model)
    if normalized == "auto":
        if OpenAIResponsesClient.available():
            return OpenAIResponsesClient(default_model=default_model)
        return MockLLMClient(provider_name="mock-llm-auto")
    raise ValueError(
        f"Unsupported LLM backend {backend!r}. Use auto, openai, huggingface, or mock-llm."
    )


def image_text_model_class():
    import transformers

    for name in (
        "AutoModelForImageTextToText",
        "AutoModelForVision2Seq",
        "Qwen3VLForConditionalGeneration",
        "Qwen2_5_VLForConditionalGeneration",
    ):
        model_cls = getattr(transformers, name, None)
        if model_cls is not None:
            return model_cls
    raise LLMClientError(
        "This transformers version does not expose an image-text model class. "
        "Install a newer transformers release from requirements-hf.txt."
    )


def private_observation(user_payload: JsonDict) -> JsonDict:
    value = user_payload.get("private_observation") or {}
    return value if isinstance(value, dict) else {}


def parse_json_object(text: str) -> JsonDict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = json.loads(extract_json_object(cleaned))
    if not isinstance(parsed, dict):
        raise LLMClientError(f"Expected a JSON object, got {type(parsed).__name__}: {text!r}")
    return parsed


def extract_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise LLMClientError(f"No JSON object found in model output: {text!r}")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise LLMClientError(f"Unclosed JSON object in model output: {text!r}")


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


def summarize_history(history) -> str:
    if not history:
        return "none"
    latest = history[-3:]
    parts = []
    for item in latest:
        if not isinstance(item, dict):
            continue
        mode = item.get("mode") or "unknown"
        prompt = item.get("user_prompt") or item.get("report_query") or item.get("heard_broadcast")
        output = item.get("output_language")
        prompt_text = str(prompt or "")
        output_text = str(output or "")
        if len(prompt_text) > 60:
            prompt_text = prompt_text[:57] + "..."
        if len(output_text) > 60:
            output_text = output_text[:57] + "..."
        parts.append(f"{mode}: input={prompt_text}; output={output_text}")
    return " | ".join(parts) if parts else "none"


def extract_positions_from_broadcast(value) -> JsonDict:
    """Extract target coordinates that were globally broadcast, not private to motor."""
    positions: JsonDict = {}
    if not isinstance(value, dict):
        return positions
    content = value.get("content")
    if not isinstance(content, dict):
        return positions
    for key in ("resource_position", "base_position", "agent_position", "target_position"):
        if key in content:
            parsed = parse_position_value(content.get(key))
            if parsed is not None:
                positions[key] = parsed
    observations = content.get("observations")
    if isinstance(observations, list):
        for item in observations:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, raw_value = item.split("=", 1)
            key = key.strip()
            if key in {"resource_position", "base_position", "agent_position", "target_position"}:
                parsed = parse_position_value(raw_value.strip())
                if parsed is not None:
                    positions[key] = parsed
    return positions


def parse_position_value(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    text = str(value)
    match = re.search(r"[-+]?\d+\s*,\s*[-+]?\d+", text)
    if not match:
        return None
    left, right = match.group(0).split(",", 1)
    return (int(left.strip()), int(right.strip()))


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
