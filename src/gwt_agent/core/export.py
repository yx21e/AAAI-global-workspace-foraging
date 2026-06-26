from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional

from gwt_agent.core.types import EnvAction, TraceEnvelope, TraceStep


def action_payload(action: EnvAction) -> dict:
    """Return the minimal payload Qiyuan's simulator can consume."""
    return {
        "should_step": action.should_step,
        "action": action.command,
        "action_type": action.action_type,
        "direction": action.direction,
        "confidence": action.confidence,
        "source_module": action.source_module,
        "source_timestamp": action.source_timestamp,
    }


def trace_step_to_envelope(
    trace: TraceStep,
    run_id: str,
    schema_version: str = "gwt_trace_v1",
) -> TraceEnvelope:
    if trace.env_action is None:
        raise ValueError("TraceStep does not contain env_action.")
    return TraceEnvelope(
        schema_version=schema_version,
        run_id=run_id,
        timestamp=trace.timestamp,
        env_t=trace.env_t,
        cycle_t=trace.cycle_t,
        env_state=trace.env_state,
        module_states=trace.module_states,
        workspace_state=trace.workspace_state,
        workspace_broadcast=trace.broadcast,
        env_action=trace.env_action,
        next_env_state=trace.next_env_state,
        intervention_config=trace.intervention_config,
        metadata={"selected_action": trace.selected_action},
    )


def write_envelopes_jsonl(path: str, envelopes: Iterable[TraceEnvelope]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for envelope in envelopes:
            handle.write(json.dumps(envelope.to_dict(), ensure_ascii=True) + "\n")


def write_action_stream(path: str, envelopes: Iterable[TraceEnvelope]) -> None:
    """Write one JSON object per action for replay in the foraging simulator."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for envelope in envelopes:
            payload = action_payload(envelope.env_action)
            payload.update(
                {
                    "run_id": envelope.run_id,
                    "timestamp": envelope.timestamp,
                    "schema_version": envelope.schema_version,
                }
            )
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def load_action_stream(path: str) -> List[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay_actions(env, action_records: Iterable[dict], render_dir: Optional[str] = None):
    """Replay standardized actions against a ForagingEnv-like object.

    Qiyuan's environment has no STAY/NOOP action. For records with
    should_step=false, this helper skips env.step(action).
    """
    states = []
    render_path = Path(render_dir) if render_dir else None
    if render_path:
        render_path.mkdir(parents=True, exist_ok=True)

    for index, record in enumerate(action_records):
        if record.get("should_step"):
            state = env.step(record["action"])
        else:
            state = None
        states.append(state)
        if render_path:
            env.render(str(render_path / f"replay_{index:04d}.png"))
    return states
