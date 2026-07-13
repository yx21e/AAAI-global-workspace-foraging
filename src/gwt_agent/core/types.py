from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


def to_jsonable(value: Any) -> Any:
    """Convert common Python objects into JSON-friendly structures."""
    if is_dataclass(value):
        return {key: to_jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(to_jsonable(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


@dataclass
class EnvironmentState:
    """Unified environment state passed from an adapter into the workspace."""

    timestamp: int
    observation: Any
    symbolic_state: JsonDict = field(default_factory=dict)
    available_actions: List[str] = field(default_factory=list)
    reward: float = 0.0
    done: bool = False
    info: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class WorkspaceBroadcast:
    """The single winning content broadcast to all modules after competition."""

    timestamp: int
    winner_module: str
    content: Any
    importance_score: float
    confidence: Optional[float] = None
    action_hint: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class WorkspaceState:
    """Persistent limited-capacity workspace / working-memory state."""

    cycle_t: int = 0
    active_content: Optional[WorkspaceBroadcast] = None
    history: List[WorkspaceBroadcast] = field(default_factory=list)
    capacity: int = 1
    active_strength: float = 0.0
    active_age: int = 0
    decay_rate: float = 0.85
    maintenance_steps: int = 4
    metadata: JsonDict = field(default_factory=dict)

    def update(self, broadcast: WorkspaceBroadcast, strength: float = 1.0) -> None:
        self.active_content = broadcast
        self.active_strength = strength
        self.active_age = 0
        self.history.append(broadcast)
        if len(self.history) > self.capacity:
            self.history = self.history[-self.capacity :]

    def decay(self) -> Optional[WorkspaceBroadcast]:
        if self.active_content is None:
            return None
        self.active_age += 1
        self.active_strength *= self.decay_rate
        if self.active_age > self.maintenance_steps or self.active_strength <= 0.01:
            self.active_content = None
            self.active_strength = 0.0
            self.active_age = 0
            return None
        return self.active_content

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class ModuleContext:
    """Input bundle seen by every module at one timestamp."""

    timestamp: int
    env_state: EnvironmentState
    last_broadcast: Optional[WorkspaceBroadcast] = None
    shared_memory: JsonDict = field(default_factory=dict)
    experiment: JsonDict = field(default_factory=dict)


@dataclass
class ModuleInput:
    """Module-specific input; modules need not share identical information."""

    module_name: str
    env_t: int
    cycle_t: int
    private_observation: Any = None
    private_state: JsonDict = field(default_factory=dict)
    global_broadcast: Optional[WorkspaceBroadcast] = None
    workspace_state: Optional[WorkspaceState] = None
    task_goal: Optional[str] = None
    available_actions: List[str] = field(default_factory=list)
    experiment: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_legacy_context(self) -> ModuleContext:
        env_state = self.metadata.get("env_state")
        if not isinstance(env_state, EnvironmentState):
            env_state = EnvironmentState(
                timestamp=self.env_t,
                observation=self.private_observation,
                symbolic_state=self.private_observation
                if isinstance(self.private_observation, dict)
                else {},
                available_actions=self.available_actions,
            )
        return ModuleContext(
            timestamp=self.cycle_t,
            env_state=env_state,
            last_broadcast=self.global_broadcast,
            shared_memory=self.private_state,
            experiment=self.experiment,
        )

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class ModuleProposal:
    """Candidate content uploaded by a module for workspace competition."""

    module_name: str
    content: Any
    importance_score: float
    confidence: Optional[float] = None
    action_hint: Optional[str] = None
    rationale: str = ""
    reflection: str = ""
    salience_score: Optional[float] = None
    goal_relevance_score: Optional[float] = None
    uptake_score: Optional[float] = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class EnvAction:
    """Standardized action command that an external simulator can consume."""

    action_type: str
    command: Optional[str]
    should_step: bool
    direction: Optional[str] = None
    target: Any = None
    confidence: Optional[float] = None
    source_module: Optional[str] = None
    source_timestamp: Optional[int] = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class ModuleStateSnapshot:
    """Standardized per-module state recorded for replay and analysis."""

    module_name: str
    status: str
    proposal: Optional[ModuleProposal] = None
    module_input: Optional[ModuleInput] = None
    private_state: JsonDict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class TraceStep:
    """One logged timestamp of the full perception-competition-action loop."""

    timestamp: int
    env_state: EnvironmentState
    proposals: List[ModuleProposal]
    broadcast: WorkspaceBroadcast
    selected_action: Optional[str]
    env_t: Optional[int] = None
    cycle_t: Optional[int] = None
    env_action: Optional[EnvAction] = None
    module_states: List[ModuleStateSnapshot] = field(default_factory=list)
    workspace_state: Optional[WorkspaceState] = None
    next_env_state: Optional[EnvironmentState] = None
    intervention_config: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)


@dataclass
class TraceEnvelope:
    """Full standardized record shared across our side and the simulator side."""

    schema_version: str
    run_id: str
    timestamp: int
    env_state: EnvironmentState
    module_states: List[ModuleStateSnapshot]
    workspace_broadcast: WorkspaceBroadcast
    env_action: EnvAction
    env_t: Optional[int] = None
    cycle_t: Optional[int] = None
    workspace_state: Optional[WorkspaceState] = None
    next_env_state: Optional[EnvironmentState] = None
    intervention_config: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return to_jsonable(self)
