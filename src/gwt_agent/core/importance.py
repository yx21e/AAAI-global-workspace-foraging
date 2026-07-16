from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol

from gwt_agent.core.types import ModuleInput, ModuleProposal, WorkspaceBroadcast, to_jsonable


def stable_text(value) -> str:
    """Serialize structured content into deterministic text for scoring."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(to_jsonable(value), sort_keys=True, ensure_ascii=True)
    except TypeError:
        return repr(value)


class SentenceEncoder(Protocol):
    def encode(self, text: str) -> List[float]:
        ...


@dataclass
class HashingSentenceEncoder:
    """Small deterministic sentence encoder used when no external model is loaded.

    This keeps the scaffold dependency-free while preserving the same interface
    as a sentence-transformers style encoder.
    """

    dimensions: int = 128

    def encode(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        return vector


@dataclass
class ImportanceWeights:
    salience: float = 0.55
    relevance: float = 0.45


@dataclass
class ProposalImportance:
    salience: float
    relevance: float
    importance: float


class DeterministicImportanceScorer:
    """Fixed importance function outside module self-report.

    Importance = bottom-up salience + top-down relevance, with editable weights.
    Bottom-up salience is the embedding-space change in the module's private
    input relative to its previous private input. Top-down relevance is semantic
    similarity between a proposal and task goal + previous broadcast.
    """

    def __init__(
        self,
        encoder: Optional[SentenceEncoder] = None,
        weights: Optional[ImportanceWeights] = None,
    ) -> None:
        self.encoder = encoder or HashingSentenceEncoder()
        self.weights = weights or ImportanceWeights()

    def score(
        self,
        proposal: ModuleProposal,
        module_input: ModuleInput,
        previous_private_input,
        last_broadcast: Optional[WorkspaceBroadcast],
    ) -> ProposalImportance:
        current_private = stable_text(salience_view(module_input.private_observation))
        previous_private = stable_text(salience_view(previous_private_input))
        proposal_text = stable_text(relevance_view(proposal.content))
        context_text = self._context_text(module_input, last_broadcast)

        salience = self._change_amount(current_private, previous_private)
        relevance = self._cosine01(proposal_text, context_text)
        importance = (
            self.weights.salience * salience
            + self.weights.relevance * relevance
        )
        return ProposalImportance(
            salience=salience,
            relevance=relevance,
            importance=importance,
        )

    def _context_text(
        self,
        module_input: ModuleInput,
        last_broadcast: Optional[WorkspaceBroadcast],
    ) -> str:
        return "\n".join(
            item
            for item in [
                stable_text(module_input.task_goal),
                stable_text(last_broadcast.content if last_broadcast else None),
            ]
            if item
        )

    def _change_amount(self, current_text: str, previous_text: str) -> float:
        if not previous_text:
            return 1.0 if current_text else 0.0
        similarity = self._cosine01(current_text, previous_text)
        return max(0.0, min(1.0, 1.0 - similarity))

    def _cosine01(self, left_text: str, right_text: str) -> float:
        if not left_text or not right_text:
            return 0.0
        cosine = cosine_similarity(
            self.encoder.encode(left_text),
            self.encoder.encode(right_text),
        )
        return max(0.0, min(1.0, cosine))


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    dot = sum(a * b for a, b in zip(left_values, right_values))
    left_norm = math.sqrt(sum(a * a for a in left_values))
    right_norm = math.sqrt(sum(b * b for b in right_values))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def salience_view(value):
    """Use task-relevant changing fields for bottom-up salience.

    Full visual maps are useful for perception agents, but they are too large and
    mostly static for a simple embedding-change salience score. This compact
    view keeps movement/carry/task-state changes from being diluted by unchanged
    wall layout or screenshot path strings.
    """
    if not isinstance(value, dict):
        return value
    if "global_visual_observation" in value:
        return {
            "agent_position": value.get("agent_position"),
            "resource_position": value.get("resource_position"),
            "base_position": value.get("base_position"),
            "carrying_resource": value.get("carrying_resource"),
            "resources_collected": value.get("resources_collected"),
            "action_success": value.get("action_success"),
            "grid_size": value.get("grid_size"),
        }
    if "blocked_directions" in value:
        return {
            "agent_position": value.get("agent_position"),
            "carrying_resource": value.get("carrying_resource"),
            "blocked_directions": value.get("blocked_directions"),
            "nearby_obstacles": value.get("nearby_obstacles"),
            "action_success": value.get("action_success"),
        }
    return value


def relevance_view(value):
    """Compact proposal content before top-down relevance scoring.

    Modules may broadcast structured artifacts such as a full global map. Those
    artifacts are useful downstream, but they can swamp the lexical signal used
    by the deterministic sentence encoder. Keep summaries, observations, and
    compact task coordinates while excluding bulky static layout fields.
    """
    if isinstance(value, dict):
        compact = {}
        for key, item in value.items():
            if key in {"global_map", "wall_positions", "global_screenshot"}:
                continue
            compact[key] = relevance_view(item)
        return compact
    if isinstance(value, list):
        return [relevance_view(item) for item in value]
    return value
