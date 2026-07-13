from __future__ import annotations

import re
from copy import deepcopy
from typing import Iterable, List, Optional

from gwt_agent.core.types import ModuleProposal, WorkspaceBroadcast, WorkspaceState


TARGET_KEYS = {"resource_position", "base_position", "target_position"}
TARGET_TEXT_KEYS = {"resource", "base", "target"}
TRANSIENT_ACTION_KEYS = {"planned_action", "action", "action_hint", "command", "direction"}
TRANSIENT_ACTIONS = r"(?:UP|DOWN|LEFT|RIGHT|PICKUP|NOOP|WAIT|STAY|NONE)"


class CentralWorkspace:
    """All-or-none global workspace with decaying maintained content."""

    def __init__(
        self,
        capacity: int = 1,
        ignition_threshold: float = 0.25,
        decay_rate: float = 0.85,
        maintenance_steps: int = 4,
    ) -> None:
        self.state = WorkspaceState(
            capacity=capacity,
            decay_rate=decay_rate,
            maintenance_steps=maintenance_steps,
        )
        self.ignition_threshold = ignition_threshold

    def select_winner(self, proposals: Iterable[ModuleProposal]) -> Optional[ModuleProposal]:
        proposal_list: List[ModuleProposal] = list(proposals)
        if not proposal_list:
            raise ValueError("CentralWorkspace requires at least one proposal.")
        winner = max(
            proposal_list,
            key=lambda proposal: (
                proposal.uptake_score
                if proposal.uptake_score is not None
                else proposal.importance_score,
                proposal.confidence if proposal.confidence is not None else -1.0,
                proposal.module_name,
            ),
        )
        score = winner.uptake_score if winner.uptake_score is not None else winner.importance_score
        if score < self.ignition_threshold:
            return None
        return winner

    def broadcast(
        self,
        timestamp: int,
        winner: Optional[ModuleProposal],
    ) -> WorkspaceBroadcast:
        self.state.cycle_t = timestamp
        if winner is None:
            return self._maintain_or_idle(timestamp)

        score = winner.uptake_score if winner.uptake_score is not None else winner.importance_score
        metadata = global_metadata_for_winner(winner)
        metadata["workspace"] = {
            "ignited": True,
            "ignition_threshold": self.ignition_threshold,
            "maintained": False,
            "strength": 1.0,
        }
        broadcast = WorkspaceBroadcast(
            timestamp=timestamp,
            winner_module=winner.module_name,
            content=global_content_for_winner(winner),
            importance_score=score,
            confidence=winner.confidence,
            action_hint=winner.action_hint,
            metadata=metadata,
        )
        self.state.update(memory_broadcast_for_context(broadcast), strength=1.0)
        return broadcast

    def _maintain_or_idle(self, timestamp: int) -> WorkspaceBroadcast:
        maintained = self.state.decay()
        if maintained is None:
            return WorkspaceBroadcast(
                timestamp=timestamp,
                winner_module="workspace",
                content={"status": "no_ignition", "active_content": None},
                importance_score=0.0,
                confidence=None,
                action_hint=None,
                metadata={
                    "workspace": {
                        "ignited": False,
                        "maintained": False,
                        "ignition_threshold": self.ignition_threshold,
                        "strength": 0.0,
                    }
                },
            )
        return WorkspaceBroadcast(
            timestamp=timestamp,
            winner_module=maintained.winner_module,
            content=maintained.content,
            importance_score=self.state.active_strength,
            confidence=maintained.confidence,
            action_hint=maintained.action_hint,
            metadata={
                **maintained.metadata,
                "workspace": {
                    "ignited": False,
                    "maintained": True,
                    "ignition_threshold": self.ignition_threshold,
                    "strength": self.state.active_strength,
                    "age": self.state.active_age,
                },
            },
        )


def global_content_for_winner(winner: ModuleProposal):
    """Return the content that is actually globally broadcast.

    Raw module proposals remain in the trace for debugging. The global broadcast
    itself is stricter: only perception may broadcast resource/base/target
    coordinates. This prevents motor from carrying a target forward through its
    own winning broadcasts.
    """

    if str(winner.module_name).lower().startswith("perception"):
        return winner.content
    return strip_target_coordinates(winner.content)


