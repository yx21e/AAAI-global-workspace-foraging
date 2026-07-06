#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from gwt_agent.core.export import (
    trace_step_to_envelope,
    write_action_stream,
    write_envelopes_jsonl,
)
from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.router import InputRouter
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.envs.qiyuan_loader import load_foraging_env_class
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.perception import PerceptionModule


DEFAULT_INSTRUCTION = (
    "Collect exactly one resource, avoid walls, use PICKUP only when standing "
    "on the resource, return to base, and stop after the resource is delivered."
)


def default_qiyuan_path(project_root: Path) -> Path:
    return (project_root.parent / "qiyuan_foraging_env").resolve()


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run the GWT scaffold with Qiyuan's ForagingEnv.",
    )
    parser.add_argument(
        "--qiyuan-path",
        default=str(default_qiyuan_path(project_root)),
        help="Path to a local Foraging-Environment-Design checkout.",
    )
    parser.add_argument("--difficulty", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-resources", type=int, default=1)
    parser.add_argument("--max-cycles", type=int, default=200)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument(
        "--out-dir",
        default=str(project_root / "runs" / "qiyuan_integrated"),
    )
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def main() -> None:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    args = parse_args()
    random.seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"qiyuan-d{args.difficulty}-seed{args.seed}"
    trace_path = out_dir / f"{run_id}_trace.jsonl"
    envelope_path = out_dir / f"{run_id}_envelopes.jsonl"
    action_path = out_dir / f"{run_id}_actions.jsonl"
    summary_path = out_dir / f"{run_id}_summary.json"
    frame_dir = out_dir / f"{run_id}_frames"

    ForagingEnv = load_foraging_env_class(args.qiyuan_path)
    env = ForagingEnv()
    adapter = ForagingEnvAdapter(
        env=env,
        difficulty=args.difficulty,
        experimenter_instruction=args.instruction,
        target_resources=args.target_resources,
    )
    runner = WorkspaceRunner(
        env_adapter=adapter,
        modules=[
            PerceptionModule(),
            MotorModule(),
            LanguageReportModule(),
        ],
        experiment=ExperimentConfig(),
        logger=TraceLogger(str(trace_path)),
        run_id=run_id,
        input_router=InputRouter(task_goal=args.instruction),
    )

    initial_state = adapter.reset()
    runner._current_state = initial_state
    if not args.no_render:
        frame_dir.mkdir(parents=True, exist_ok=True)
        env.render(str(frame_dir / "frame_0000_initial.png"))

    traces = []
    for cycle_index in range(args.max_cycles):
        trace = runner.step()
        traces.append(trace)
        if not args.no_render:
            env.render(str(frame_dir / f"frame_{cycle_index + 1:04d}.png"))
        if trace.next_env_state and trace.next_env_state.done:
            break

    envelopes = [
        trace_step_to_envelope(trace=trace, run_id=runner.run_id)
        for trace in traces
    ]
    write_envelopes_jsonl(str(envelope_path), envelopes)
    write_action_stream(str(action_path), envelopes)

    final_state = traces[-1].next_env_state if traces else initial_state
    final_symbolic = final_state.symbolic_state if final_state else {}
    summary = {
        "run_id": run_id,
        "qiyuan_path": str(Path(args.qiyuan_path).resolve()),
        "difficulty": args.difficulty,
        "seed": args.seed,
        "target_resources": args.target_resources,
        "experimenter_instruction": args.instruction,
        "cycle_count": len(traces),
        "env_step_count": final_state.timestamp if final_state else None,
        "done": bool(final_state.done) if final_state else False,
        "resources_collected": final_symbolic.get("resources_collected"),
        "agent_position": final_symbolic.get("agent_position"),
        "carrying_resource": final_symbolic.get("carrying_resource"),
        "trace_path": str(trace_path),
        "envelope_path": str(envelope_path),
        "action_stream_path": str(action_path),
        "frame_dir": None if args.no_render else str(frame_dir),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
