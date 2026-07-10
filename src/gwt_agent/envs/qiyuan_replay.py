from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional


WALL_LABELS = {"WALL", "OBSTACLE", 1}


def load_jsonl(path: str) -> List[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_grid(path: Optional[str]):
    if not path:
        return None
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def episode_grid_from_trace(envelope_records: Iterable[dict]):
    for record in envelope_records:
        for state_key in ("env_state", "next_env_state"):
            state = record.get(state_key) or {}
            info = state.get("info") or {}
            grid = info.get("qiyuan_episode_grid")
            if grid:
                return grid
    return None


def restore_env_from_symbolic(env, symbolic_state: dict) -> None:
    """Restore Qiyuan's mutable env fields from a recorded symbolic state."""
    global_map = symbolic_state.get("global_map")
    if global_map:
        env.grid = [
            [1 if cell in WALL_LABELS else 0 for cell in row]
            for row in global_map
        ]
        env.grid_size = len(global_map)

    base_position = symbolic_state.get("base_position")
    if base_position is not None:
        env.base_pos = tuple(base_position)

    agent_position = symbolic_state.get("agent_position")
    if agent_position is not None:
        env.agent_pos = list(agent_position)

    resource_position = symbolic_state.get("resource_position")
    env.resource_pos = (
        list(resource_position)
        if resource_position is not None
        else None
    )

    env.carrying = bool(symbolic_state.get("carrying_resource", False))
    env.step_count = int(symbolic_state.get("step_count", 0) or 0)
    env.resources_collected = int(
        symbolic_state.get("resources_collected", 0) or 0
    )
    facing = symbolic_state.get("facing")
    if facing is not None:
        env.facing = facing


def restore_env_from_recorded_state(env, state_record: dict, episode_grid=None) -> str:
    """Restore env using Qiyuan's official load_state API when available."""
    observation = state_record.get("observation")
    if episode_grid is not None and observation is not None and hasattr(env, "load_state"):
        env.load_state(observation, episode_grid)
        return "load_state"
    restore_env_from_symbolic(env, state_record.get("symbolic_state") or {})
    return "symbolic"


def render_trace_replay(
    env,
    envelope_records: Iterable[dict],
    render_dir: str,
    prefix: str = "trace",
    episode_grid=None,
) -> List[str]:
    """Render exact historical frames from full trace envelopes.

    This does not call env.step(). It restores the recorded symbolic state for
    the first pre-action frame and for every recorded next_env_state.
    """
    records = list(envelope_records)
    if not records:
        return []
    grid = episode_grid if episode_grid is not None else episode_grid_from_trace(records)

    out = Path(render_dir)
    out.mkdir(parents=True, exist_ok=True)
    rendered = []

    restore_env_from_recorded_state(env, records[0]["env_state"], grid)
    rendered.append(env.render(str(out / f"{prefix}_0000.png")))

    for index, record in enumerate(records, start=1):
        next_state = record.get("next_env_state") or record.get("env_state")
        restore_env_from_recorded_state(env, next_state, grid)
        rendered.append(env.render(str(out / f"{prefix}_{index:04d}.png")))

    return rendered


def restore_initial_env_from_trace(env, envelope_records: Iterable[dict], episode_grid=None) -> bool:
    records = list(envelope_records)
    if not records:
        return False
    grid = episode_grid if episode_grid is not None else episode_grid_from_trace(records)
    restore_env_from_recorded_state(env, records[0]["env_state"], grid)
    return True


def render_action_replay(
    env,
    action_records: Iterable[dict],
    render_dir: str,
    prefix: str = "action",
) -> List[str]:
    """Replay action records through Qiyuan env.step() and render frames."""
    out = Path(render_dir)
    out.mkdir(parents=True, exist_ok=True)
    rendered = [env.render(str(out / f"{prefix}_0000.png"))]

    for index, record in enumerate(action_records, start=1):
        if record.get("should_step"):
            env.step(record["action"])
        rendered.append(env.render(str(out / f"{prefix}_{index:04d}.png")))

    return rendered


def write_replay_summary(
    path: str,
    *,
    mode: str,
    frames: List[str],
    source_trace: Optional[str] = None,
    source_actions: Optional[str] = None,
    source_grid: Optional[str] = None,
    used_load_state: bool = False,
) -> None:
    payload = {
        "mode": mode,
        "frame_count": len(frames),
        "first_frame": frames[0] if frames else None,
        "last_frame": frames[-1] if frames else None,
        "source_trace": source_trace,
        "source_actions": source_actions,
        "source_grid": source_grid,
        "used_qiyuan_load_state": used_load_state,
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