def global_metadata_for_winner(winner: ModuleProposal) -> dict:
    metadata = deepcopy(winner.metadata)
    if str(winner.module_name).lower().startswith("perception"):
        metadata["winner_rationale"] = winner.rationale
        metadata["winner_reflection"] = winner.reflection
        return metadata
    metadata["winner_rationale"] = redact_target_text(winner.rationale)
    metadata["winner_reflection"] = redact_target_text(winner.reflection)
    metadata["spatial_target_redaction"] = {
        "applied": True,
        "reason": "Only perception broadcasts resource/base/target coordinates.",
    }
    return metadata


def memory_broadcast_for_context(broadcast: WorkspaceBroadcast) -> WorkspaceBroadcast:
    """Store a non-executable context copy in workspace memory.

    The returned broadcast from ``CentralWorkspace.broadcast`` is the fresh
    same-cycle event used by ActionResolver and the trace. Workspace memory is
    what modules hear on the next cycle. Action hints are transient commands, so
    they should not be maintained as new action cues.
    """

    metadata = deepcopy(broadcast.metadata)
    if broadcast.action_hint:
        metadata = strip_transient_action_cues(metadata)
        metadata["transient_action_redaction"] = {
            "applied": True,
            "reason": "Action hints are same-cycle commands and are not maintained as next-cycle context.",
        }
    return WorkspaceBroadcast(
        timestamp=broadcast.timestamp,
        winner_module=broadcast.winner_module,
        content=strip_transient_action_cues(deepcopy(broadcast.content))
        if broadcast.action_hint
        else deepcopy(broadcast.content),
        importance_score=broadcast.importance_score,
        confidence=broadcast.confidence,
        action_hint=None,
        metadata=metadata,
    )


def strip_target_coordinates(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in TARGET_KEYS:
                continue
            sanitized_item = strip_target_coordinates(item)
            if sanitized_item is None and key == "observations":
                sanitized_item = []
            sanitized[key] = sanitized_item
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for item in value:
            sanitized_item = strip_target_coordinates(item)
            if sanitized_item is not None:
                sanitized_items.append(sanitized_item)
        return sanitized_items
    if isinstance(value, str):
        if should_drop_observation_string(value):
            return None
        return redact_target_text(value)
    return value


def strip_transient_action_cues(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in TRANSIENT_ACTION_KEYS:
                continue
            sanitized_item = strip_transient_action_cues(item)
            if sanitized_item is None and key == "observations":
                sanitized_item = []
            sanitized[key] = sanitized_item
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for item in value:
            sanitized_item = strip_transient_action_cues(item)
            if sanitized_item is not None:
                sanitized_items.append(sanitized_item)
        return sanitized_items
    if isinstance(value, str):
        if should_drop_action_observation_string(value):
            return None
        return redact_action_text(value)
    return value


def should_drop_observation_string(value: str) -> bool:
    if "=" not in value:
        return False
    key = value.split("=", 1)[0].strip()
    return key in TARGET_KEYS


def should_drop_action_observation_string(value: str) -> bool:
    if "=" not in value:
        return False
    key = value.split("=", 1)[0].strip()
    return key in TRANSIENT_ACTION_KEYS


def redact_target_text(text: str) -> str:
    if not text:
        return text
    redacted = str(text)
    coordinate = r"(?:\[[^\]]*(?:\]|\.{3})?|\([^)]+\)|None)"
    for key in TARGET_KEYS:
        redacted = re.sub(
            rf"({key}\s*=\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
        )
    for key in TARGET_TEXT_KEYS:
        redacted = re.sub(
            rf"({key}\s+target\s+at\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            rf"({key}\s+target\s*=\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            rf"({key}\s+at\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            rf"({key}\s*=\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            rf"(\b{key}\s*){coordinate}",
            rf"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
    return redacted


def redact_action_text(text: str) -> str:
    if not text:
        return text
    redacted = str(text)
    patterns = [
        rf"(Motor proposes\s+){TRANSIENT_ACTIONS}",
        rf"(planned_action\s*=\s*){TRANSIENT_ACTIONS}",
        rf"(action_hint\s*=\s*){TRANSIENT_ACTIONS}",
        rf"(proposed action\s+){TRANSIENT_ACTIONS}",
        rf"(chosen action\s+){TRANSIENT_ACTIONS}",
        rf"(I chose\s+){TRANSIENT_ACTIONS}",
        rf"(I will hold with\s+){TRANSIENT_ACTIONS}",
    ]
    for pattern in patterns:
        redacted = re.sub(pattern, rf"\1<action>", redacted, flags=re.IGNORECASE)
    return redacted
